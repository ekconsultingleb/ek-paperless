"""
dpos.py
───────
D-POS Pricing Studio — Paperless module.
Entry point: show_dpos(supabase)
"""

import streamlit as st
import pandas as pd
import numpy as np
from supabase import Client
from datetime import datetime, timezone
from modules.dpos_simulation import (
    compute_simulation,
    enrich_with_prices,
    detect_btl_gls,
    fmt_usd, fmt_pct, fmt_variance, fmt_variance_pct,
)

EK_DARK = "#1B252C"
EK_SAND = "#E3C5AD"
TABS    = ["Setup", "Sessions", "Final Report"]

TIER_OPTIONS    = ["", "Regular", "Premium", "Ultra Premium"]
SPIRITS_OPTIONS = ["", "Gin", "Whisky", "Tequila", "Vodka", "Rum", "Cognac",
                   "Champagne / Prosecco", "Wine", "Beer", "Liqueur", "Other"]

# Item types available for tranche assignment
ITEM_TYPE_OPTIONS = ["All types", "BTL", "GLS", "Food", "Soft", "Beer", "Other"]


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def _most_recent_date(supabase: Client, table: str, client_id: int):
    res = supabase.table(table).select("report_date") \
        .eq("client_id", client_id).order("report_date", desc=True).limit(1).execute()
    return res.data[0]["report_date"] if res.data else None


@st.cache_data(ttl=120, show_spinner=False)
def load_clients(_supabase: Client) -> pd.DataFrame:
    res = _supabase.table("clients").select("id, client_name").order("client_name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_dpos_recipes(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_recipes").select("*").eq("client_id", client_id).order("category").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_dpos_unit_costs(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_unit_costs").select("*").eq("client_id", client_id).order("category").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_dpos_sub_recipes(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_sub_recipes").select("*").eq("client_id", client_id).order("product_name").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


@st.cache_data(ttl=60, show_spinner=False)
def load_sessions(_supabase: Client, client_id: int) -> pd.DataFrame:
    res = _supabase.table("dpos_sessions").select("*").eq("client_id", client_id) \
        .order("created_at", desc=True).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()


def load_tranches(supabase: Client, session_id: int) -> list:
    res = supabase.table("dpos_tranches").select("*").eq("session_id", session_id) \
        .order("min_cost").execute()
    return res.data if res.data else []


def load_client_config(supabase: Client, client_id: int) -> dict:
    res = supabase.table("clients").select("dpos_btl_gls_derive").eq("id", client_id).limit(1).execute()
    if res.data:
        return {"btl_gls_derive": res.data[0].get("dpos_btl_gls_derive", True)}
    return {"btl_gls_derive": True}


def save_client_config(supabase: Client, client_id: int, btl_gls_derive: bool):
    supabase.table("clients").update({"dpos_btl_gls_derive": btl_gls_derive}) \
        .eq("id", client_id).execute()


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
    c1.metric("Unit costs",       len(uc_df))
    c2.metric("Recipe lines",     len(rec_df))
    c3.metric("Sub recipe lines", len(sr_df))

    if has_data:
        st.success(f"Data loaded for **{client_name}**.")
    else:
        st.warning(f"No data yet for **{client_name}**. Run Full sync below.")

    st.divider()

    st.markdown("**Sync from Auto Calc**")
    col_full, col_uc = st.columns(2)
    with col_full:
        st.markdown("**Full sync**")
        st.caption("First time or when recipes change.")
        if st.button("Full sync", type="primary", key="sync_full"):
            _run_full_sync(supabase, client_id, client_name)
    with col_uc:
        st.markdown("**Unit costs only**")
        st.caption("Every month after Auto Calc upload.")
        if st.button("Sync unit costs only", key="sync_uc"):
            _run_unit_cost_sync(supabase, client_id)

    if not has_data:
        return

    st.divider()

    setup_tab1, setup_tab2, setup_tab3 = st.tabs(["Menu visibility", "Bottle / Glass config", "Pricing Rules"])

    with setup_tab1:
        _tab_menu_visibility(supabase, client_id, rec_df)
    with setup_tab2:
        _tab_bottle_glass(supabase, client_id, rec_df)
    with setup_tab3:
        _tab_pricing_rules(supabase, client_id, rec_df)

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


def _tab_menu_visibility(supabase: Client, client_id: int, rec_df: pd.DataFrame):
    st.markdown("**Menu visibility**")
    st.caption("Toggle which items appear on the client's printed menu.")

    f1, f2, f3 = st.columns([2, 2, 3])
    with f1:
        cats  = sorted(rec_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="vm_cat")
    with f2:
        grp_opts = ["All"] + sorted(
            rec_df[rec_df["category"] == cat_f]["group_name"].dropna().unique().tolist()
        )
        grp_f = st.selectbox("Group", grp_opts, key="vm_grp")
    with f3:
        search = st.text_input("Search", placeholder="e.g. pizza, gin…", key="vm_search")

    items_df = rec_df.drop_duplicates(subset="menu_item")[
        ["menu_item", "category", "group_name", "on_menu", "current_selling_price"]
    ].copy()

    items_df = items_df[items_df["category"] == cat_f]
    if grp_f != "All": items_df = items_df[items_df["group_name"] == grp_f]
    if search:         items_df = items_df[items_df["menu_item"].str.contains(search, case=False, na=False)]

    on_count  = int(rec_df.drop_duplicates("menu_item")["on_menu"].sum()) if "on_menu" in rec_df.columns else 0
    off_count = len(rec_df.drop_duplicates("menu_item")) - on_count
    st.caption(f"{on_count} on menu · {off_count} off menu · showing {len(items_df)}")

    b1, b2, _ = st.columns([1, 1, 4])
    with b1:
        if st.button("All on menu", key="bulk_on"):
            all_items = rec_df[rec_df["category"] == cat_f]["menu_item"].unique().tolist()
            supabase.table("dpos_recipes").update({"on_menu": True}) \
                .eq("client_id", client_id).in_("menu_item", all_items).execute()
            clear_cache(); st.rerun()
    with b2:
        if st.button("All off menu", key="bulk_off"):
            all_items = rec_df[rec_df["category"] == cat_f]["menu_item"].unique().tolist()
            supabase.table("dpos_recipes").update({"on_menu": False}) \
                .eq("client_id", client_id).in_("menu_item", all_items).execute()
            clear_cache(); st.rerun()

    for _, row in items_df.iterrows():
        col_name, col_sp, col_toggle = st.columns([4, 2, 1])
        with col_name:
            sub = f"  <span style='opacity:0.4;font-size:11px'>{row.get('group_name','')}</span>"
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


def _tab_bottle_glass(supabase: Client, client_id: int, rec_df: pd.DataFrame):
    st.markdown("**Bottle / Glass configuration**")
    st.caption("Set glasses per bottle. Glass price = Bottle price ÷ glasses count.")

    # ── BTL→GLS derivation toggle ──
    client_cfg = load_client_config(supabase, client_id)
    btl_gls_on = bool(client_cfg.get("btl_gls_derive", True))

    col_tog, col_tog_desc = st.columns([1, 4])
    with col_tog:
        new_toggle = st.toggle("BTL → GLS auto-derive", value=btl_gls_on, key="btl_gls_toggle")
    with col_tog_desc:
        if new_toggle:
            st.caption("GLS price = BTL simulated price ÷ glasses count (auto-matched by name). Ideal for bottle-focused venues.")
        else:
            st.caption("GLS priced independently using its own Pricing Rules. Ideal for glass-focused venues (pubs, etc.).")

    if new_toggle != btl_gls_on:
        save_client_config(supabase, client_id, new_toggle)
        st.rerun()

    st.divider()

    items_df = rec_df.drop_duplicates("menu_item")[
        ["menu_item", "category", "group_name", "glasses_count"]
    ].copy()
    items_df["item_type"] = items_df["menu_item"].apply(detect_btl_gls)
    btl_gls = items_df[items_df["item_type"].isin(["btl", "gls"])].copy()

    if btl_gls.empty:
        st.info("No Btl/Gls items detected.")
        return

    # Filters — Category, Group, Type
    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        cats  = ["All"] + sorted(btl_gls["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="bg_cat")
    with f2:
        if cat_f != "All":
            grp_opts = ["All"] + sorted(btl_gls[btl_gls["category"] == cat_f]["group_name"].dropna().unique().tolist())
        else:
            grp_opts = ["All"] + sorted(btl_gls["group_name"].dropna().unique().tolist())
        grp_f = st.selectbox("Group", grp_opts, key="bg_grp")
    with f3:
        type_f = st.selectbox("Type", ["All", "Bottle", "Glass"], key="bg_type")

    view = btl_gls.copy()
    if cat_f  != "All":    view = view[view["category"]   == cat_f]
    if grp_f  != "All":    view = view[view["group_name"] == grp_f]
    if type_f == "Bottle": view = view[view["item_type"]  == "btl"]
    if type_f == "Glass":  view = view[view["item_type"]  == "gls"]

    st.caption(f"Showing {len(view)} items")

    with st.expander("Bulk set glasses count", expanded=False):
        with st.form("bulk_glasses_form"):
            bc1, bc2 = st.columns([2, 2])
            with bc1:
                bulk_grp = st.selectbox(
                    "Filter by Group",
                    ["All groups"] + sorted(btl_gls["group_name"].dropna().unique().tolist()),
                    key="bulk_grp_sel",
                )
            with bc2:
                bulk_glasses = st.number_input("Glasses per bottle", value=10.0, min_value=1.0, step=0.5)
            if st.form_submit_button("Apply to visible bottles", type="primary"):
                target_view = view[view["item_type"] == "btl"]
                if bulk_grp != "All groups":
                    target_view = target_view[target_view["group_name"] == bulk_grp]
                btl_items = target_view["menu_item"].tolist()
                if btl_items:
                    supabase.table("dpos_recipes") \
                        .update({"glasses_count": float(bulk_glasses)}) \
                        .eq("client_id", client_id) \
                        .in_("menu_item", btl_items).execute()
                    for item in btl_items:
                        st.session_state[f"gl_{item}"] = float(bulk_glasses)
                    clear_cache()
                    st.success(f"Set {bulk_glasses:.0f} glasses for {len(btl_items)} bottle items.")
                    st.rerun()

    for _, row in view.iterrows():
        col_name, col_type, col_glasses = st.columns([4, 1, 2])
        with col_name:
            item_name = str(row.get("menu_item") or "")
            grp_label = str(row.get("group_name") or "")
            sub_label = f"  <span style='opacity:0.4;font-size:11px'>{grp_label}</span>" if grp_label else ""
            st.markdown(f"**{item_name}**{sub_label}", unsafe_allow_html=True)
        with col_type:
            badge_color = "#1B4F72" if row["item_type"] == "btl" else "#1B6B3A"
            st.markdown(
                f"<span style='background:{badge_color};color:white;padding:2px 8px;"
                f"border-radius:4px;font-size:11px'>"
                f"{'BTL' if row['item_type'] == 'btl' else 'GLS'}</span>",
                unsafe_allow_html=True,
            )
        with col_glasses:
            if row["item_type"] == "btl":
                raw = row.get("glasses_count")
                if raw is None or (isinstance(raw, float) and np.isnan(raw)):
                    current_glasses = 10.0
                else:
                    current_glasses = float(raw)
                st.number_input(
                    "Glasses",
                    value=current_glasses,
                    min_value=1.0,
                    step=0.5,
                    key=f"gl_{item_name}",
                    label_visibility="collapsed",
                )
            else:
                if new_toggle:
                    st.caption("Derived from Btl")
                else:
                    st.caption("Independent (toggle off)")

    if st.button("Save glasses counts", type="primary", key="save_glasses"):
        btl_view = view[view["item_type"] == "btl"]
        for _, row in btl_view.iterrows():
            item_name = str(row.get("menu_item") or "")
            key = f"gl_{item_name}"
            if key in st.session_state:
                val = float(st.session_state[key])
                supabase.table("dpos_recipes").update({"glasses_count": val}) \
                    .eq("client_id", client_id).eq("menu_item", item_name).execute()
        clear_cache()
        st.success("Glasses counts saved.")
        st.rerun()


def _tab_pricing_rules(supabase: Client, client_id: int, rec_df: pd.DataFrame):
    """
    Pricing Rules tab — previously 'Sub-category & Tier'.
    Two sections:
      1. Tier tagging (per item)
      2. Item type assignment (tag items with a custom type like Wine, Spirits, etc.)
    Note: Tranches are defined per session, not here. This tab manages per-item metadata.
    """
    st.markdown("**Pricing Rules — Item tagging**")
    st.caption("Tag items with a tier (Regular / Premium / Ultra Premium) for hierarchy validation.")

    items_df = rec_df.drop_duplicates("menu_item")[
        ["menu_item", "category", "group_name", "tier"]
    ].copy()

    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        cats  = ["All"] + sorted(items_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="tt_cat")
    with f2:
        if cat_f != "All":
            grp_opts = ["All"] + sorted(
                items_df[items_df["category"] == cat_f]["group_name"].dropna().unique().tolist()
            )
        else:
            grp_opts = ["All"] + sorted(items_df["group_name"].dropna().unique().tolist())
        grp_f = st.selectbox("Group", grp_opts, key="tt_grp")
    with f3:
        search = st.text_input("Search", key="tt_search")

    view = items_df.copy()
    if cat_f != "All": view = view[view["category"]   == cat_f]
    if grp_f != "All": view = view[view["group_name"] == grp_f]
    if search:         view = view[view["menu_item"].str.contains(search, case=False, na=False)]

    tagged_count = int(items_df["tier"].notna().sum())
    st.caption(f"{tagged_count} items tagged · showing {len(view)}")

    if view.empty:
        st.info("No items match the filter.")
        return

    bulk_tier = st.session_state.pop("bulk_tier_value", None)

    for _, row in view.iterrows():
        item_name    = str(row.get("menu_item") or "")
        group_name   = str(row.get("group_name") or "")
        current_tier = str(row.get("tier") or "")
        display_tier = bulk_tier if bulk_tier is not None else current_tier

        col_name, col_tier = st.columns([4, 2])
        with col_name:
            st.markdown(
                f"**{item_name}**  <span style='opacity:0.4;font-size:11px'>{group_name}</span>",
                unsafe_allow_html=True,
            )
        with col_tier:
            idx_t = TIER_OPTIONS.index(display_tier) if display_tier in TIER_OPTIONS else 0
            st.selectbox("Tier", TIER_OPTIONS, index=idx_t,
                         key=f"tier_{item_name}", label_visibility="collapsed")

    b1, b2, b3 = st.columns([2, 2, 2])
    with b1:
        if st.button("Set all visible to Regular", key="bulk_regular"):
            st.session_state["bulk_tier_value"] = "Regular"
            st.rerun()
    with b2:
        if st.button("Clear all tiers", key="bulk_clear_tier"):
            st.session_state["bulk_tier_value"] = ""
            st.rerun()
    with b3:
        if st.button("Save tiers", type="primary", key="save_tier"):
            updated = 0
            for _, row in view.iterrows():
                item_name = str(row.get("menu_item") or "")
                new_tier  = st.session_state.get(f"tier_{item_name}", "")
                supabase.table("dpos_recipes").update({
                    "tier": new_tier or None,
                }).eq("client_id", client_id).eq("menu_item", item_name).execute()
                updated += 1
            clear_cache()
            st.success(f"Saved {updated} items.")
            st.rerun()


# ─────────────────────────────────────────────
#  SYNC FUNCTIONS
# ─────────────────────────────────────────────

def _run_full_sync(supabase: Client, client_id: int, client_name: str):
    with st.spinner("Syncing from Auto Calc…"):
        try:
            uc_date  = _most_recent_date(supabase, "ac_unit_cost",     client_id)
            rec_date = _most_recent_date(supabase, "ac_recipes",        client_id)
            sr_date  = _most_recent_date(supabase, "ac_sub_recipes",    client_id)
            sp_date  = _most_recent_date(supabase, "ac_selling_prices", client_id)

            if not rec_date:
                st.error("No Auto Calc recipe data found. Upload Auto Calc first.")
                return

            st.caption(f"Using: recipes {rec_date} · unit costs {uc_date} · selling prices {sp_date}")

            existing = supabase.table("dpos_recipes") \
                .select("menu_item, on_menu, current_selling_price, glasses_count, tier") \
                .eq("client_id", client_id).execute()

            on_menu_map = {}
            sp_map      = {}
            glasses_map = {}
            tier_map    = {}

            if existing.data:
                for r in existing.data:
                    item = r["menu_item"]
                    on_menu_map[item] = r.get("on_menu", True)
                    if r.get("current_selling_price"):
                        sp_map[item] = float(r["current_selling_price"])
                    if r.get("glasses_count"):
                        glasses_map[item] = float(r["glasses_count"])
                    if r.get("tier"):
                        tier_map[item] = r["tier"]

            if sp_date:
                sp_res = supabase.table("ac_selling_prices") \
                    .select("menu_items, sp_exc_vat") \
                    .eq("client_id", client_id).eq("report_date", sp_date).execute()
                if sp_res.data:
                    for row in sp_res.data:
                        if row.get("menu_items") and row.get("sp_exc_vat") is not None:
                            sp_map[row["menu_items"]] = float(row["sp_exc_vat"])

            _sync_unit_costs(supabase, client_id, uc_date)

            rec_res = supabase.table("ac_recipes") \
                .select("category, item_group, menu_items, product_description, qty, unit, avgpurusacost, avg_cost") \
                .eq("client_id", client_id).eq("report_date", rec_date).execute()

            if rec_res.data:
                supabase.table("dpos_recipes").delete().eq("client_id", client_id).execute()
                records = []
                for row in rec_res.data:
                    item = row.get("menu_items", "")
                    if not item:
                        continue
                    gw  = float(row.get("qty") or 0)
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
                        "glasses_count":          glasses_map.get(item),
                        "tier":                   tier_map.get(item),
                    })
                for i in range(0, len(records), 500):
                    supabase.table("dpos_recipes").insert(records[i:i+500]).execute()

            sr_res = supabase.table("ac_sub_recipes") \
                .select("production_name, product_description, qty, unit_name, average_cost, qty_to_prepared, prepared_unit, cost_for_1") \
                .eq("client_id", client_id).eq("report_date", sr_date).execute()

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
                        "cost_for_1":             float(row.get("cost_for_1") or 0),
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
        .eq("client_id", client_id).eq("report_date", uc_date).execute()

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

    rec_df = load_dpos_recipes(supabase, client_id)
    df     = load_sessions(supabase, client_id)

    with st.expander("Create new session", expanded=df.empty):
        with st.form("sess_form", clear_on_submit=True):
            s1, s2, s3, s4 = st.columns(4)
            with s1: sess_name  = st.text_input("Session name *", placeholder="e.g. April 2026")
            with s2: vat_rate   = st.number_input("VAT %",             min_value=0.0,  max_value=30.0, value=11.0, step=0.5)
            with s3: target_pct = st.number_input("Global target cost %", min_value=5.0, max_value=80.0, value=30.0, step=1.0)
            with s4: rounding   = st.selectbox("Price rounding $", [0.25, 0.50, 1.00], index=1)
            notes = st.text_area("Notes (optional)", height=50)
            if st.form_submit_button("Create session", type="primary"):
                if not sess_name.strip():
                    st.error("Session name required.")
                else:
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
        status  = sess.get("status", "draft")
        sess_id = int(sess["id"])
        with st.expander(
            f"**{sess['session_name']}**  —  {str(sess.get('created_at',''))[:10]}  |  {status.upper()}",
            expanded=False,
        ):
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("VAT",             f"{float(sess.get('vat_rate',0))*100:.1f}%")
            sc2.metric("Global target %", f"{float(sess.get('target_cost_pct',0.3))*100:.1f}%")
            sc3.metric("Rounding",        f"${float(sess.get('rounding',0.5)):.2f}")
            sc4.metric("Status",          status.upper())

            if sess.get("notes"):
                st.caption(f"Notes: {sess['notes']}")

            st1, st2, st3 = st.tabs(["Actions", "Per-category targets", "Cost tranches"])

            with st1:
                _session_actions(supabase, sess_id, status, client_id)
            with st2:
                _tab_category_targets(supabase, sess_id, rec_df, float(sess.get("target_cost_pct", 0.30)))
            with st3:
                _tab_tranches(supabase, sess_id)


def _session_actions(supabase, sess_id, status, client_id):
    a1, a2, a3 = st.columns(3)
    with a1:
        if status == "draft" and st.button("Mark approved", key=f"approve_{sess_id}"):
            supabase.table("dpos_sessions").update({"status": "approved"}).eq("id", sess_id).execute()
            load_sessions.clear(); st.rerun()
    with a2:
        if status != "archived" and st.button("Archive", key=f"archive_{sess_id}"):
            supabase.table("dpos_sessions").update({"status": "archived"}).eq("id", sess_id).execute()
            load_sessions.clear(); st.rerun()
    with a3:
        if st.button("Delete", key=f"del_{sess_id}", type="secondary"):
            supabase.table("dpos_sessions").delete().eq("id", sess_id).execute()
            load_sessions.clear(); st.rerun()

    ov_res = supabase.table("dpos_cost_overrides").select("*").eq("session_id", sess_id).execute()
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
        _add_override_form(supabase, sess_id, client_id)


def _tab_category_targets(supabase: Client, session_id: int, rec_df: pd.DataFrame, global_target: float):
    st.markdown("**Per-category target cost %**")
    st.caption("Override the global target for specific categories. 0 = use global.")

    categories = sorted(rec_df["category"].dropna().unique().tolist()) if not rec_df.empty else []

    existing = supabase.table("dpos_session_targets").select("*").eq("session_id", session_id).execute()
    existing_map = {}
    if existing.data:
        for r in existing.data:
            existing_map[r["category"]] = float(r["target_cost_pct"])

    if not categories:
        st.info("No categories found. Run full sync first.")
        return

    with st.form(f"cat_targets_{session_id}", clear_on_submit=False):
        cols = st.columns(3)
        new_targets = {}
        for idx, cat in enumerate(categories):
            with cols[idx % 3]:
                current = existing_map.get(cat, 0.0)
                val = st.number_input(
                    cat,
                    value=float(current * 100) if current else 0.0,
                    min_value=0.0, max_value=80.0, step=1.0,
                    key=f"ct_{session_id}_{cat}",
                )
                new_targets[cat] = val / 100 if val > 0 else None

        if st.form_submit_button("Save category targets", type="primary"):
            supabase.table("dpos_session_targets").delete().eq("session_id", session_id).execute()
            records = [
                {"session_id": session_id, "category": cat, "target_cost_pct": tgt}
                for cat, tgt in new_targets.items() if tgt
            ]
            if records:
                supabase.table("dpos_session_targets").insert(records).execute()
            st.success("Category targets saved.")


def _tab_tranches(supabase: Client, session_id: int):
    st.markdown("**Cost tranches**")
    st.caption(
        "Define cost brackets per item type. "
        "Two modes: Target % (calculate from cost) or Fixed price (set directly). "
        "Leave item type as 'All types' to apply the rule to all items regardless of type."
    )

    tranches = load_tranches(supabase, session_id)

    if tranches:
        rows = []
        for t in tranches:
            mode      = t.get("mode", "target_pct")
            item_type = t.get("item_type") or "All types"
            if mode == "fixed_price":
                rule = f"Fixed price: ${float(t.get('fixed_price') or 0):.2f}"
            else:
                rule = f"Target: {float(t.get('target_pct') or 0)*100:.1f}%"
            rows.append({
                "Item type":  item_type.upper() if item_type != "All types" else "All types",
                "Min cost $": f"${float(t['min_cost']):.2f}",
                "Max cost $": f"${float(t['max_cost']):.2f}",
                "Mode":       mode.replace("_", " ").title(),
                "Rule":       rule,
                "ID":         t["id"],
            })
        t_df = pd.DataFrame(rows)
        st.dataframe(t_df[["Item type", "Min cost $", "Max cost $", "Mode", "Rule"]], use_container_width=True, hide_index=True)

        del_options = {
            f"{t.get('item_type','All') or 'All'}  ${float(t['min_cost']):.2f}–${float(t['max_cost']):.2f}": t["id"]
            for t in tranches
        }
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            del_sel = st.selectbox("Delete tranche", ["—"] + list(del_options.keys()), key=f"del_t_{session_id}")
        with col_del2:
            if st.button("Delete", key=f"del_t_btn_{session_id}") and del_sel != "—":
                supabase.table("dpos_tranches").delete().eq("id", del_options[del_sel]).execute()
                st.rerun()

    # Add new tranche — mode selector outside form so it re-renders dynamically
    st.markdown("**Add tranche**")
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        item_type_sel = st.selectbox(
            "Item type",
            ITEM_TYPE_OPTIONS,
            key=f"tr_itype_{session_id}",
            help="Select a specific type (BTL, GLS, etc.) or 'All types' to apply to everything.",
        )
        min_c = st.number_input("Min cost $", value=0.0,  min_value=0.0,  step=0.5, key=f"tr_min_{session_id}")
        max_c = st.number_input("Max cost $", value=10.0, min_value=0.01, step=0.5, key=f"tr_max_{session_id}")
    with tc2:
        mode = st.selectbox("Mode", ["target_pct", "fixed_price"],
                            format_func=lambda x: "Target %" if x == "target_pct" else "Fixed price",
                            key=f"tr_mode_{session_id}")
    with tc3:
        if mode == "target_pct":
            tgt = st.number_input("Target %", value=25.0, min_value=1.0, max_value=80.0, step=1.0, key=f"tr_tgt_{session_id}")
            fp  = None
        else:
            fp  = st.number_input("Fixed price $", value=100.0, min_value=0.01, step=5.0, key=f"tr_fp_{session_id}")
            tgt = None

    if st.button("Add tranche", type="primary", key=f"tr_add_{session_id}"):
        if min_c >= max_c:
            st.error("Min cost must be less than max cost.")
        elif mode == "fixed_price" and (fp is None or fp <= 0):
            st.error("Fixed price must be greater than 0.")
        else:
            stored_type = None if item_type_sel == "All types" else item_type_sel.lower()
            supabase.table("dpos_tranches").insert({
                "session_id":  session_id,
                "item_type":   stored_type,
                "min_cost":    min_c,
                "max_cost":    max_c,
                "mode":        mode,
                "target_pct":  tgt / 100 if tgt else None,
                "fixed_price": fp,
            }).execute()
            type_label = item_type_sel.upper() if item_type_sel != "All types" else "All types"
            rule_label = f"${fp:.2f} fixed" if mode == "fixed_price" else f"{tgt:.1f}%"
            st.success(f"Tranche added: [{type_label}] ${min_c}–${max_c} → {rule_label}")
            st.rerun()


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
            st.caption(f"Change: {'+' if chg > 0 else ''}{chg:.1f}%")

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

    sess_res = supabase.table("dpos_sessions").select("*").eq("client_id", client_id) \
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
    sc1.metric("VAT",             f"{vat*100:.1f}%")
    sc2.metric("Global target %", f"{target*100:.1f}%")
    sc3.metric("Rounding",        f"${rounding:.2f}")
    sc4.metric("Status",          session.get("status", "draft").upper())

    st.divider()

    with st.spinner("Loading…"):
        uc_df    = load_dpos_unit_costs(supabase, client_id)
        sr_df    = load_dpos_sub_recipes(supabase, client_id)
        rec_df   = load_dpos_recipes(supabase, client_id)
        ov_res   = supabase.table("dpos_cost_overrides").select("*").eq("session_id", session_id).execute()
        ap_res   = supabase.table("dpos_approved_prices").select("*").eq("session_id", session_id).execute()
        tgt_res  = supabase.table("dpos_session_targets").select("*").eq("session_id", session_id).execute()
        tranches = load_tranches(supabase, session_id)
        client_cfg = load_client_config(supabase, client_id)

    btl_gls_derive = bool(client_cfg.get("btl_gls_derive", True))

    if rec_df.empty:
        st.warning("No recipes. Run Setup → Full sync first.")
        return
    if uc_df.empty:
        st.warning("No unit costs. Run Setup → Full sync first.")
        return

    ap_df = pd.DataFrame(ap_res.data) if ap_res.data else pd.DataFrame()

    overrides = {}
    if ov_res.data:
        for ov in ov_res.data:
            overrides[str(ov.get("product_description","")).lower().strip()] = float(ov.get("predicted_cost", 0))

    category_targets = {}
    if tgt_res.data:
        for t in tgt_res.data:
            category_targets[t["category"].lower().strip()] = float(t["target_cost_pct"])

    # Show active tranches summary
    if tranches:
        with st.expander(f"Active tranches ({len(tranches)})", expanded=False):
            for t in tranches:
                mode      = t.get("mode", "target_pct")
                item_type = (t.get("item_type") or "All types").upper() if t.get("item_type") else "All types"
                if mode == "fixed_price":
                    rule = f"→ Fixed ${float(t.get('fixed_price') or 0):.2f}"
                else:
                    rule = f"→ Target {float(t.get('target_pct') or 0)*100:.1f}%"
                st.caption(f"[{item_type}]  ${float(t['min_cost']):.2f} – ${float(t['max_cost']):.2f}  {rule}")

    # Show BTL→GLS derive status
    derive_label = "BTL→GLS derive: **ON**" if btl_gls_derive else "BTL→GLS derive: **OFF** (GLS uses own tranche rules)"
    st.caption(derive_label)

    # ── Item selection ──
    st.markdown("**Item selection**")
    all_items     = sorted(rec_df["menu_item"].dropna().unique().tolist())
    on_menu_items = rec_df[rec_df["on_menu"] == True]["menu_item"].unique().tolist() \
        if "on_menu" in rec_df.columns else all_items

    sel_key = f"fr_sel_{session_id}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = list(on_menu_items)

    fi1, fi2, fi3, fi4 = st.columns([2, 2, 2, 1])
    with fi1:
        cats  = ["All"] + sorted(rec_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", cats, key="fr_cat")
    with fi2:
        if cat_f != "All":
            grp_opts = ["All"] + sorted(rec_df[rec_df["category"] == cat_f]["group_name"].dropna().unique().tolist())
        else:
            grp_opts = ["All"] + sorted(rec_df["group_name"].dropna().unique().tolist())
        grp_f = st.selectbox("Group", grp_opts, key="fr_grp")
    with fi3:
        show_off = st.checkbox("Include off-menu items", value=False, key="fr_off")
    with fi4:
        st.markdown("<br>", unsafe_allow_html=True)

    filt = rec_df.drop_duplicates("menu_item").copy()
    if cat_f != "All": filt = filt[filt["category"]   == cat_f]
    if grp_f != "All": filt = filt[filt["group_name"] == grp_f]
    if not show_off and "on_menu" in filt.columns:
        filt = filt[filt["on_menu"] == True]

    visible  = sorted(filt["menu_item"].dropna().unique().tolist())
    selected = list(st.session_state[sel_key])

    sb1, sb2 = st.columns(2)
    with sb1:
        if st.button("Select all visible", key="sel_all"):
            st.session_state[sel_key] = list(set(selected) | set(visible))
            st.rerun()
    with sb2:
        if st.button("Deselect all visible", key="desel_all"):
            st.session_state[sel_key] = [i for i in selected if i not in visible]
            st.rerun()

    cols = st.columns(3)
    for idx, item in enumerate(visible):
        with cols[idx % 3]:
            chk = st.checkbox(item, value=item in selected, key=f"chk_{session_id}_{item}")
            if chk and item not in selected:
                selected.append(item)
            elif not chk and item in selected:
                selected.remove(item)
    st.session_state[sel_key] = selected

    items_to_simulate = [i for i in selected if i in visible]
    st.caption(f"{len(items_to_simulate)} items will be simulated")

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
        if not items_to_simulate:
            st.warning("No items selected. Use filters and checkboxes to select items.")
        else:
            sim_rec = rec_df[rec_df["menu_item"].isin(items_to_simulate)].copy()
            with st.spinner(f"Calculating {len(items_to_simulate)} items…"):
                raw, usage_lookup, _ = compute_simulation(
                    sim_rec, uc_df, sr_df, overrides, session,
                    category_targets=category_targets,
                    tranches=tranches,
                    item_config=rec_df.drop_duplicates("menu_item"),
                    btl_gls_derive=btl_gls_derive,
                )
                old_costs = {}
                if not ap_df.empty and "new_cost" in ap_df.columns:
                    old_costs = dict(zip(ap_df["menu_item"], ap_df["new_cost"].astype(float)))
                sim_df = enrich_with_prices(raw, old_costs, session)
                st.session_state[sim_key] = {"df": sim_df, "usage_lookup": usage_lookup}

    cached = st.session_state.get(sim_key)

    if cached is None:
        st.info("Select items then click **Run simulation**.")
        return

    sim_df       = cached["df"]
    usage_lookup = cached["usage_lookup"]

    if sim_df.empty:
        st.warning("Simulation returned no results.")
        return

    # ── Summary ──
    total_items  = len(sim_df)
    affected     = int(sim_df["affected"].sum()) if "affected" in sim_df.columns else 0
    above_target = int((sim_df["current_cost_pct"].dropna() > target*100).sum()) if "current_cost_pct" in sim_df.columns else 0
    avg_margin   = sim_df["profit_margin"].dropna().mean() if "profit_margin" in sim_df.columns else None
    violations   = int(sim_df["tier_violation"].sum()) if "tier_violation" in sim_df.columns else 0
    fixed_count  = int((sim_df["pricing_mode"] == "fixed_price").sum()) if "pricing_mode" in sim_df.columns else 0
    gls_derived  = int(sim_df["gls_derived_from_btl"].sum()) if "gls_derived_from_btl" in sim_df.columns else 0

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("Items",           total_items)
    m2.metric("Fixed price",     fixed_count)
    m3.metric("GLS derived",     gls_derived)
    m4.metric("Cost affected",   affected)
    m5.metric("Above target %",  above_target)
    m6.metric("Avg margin",      fmt_pct(avg_margin))
    m7.metric("Tier violations", violations)

    st.divider()

    if violations > 0 and "tier_violation" in sim_df.columns:
        with st.expander(f"⚠️ {violations} tier hierarchy violation(s)", expanded=True):
            for _, row in sim_df[sim_df["tier_violation"] == True].iterrows():
                st.warning(f"**{row['menu_item']}** — {row.get('tier_violation_msg','')}")

    # ── Results table ──
    rows = []
    for _, row in sim_df.iterrows():
        sp_ex    = row.get("current_selling_price_ex")
        sp_inc   = row.get("current_sp_inc_vat")
        eff_tgt  = row.get("effective_target_pct", target)
        mode     = row.get("pricing_mode", "target_pct")
        fp       = row.get("fixed_price")
        gls_flag = " ✓" if row.get("gls_derived_from_btl") else ""
        tier_flag = " ⚠️" if row.get("tier_violation") else ""
        mode_label = f"Fixed ${float(fp):.2f}" if mode == "fixed_price" and fp is not None else fmt_pct(eff_tgt * 100)

        rows.append({
            "":                     "⚡" if row.get("affected") else "—",
            "Category":             row.get("category",""),
            "Group":                row.get("group_name",""),
            "Menu item":            row.get("menu_item",""),
            "Type":                 row.get("item_type","other").upper() if row.get("item_type","other") != "other" else "—",
            "Tier":                 (row.get("tier","") or "—") + tier_flag,
            "Recipe cost $":        fmt_usd(row.get("new_cost"), 4),
            "Pricing rule":         mode_label,
            "Current SP (ex VAT)":  fmt_usd(sp_ex, 2) if sp_ex else "—",
            "Current SP (inc VAT)": fmt_usd(sp_inc, 2) if sp_inc else "—",
            "Current cost %":       fmt_pct(row.get("current_cost_pct")),
            "Curr. margin %":       fmt_pct(row.get("current_profit_margin")),
            "Cost var. $":          fmt_variance(row.get("cost_variance")),
            "Suggestive (inc VAT)": fmt_usd(row.get("suggestive_price"), 2),
            "Rounded SP $":         fmt_usd(row.get("psychological_price"), 2) + gls_flag,
            "New cost %":           fmt_pct(row.get("new_cost_pct")),
            "New margin %":         fmt_pct(row.get("profit_margin")),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Drill-down ──
    st.divider()
    st.markdown("**Ingredient breakdown**")
    drill = st.selectbox("Inspect menu item", ["— select —"] + sorted(sim_df["menu_item"].tolist()), key="fr_drill")

    if drill and drill != "— select —":
        lines = rec_df[rec_df["menu_item"] == drill].copy()
        if not lines.empty:
            drows  = []
            total  = 0.0
            for _, ln in lines.iterrows():
                ing  = str(ln.get("ingredient_description",""))
                key  = ing.lower().strip()
                gw   = float(ln.get("gross_w") or ln.get("net_w") or 0)
                nw   = float(ln.get("net_w") or gw)
                yp   = ln.get("yield_pct")
                uc   = usage_lookup.get(key, float(ln.get("avg_cost") or 0))
                lc   = gw * uc
                total += lc
                drows.append({
                    "Ingredient":     ing + ("  ← substitution" if gw < 0 else ""),
                    "Net W":          f"{nw:g}",
                    "Gross W":        f"{gw:g}",
                    "Yield %":        f"{yp:.1f}%" if yp else "—",
                    "Usage cost $/u": fmt_usd(uc, 6),
                    "Line cost $":    fmt_usd(lc, 4),
                    "Override":       "✓" if key in overrides else "",
                })
            st.dataframe(pd.DataFrame(drows), use_container_width=True, hide_index=True)
            st.markdown(f"**Total recipe cost: {fmt_usd(total, 4)}**")

            item_row = sim_df[sim_df["menu_item"] == drill]
            if not item_row.empty:
                r = item_row.iloc[0]
                mode = r.get("pricing_mode", "target_pct")
                if r.get("gls_derived_from_btl"):
                    btl_name = drill.replace("Gls ", "Btl ").replace("gls ", "btl ").replace("Glass ", "Bottle ")
                    gc = r.get("glasses_count") or "?"
                    st.info(f"Pricing mode: **GLS derived from BTL** ({btl_name}, ÷ {gc:.0f} glasses)")
                elif mode == "fixed_price":
                    st.info(f"Pricing mode: **Fixed price** ${float(r.get('fixed_price') or 0):.2f} (tranche rule)")
                else:
                    st.info(f"Pricing mode: **Target {float(r.get('effective_target_pct', target))*100:.1f}%**")

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
