"""
dpos.py
───────
D-POS Pricing Studio — Paperless module.
Entry point: show_dpos(supabase)

Tabs:
  1. Setup       — sync from Auto Calc, manage on_menu flags, view unit costs
  2. Sessions    — create / manage repricing exercises
  3. Final Report — simulation, item selection, CSV export
"""

import streamlit as st
import pandas as pd
import numpy as np
from supabase import Client
from datetime import datetime, timezone
from modules.dpos_simulation import (
    compute_simulation,
    enrich_with_prices,
    fmt_usd, fmt_pct, fmt_variance, fmt_variance_pct,
)

EK_DARK = "#1B252C"
EK_SAND = "#E3C5AD"
TABS    = ["Setup", "Sessions", "Final Report"]


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _most_recent_date(supabase: Client, table: str, client_id: int):
    res = supabase.table(table) \
        .select("report_date") \
        .eq("client_id", client_id) \
        .order("report_date", desc=True) \
        .limit(1).execute()
    return res.data[0]["report_date"] if res.data else None


@st.cache_data(ttl=120, show_spinner=False)
def load_clients(_supabase: Client) -> pd.DataFrame:
    res = _supabase.table("clients").select("id, client_name").order("client_name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_dpos_recipes(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_recipes") \
        .select("*").eq("client_id", client_id).order("category").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_dpos_unit_costs(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_unit_costs") \
        .select("*").eq("client_id", client_id).order("category").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_dpos_sub_recipes(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_sub_recipes") \
        .select("*").eq("client_id", client_id).order("product_name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_sessions(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_sessions") \
        .select("*").eq("client_id", client_id) \
        .order("created_at", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


def clear_cache():
    load_dpos_recipes.clear()
    load_dpos_unit_costs.clear()
    load_dpos_sub_recipes.clear()
    load_sessions.clear()
    load_clients.clear()


# ─────────────────────────────────────────────
#  TAB 1 — SETUP
# ─────────────────────────────────────────────

def tab_setup(supabase: Client, client_id: int, client_name: str):
    st.markdown("#### Setup")

    uc_df  = load_dpos_unit_costs(supabase, client_id)
    rec_df = load_dpos_recipes(supabase, client_id)
    sr_df  = load_dpos_sub_recipes(supabase, client_id)
    has_data = not rec_df.empty

    c1, c2, c3 = st.columns(3)
    c1.metric("Unit costs",      len(uc_df))
    c2.metric("Recipe lines",    len(rec_df))
    c3.metric("Sub recipe lines", len(sr_df))

    if has_data:
        st.success(f"Data loaded for **{client_name}**.")
    else:
        st.warning(f"No data yet for **{client_name}**. Run Full sync below.")

    st.divider()

    # ── Sync controls ──
    st.markdown("**Sync from Auto Calc**")
    col_full, col_uc = st.columns(2)

    with col_full:
        st.markdown("**Full sync**")
        st.caption("First time or when recipes change. Pulls recipes, unit costs, selling prices.")
        if st.button("Full sync", type="primary", key="sync_full"):
            _run_full_sync(supabase, client_id, client_name)

    with col_uc:
        st.markdown("**Unit costs only**")
        st.caption("Every month after Auto Calc upload. Preserves on_menu flags and selling prices.")
        if st.button("Sync unit costs only", key="sync_uc"):
            _run_unit_cost_sync(supabase, client_id)

    if not has_data:
        return

    st.divider()

    # ── On menu manager ──
    st.markdown("**Menu visibility**")
    st.caption("Mark items that appear on the client's printed menu. Off-menu items (e.g. Add Lemon) are hidden from the Final Report by default.")

    f1, f2, f3 = st.columns([2, 2, 3])
    with f1:
        cats  = ["All"] + sorted(rec_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="setup_cat")
    with f2:
        grps  = ["All"] + sorted(rec_df["group_name"].dropna().unique().tolist())
        grp_f = st.selectbox("Group", grps, key="setup_grp")
    with f3:
        search = st.text_input("Search item", placeholder="e.g. burger, lemon…", key="setup_search")

    items_df = rec_df.drop_duplicates(subset="menu_item")[
        ["menu_item", "category", "group_name", "on_menu", "current_selling_price"]
    ].copy()

    if cat_f   != "All": items_df = items_df[items_df["category"]   == cat_f]
    if grp_f   != "All": items_df = items_df[items_df["group_name"] == grp_f]
    if search:            items_df = items_df[items_df["menu_item"].str.contains(search, case=False, na=False)]

    on_count  = int(rec_df.drop_duplicates("menu_item")["on_menu"].sum()) if "on_menu" in rec_df.columns else 0
    off_count = len(rec_df.drop_duplicates("menu_item")) - on_count
    st.caption(f"{on_count} on menu · {off_count} off menu · showing {len(items_df)}")

    b1, b2, _ = st.columns([1, 1, 4])
    with b1:
        if st.button("All on menu", key="bulk_on"):
            for item in rec_df["menu_item"].unique():
                supabase.table("dpos_recipes").update({"on_menu": True}) \
                    .eq("client_id", client_id).eq("menu_item", item).execute()
            clear_cache(); st.rerun()
    with b2:
        if st.button("All off menu", key="bulk_off"):
            for item in rec_df["menu_item"].unique():
                supabase.table("dpos_recipes").update({"on_menu": False}) \
                    .eq("client_id", client_id).eq("menu_item", item).execute()
            clear_cache(); st.rerun()

    for _, row in items_df.iterrows():
        col_name, col_sp, col_toggle = st.columns([4, 2, 1])
        with col_name:
            sub = f"  <span style='opacity:0.4;font-size:11px'>{row.get('category','')} / {row.get('group_name','')}</span>"
            st.markdown(f"**{row['menu_item']}**{sub}", unsafe_allow_html=True)
        with col_sp:
            sp = row.get("current_selling_price")
            st.caption(f"SP ex-VAT: {fmt_usd(float(sp),2) if sp else '—'}")
        with col_toggle:
            current = bool(row.get("on_menu", True))
            new_val = st.toggle("", value=current, key=f"om_{row['menu_item']}")
            if new_val != current:
                supabase.table("dpos_recipes").update({"on_menu": new_val}) \
                    .eq("client_id", client_id).eq("menu_item", row["menu_item"]).execute()
                clear_cache(); st.rerun()

    st.divider()

    with st.expander("View unit costs", expanded=False):
        if uc_df.empty:
            st.info("No unit costs loaded.")
        else:
            s = st.text_input("Search", key="uc_view_s")
            view = uc_df[uc_df["product_description"].str.contains(s, case=False, na=False)] if s else uc_df
            st.dataframe(
                view[["category", "group_name", "product_description", "unit", "usage_cost_usd"]].rename(columns={
                    "category": "Category", "group_name": "Group",
                    "product_description": "Ingredient", "unit": "Unit",
                    "usage_cost_usd": "Usage Cost $",
                }),
                use_container_width=True, hide_index=True,
            )


# ─────────────────────────────────────────────
#  SYNC FUNCTIONS
# ─────────────────────────────────────────────

def _run_full_sync(supabase: Client, client_id: int, client_name: str):
    with st.spinner("Syncing from Auto Calc…"):
        try:
            uc_date  = _most_recent_date(supabase, "ac_unit_cost",      client_id)
            rec_date = _most_recent_date(supabase, "ac_recipes",         client_id)
            sr_date  = _most_recent_date(supabase, "ac_sub_recipes",     client_id)
            sp_date  = _most_recent_date(supabase, "ac_selling_prices",  client_id)

            if not rec_date:
                st.error("No Auto Calc recipe data found. Upload Auto Calc first.")
                return

            st.caption(f"Using: recipes {rec_date} · unit costs {uc_date} · selling prices {sp_date}")

            # Preserve existing on_menu flags and selling prices
            existing = supabase.table("dpos_recipes") \
                .select("menu_item, on_menu, current_selling_price") \
                .eq("client_id", client_id).execute()
            on_menu_map = {}
            sp_map      = {}
            if existing.data:
                for r in existing.data:
                    on_menu_map[r["menu_item"]] = r.get("on_menu", True)
                    if r.get("current_selling_price"):
                        sp_map[r["menu_item"]] = float(r["current_selling_price"])

            # Pull selling prices from ac_selling_prices
            if sp_date:
                sp_res = supabase.table("ac_selling_prices") \
                    .select("menu_items, sp_exc_vat") \
                    .eq("client_id", client_id) \
                    .eq("report_date", sp_date).execute()
                if sp_res.data:
                    for row in sp_res.data:
                        if row.get("menu_items") and row.get("sp_exc_vat") is not None:
                            sp_map[row["menu_items"]] = float(row["sp_exc_vat"])

            # Sync unit costs
            _sync_unit_costs(supabase, client_id, uc_date)

            # Sync recipes
            rec_res = supabase.table("ac_recipes") \
                .select("category, item_group, menu_items, product_description, qty, unit, avgpurusacost, avg_cost") \
                .eq("client_id", client_id) \
                .eq("report_date", rec_date).execute()

            if rec_res.data:
                supabase.table("dpos_recipes").delete().eq("client_id", client_id).execute()
                records = []
                for row in rec_res.data:
                    item = row.get("menu_items", "")
                    if not item:
                        continue
                    gw = float(row.get("qty") or 0)
                    # avgpurusacost = usage cost in USD per unit
                    avg = float(row.get("avgpurusacost") or row.get("avg_cost") or 0)
                    records.append({
                        "client_id":              client_id,
                        "category":               row.get("category"),
                        "group_name":             row.get("item_group"),
                        "menu_item":              item,
                        "ingredient_description": row.get("product_description"),
                        "net_w":                  gw,
                        "gross_w":                gw,
                        "unit":                   row.get("unit"),
                        "avg_cost":               avg,
                        "on_menu":                on_menu_map.get(item, True),
                        "current_selling_price":  sp_map.get(item),
                    })
                for i in range(0, len(records), 500):
                    supabase.table("dpos_recipes").insert(records[i:i+500]).execute()

            # Sync sub recipes
            sr_res = supabase.table("ac_sub_recipes") \
                .select("production_name, product_description, qty, unit_name, average_cost, qty_to_prepared, prepared_unit") \
                .eq("client_id", client_id) \
                .eq("report_date", sr_date).execute()

            if sr_res.data:
                supabase.table("dpos_sub_recipes").delete().eq("client_id", client_id).execute()
                sr_records = []
                for row in sr_res.data:
                    if not row.get("production_name"):
                        continue
                    gw = float(row.get("qty") or 0)
                    sr_records.append({
                        "client_id":              client_id,
                        "product_name":           row.get("production_name"),
                        "ingredient_description": row.get("product_description"),
                        "net_w":                  gw,
                        "gross_w":                gw,
                        "unit_name":              row.get("unit_name"),
                        "avg_cost":               float(row.get("average_cost") or 0),
                        "prepared_qty":           float(row.get("qty_to_prepared") or 1),
                        "prepared_unit":          row.get("prepared_unit"),
                    })
                for i in range(0, len(sr_records), 500):
                    supabase.table("dpos_sub_recipes").insert(sr_records[i:i+500]).execute()

            clear_cache()
            st.success(
                f"Sync complete — "
                f"{len(rec_res.data) if rec_res.data else 0} recipe lines · "
                f"{len(sr_res.data) if sr_res.data else 0} sub recipe lines."
            )
            st.rerun()

        except Exception as e:
            st.error(f"Sync failed: {e}")


def _sync_unit_costs(supabase: Client, client_id: int, uc_date):
    if not uc_date:
        return
    uc_res = supabase.table("ac_unit_cost") \
        .select("category, item_group, product_description, unit, qty_i_f, qty_pur, lbp, rate, unit_cost, usage_cost") \
        .eq("client_id", client_id) \
        .eq("report_date", uc_date).execute()

    if not uc_res.data:
        return

    supabase.table("dpos_unit_costs").delete().eq("client_id", client_id).execute()
    records = []
    for row in uc_res.data:
        if not row.get("product_description"):
            continue
        records.append({
            "client_id":           client_id,
            "category":            row.get("category"),
            "group_name":          row.get("item_group"),
            "product_description": row.get("product_description"),
            "unit":                row.get("unit"),
            "qty_inv":             float(row.get("qty_i_f") or 1),
            "qty_buy":             float(row.get("qty_pur") or 1),
            "avg_cost_lbp":        float(row.get("lbp") or 0),
            "rate":                float(row.get("rate") or 90000),
            "usage_cost_usd":      float(row.get("usage_cost") or 0),
            "show_in_report":      True,
        })
    for i in range(0, len(records), 500):
        supabase.table("dpos_unit_costs").insert(records[i:i+500]).execute()


def _run_unit_cost_sync(supabase: Client, client_id: int):
    with st.spinner("Syncing unit costs…"):
        try:
            uc_date = _most_recent_date(supabase, "ac_unit_cost", client_id)
            if not uc_date:
                st.error("No unit cost data found.")
                return
            _sync_unit_costs(supabase, client_id, uc_date)
            clear_cache()
            st.success(f"Unit costs synced from {uc_date}.")
            st.rerun()
        except Exception as e:
            st.error(f"Sync failed: {e}")


# ─────────────────────────────────────────────
#  TAB 2 — SESSIONS
# ─────────────────────────────────────────────

def tab_sessions(supabase: Client, client_id: int):
    st.markdown("#### Pricing Sessions")

    df = load_sessions(supabase, client_id)

    with st.expander("Create new session", expanded=df.empty):
        with st.form("sess_form", clear_on_submit=True):
            s1, s2, s3, s4 = st.columns(4)
            with s1: sess_name  = st.text_input("Session name *", placeholder="e.g. April 2026")
            with s2: vat_rate   = st.number_input("VAT %",            min_value=0.0,  max_value=30.0, value=11.0, step=0.5)
            with s3: target_pct = st.number_input("Target food cost %", min_value=5.0, max_value=80.0, value=30.0, step=1.0)
            with s4: rounding   = st.selectbox("Price rounding $", [0.25, 0.50, 1.00], index=1)
            notes = st.text_area("Notes (optional)", height=60)
            if st.form_submit_button("Create session", type="primary"):
                if not sess_name.strip():
                    st.error("Session name required.")
                else:
                    st.write(f"Trying to insert: {sess_name}")
                    supabase.table("dpos_sessions").insert({
                        "client_id":       client_id,
                        "session_name":    sess_name.strip(),
                        "vat_rate":        vat_rate / 100,
                        "target_cost_pct": target_pct / 100,
                        "rounding":        rounding,
                        "status":          "draft",
                        "notes":           notes or None,
                        "created_by":      st.session_state.get("user", "EK Team"),
                    }).execute()
                    st.success(f"Session '{sess_name}' created.")
                    load_sessions.clear()
                    st.rerun()

    if df.empty:
        st.info("No sessions yet.")
        return

    for _, sess in df.iterrows():
        status = sess.get("status", "draft")
        with st.expander(
            f"**{sess['session_name']}**  —  {str(sess.get('created_at',''))[:10]}  |  {status.upper()}",
            expanded=False,
        ):
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("VAT",           f"{float(sess.get('vat_rate',0))*100:.1f}%")
            sc2.metric("Target cost %", f"{float(sess.get('target_cost_pct',0.3))*100:.1f}%")
            sc3.metric("Rounding",      f"${float(sess.get('rounding',0.5)):.2f}")
            sc4.metric("Status",        status.upper())

            if sess.get("notes"):
                st.caption(f"Notes: {sess['notes']}")

            a1, a2, a3 = st.columns(3)
            with a1:
                if status == "draft" and st.button("Mark approved", key=f"approve_{sess['id']}"):
                    supabase.table("dpos_sessions").update({"status": "approved"}).eq("id", sess["id"]).execute()
                    load_sessions.clear(); st.rerun()
            with a2:
                if status != "archived" and st.button("Archive", key=f"archive_{sess['id']}"):
                    supabase.table("dpos_sessions").update({"status": "archived"}).eq("id", sess["id"]).execute()
                    load_sessions.clear(); st.rerun()
            with a3:
                if st.button("Delete", key=f"del_{sess['id']}", type="secondary"):
                    supabase.table("dpos_sessions").delete().eq("id", sess["id"]).execute()
                    load_sessions.clear(); st.rerun()

            # Cost overrides
            ov_res = supabase.table("dpos_cost_overrides").select("*").eq("session_id", int(sess["id"])).execute()
            if ov_res.data:
                st.markdown("**Cost overrides**")
                ov_df = pd.DataFrame(ov_res.data)
                ov_df["change %"] = ((ov_df["predicted_cost"] - ov_df["original_cost"]) / ov_df["original_cost"] * 100).round(1)
                st.dataframe(
                    ov_df[["product_description", "original_cost", "predicted_cost", "change %", "notes"]].rename(columns={
                        "product_description": "Ingredient",
                        "original_cost": "Current LBP",
                        "predicted_cost": "Predicted LBP",
                    }),
                    use_container_width=True, hide_index=True,
                )

            with st.expander("Add cost override", expanded=False):
                _add_override_form(supabase, int(sess["id"]), client_id)


def _add_override_form(supabase: Client, session_id: int, client_id: int):
    uc_df   = load_dpos_unit_costs(supabase, client_id)
    options = uc_df["product_description"].tolist() if not uc_df.empty else []

    with st.form(f"ov_{session_id}", clear_on_submit=True):
        o1, o2, o3, o4 = st.columns(4)
        with o1:
            ing = st.selectbox("Ingredient", [""] + options, key=f"ov_i_{session_id}") \
                if options else st.text_input("Ingredient", key=f"ov_i_{session_id}")
        with o2:
            cur_lbp = 0.0
            if ing and not uc_df.empty:
                m = uc_df[uc_df["product_description"] == ing]
                if not m.empty:
                    cur_lbp = float(m.iloc[0].get("avg_cost_lbp") or 0)
            orig = st.number_input("Current cost (LBP)", value=cur_lbp, key=f"ov_o_{session_id}")
        with o3:
            pred = st.number_input("Predicted cost (LBP)", value=cur_lbp, key=f"ov_p_{session_id}")
        with o4:
            notes = st.text_input("Notes", key=f"ov_n_{session_id}")

        if orig > 0 and pred > 0:
            chg = ((pred - orig) / orig) * 100
            st.caption(f"Change: {'+' if chg>0 else ''}{chg:.1f}%")

        if st.form_submit_button("Add override", type="primary"):
            if not str(ing).strip():
                st.error("Ingredient required.")
            else:
                supabase.table("dpos_cost_overrides").insert({
                    "session_id":          session_id,
                    "product_description": str(ing).strip(),
                    "original_cost":       orig or None,
                    "predicted_cost":      pred,
                    "notes":               notes or None,
                }).execute()
                st.success("Override added.")
                st.rerun()


# ─────────────────────────────────────────────
#  TAB 3 — FINAL REPORT
# ─────────────────────────────────────────────

def tab_final_report(supabase: Client, client_id: int):
    st.markdown("#### Final Report — Pricing Simulation")

    sess_res = supabase.table("dpos_sessions") \
        .select("*").eq("client_id", client_id) \
        .order("created_at", desc=True).execute()

    if not sess_res.data:
        st.info("No sessions found. Create one in the Sessions tab.")
        return

    sess_options  = {s["session_name"]: s for s in sess_res.data}
    selected_name = st.selectbox("Select session", list(sess_options.keys()), key="fr_session")
    session       = sess_options[selected_name]
    session_id    = int(session["id"])

    vat      = float(session.get("vat_rate", 0))
    target   = float(session.get("target_cost_pct", 0.30))
    rounding = float(session.get("rounding", 0.50))

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("VAT",           f"{vat*100:.1f}%")
    sc2.metric("Target cost %", f"{target*100:.1f}%")
    sc3.metric("Rounding",      f"${rounding:.2f}")
    sc4.metric("Status",        session.get("status", "draft").upper())

    st.divider()

    with st.spinner("Loading…"):
        uc_df  = load_dpos_unit_costs(supabase, client_id)
        sr_df  = load_dpos_sub_recipes(supabase, client_id)
        rec_df = load_dpos_recipes(supabase, client_id)
        ov_res = supabase.table("dpos_cost_overrides").select("*").eq("session_id", session_id).execute()
        ap_res = supabase.table("dpos_approved_prices").select("*").eq("session_id", session_id).execute()

    if rec_df.empty:
        st.warning("No recipes. Run Setup → Full sync first.")
        return
    if uc_df.empty:
        st.warning("No unit costs. Run Setup → Full sync first.")
        return

    ap_df     = pd.DataFrame(ap_res.data) if ap_res.data else pd.DataFrame()
    overrides = {}
    if ov_res.data:
        for ov in ov_res.data:
            overrides[str(ov.get("product_description","")).lower().strip()] = float(ov.get("predicted_cost", 0))

    # ── Item selection ──
    st.markdown("**Item selection**")
    st.caption("Select items to include. Defaults to on-menu items only.")

    all_items     = sorted(rec_df["menu_item"].dropna().unique().tolist())
    on_menu_items = rec_df[rec_df["on_menu"] == True]["menu_item"].unique().tolist() \
        if "on_menu" in rec_df.columns else all_items

    sel_key = f"fr_sel_{session_id}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = on_menu_items

    fi1, fi2, fi3 = st.columns([2, 2, 2])
    with fi1:
        cats  = ["All"] + sorted(rec_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="fr_cat")
    with fi2:
        grps  = ["All"] + sorted(rec_df["group_name"].dropna().unique().tolist())
        grp_f = st.selectbox("Group", grps, key="fr_grp")
    with fi3:
        show_off = st.checkbox("Include off-menu items", value=False, key="fr_off")

    filt = rec_df.drop_duplicates("menu_item").copy()
    if cat_f != "All": filt = filt[filt["category"]   == cat_f]
    if grp_f != "All": filt = filt[filt["group_name"] == grp_f]
    if not show_off and "on_menu" in filt.columns:
        filt = filt[filt["on_menu"] == True]

    visible = sorted(filt["menu_item"].dropna().unique().tolist())

    sb1, sb2 = st.columns(2)
    with sb1:
        if st.button("Select all visible", key="sel_all"):
            st.session_state[sel_key] = list(set(st.session_state[sel_key]) | set(visible))
            st.rerun()
    with sb2:
        if st.button("Deselect all visible", key="desel_all"):
            st.session_state[sel_key] = [i for i in st.session_state[sel_key] if i not in visible]
            st.rerun()

    selected = list(st.session_state[sel_key])
    cols = st.columns(3)
    for idx, item in enumerate(visible):
        with cols[idx % 3]:
            chk = st.checkbox(item, value=item in selected, key=f"chk_{session_id}_{item}")
            if chk and item not in selected:
                selected.append(item)
            elif not chk and item in selected:
                selected.remove(item)
    st.session_state[sel_key] = selected
    st.caption(f"{len(selected)} items selected")

    st.divider()

    col_run, col_clear, _ = st.columns([1, 1, 5])
    with col_run:
        run = st.button("Run simulation", type="primary", key="fr_run")
    with col_clear:
        if st.button("Clear", key="fr_clear"):
            st.session_state.pop(f"fr_sim_{session_id}", None)
            st.rerun()

    sim_key = f"fr_sim_{session_id}"

    if run:
        sim_rec = rec_df[rec_df["menu_item"].isin(selected)].copy()
        with st.spinner("Calculating…"):
            raw, usage_lookup, sr_lookup = compute_simulation(sim_rec, uc_df, sr_df, overrides, session)
            old_costs = {}
            if not ap_df.empty and "new_cost" in ap_df.columns:
                old_costs = dict(zip(ap_df["menu_item"], ap_df["new_cost"].astype(float)))
            sim_df = enrich_with_prices(raw, old_costs, session)
            st.session_state[sim_key] = {
                "df": sim_df,
                "usage_lookup": usage_lookup,
                "sr_lookup": sr_lookup,
            }

    cached = st.session_state.get(sim_key)
    if cached is None:
        st.info("Select items then click **Run simulation**.")
        return

    sim_df       = cached["df"]
    usage_lookup = cached["usage_lookup"]
    sr_lookup    = cached["sr_lookup"]

    if sim_df.empty:
        st.warning("Simulation returned no results.")
        return

    # ── Summary ──
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Items",           len(sim_df))
    m2.metric("Cost affected",   int(sim_df["affected"].sum()) if "affected" in sim_df.columns else 0)
    m3.metric("Above target %",  int((sim_df["current_cost_pct"].dropna() > target*100).sum()) if "current_cost_pct" in sim_df.columns else 0)
    m4.metric("Avg margin",      fmt_pct(sim_df["profit_margin"].dropna().mean()) if "profit_margin" in sim_df.columns else "—")

    st.divider()

    # ── Results table ──
    rows = []
    for _, row in sim_df.iterrows():
        sp_ex  = row.get("current_selling_price_ex")
        sp_inc = row.get("current_sp_inc_vat")
        rows.append({
            "":                   "⚡" if row.get("affected") else "—",
            "Category":           row.get("category",""),
            "Group":              row.get("group_name",""),
            "Menu item":          row.get("menu_item",""),
            "Recipe cost $":      fmt_usd(row.get("new_cost"), 4),
            "Current SP (ex VAT)": fmt_usd(sp_ex, 2) if sp_ex else "—",
            "Current SP (inc VAT)": fmt_usd(sp_inc, 2) if sp_inc else "—",
            "Current cost %":     fmt_pct(row.get("current_cost_pct")),
            "Curr. margin %":     fmt_pct(row.get("current_profit_margin")),
            "Cost var. $":        fmt_variance(row.get("cost_variance")),
            "Cost var. %":        fmt_variance_pct(row.get("cost_variance_pct")),
            "Suggestive (ex VAT)": fmt_usd(row.get("suggestive_ex_vat"), 2),
            "Suggestive (inc VAT)": fmt_usd(row.get("suggestive_price"), 2),
            "Rounded SP $":       fmt_usd(row.get("psychological_price"), 2),
            "New cost %":         fmt_pct(row.get("new_cost_pct")),
            "New margin %":       fmt_pct(row.get("profit_margin")),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Drill-down ──
    st.divider()
    st.markdown("**Ingredient breakdown**")
    drill = st.selectbox("Inspect menu item", ["— select —"] + sorted(sim_df["menu_item"].tolist()), key="fr_drill")

    if drill and drill != "— select —":
        lines = rec_df[rec_df["menu_item"] == drill].copy()
        if not lines.empty:
            drows = []
            total = 0.0
            for _, ln in lines.iterrows():
                ing   = str(ln.get("ingredient_description",""))
                key   = ing.lower().strip()
                gw    = float(ln.get("gross_w") or ln.get("net_w") or 0)
                nw    = float(ln.get("net_w") or gw)
                yp    = ln.get("yield_pct")
                uc    = sr_lookup.get(key, usage_lookup.get(key, float(ln.get("avg_cost") or 0)))
                src   = "sub recipe" if key in sr_lookup else "unit cost"
                lc    = gw * uc
                total += lc
                drows.append({
                    "Ingredient":     ing + ("  ← substitution" if gw < 0 else ""),
                    "Net W":          f"{nw:g}",
                    "Gross W":        f"{gw:g}",
                    "Yield %":        f"{yp:.1f}%" if yp else "—",
                    "Source":         src,
                    "Usage cost $/u": fmt_usd(uc, 6),
                    "Line cost $":    fmt_usd(lc, 4),
                    "Override":       "✓" if key in overrides else "",
                })
            st.dataframe(pd.DataFrame(drows), use_container_width=True, hide_index=True)
            st.markdown(f"**Total recipe cost: {fmt_usd(total, 4)}**")

    # ── Approve & export ──
    st.divider()
    if session.get("status") == "approved":
        st.success("Session approved — prices locked.")
    else:
        if st.button("Submit approved prices", type="primary", key="fr_submit"):
            _submit_approved(supabase, session_id, sim_df, st.session_state.get("user","EK Team"))

    st.download_button(
        "Export to CSV",
        data=sim_df.to_csv(index=False),
        file_name=f"dpos_{selected_name.replace(' ','_')}.csv",
        mime="text/csv",
        key="fr_export",
    )


def _submit_approved(supabase, session_id, sim_df, approved_by):
    supabase.table("dpos_approved_prices").delete().eq("session_id", session_id).execute()
    records = []
    for _, row in sim_df.iterrows():
        psych = float(row.get("psychological_price") or row.get("suggestive_price") or 0)
        records.append({
            "session_id":          session_id,
            "menu_item":           row["menu_item"],
            "category":            row.get("category") or None,
            "group_name":          row.get("group_name") or None,
            "old_price":           float(row.get("current_sp_inc_vat") or 0) or None,
            "new_price":           psych,
            "new_cost":            float(row.get("new_cost") or 0),
            "new_cost_pct":        float(row["new_cost_pct"])  if row.get("new_cost_pct")  else None,
            "new_profit_margin":   float(row["profit_margin"]) if row.get("profit_margin") else None,
            "psychological_price": psych,
            "approved_at":         datetime.now(timezone.utc).isoformat(),
            "approved_by":         approved_by,
        })
    if records:
        for i in range(0, len(records), 500):
            supabase.table("dpos_approved_prices").insert(records[i:i+500]).execute()
        st.success(f"Saved {len(records)} approved prices.")
        st.rerun()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def show_dpos(supabase: Client):
    user_role = str(st.session_state.get("role","")).lower()
    if user_role not in ("admin", "admin_all", "manager"):
        st.error("Access restricted to EK team members.")
        st.stop()

    st.markdown(
        f"""<div style="background:{EK_DARK};padding:16px 20px;border-radius:10px;margin-bottom:20px">
          <span style="color:{EK_SAND};font-size:20px;font-weight:600">D-POS Pricing Studio</span>
          <span style="color:{EK_SAND};opacity:0.6;font-size:13px;margin-left:12px">Dynamic Price Optimization Solution</span>
        </div>""",
        unsafe_allow_html=True,
    )

    clients_df = load_clients(supabase)
    if clients_df.empty:
        st.error("No clients found.")
        st.stop()

    client_options = dict(zip(clients_df["client_name"], clients_df["id"]))
    selected_name  = st.selectbox("Client", list(client_options.keys()), key="dpos_client")
    client_id      = client_options[selected_name]

    st.divider()

    tab1, tab2, tab3 = st.tabs(TABS)
    with tab1: tab_setup(supabase, client_id, selected_name)
    with tab2: tab_sessions(supabase, client_id)
    with tab3: tab_final_report(supabase, client_id)
