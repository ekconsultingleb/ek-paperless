import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from modules.nav_helper import (
    build_outlet_location_sidebar,
    get_all_clients,
    get_outlets_for_client,
)


# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ══════════════════════════════════════════════════════════════════════════════
# DEFAULT CONFIG — must mirror branch_config.py and the migration defaults
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    "vat_enabled": False,
    "vat_rate": 0.11,
    "third_party_enabled": False,
    "third_party_label": "Third Party",
    "multi_currency_enabled": True,
    "lbp_rate": 90000,
    "mgt_fees_enabled": False,
    "void_tracking_enabled": False,
    "expenses_tracking_enabled": True,
    "base_currency": "USD",
}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG FETCHER
# ══════════════════════════════════════════════════════════════════════════════

def get_branch_config(outlet: str) -> dict:
    """Load cash_form_config for a branch, merged on top of defaults."""
    try:
        res = (get_supabase()
               .table("branches")
               .select("cash_form_config")
               .eq("outlet", outlet)
               .limit(1)
               .execute())
        if res.data and res.data[0].get("cash_form_config"):
            return {**DEFAULT_CONFIG, **res.data[0]["cash_form_config"]}
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def render_daily_cash(conn, sheet_link, user, role,
                      assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 🏦 Daily Cash Report")
    supabase = get_supabase()

    try:
        # ══════════════════════════════════════════════════════════════════════
        # VIEWER MODE — read-only date-range browser
        # ══════════════════════════════════════════════════════════════════════
        if str(role).lower() == "viewer":
            _render_viewer_mode(supabase, assigned_client)
            return

        # ══════════════════════════════════════════════════════════════════════
        # SIDEBAR NAVIGATION → final_client / final_outlet
        # ══════════════════════════════════════════════════════════════════════
        final_client, final_outlet, _ = build_outlet_location_sidebar(
            assigned_client, assigned_outlet, assigned_location,
            outlet_key="cash_outlet", location_key="cash_location",
        )

        # ══════════════════════════════════════════════════════════════════════
        # TWO TABS: Entry | Reports
        # ══════════════════════════════════════════════════════════════════════
        tab_entry, tab_reports = st.tabs(["📝 Daily Entry", "📊 Reports & Export"])

        with tab_entry:
            _render_entry_form(supabase, user, role,
                               final_client, final_outlet)

        with tab_reports:
            _render_reports(supabase, role,
                            final_client, final_outlet)

    except Exception as e:
        st.error(f"❌ System Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# VIEWER MODE
# ══════════════════════════════════════════════════════════════════════════════

def _render_viewer_mode(supabase, assigned_client):
    st.info("👁️ Viewer Mode — read-only access to daily cash logs")

    today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
    default_start = today - timedelta(days=7)
    date_range = st.date_input("📅 Date Range",
                                value=(default_start, today),
                                max_value=today)

    if len(date_range) != 2:
        st.info("Please select both a start and end date.")
        return

    start_date, end_date = date_range
    q = (supabase.table("daily_cash").select("*")
         .gte("date", str(start_date))
         .lte("date", str(end_date)))

    if str(assigned_client).lower() != "all":
        q = q.eq("client_name", str(assigned_client).strip())

    res = q.order("date", desc=True).limit(2000).execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()

    if df.empty:
        st.warning(f"No cash reports found between {start_date} and {end_date}.")
        return

    # Format currency-like columns
    money_cols = [c for c in df.columns if c in (
        "main_reading", "cash", "visa", "expenses", "on_account",
        "revenue", "over_short", "sales_ht", "vat", "third_party",
        "credit_card_usd", "credit_card_lbp", "cc_lbp_to_usd",
        "closing_balance_usd", "mgt_fees",
    )]
    for c in money_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).map(lambda x: f"{x:,.2f}")

    st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY FORM — config-driven
# ══════════════════════════════════════════════════════════════════════════════

def _render_entry_form(supabase, user, role, final_client, final_outlet):
    # ── Guard against missing branch selection ────────────────────────────────
    if final_outlet in ("None", "", None) or final_client in ("Select Branch", "", None):
        st.warning("⚠️ Please select a valid Branch and Outlet from the sidebar.")
        return

    # ── Load branch config ────────────────────────────────────────────────────
    cfg = get_branch_config(final_outlet)

    st.info(f"📝 Daily Cash Entry for **{final_outlet}**")

    # Show which features are active for this branch (transparent for the cashier)
    active_features = []
    if cfg["vat_enabled"]:
        active_features.append(f"VAT {cfg['vat_rate']*100:.1f}%")
    if cfg["third_party_enabled"]:
        active_features.append(cfg["third_party_label"])
    if cfg["multi_currency_enabled"]:
        active_features.append("USD + LBP cards")
    if cfg["mgt_fees_enabled"]:
        active_features.append("Mgt fees")
    if active_features:
        st.caption("Active for this branch: " + " · ".join(active_features))

    # ══════════════════════════════════════════════════════════════════════════
    # FORM FIELDS — rendered conditionally based on cfg
    # ══════════════════════════════════════════════════════════════════════════

    # ── Date & Main Reading ───────────────────────────────────────────────────
    col_date, col_main = st.columns(2)
    with col_date:
        entry_date = st.date_input(
            "📅 Report Date",
            datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")),
            key="dc_date",
        )
    with col_main:
        main_reading = st.number_input(
            "Main Reading (Sales TTC)",
            min_value=0.0, step=10.0, format="%.2f",
            key="dc_main",
            help="Total sales including VAT — straight from the POS.",
        )

    # ── VAT split (auto-calculated, read-only display) ────────────────────────
    if cfg["vat_enabled"]:
        vat_rate = float(cfg["vat_rate"])
        sales_ht = main_reading / (1 + vat_rate) if main_reading > 0 else 0.0
        vat_amount = main_reading - sales_ht
        c_ht, c_vat = st.columns(2)
        c_ht.metric(f"Sales HT (before {vat_rate*100:.1f}% VAT)", f"{sales_ht:,.2f}")
        c_vat.metric(f"VAT ({vat_rate*100:.1f}%)", f"{vat_amount:,.2f}")
    else:
        sales_ht = main_reading
        vat_amount = 0.0

    st.markdown("##### 💵 Cash & Expenses")
    col_cash, col_exp = st.columns(2)
    with col_cash:
        cash_val = st.number_input(
            "Cash in Drawer (USD)",
            min_value=0.0, step=10.0, format="%.2f",
            key="dc_cash",
        )
    with col_exp:
        exp_val = st.number_input(
            "Expenses (Petty Cash)",
            min_value=0.0, step=10.0, format="%.2f",
            key="dc_exp",
        )

    # ── Credit Cards ──────────────────────────────────────────────────────────
    st.markdown("##### 💳 Credit Cards")
    if cfg["multi_currency_enabled"]:
        col_cu, col_cl, col_rate = st.columns([1, 1, 1])
        with col_cu:
            cc_usd = st.number_input(
                "Credit Card USD",
                min_value=0.0, step=10.0, format="%.2f",
                key="dc_ccusd",
            )
        with col_cl:
            cc_lbp = st.number_input(
                "Credit Card LBP",
                min_value=0.0, step=10000.0, format="%.0f",
                key="dc_cclbp",
            )
        with col_rate:
            lbp_rate = st.number_input(
                "LBP Rate",
                value=int(cfg["lbp_rate"]),
                min_value=1000, step=1000,
                key="dc_lbprate",
                help="LBP per 1 USD. Defaults to branch config; override only if needed.",
            )
        cc_lbp_usd = (cc_lbp / lbp_rate) if lbp_rate > 0 else 0.0
        st.caption(f"💱 LBP cards converted: **{cc_lbp_usd:,.2f} USD** at rate {lbp_rate:,}")
    else:
        col_cu = st.columns(1)[0]
        with col_cu:
            cc_usd = st.number_input(
                "Credit Card USD",
                min_value=0.0, step=10.0, format="%.2f",
                key="dc_ccusd",
            )
        cc_lbp = 0.0
        cc_lbp_usd = 0.0
        lbp_rate = int(cfg["lbp_rate"])

    # ── Third-party delivery ──────────────────────────────────────────────────
    if cfg["third_party_enabled"]:
        third_party = st.number_input(
            f"📦 {cfg['third_party_label']} (USD)",
            min_value=0.0, step=10.0, format="%.2f",
            key="dc_3p",
            help=f"Total revenue from {cfg['third_party_label']} for this day.",
        )
    else:
        third_party = 0.0

    # ── On Account ────────────────────────────────────────────────────────────
    on_account = st.number_input(
        "On Account / Credit Sales",
        min_value=0.0, step=10.0, format="%.2f",
        key="dc_onacc",
        help="Sales recorded as credit / not yet collected.",
    )

    # ── Mgt Fees ──────────────────────────────────────────────────────────────
    if cfg["mgt_fees_enabled"]:
        mgt_fees = st.number_input(
            "💼 Management Fees (USD)",
            min_value=0.0, step=1.0, format="%.2f",
            key="dc_mgt",
            help="Daily management fee (EK consulting).",
        )
    else:
        mgt_fees = 0.0

    # ══════════════════════════════════════════════════════════════════════════
    # LIVE MATH — Closing Balance & Variance
    # ══════════════════════════════════════════════════════════════════════════
    # Total accounted for = cash + cc_usd + cc_lbp_usd + third_party + on_account + expenses
    accounted = cash_val + cc_usd + cc_lbp_usd + third_party + on_account + exp_val
    closing_balance_usd = accounted  # what was reported in
    over_short = accounted - main_reading  # vs expected POS reading

    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Accounted", f"{accounted:,.2f}")
    m2.metric("Closing Balance (USD)", f"{closing_balance_usd:,.2f}")
    m3.metric("Over / Short", f"{over_short:+,.2f}",
              delta=f"{over_short:+,.2f}", delta_color="normal")

    # Optional notes
    notes = st.text_area("📝 Notes (optional)",
                          placeholder="Anything noteworthy about today's reconciliation…",
                          key="dc_notes", height=80)

    # ══════════════════════════════════════════════════════════════════════════
    # SUBMIT — with duplicate check & confirmation flow
    # ══════════════════════════════════════════════════════════════════════════
    st.divider()

    if "dc_confirm_dup" not in st.session_state:
        st.session_state["dc_confirm_dup"] = False

    submission = {
        # ── identifiers
        "date": str(entry_date),
        "client_name": final_client,
        "outlet": final_outlet,
        "reported_by": user,
        # ── new universal fields (Phase 1 schema)
        "sales_ht": round(sales_ht, 2),
        "vat": round(vat_amount, 2),
        "third_party": round(third_party, 2),
        "credit_card_usd": round(cc_usd, 2),
        "credit_card_lbp": round(cc_lbp, 2),
        "cc_lbp_to_usd": round(cc_lbp_usd, 2),
        "closing_balance_usd": round(closing_balance_usd, 2),
        "lbp_rate": int(lbp_rate),
        "mgt_fees": round(mgt_fees, 2),
        "form_config": cfg,  # snapshot of toggles at submission time
        "notes": notes.strip() or None,
        # ── legacy columns (kept for backwards-compat with any old reports)
        "main_reading": round(main_reading, 2),
        "cash": round(cash_val, 2),
        "visa": round(cc_usd + cc_lbp_usd, 2),  # combined card revenue in USD
        "expenses": round(exp_val, 2),
        "on_account": round(on_account, 2),
        "revenue": round(accounted, 2),
        "over_short": round(over_short, 2),
    }

    # ── Confirmation flow for duplicates ──────────────────────────────────────
    if st.session_state["dc_confirm_dup"]:
        st.warning(f"⚠️ A report already exists for **{final_outlet}** "
                   f"on **{entry_date}**. Submit anyway?")
        c_yes, c_no = st.columns(2)
        with c_yes:
            if st.button("Yes, submit anyway", type="primary",
                         use_container_width=True, key="dc_dup_yes"):
                _do_insert(supabase, submission, final_outlet, over_short)
                st.session_state["dc_confirm_dup"] = False
        with c_no:
            if st.button("Cancel", use_container_width=True, key="dc_dup_no"):
                st.session_state["dc_confirm_dup"] = False
                st.rerun()
    else:
        if st.button("🚀 Submit Daily Report", type="primary",
                     use_container_width=True, key="dc_submit"):
            try:
                existing = (supabase.table("daily_cash").select("id")
                            .eq("date", str(entry_date))
                            .eq("outlet", final_outlet)
                            .execute())
                if existing.data:
                    st.session_state["dc_confirm_dup"] = True
                    st.rerun()
                else:
                    _do_insert(supabase, submission, final_outlet, over_short)
            except Exception as e:
                st.error(f"❌ Database error: {e}")


def _do_insert(supabase, submission, final_outlet, over_short):
    try:
        supabase.table("daily_cash").insert([submission]).execute()
        st.success(f"✅ Saved for {final_outlet} — Variance: {over_short:+,.2f}")
        st.balloons()
    except Exception as e:
        st.error(f"❌ Insert failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS TAB
# ══════════════════════════════════════════════════════════════════════════════

def _render_reports(supabase, role, sidebar_client, sidebar_outlet):
    st.markdown("##### 📈 Cash Reports")

    is_admin = str(role).lower() in ("admin", "admin_all")

    # ── Filter selectors (admins can override sidebar) ────────────────────────
    if is_admin:
        col_c, col_o = st.columns(2)
        with col_c:
            client_opts = ["All"] + get_all_clients()
            rep_client = st.selectbox("🏢 Client", client_opts, key="dcrep_client")
        with col_o:
            outlet_opts = (["All"] + get_outlets_for_client(rep_client)
                           if rep_client != "All" else ["All"])
            rep_outlet = st.selectbox("🏠 Outlet", outlet_opts, key="dcrep_outlet")
    else:
        rep_client = sidebar_client
        rep_outlet = sidebar_outlet

    # ── Timeframe presets ─────────────────────────────────────────────────────
    today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
    timeframe = st.radio(
        "Timeframe",
        ["Today", "Month-to-date", "Year-to-date", "Custom range"],
        horizontal=True, key="dcrep_tf",
    )
    if timeframe == "Today":
        start_d, end_d = today, today
    elif timeframe == "Month-to-date":
        start_d, end_d = today.replace(day=1), today
    elif timeframe == "Year-to-date":
        start_d, end_d = today.replace(month=1, day=1), today
    else:
        dr = st.date_input("Pick range",
                            value=(today - timedelta(days=30), today),
                            max_value=today, key="dcrep_range")
        if len(dr) != 2:
            st.info("Pick both a start and end date.")
            return
        start_d, end_d = dr

    # ── Query ─────────────────────────────────────────────────────────────────
    q = (supabase.table("daily_cash").select("*")
         .gte("date", str(start_d))
         .lte("date", str(end_d))
         .order("date", desc=True)
         .limit(5000))

    if str(rep_client).lower() not in ("all", "", "none"):
        q = q.eq("client_name", rep_client)
    if str(rep_outlet).lower() not in ("all", "", "none"):
        q = q.eq("outlet", rep_outlet)

    res = q.execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()

    if df.empty:
        st.info("No cash reports found for this period.")
        return

    # ── Aggregated metrics ────────────────────────────────────────────────────
    money_cols = ["main_reading", "sales_ht", "vat", "revenue", "expenses",
                  "third_party", "credit_card_usd", "cc_lbp_to_usd",
                  "closing_balance_usd", "over_short", "mgt_fees"]
    for c in money_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    total_rev = df["revenue"].sum() if "revenue" in df.columns else 0
    total_exp = df["expenses"].sum() if "expenses" in df.columns else 0
    total_var = df["over_short"].sum() if "over_short" in df.columns else 0
    total_vat = df["vat"].sum() if "vat" in df.columns else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Revenue", f"{total_rev:,.2f}")
    m2.metric("Total Expenses", f"{total_exp:,.2f}")
    m3.metric("Total VAT", f"{total_vat:,.2f}")
    delta_color = "normal" if abs(total_var) < 1 else "inverse"
    m4.metric("Net Variance", f"{total_var:+,.2f}",
              delta=f"{total_var:+,.2f}", delta_color=delta_color)

    st.write("###")

    # ── Display table ─────────────────────────────────────────────────────────
    drop_cols = [c for c in ("id", "created_at", "form_config") if c in df.columns]
    df_show = df.drop(columns=drop_cols).copy()
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.caption(f"{len(df_show)} entries · {start_d} → {end_d}")

    # ── CSV download ──────────────────────────────────────────────────────────
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Download CSV",
        data=csv_bytes,
        file_name=f"DailyCash_{start_d}_{end_d}.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )