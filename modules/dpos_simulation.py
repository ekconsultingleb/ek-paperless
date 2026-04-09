"""
dpos_simulation.py
──────────────────
Final Report tab for the DPOS Pricing Studio.

Currency flow (mirrors the original Excel exactly):

  Unit Cost sheet:
    avg_cost_lbp  ÷  rate         → unit_cost_usd   (Conversion column)
    IF product_description found in sub_recipes.product_name
      → unit_cost_usd = SUMIF(sub_recipes.total_cost_of_1)
    ELSE
      → unit_cost_usd = avg_cost_lbp / rate

  Usage Cost formula (exact Excel):
    IF qty_buy = 1  → usage_cost = unit_cost_usd / qty_inv
    IF qty_buy < 1  → usage_cost = (unit_cost_usd / qty_buy) / 1000
    ELSE            → usage_cost = unit_cost_usd / qty_buy

  Sub recipe Total Cost of 1 (per ingredient line):
    avg_cost in sub_recipes = XLOOKUP → Usage Cost from Unit Cost (already USD)
    batch_cost_line   = gross_w × avg_cost
    total_cost_of_1   = batch_cost_line / prepared_qty
    Sub recipe cost   = SUM of all total_cost_of_1 lines  (SUMIF col J)

  Recipe line:
    total_cost = gross_w × usage_cost   (negative gross_w = substitution)

  Menu item cost = SUM of all recipe line total_costs

  Suggestive price (VAT-inclusive) = (new_cost / target_cost_pct) × (1 + vat_rate)
  Psychological price = round to nearest $0.25
"""

import streamlit as st
import pandas as pd
import numpy as np
from supabase import Client

EK_DARK = "#1B252C"
EK_SAND = "#E3C5AD"


# ─────────────────────────────────────────────
#  CORE FORMULA FUNCTIONS
# ─────────────────────────────────────────────

def compute_unit_cost_usd(avg_cost_lbp: float, rate: float) -> float:
    """Conversion column: avg_cost_lbp / rate → USD per purchase unit."""
    if not rate or rate == 0:
        return 0.0
    return avg_cost_lbp / rate


def compute_usage_cost(unit_cost_usd: float, qty_inv: float, qty_buy: float) -> float:
    """
    Exact Excel Usage Cost formula:
      IF qty_buy = 1  → unit_cost_usd / qty_inv
      IF qty_buy < 1  → (unit_cost_usd / qty_buy) / 1000
      ELSE            → unit_cost_usd / qty_buy

    Input: unit_cost_usd already in USD.
    Returns: USD per gram / ml / unit.
    """
    qty_buy = qty_buy or 1
    qty_inv = qty_inv or 1

    if qty_buy == 1:
        return unit_cost_usd / qty_inv
    elif qty_buy < 1:
        return (unit_cost_usd / qty_buy) / 1000
    else:
        return unit_cost_usd / qty_buy


def compute_sub_recipe_cost(sr_lines: pd.DataFrame, usage_lookup: dict) -> float:
    """
    Replicates SUMIF on sub_recipes column J (Total Cost of 1).

    For each ingredient line:
      avg_cost (USD) = XLOOKUP → Usage Cost from Unit Cost (already USD/g)
      batch_cost_line   = gross_w × avg_cost
      total_cost_of_1   = batch_cost_line / prepared_qty

    Returns SUM of all total_cost_of_1 = full sub recipe cost per prepared unit.

    Note: avg_cost in sub_recipes is already USD — no rate conversion here.
    The usage_lookup already has overrides applied so sub recipe
    ingredients automatically pick up any cost changes.
    """
    total = 0.0
    for _, line in sr_lines.iterrows():
        ing_key  = str(line.get("ingredient_description", "")).lower().strip()
        gross_w  = float(line.get("gross_w") or line.get("net_w") or 0)
        prep_qty = float(line.get("prepared_qty") or 1)

        # Use the live usage_lookup so overrides propagate into sub recipes
        avg_cost_usd = usage_lookup.get(ing_key, float(line.get("avg_cost") or 0))

        batch_cost_line = gross_w * avg_cost_usd
        total += batch_cost_line / prep_qty if prep_qty > 0 else 0.0

    return total


def psychological_price(price: float) -> float:
    """Round to nearest $0.25."""
    if not price or price <= 0:
        return 0.0
    return round(price * 4) / 4


# ─────────────────────────────────────────────
#  SIMULATION ENGINE
# ─────────────────────────────────────────────

def compute_simulation(
    recipes_df: pd.DataFrame,
    unit_costs_df: pd.DataFrame,
    sub_recipes_df: pd.DataFrame,
    overrides: dict,
    session: dict,
) -> tuple[pd.DataFrame, dict, dict]:
    """
    Full bottom-up pricing simulation.

    overrides: {product_description_lower: predicted_avg_cost_lbp}

    Returns:
      sim_df       — one row per menu item with pricing metrics
      usage_lookup — for drill-down display
      sr_cost_lookup — for drill-down display
    """
    vat_rate   = float(session.get("vat_rate", 0))
    target_pct = float(session.get("target_cost_pct", 0.30))

    if recipes_df.empty:
        return pd.DataFrame(), {}, {}

    # ── Step 1: Build usage cost lookup ──
    # product_description lower → usage_cost USD/g or USD/unit
    usage_lookup = {}

    if not unit_costs_df.empty:
        for _, uc in unit_costs_df.iterrows():
            desc_key     = str(uc.get("product_description", "")).lower().strip()
            avg_cost_lbp = float(uc.get("avg_cost_lbp") or 0)
            rate         = float(uc.get("rate") or 90000)
            qty_inv      = float(uc.get("qty_inv") or 1)
            qty_buy      = float(uc.get("qty_buy") or 1)

            # Apply override (predicted_cost is LBP)
            if desc_key in overrides:
                avg_cost_lbp = float(overrides[desc_key])

            # LBP → USD  (Conversion column)
            unit_cost_usd = compute_unit_cost_usd(avg_cost_lbp, rate)

            # Usage Cost (exact Excel formula)
            usage = compute_usage_cost(unit_cost_usd, qty_inv, qty_buy)
            usage_lookup[desc_key] = usage

    # ── Step 2: Build sub recipe cost lookup ──
    # product_name lower → total cost of 1 prepared unit USD
    # Replicates: SUMIF(sub_recipes.A, product_name, sub_recipes.J)
    sr_cost_lookup = {}

    if not sub_recipes_df.empty:
        for prod_name, grp in sub_recipes_df.groupby("product_name"):
            key = prod_name.lower().strip()
            # Pass usage_lookup so overrides on ingredients propagate
            sr_cost_lookup[key] = compute_sub_recipe_cost(grp, usage_lookup)

    # ── Step 3: Resolve ingredient cost ──
    # IF product_description in sub_recipes.product_name → sr_cost_lookup
    # ELSE → usage_lookup
    # This is the exact IF(ISERROR(MATCH(...))) logic from the Unit Cost sheet
    def get_ingredient_cost(ingredient_desc: str) -> float:
        key = ingredient_desc.lower().strip()
        if key in sr_cost_lookup:
            return sr_cost_lookup[key]
        return usage_lookup.get(key, 0.0)

    # ── Step 4: Sum recipe costs per menu item ──
    results = {}
    for _, line in recipes_df.iterrows():
        item = str(line.get("menu_item", "")).strip()
        if not item:
            continue

        gross_w   = float(line.get("gross_w") or line.get("net_w") or 0)
        usage     = get_ingredient_cost(str(line.get("ingredient_description", "")))
        line_cost = gross_w * usage   # negative gross_w = substitution line

        if item not in results:
            results[item] = {
                "menu_item":  item,
                "category":   line.get("category") or "",
                "group_name": line.get("group_name") or "",
                "new_cost":   0.0,
            }
        results[item]["new_cost"] += line_cost

    # ── Step 5: Build output rows ──
    rows = []
    for item, data in results.items():
        new_cost = data["new_cost"]

        if target_pct > 0:
            suggestive = (new_cost / target_pct) * (1 + vat_rate) if vat_rate > 0 else new_cost / target_pct
        else:
            suggestive = 0.0

        rows.append({
            "menu_item":          item,
            "category":           data.get("category", ""),
            "group_name":         data.get("group_name", ""),
            "new_cost":           round(new_cost, 6),
            "suggestive_price":   round(suggestive, 4),
            "psychological_price": psychological_price(suggestive),
            "target_cost_pct":    target_pct,
            "vat_rate":           vat_rate,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, usage_lookup, sr_cost_lookup

    df = df.sort_values(["category", "group_name", "menu_item"]).reset_index(drop=True)
    return df, usage_lookup, sr_cost_lookup


def enrich_with_prices(
    sim_df: pd.DataFrame,
    prices: dict,
    old_costs: dict,
    session: dict,
) -> pd.DataFrame:
    """
    Merge current selling prices and compute all cost % metrics.

    prices:    {menu_item: current_selling_price_usd}
    old_costs: {menu_item: previous_new_cost_usd} from last approved session
    """
    if sim_df.empty:
        return sim_df

    vat    = float(session.get("vat_rate", 0))
    target = float(session.get("target_cost_pct", 0.30)) * 100

    df = sim_df.copy()
    df["current_price"] = df["menu_item"].map(lambda x: prices.get(x) or 0.0)
    df["old_cost"]      = df["menu_item"].map(lambda x: old_costs.get(x))

    def ex_vat(p):
        return p / (1 + vat) if vat > 0 and p else p

    # Cost variance vs previous approved session
    df["cost_variance"] = df.apply(
        lambda r: round(r["new_cost"] - float(r["old_cost"]), 6)
        if r["old_cost"] is not None else None, axis=1
    )
    df["cost_variance_pct"] = df.apply(
        lambda r: round((r["cost_variance"] / float(r["old_cost"])) * 100, 2)
        if r["old_cost"] and r["cost_variance"] is not None else None, axis=1
    )
    df["affected"] = df["cost_variance"].notna() & (df["cost_variance"].abs() > 0.000001)

    # Current cost % — new_cost vs current selling price ex-VAT
    df["current_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / ex_vat(r["current_price"])) * 100, 2)
        if r["current_price"] and r["current_price"] > 0 else None, axis=1
    )

    # Current profit margin — based on current price
    df["current_profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / ex_vat(r["current_price"])) * 100, 2)
        if r["current_price"] and r["current_price"] > 0 else None, axis=1
    )

    # New cost % — new_cost vs suggestive price ex-VAT
    df["new_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / ex_vat(r["suggestive_price"])) * 100, 2)
        if r["suggestive_price"] and r["suggestive_price"] > 0 else None, axis=1
    )

    # New profit margin — based on suggestive price
    df["profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / ex_vat(r["suggestive_price"])) * 100, 2)
        if r["suggestive_price"] and r["suggestive_price"] > 0 else None, axis=1
    )

    # Cost position flag
    df["cost_position"] = df["current_cost_pct"].apply(
        lambda v: f"Higher > {target:.0f}%" if v and v > target
        else (f"Lower ≤ {target:.0f}%" if v else "—")
    )

    return df


# ─────────────────────────────────────────────
#  DISPLAY HELPERS
# ─────────────────────────────────────────────

def fmt_usd(val, decimals=4):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"${val:,.{decimals}f}"


def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:.2f}%"


def fmt_variance(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    prefix = "+" if val > 0 else ""
    return f"{prefix}${val:,.4f}"


def fmt_variance_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    prefix = "+" if val > 0 else ""
    return f"{prefix}{val:.2f}%"


# ─────────────────────────────────────────────
#  FINAL REPORT TAB
# ─────────────────────────────────────────────

def tab_final_report(supabase: Client, client_id: int):
    st.markdown("#### Final Report — Pricing Simulation")

    # ── Sessions ──
    sess_res = supabase.table("dpos_sessions") \
        .select("*").eq("client_id", client_id) \
        .order("created_at", desc=True).execute()

    if not sess_res.data:
        st.info("No sessions found. Create one in the Sessions tab.")
        return

    sess_options  = {s["session_name"]: s for s in sess_res.data}
    selected_name = st.selectbox("Select session", list(sess_options.keys()), key="fr_session_select")
    session       = sess_options[selected_name]
    session_id    = int(session["id"])

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        st.metric("VAT", f"{float(session.get('vat_rate', 0)) * 100:.1f}%")
    with sc2:
        st.metric("Target cost %", f"{float(session.get('target_cost_pct', 0.3)) * 100:.1f}%")
    with sc3:
        st.metric("Status", session.get("status", "draft").upper())
    with sc4:
        st.metric("Created", str(session.get("created_at", ""))[:10])

    st.divider()

    # ── Load all data ──
    with st.spinner("Loading…"):
        uc_res  = supabase.table("dpos_unit_costs").select("*").eq("client_id", client_id).execute()
        sr_res  = supabase.table("dpos_sub_recipes").select("*").eq("client_id", client_id).execute()
        rec_res = supabase.table("dpos_recipes").select("*").eq("client_id", client_id).execute()
        ov_res  = supabase.table("dpos_cost_overrides").select("*").eq("session_id", session_id).execute()
        ap_res  = supabase.table("dpos_approved_prices").select("*").eq("session_id", session_id).execute()

    uc_df  = pd.DataFrame(uc_res.data)  if uc_res.data  else pd.DataFrame()
    sr_df  = pd.DataFrame(sr_res.data)  if sr_res.data  else pd.DataFrame()
    rec_df = pd.DataFrame(rec_res.data) if rec_res.data else pd.DataFrame()
    ap_df  = pd.DataFrame(ap_res.data)  if ap_res.data  else pd.DataFrame()

    if rec_df.empty:
        st.warning("No recipes found for this client. Add recipes in the Recipes tab.")
        return
    if uc_df.empty:
        st.warning("No unit costs found. Import unit costs first.")
        return

    # Overrides dict: ingredient lower → predicted_avg_cost_lbp
    overrides = {}
    if ov_res.data:
        for ov in ov_res.data:
            key = str(ov.get("product_description", "")).lower().strip()
            overrides[key] = float(ov.get("predicted_cost", 0))

    # ── Current selling prices ──
    menu_items = sorted(rec_df["menu_item"].dropna().unique().tolist())
    state_key  = f"fr_prices_{session_id}"

    if state_key not in st.session_state:
        defaults = {}
        if not ap_df.empty and "old_price" in ap_df.columns:
            for _, row in ap_df.iterrows():
                if row.get("old_price"):
                    defaults[row["menu_item"]] = float(row["old_price"])
        st.session_state[state_key] = defaults

    st.markdown("**Current selling prices (USD)**")
    st.caption("Enter current menu prices to calculate current cost % and variance.")

    with st.expander("Enter / edit prices", expanded=ap_df.empty):
        chunks = [menu_items[i:i+3] for i in range(0, len(menu_items), 3)]
        for chunk in chunks:
            cols = st.columns(3)
            for j, item in enumerate(chunk):
                with cols[j]:
                    val = float(st.session_state[state_key].get(item, 0.0))
                    new_val = st.number_input(
                        item, value=val, min_value=0.0,
                        step=0.25, format="%.2f",
                        key=f"fr_price_{session_id}_{item}",
                    )
                    st.session_state[state_key][item] = new_val

    st.divider()

    # ── Run / clear ──
    col_run, col_clear, _ = st.columns([1, 1, 5])
    with col_run:
        run = st.button("Run simulation", type="primary", key="fr_run")
    with col_clear:
        if st.button("Clear", key="fr_clear"):
            st.session_state.pop(f"fr_sim_{session_id}", None)
            st.session_state.pop(f"fr_lookups_{session_id}", None)
            st.rerun()

    sim_key     = f"fr_sim_{session_id}"
    lookups_key = f"fr_lookups_{session_id}"

    if run:
        with st.spinner("Calculating…"):
            raw_sim, usage_lookup, sr_cost_lookup = compute_simulation(
                rec_df, uc_df, sr_df, overrides, session
            )
            prices    = st.session_state[state_key]
            old_costs = {}
            if not ap_df.empty and "new_cost" in ap_df.columns:
                old_costs = dict(zip(ap_df["menu_item"], ap_df["new_cost"].astype(float)))

            sim_df = enrich_with_prices(raw_sim, prices, old_costs, session)
            st.session_state[sim_key]     = sim_df
            st.session_state[lookups_key] = (usage_lookup, sr_cost_lookup)

    sim_df = st.session_state.get(sim_key)

    if sim_df is None:
        st.info("Enter selling prices then click **Run simulation**.")
        return

    if sim_df.empty:
        st.warning("Simulation returned no results.")
        return

    usage_lookup, sr_cost_lookup = st.session_state.get(lookups_key, ({}, {}))
    target_pct = float(session.get("target_cost_pct", 0.3))

    # ── Summary metrics ──
    total_items    = len(sim_df)
    affected       = int(sim_df["affected"].sum()) if "affected" in sim_df.columns else 0
    above_target   = int((sim_df["current_cost_pct"].dropna() > target_pct * 100).sum()) if "current_cost_pct" in sim_df.columns else 0
    avg_cost       = sim_df["new_cost"].mean()
    avg_margin     = sim_df["profit_margin"].dropna().mean() if "profit_margin" in sim_df.columns else None

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Menu items",      total_items)
    m2.metric("Cost affected",   affected)
    m3.metric("Above target %",  above_target)
    m4.metric("Avg recipe cost", fmt_usd(avg_cost, 3))
    m5.metric("Avg profit margin", fmt_pct(avg_margin))

    st.divider()

    # ── Filters ──
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        cats  = ["All"] + sorted(sim_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="fr_cat")
    with f2:
        grps  = ["All"] + sorted(sim_df["group_name"].dropna().unique().tolist())
        grp_f = st.selectbox("Group", grps, key="fr_grp")
    with f3:
        status_f = st.selectbox("Status", ["All", "Affected only", "Unaffected only"], key="fr_status")
    with f4:
        cost_opts = ["All", f"Higher > {target_pct*100:.0f}%", f"Lower ≤ {target_pct*100:.0f}%"]
        cost_f    = st.selectbox("Cost position", cost_opts, key="fr_cost_pos")

    disp = sim_df.copy()
    if cat_f    != "All":           disp = disp[disp["category"]   == cat_f]
    if grp_f    != "All":           disp = disp[disp["group_name"] == grp_f]
    if status_f == "Affected only": disp = disp[disp["affected"]   == True]
    if status_f == "Unaffected only": disp = disp[disp["affected"] == False]
    if cost_f != "All" and "current_cost_pct" in disp.columns:
        if "Higher" in cost_f:
            disp = disp[disp["current_cost_pct"].notna() & (disp["current_cost_pct"] > target_pct * 100)]
        else:
            disp = disp[disp["current_cost_pct"].notna() & (disp["current_cost_pct"] <= target_pct * 100)]

    st.caption(f"Showing {len(disp)} of {total_items} items")

    # ── Results table ──
    table_rows = []
    for _, row in disp.iterrows():
        table_rows.append({
            "":                "⚡" if row.get("affected") else "—",
            "Category":        row.get("category", ""),
            "Group":           row.get("group_name", ""),
            "Menu item":       row.get("menu_item", ""),
            "New cost":        fmt_usd(row.get("new_cost"), 4),
            "Current price":   fmt_usd(row.get("current_price"), 2) if row.get("current_price") else "—",
            "Current cost %":  fmt_pct(row.get("current_cost_pct")),
            "Curr. margin %":  fmt_pct(row.get("current_profit_margin")),
            "Cost var. $":     fmt_variance(row.get("cost_variance")),
            "Cost var. %":     fmt_variance_pct(row.get("cost_variance_pct")),
            "Suggestive $":    fmt_usd(row.get("suggestive_price"), 2),
            "Psych. price $":  fmt_usd(row.get("psychological_price"), 2),
            "New cost %":      fmt_pct(row.get("new_cost_pct")),
            "New margin %":    fmt_pct(row.get("profit_margin")),
        })

    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    # ── Ingredient drill-down ──
    st.divider()
    st.markdown("**Ingredient breakdown**")
    selected_item = st.selectbox(
        "Inspect menu item",
        ["— select —"] + sorted(disp["menu_item"].tolist()),
        key="fr_drill",
    )

    if selected_item and selected_item != "— select —":
        item_lines = rec_df[rec_df["menu_item"] == selected_item].copy()

        if not item_lines.empty:
            drill_rows  = []
            drill_total = 0.0

            for _, line in item_lines.iterrows():
                ing_desc  = str(line.get("ingredient_description", ""))
                ing_key   = ing_desc.lower().strip()
                gross_w   = float(line.get("gross_w") or line.get("net_w") or 0)
                net_w     = float(line.get("net_w") or gross_w)
                yield_pct = line.get("yield_pct")

                if ing_key in sr_cost_lookup:
                    usage_cost = sr_cost_lookup[ing_key]
                    source = "sub recipe"
                else:
                    usage_cost = usage_lookup.get(ing_key, float(line.get("avg_cost") or 0))
                    source = "unit cost"

                line_cost    = gross_w * usage_cost
                drill_total += line_cost

                label = ing_desc + ("  ← substitution" if gross_w < 0 else "")
                drill_rows.append({
                    "Ingredient":     label,
                    "Net W":          f"{net_w:g}",
                    "Gross W":        f"{gross_w:g}",
                    "Yield %":        f"{yield_pct:.1f}%" if yield_pct else "—",
                    "Source":         source,
                    "Usage cost $/u": fmt_usd(usage_cost, 6),
                    "Line cost $":    fmt_usd(line_cost, 4),
                    "Override":       "✓" if ing_key in overrides else "",
                })

            st.dataframe(pd.DataFrame(drill_rows), use_container_width=True, hide_index=True)
            st.markdown(f"**Total recipe cost: {fmt_usd(drill_total, 4)}**")

            if "yield_pct" in item_lines.columns:
                for _, lrow in item_lines[item_lines["yield_pct"].notna() & (item_lines["yield_pct"] < 70)].iterrows():
                    st.warning(f"Low yield on **{lrow['ingredient_description']}**: {lrow['yield_pct']:.1f}%")

    # ── Submit approved prices ──
    st.divider()
    st.markdown("**Approve & lock prices**")

    if session.get("status") == "approved":
        st.success("Session is approved. Prices are locked.")
    else:
        st.caption("Locks psychological prices as approved selling prices for this session.")
        if st.button("Submit approved prices", type="primary", key="fr_submit"):
            _submit_approved_prices(
                supabase, session_id, sim_df,
                st.session_state[state_key],
                st.session_state.get("username", "EK Team"),
            )

    # ── Export ──
    st.divider()
    export_cols = [c for c in [
        "category", "group_name", "menu_item",
        "new_cost", "current_price", "current_cost_pct", "current_profit_margin",
        "cost_variance", "cost_variance_pct",
        "suggestive_price", "psychological_price",
        "new_cost_pct", "profit_margin",
    ] if c in disp.columns]

    st.download_button(
        "Export to CSV",
        data=disp[export_cols].to_csv(index=False),
        file_name=f"dpos_{selected_name.replace(' ', '_')}.csv",
        mime="text/csv",
        key="fr_export",
    )


# ─────────────────────────────────────────────
#  SUBMIT APPROVED PRICES
# ─────────────────────────────────────────────

def _submit_approved_prices(
    supabase: Client,
    session_id: int,
    sim_df: pd.DataFrame,
    prices: dict,
    approved_by: str = "EK Team",
):
    from datetime import datetime, timezone

    supabase.table("dpos_approved_prices").delete().eq("session_id", session_id).execute()

    records = []
    for _, row in sim_df.iterrows():
        item  = row["menu_item"]
        psych = float(row.get("psychological_price") or row.get("suggestive_price") or 0)

        records.append({
            "session_id":         session_id,
            "menu_item":          item,
            "category":           row.get("category") or None,
            "group_name":         row.get("group_name") or None,
            "old_price":          float(prices.get(item) or 0) or None,
            "new_price":          psych,
            "new_cost":           float(row.get("new_cost") or 0),
            "new_cost_pct":       float(row["new_cost_pct"])   if row.get("new_cost_pct")  else None,
            "new_profit_margin":  float(row["profit_margin"])  if row.get("profit_margin") else None,
            "psychological_price": psych,
            "approved_at":        datetime.now(timezone.utc).isoformat(),
            "approved_by":        approved_by,
        })

    if records:
        for i in range(0, len(records), 500):
            supabase.table("dpos_approved_prices").insert(records[i:i+500]).execute()
        st.success(f"Saved {len(records)} approved prices.")
        st.rerun()
    else:
        st.error("No records to save.")
