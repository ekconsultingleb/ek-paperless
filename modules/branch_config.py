import streamlit as st
from supabase import create_client, Client
from modules.nav_helper import get_all_clients, get_outlets_for_client


# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ══════════════════════════════════════════════════════════════════════════════
# DEFAULTS — single source of truth, must match the migration defaults
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "vat_enabled": False,
    "vat_rate": 0.11,
    "third_party_enabled": False,
    "third_party_label": "Third Party",
    "multi_currency_enabled": True,
    "lbp_rate": 90000,
    "mgt_fees_enabled": False,
    "mgt_fees_rate": 0.05,
    "mgt_fees_include_third_party": True,
    "void_tracking_enabled": False,
    "expenses_tracking_enabled": True,
    "base_currency": "USD",
}


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHERS
# ══════════════════════════════════════════════════════════════════════════════

def get_branch_config(outlet: str) -> dict:
    """Fetch the cash_form_config JSONB for a single branch. Falls back to defaults."""
    try:
        res = (get_supabase()
               .table("branches")
               .select("cash_form_config")
               .eq("outlet", outlet)
               .limit(1)
               .execute())
        if res.data and res.data[0].get("cash_form_config"):
            # Merge with defaults so any missing keys (from older configs) get filled
            cfg = {**DEFAULT_CONFIG, **res.data[0]["cash_form_config"]}
            return cfg
    except Exception as e:
        st.error(f"❌ Could not load config for {outlet}: {e}")
    return DEFAULT_CONFIG.copy()


def save_branch_config(outlet: str, config: dict) -> bool:
    """Update the cash_form_config for a single branch. Returns success bool."""
    try:
        (get_supabase()
         .table("branches")
         .update({"cash_form_config": config})
         .eq("outlet", outlet)
         .execute())
        return True
    except Exception as e:
        st.error(f"❌ Save failed: {e}")
        return False


def save_config_for_client(client_name: str, config: dict) -> int:
    """Apply the same config to ALL branches of a client. Returns count updated."""
    try:
        res = (get_supabase()
               .table("branches")
               .update({"cash_form_config": config})
               .eq("client_name", client_name)
               .execute())
        return len(res.data or [])
    except Exception as e:
        st.error(f"❌ Bulk save failed: {e}")
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def render_branch_config(user, role):
    """
    Admin-only screen for configuring per-branch cash form behavior.
    Writes to branches.cash_form_config (JSONB).
    """
    st.markdown("### ⚙️ Branch Cash Form Configuration")

    # ── ACCESS GUARD ──────────────────────────────────────────────────────────
    if str(role).lower() not in ["admin", "admin_all"]:
        st.error("🔒 Access restricted to EK staff.")
        return

    st.caption("Configure how the daily cash form behaves for each branch. "
               "Toggles here control which fields cashiers see when they fill the daily report.")

    # ══════════════════════════════════════════════════════════════════════════
    # 1. CLIENT + BRANCH PICKER
    # ══════════════════════════════════════════════════════════════════════════
    col_c, col_b = st.columns(2)
    with col_c:
        clients = get_all_clients()
        if not clients:
            st.warning("⚠️ No clients found.")
            return
        sel_client = st.selectbox("🏢 Client", clients, key="bcfg_client")

    with col_b:
        branches = get_outlets_for_client(sel_client)
        if not branches:
            st.warning(f"⚠️ No branches found for {sel_client}.")
            return
        sel_branch = st.selectbox("🏠 Branch", branches, key="bcfg_branch")

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # 2. LOAD CURRENT CONFIG
    # ══════════════════════════════════════════════════════════════════════════
    cfg = get_branch_config(sel_branch)
    st.markdown(f"#### 🏠 {sel_branch}")

    # ══════════════════════════════════════════════════════════════════════════
    # 3. CONFIG FORM — sectioned for clarity
    # ══════════════════════════════════════════════════════════════════════════

    # ── Sales & VAT ───────────────────────────────────────────────────────────
    st.markdown("##### 💰 Sales & VAT")
    col1, col2 = st.columns(2)
    with col1:
        vat_enabled = st.checkbox("VAT tracking enabled",
                                   value=cfg["vat_enabled"],
                                   key="bcfg_vat_on",
                                   help="Splits Sales TTC into Sales HT + VAT on the daily form.")
    with col2:
        vat_rate_pct = st.number_input("VAT rate (%)",
                                        value=float(cfg["vat_rate"]) * 100,
                                        min_value=0.0, max_value=100.0, step=0.5,
                                        format="%.2f",
                                        disabled=not vat_enabled,
                                        key="bcfg_vat_rate")

    # ── Payment Methods ───────────────────────────────────────────────────────
    st.markdown("##### 💳 Payment Methods")
    col3, col4 = st.columns(2)
    with col3:
        multi_currency = st.checkbox("Multi-currency (USD + LBP)",
                                      value=cfg["multi_currency_enabled"],
                                      key="bcfg_multicur",
                                      help="Adds Credit Card LBP field with auto-conversion to USD.")
    with col4:
        lbp_rate = st.number_input("Default LBP rate",
                                    value=int(cfg["lbp_rate"]),
                                    min_value=1000, step=1000,
                                    disabled=not multi_currency,
                                    key="bcfg_lbp_rate",
                                    help="LBP per 1 USD. Cashier can override per day if needed.")

    # ── Operations ────────────────────────────────────────────────────────────
    st.markdown("##### 🍽️ Operations")
    col5, col6 = st.columns(2)
    with col5:
        third_party_enabled = st.checkbox("Third-party delivery",
                                           value=cfg["third_party_enabled"],
                                           key="bcfg_3p_on",
                                           help="Adds a delivery revenue field.")
        expenses_enabled = st.checkbox("Daily expenses tracking",
                                        value=cfg["expenses_tracking_enabled"],
                                        key="bcfg_exp_on",
                                        help="Adds the petty cash expenses sub-form.")
    with col6:
        third_party_label = st.text_input("Third-party label",
                                            value=cfg["third_party_label"],
                                            disabled=not third_party_enabled,
                                            key="bcfg_3p_label",
                                            help="e.g. Toters, Talabat, Online Orders")
        void_enabled = st.checkbox("Void & discount tracking",
                                    value=cfg["void_tracking_enabled"],
                                    key="bcfg_void_on",
                                    help="Adds the voids & discounts sub-form.")

    # ── Management Fees ───────────────────────────────────────────────────────
    st.markdown("##### 💼 Management Fees")
    st.caption("Calculated automatically on reports as a percentage of sales.")
    col7, col8, col9 = st.columns([1, 1, 1.3])
    with col7:
        mgt_fees_enabled = st.checkbox("Mgt fees enabled",
                                        value=cfg["mgt_fees_enabled"],
                                        key="bcfg_mgt_on")
    with col8:
        mgt_fees_rate_pct = st.number_input("Rate (%)",
                                              value=float(cfg["mgt_fees_rate"]) * 100,
                                              min_value=0.0, max_value=100.0,
                                              step=0.5, format="%.2f",
                                              disabled=not mgt_fees_enabled,
                                              key="bcfg_mgt_rate",
                                              help="Percentage of the base. Typical agreements: 5–7%.")
    with col9:
        mgt_fees_include_3p = st.checkbox(
            "Include third-party in base",
            value=cfg["mgt_fees_include_third_party"],
            disabled=not mgt_fees_enabled,
            key="bcfg_mgt_inc3p",
            help="If checked: base = Main Reading + Third Party. If not: base = Main Reading only.",
        )

    # ── Base Currency ─────────────────────────────────────────────────────────
    st.markdown("##### 💱 Base Currency")
    base_currency = st.radio("POS base currency",
                              ["USD", "LBP"],
                              index=0 if cfg["base_currency"] == "USD" else 1,
                              horizontal=True,
                              key="bcfg_base_cur",
                              label_visibility="collapsed")

    # ══════════════════════════════════════════════════════════════════════════
    # 4. BUILD NEW CONFIG DICT
    # ══════════════════════════════════════════════════════════════════════════
    new_config = {
        "vat_enabled": vat_enabled,
        "vat_rate": round(vat_rate_pct / 100, 4),
        "third_party_enabled": third_party_enabled,
        "third_party_label": third_party_label.strip() or "Third Party",
        "multi_currency_enabled": multi_currency,
        "lbp_rate": int(lbp_rate),
        "mgt_fees_enabled": mgt_fees_enabled,
        "mgt_fees_rate": round(mgt_fees_rate_pct / 100, 4),
        "mgt_fees_include_third_party": mgt_fees_include_3p,
        "void_tracking_enabled": void_enabled,
        "expenses_tracking_enabled": expenses_enabled,
        "base_currency": base_currency,
    }

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # 5. SAVE BUTTONS
    # ══════════════════════════════════════════════════════════════════════════
    col_s1, col_s2, col_s3 = st.columns([2, 2, 1])

    with col_s1:
        if st.button(f"💾 Save for {sel_branch}",
                     type="primary", use_container_width=True,
                     key="bcfg_save_one"):
            if save_branch_config(sel_branch, new_config):
                st.success(f"✅ Saved configuration for **{sel_branch}**")
                # Clear cached fetch so re-load shows fresh data
                st.rerun()

    with col_s2:
        if st.button(f"📋 Apply to all {sel_client} branches",
                     use_container_width=True,
                     key="bcfg_save_all",
                     help=f"Applies this exact config to every branch under {sel_client}."):
            st.session_state["bcfg_confirm_bulk"] = True

    with col_s3:
        if st.button("↺ Reset",
                     use_container_width=True,
                     key="bcfg_reset",
                     help="Reset form to default values (does NOT save until you click Save)."):
            for k in list(st.session_state.keys()):
                if k.startswith("bcfg_") and k not in ("bcfg_client", "bcfg_branch"):
                    del st.session_state[k]
            st.rerun()

    # ── Bulk-apply confirmation ───────────────────────────────────────────────
    if st.session_state.get("bcfg_confirm_bulk"):
        all_branches = get_outlets_for_client(sel_client)
        st.warning(f"⚠️ This will overwrite the config of **all {len(all_branches)} branches** "
                   f"under {sel_client}: {', '.join(all_branches)}. Continue?")
        cy, cn = st.columns(2)
        with cy:
            if st.button("Yes, apply to all", type="primary", use_container_width=True,
                         key="bcfg_bulk_yes"):
                count = save_config_for_client(sel_client, new_config)
                st.session_state["bcfg_confirm_bulk"] = False
                st.success(f"✅ Updated {count} branch(es) under {sel_client}")
                st.rerun()
        with cn:
            if st.button("Cancel", use_container_width=True, key="bcfg_bulk_no"):
                st.session_state["bcfg_confirm_bulk"] = False
                st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # 6. JSONB PREVIEW (collapsed)
    # ══════════════════════════════════════════════════════════════════════════
    with st.expander("🔍 Raw JSON preview (debug)", expanded=False):
        st.json(new_config)
        st.caption("This is what will be written to `branches.cash_form_config`. "
                   "You normally don't need to look here — it's for sanity-checking only.")