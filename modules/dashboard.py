import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from modules.nav_helper import get_nav_data
import plotly.express as px
import plotly.graph_objects as go

# ─────────────────────────────────────────────
# EK BRAND COLORS
# ─────────────────────────────────────────────
EK_DARK  = "#1B252C"
EK_SAND  = "#E3C5AD"
EK_RED   = "#ff4b4b"
EK_GREEN = "#2ecc71"
CHART_BG = "rgba(0,0,0,0)"

PERIOD_COLORS = [
    "#E3C5AD", "#7EB8C9", "#E8A87C", "#85C1AE",
    "#C39BD3", "#F1948A", "#82E0AA", "#F8C471",
]

# ─────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def _to_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _chart_layout(fig, **kwargs):
    fig.update_layout(
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        margin=dict(l=0, r=0, t=30, b=0),
        font=dict(color=EK_SAND),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        **kwargs,
    )
    return fig


def _fmt(val, decimals=2):
    try:
        return f"{val:,.{decimals}f}"
    except Exception:
        return str(val)


# ─────────────────────────────────────────────
# BRANCH RESOLUTION
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def _get_branches_for_client(client_name: str):
    sb = get_supabase()
    res = sb.table("branches").select("id, outlet, client_name").eq("client_name", client_name).execute()
    return res.data or []


@st.cache_data(ttl=300)
def _get_all_clients():
    sb = get_supabase()
    res = sb.table("clients").select("id, client_name").eq("status", "active").order("client_name").execute()
    return res.data or []


@st.cache_data(ttl=300)
def _get_ac_periods(branch_ids: tuple):
    if not branch_ids:
        return []
    sb = get_supabase()
    res = sb.table("ac_cogs").select("report_date").in_("branch_id", list(branch_ids)).execute()
    if not res.data:
        return []
    dates = sorted(set(r["report_date"] for r in res.data if r.get("report_date")), reverse=True)
    return dates


def _label_period(date_str: str) -> str:
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%B %Y")
    except Exception:
        return date_str


# ─────────────────────────────────────────────
# LIVE DATA FETCHERS
# ─────────────────────────────────────────────
def _live_query(table, client_name, outlet, start, end, limit=5000):
    sb = get_supabase()
    q = sb.table(table).select("*").gte("date", str(start)).lte("date", str(end))
    if client_name and client_name != "All":
        q = q.ilike("client_name", f"%{client_name}%")
    if outlet and outlet != "All":
        q = q.ilike("outlet", f"%{outlet}%")
    return pd.DataFrame(q.limit(limit).execute().data or [])


# ─────────────────────────────────────────────
# AC DATA FETCHERS
# ─────────────────────────────────────────────
def _ac_query(table, branch_ids: list, report_date: str, limit=10000):
    sb = get_supabase()
    q = sb.table(table).select("*").in_("branch_id", branch_ids).eq("report_date", report_date)
    return pd.DataFrame(q.limit(limit).execute().data or [])


def _ac_query_multi(table, branch_ids: list, report_dates: list, limit=20000):
    sb = get_supabase()
    frames = []
    for rd in report_dates:
        q = sb.table(table).select("*").in_("branch_id", branch_ids).eq("report_date", rd)
        df = pd.DataFrame(q.limit(limit).execute().data or [])
        if not df.empty:
            df["period_label"] = _label_period(rd)
            df["report_date"]  = rd
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()


# ═══════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═══════════════════════════════════════════════════════════════════
def render_dashboard(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 📈 Executive Operations Dashboard")
    supabase = get_supabase()

    try:
        user_role     = role.lower()
        is_admin      = user_role in ("admin", "admin_all")
        clean_client  = str(assigned_client).strip().title()
        clean_outlet  = str(assigned_outlet).strip().title()
        locked_client = clean_client.lower() not in ("all", "", "none", "nan")
        locked_outlet = clean_outlet.lower() not in ("all", "", "none", "nan")

        # ══════════════════════════════════════════
        # SIDEBAR — scope only (client + outlet)
        # ══════════════════════════════════════════
        st.sidebar.markdown("### 📍 Scope")

        if locked_client:
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Client:** {final_client}")
        else:
            all_clients = _get_all_clients()
            c_names = [c["client_name"] for c in all_clients]
            sel = st.sidebar.selectbox("🏢 Select Client", ["All Clients"] + c_names, key="dash_client")
            final_client = "All" if sel == "All Clients" else sel

        if final_client != "All":
            branches_data = _get_branches_for_client(final_client)
            outlet_names  = [b["outlet"] for b in branches_data]
            branch_id_map = {b["outlet"]: b["id"] for b in branches_data}
        else:
            branches_data, outlet_names, branch_id_map = [], [], {}

        if locked_outlet:
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if outlet_names:
                if len(outlet_names) > 1:
                    consolidate = st.sidebar.checkbox("🔀 Consolidate all branches", value=True, key="dash_consolidate")
                    if consolidate:
                        final_outlet = "All"
                        st.sidebar.caption(f"Showing: {', '.join(outlet_names)}")
                    else:
                        sel_o = st.sidebar.selectbox("🏠 Select Outlet", outlet_names, key="dash_outlet")
                        final_outlet = sel_o
                else:
                    final_outlet = outlet_names[0]
                    st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
            else:
                final_outlet = "All"

        if final_outlet == "All":
            active_branch_ids = list(branch_id_map.values())
        else:
            bid = branch_id_map.get(final_outlet)
            active_branch_ids = [bid] if bid else []

        # ── Exchange rate ─────────────────────────────────────────────
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💱 Exchange Rate")
        lbp_rate = st.sidebar.number_input(
            "LBP / USD", min_value=1000, max_value=500000,
            value=89500, step=500, key="dash_lbp_rate",
            help="Used to convert LBP invoices to USD. Default: 89,500"
        )

        # ══════════════════════════════════════════
        # MAIN AREA — DATA SOURCE TOGGLE (inline)
        # ══════════════════════════════════════════
        today         = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
        ac_periods    = _get_ac_periods(tuple(active_branch_ids)) if active_branch_ids else []
        date_to_label = {d: _label_period(d) for d in ac_periods}
        label_to_date = {v: k for k, v in date_to_label.items()}

        toggle_col, filter_col = st.columns([2, 3])

        with toggle_col:
            mode = st.radio(
                "Data source",
                ["🟢 Live", "📋 Report Period"],
                horizontal=True,
                key="dash_mode",
                label_visibility="collapsed",
            )

        is_live = mode == "🟢 Live"

        with filter_col:
            if is_live:
                default_start = today - timedelta(days=30)
                date_range = st.date_input(
                    "Date Range", value=(default_start, today),
                    max_value=today, key="dash_daterange",
                    label_visibility="collapsed",
                )
                if len(date_range) != 2:
                    st.warning("Please select both a start and end date.")
                    return
                start_date, end_date = date_range
                selected_dates = []
            else:
                if ac_periods:
                    available_labels = [date_to_label[d] for d in ac_periods]
                    selected_labels  = st.multiselect(
                        "Select period(s)", available_labels,
                        default=[available_labels[0]],
                        key="dash_periods",
                        label_visibility="collapsed",
                        placeholder="Select one or more periods…",
                    )
                    selected_dates = [label_to_date[l] for l in selected_labels if l in label_to_date]
                else:
                    st.info("No report periods available for this client.")
                    selected_dates = []
                start_date = end_date = None

        multi_period = not is_live and len(selected_dates) > 1

        # ── Header strip ──────────────────────────────────────────────
        st.divider()
        outlet_label = final_outlet if final_outlet != "All" else "All Branches"
        if is_live:
            mode_label = f"Live · {start_date} → {end_date}"
        elif selected_dates:
            mode_label = "Report Period · " + ", ".join(date_to_label[d] for d in selected_dates)
        else:
            mode_label = "Report Period"
        st.markdown(f"**{final_client}** · {outlet_label} · _{mode_label}_")
        st.divider()

        # ══════════════════════════════════════════
        # FETCH DATA
        # ══════════════════════════════════════════
        with st.spinner("⏳ Loading dashboard data..."):

            if is_live:
                df_cash  = _live_query("daily_cash",     final_client, final_outlet, start_date, end_date)
                df_waste = _live_query("waste_logs",     final_client, final_outlet, start_date, end_date)
                df_inv   = _live_query("inventory_logs", final_client, final_outlet, start_date, end_date)
                _iq = (
                    supabase.table("invoices_log").select("*")
                    .gte("created_at", str(start_date))
                    .lte("created_at", str(end_date) + "T23:59:59")
                )
                if final_client != "All":
                    _iq = _iq.ilike("client_name", f"%{final_client}%")
                if final_outlet != "All":
                    _iq = _iq.ilike("outlet", f"%{final_outlet}%")
                df_purch = pd.DataFrame(_iq.limit(5000).execute().data or [])
                df_ac_waste = df_ac_sales = df_ac_cogs = df_ac_inv = df_ac_purch = pd.DataFrame()

            else:
                df_cash = df_waste = df_inv = df_purch = pd.DataFrame()
                if active_branch_ids and selected_dates:
                    if multi_period:
                        df_ac_waste = _ac_query_multi("ac_waste_inventory", active_branch_ids, selected_dates)
                        df_ac_sales = _ac_query_multi("ac_sales",           active_branch_ids, selected_dates)
                        df_ac_cogs  = _ac_query_multi("ac_cogs",            active_branch_ids, selected_dates)
                        df_ac_inv   = _ac_query_multi("ac_ending",          active_branch_ids, selected_dates)
                        df_ac_purch = _ac_query_multi("ac_purchase",        active_branch_ids, selected_dates)
                    else:
                        rd = selected_dates[0]
                        df_ac_waste = _ac_query("ac_waste_inventory", active_branch_ids, rd)
                        df_ac_sales = _ac_query("ac_sales",           active_branch_ids, rd)
                        df_ac_cogs  = _ac_query("ac_cogs",            active_branch_ids, rd)
                        df_ac_inv   = _ac_query("ac_ending",          active_branch_ids, rd)
                        df_ac_purch = _ac_query("ac_purchase",        active_branch_ids, rd)
                        for df in (df_ac_waste, df_ac_sales, df_ac_cogs, df_ac_inv, df_ac_purch):
                            if not df.empty:
                                df["period_label"] = date_to_label.get(rd, rd)
                else:
                    df_ac_waste = df_ac_sales = df_ac_cogs = df_ac_inv = df_ac_purch = pd.DataFrame()

        # ══════════════════════════════════════════
        # KPI RIBBON
        # ══════════════════════════════════════════
        st.markdown("##### 🏆 Performance Snapshot")
        k1, k2, k3, k4, k5 = st.columns(5)

        if is_live:
            total_rev   = _to_num(df_cash["revenue"]).sum()    if (not df_cash.empty  and "revenue"    in df_cash.columns)  else 0.0
            total_var   = _to_num(df_cash["over_short"]).sum() if (not df_cash.empty  and "over_short" in df_cash.columns)  else 0.0
            waste_qty   = _to_num(df_waste["qty"]).sum()       if (not df_waste.empty and "qty"        in df_waste.columns) else 0.0
            inv_count   = len(df_inv) if not df_inv.empty else 0
            total_purch_usd = 0.0
            if not df_purch.empty and "total_amount" in df_purch.columns:
                df_purch["total_amount"] = _to_num(df_purch["total_amount"])
                currency_col = "currency" if "currency" in df_purch.columns else None
                if currency_col:
                    usd_rows = df_purch[df_purch[currency_col].str.upper() == "USD"]["total_amount"].sum()
                    lbp_rows = df_purch[df_purch[currency_col].str.upper() == "LBP"]["total_amount"].sum()
                    total_purch_usd = usd_rows + (lbp_rows / lbp_rate)
                else:
                    total_purch_usd = df_purch["total_amount"].sum()

            k1.metric("💵 Revenue",       _fmt(total_rev))
            var_color = "normal" if total_var >= 0 else "inverse"
            k2.metric("⚖️ Cash Variance", _fmt(total_var), delta=_fmt(total_var), delta_color=var_color)
            k3.metric("🗑️ Waste (Qty)",   _fmt(waste_qty, decimals=0))
            k4.metric("📋 Inv. Counts",   f"{inv_count:,}")
            k5.metric("🛒 Purchases",     f"$ {_fmt(total_purch_usd)}" if total_purch_usd else "—")

        else:
            gross_sales = _to_num(df_ac_cogs["gross_sales"]).sum() if (not df_ac_cogs.empty and "gross_sales" in df_ac_cogs.columns) else 0.0
            discount    = _to_num(df_ac_cogs["discount"]).sum()    if (not df_ac_cogs.empty and "discount"    in df_ac_cogs.columns) else 0.0
            cost_pct    = None
            if not df_ac_cogs.empty:
                net_sales = _to_num(df_ac_cogs["net_sales"]).sum() if "net_sales" in df_ac_cogs.columns else 0.0
                net_cogs  = _to_num(df_ac_cogs["net_cogs"]).sum()  if "net_cogs"  in df_ac_cogs.columns else 0.0
                if net_sales > 0:
                    cost_pct = (net_cogs / net_sales) * 100
            waste_cost  = _to_num(df_ac_waste["total_cost"]).sum() if (not df_ac_waste.empty and "total_cost" in df_ac_waste.columns) else 0.0
            total_purch = _to_num(df_ac_purch["total_cost"]).sum() if (not df_ac_purch.empty and "total_cost" in df_ac_purch.columns) else 0.0

            k1.metric("💵 Gross Sales", _fmt(gross_sales))
            k2.metric("🏷️ Discount",   _fmt(discount))
            k3.metric("📊 Net Cost %",  f"{cost_pct:.1f}%" if cost_pct is not None else "—")
            k4.metric("🗑️ Waste Cost", _fmt(waste_cost))
            k5.metric("🛒 Purchases",  _fmt(total_purch))

        st.divider()

        # ══════════════════════════════════════════
        # WIDGET 1 — TOP 5 WASTE  |  WIDGET 2 — SALES
        # ══════════════════════════════════════════
        w_col1, w_col2 = st.columns(2)

        with w_col1:
            st.markdown("##### 🚨 Top 5 Waste Items")
            if is_live:
                if not df_waste.empty and "item_name" in df_waste.columns and "qty" in df_waste.columns:
                    df_waste["qty"] = _to_num(df_waste["qty"])
                    top5 = df_waste.groupby("item_name")["qty"].sum().reset_index().sort_values("qty", ascending=False).head(5)
                    fig = px.bar(top5, x="qty", y="item_name", orientation="h", text_auto=".0f")
                    fig.update_traces(marker_color=EK_RED)
                    fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Qty", yaxis_title="")
                    st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.success("✅ No waste logged for this period.")
            else:
                if not df_ac_waste.empty and "product_description" in df_ac_waste.columns:
                    df_ac_waste["total_cost"] = _to_num(df_ac_waste["total_cost"]) if "total_cost" in df_ac_waste.columns else 0.0
                    df_ac_waste["qty"]        = _to_num(df_ac_waste["qty"])        if "qty"        in df_ac_waste.columns else 0.0
                    if multi_period:
                        top5_items = df_ac_waste.groupby("product_description")["total_cost"].sum().nlargest(5).index.tolist()
                        grp = (
                            df_ac_waste[df_ac_waste["product_description"].isin(top5_items)]
                            .groupby(["product_description", "period_label"])["total_cost"].sum().reset_index()
                        )
                        grp.columns = ["Item", "Period", "Total Cost"]
                        fig = px.bar(grp, x="Total Cost", y="Item", color="Period",
                                     orientation="h", barmode="group", text_auto=".0f",
                                     color_discrete_sequence=PERIOD_COLORS)
                        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Cost", yaxis_title="")
                    else:
                        top5_ac = (
                            df_ac_waste.groupby("product_description")
                            .agg(total_cost=("total_cost", "sum"), qty=("qty", "sum"))
                            .reset_index().sort_values("total_cost", ascending=False).head(5)
                        )
                        top5_ac.columns = ["Item", "Total Cost", "Qty"]
                        fig = px.bar(top5_ac, x="Total Cost", y="Item", orientation="h",
                                     text_auto=".0f", hover_data=["Qty"])
                        fig.update_traces(marker_color=EK_RED)
                        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Cost", yaxis_title="")
                    st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.success("✅ No waste data for this period.")

        with w_col2:
            st.markdown("##### 💵 Sales Summary")
            if is_live:
                if not df_cash.empty:
                    for col in ("revenue", "cash", "visa"):
                        if col in df_cash.columns:
                            df_cash[col] = _to_num(df_cash[col])
                    trend = df_cash.groupby("date")[
                        [c for c in ("revenue", "cash", "visa") if c in df_cash.columns]
                    ].sum().reset_index().sort_values("date")
                    if "revenue" in trend.columns:
                        fig = px.area(trend, x="date", y="revenue", markers=True)
                        fig.update_traces(line_color=EK_SAND, fill="tozeroy", fillcolor="rgba(227,197,173,0.15)")
                        fig.update_layout(xaxis_title="", yaxis_title="Revenue")
                        st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.info("No sales data logged for this period.")
            else:
                if not df_ac_sales.empty and "description" in df_ac_sales.columns:
                    df_ac_sales["gross_sales"] = _to_num(df_ac_sales["gross_sales"]) if "gross_sales" in df_ac_sales.columns else 0.0
                    if multi_period:
                        top8_items = df_ac_sales.groupby("description")["gross_sales"].sum().nlargest(8).index.tolist()
                        grp = (
                            df_ac_sales[df_ac_sales["description"].isin(top8_items)]
                            .groupby(["description", "period_label"])["gross_sales"].sum().reset_index()
                        )
                        grp.columns = ["Item", "Period", "Gross Sales"]
                        fig = px.bar(grp, x="Gross Sales", y="Item", color="Period",
                                     orientation="h", barmode="group", text_auto=".0f",
                                     color_discrete_sequence=PERIOD_COLORS)
                        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Gross Sales", yaxis_title="")
                    else:
                        top_items = (
                            df_ac_sales.groupby("description")["gross_sales"].sum()
                            .reset_index().sort_values("gross_sales", ascending=False).head(8)
                        )
                        fig = px.bar(top_items, x="gross_sales", y="description", orientation="h", text_auto=".0f")
                        fig.update_traces(marker_color=EK_SAND)
                        fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Gross Sales", yaxis_title="")
                    st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.info("No sales data for this period.")

        st.divider()

        # ══════════════════════════════════════════
        # WIDGET 3 — COST % BREAKDOWN
        # ══════════════════════════════════════════
        st.markdown("##### 📊 Cost % Breakdown")

        if is_live:
            c1, c2 = st.columns(2)
            with c1:
                if not df_cash.empty and "over_short" in df_cash.columns and "date" in df_cash.columns:
                    var_trend = df_cash.groupby("date")["over_short"].sum().reset_index().sort_values("date")
                    fig_var = px.bar(var_trend, x="date", y="over_short", title="Daily Cash Variance")
                    fig_var.update_traces(marker_color=[EK_GREEN if v >= 0 else EK_RED for v in var_trend["over_short"]])
                    fig_var.update_layout(xaxis_title="", yaxis_title="Amount")
                    st.plotly_chart(_chart_layout(fig_var), use_container_width=True)
                else:
                    st.info("No cash data for this period.")
            with c2:
                st.info("💡 Flash food cost will be available once daily invoice entry is active for this outlet.")
        else:
            if not df_ac_cogs.empty and "category" in df_ac_cogs.columns:
                df_ac_cogs["net_sales"]   = _to_num(df_ac_cogs["net_sales"])   if "net_sales"   in df_ac_cogs.columns else 0.0
                df_ac_cogs["net_cogs"]    = _to_num(df_ac_cogs["net_cogs"])    if "net_cogs"    in df_ac_cogs.columns else 0.0
                df_ac_cogs["gross_sales"] = _to_num(df_ac_cogs["gross_sales"]) if "gross_sales" in df_ac_cogs.columns else 0.0
                c1, c2 = st.columns(2)
                with c1:
                    if multi_period:
                        trend_data = (
                            df_ac_cogs[df_ac_cogs["net_sales"] > 0]
                            .groupby(["period_label", "category"])
                            .agg(net_sales=("net_sales","sum"), net_cogs=("net_cogs","sum"))
                            .reset_index()
                        )
                        trend_data["cost_pct"] = (trend_data["net_cogs"] / trend_data["net_sales"] * 100).round(1)
                        period_order = [date_to_label[d] for d in sorted(selected_dates)]
                        trend_data["period_label"] = pd.Categorical(trend_data["period_label"], categories=period_order, ordered=True)
                        fig_cat = px.line(trend_data.sort_values("period_label"), x="period_label", y="cost_pct",
                                          color="category", markers=True, title="Cost % Trend by Category",
                                          color_discrete_sequence=PERIOD_COLORS)
                        fig_cat.update_layout(xaxis_title="", yaxis_title="Cost %")
                    else:
                        cat_data = df_ac_cogs[df_ac_cogs["net_sales"] > 0].copy()
                        if not cat_data.empty:
                            cat_data["cost_pct"] = (cat_data["net_cogs"] / cat_data["net_sales"] * 100).round(1)
                            fig_cat = px.bar(cat_data.sort_values("cost_pct", ascending=False),
                                             x="category", y="cost_pct", text_auto=".1f",
                                             title="Net Cost % by Category")
                            fig_cat.update_traces(marker_color=EK_SAND, texttemplate="%{text}%", textposition="outside")
                            fig_cat.update_layout(xaxis_title="", yaxis_title="Cost %",
                                                  yaxis_range=[0, cat_data["cost_pct"].max() * 1.2])
                        else:
                            st.info("No cost % data available.")
                            fig_cat = None
                    if "fig_cat" in dir() and fig_cat is not None:
                        st.plotly_chart(_chart_layout(fig_cat), use_container_width=True)
                with c2:
                    if multi_period:
                        pnl_trend = (
                            df_ac_cogs.groupby("period_label")
                            .agg(gross_sales=("gross_sales","sum"), net_cogs=("net_cogs","sum"))
                            .reset_index()
                        )
                        period_order = [date_to_label[d] for d in sorted(selected_dates)]
                        pnl_trend["period_label"] = pd.Categorical(pnl_trend["period_label"], categories=period_order, ordered=True)
                        pnl_trend = pnl_trend.sort_values("period_label")
                        fig_pnl = go.Figure()
                        fig_pnl.add_bar(x=pnl_trend["period_label"], y=pnl_trend["gross_sales"], name="Gross Sales", marker_color=EK_SAND)
                        fig_pnl.add_bar(x=pnl_trend["period_label"], y=pnl_trend["net_cogs"],    name="Net COGS",    marker_color=EK_RED)
                        fig_pnl.update_layout(barmode="group", title="Sales vs COGS by Period", xaxis_title="", yaxis_title="Amount")
                        st.plotly_chart(_chart_layout(fig_pnl), use_container_width=True)
                    else:
                        disc   = _to_num(df_ac_cogs["discount"]).sum() if "discount" in df_ac_cogs.columns else 0.0
                        w_cost = _to_num(df_ac_cogs["waste"]).sum()    if "waste"    in df_ac_cogs.columns else 0.0
                        summary_df = pd.DataFrame({
                            "Item":  ["Gross Sales", "Discount", "Net Sales", "Net COGS", "Waste"],
                            "Value": [df_ac_cogs["gross_sales"].sum(), -abs(disc),
                                      df_ac_cogs["net_sales"].sum(), -abs(df_ac_cogs["net_cogs"].sum()), -abs(w_cost)],
                        })
                        fig_sum = px.bar(summary_df, x="Item", y="Value", text_auto=".0f", title="Period P&L Summary")
                        fig_sum.update_traces(
                            marker_color=[EK_SAND if v >= 0 else EK_RED for v in summary_df["Value"]],
                            textposition="outside"
                        )
                        fig_sum.update_layout(xaxis_title="", yaxis_title="Amount")
                        st.plotly_chart(_chart_layout(fig_sum), use_container_width=True)
            else:
                st.info("No COGS data for this period.")

        st.divider()

        # ══════════════════════════════════════════
        # WIDGET 4 — INVENTORY  |  WIDGET 5 — PURCHASES
        # ══════════════════════════════════════════
        inv_col, purch_col = st.columns(2)

        with inv_col:
            st.markdown("##### 📦 Inventory")
            if is_live:
                if not df_inv.empty and "item_name" in df_inv.columns:
                    st.caption(f"{len(df_inv):,} count records in selected period.")
                    show_cols = [c for c in ("date", "outlet", "item_name", "quantity") if c in df_inv.columns]
                    st.dataframe(df_inv[show_cols].sort_values("date", ascending=False).head(50),
                                 use_container_width=True, hide_index=True, height=350)
                else:
                    st.info("No inventory counts logged for this period.")
            else:
                if not df_ac_inv.empty and "product_description" in df_ac_inv.columns:
                    df_ac_inv["total_cost"] = _to_num(df_ac_inv["total_cost"]) if "total_cost" in df_ac_inv.columns else 0.0
                    if multi_period:
                        inv_trend = df_ac_inv.groupby("period_label")["total_cost"].sum().reset_index()
                        inv_trend.columns = ["Period", "Ending Value"]
                        period_order = [date_to_label[d] for d in sorted(selected_dates)]
                        inv_trend["Period"] = pd.Categorical(inv_trend["Period"], categories=period_order, ordered=True)
                        fig_inv = px.bar(inv_trend.sort_values("Period"), x="Period", y="Ending Value",
                                         text_auto=".0f", title="Ending Inventory Value by Period")
                        fig_inv.update_traces(marker_color=EK_SAND)
                        fig_inv.update_layout(xaxis_title="", yaxis_title="Value")
                        st.plotly_chart(_chart_layout(fig_inv), use_container_width=True)
                    else:
                        top_inv = (
                            df_ac_inv.groupby("product_description")["total_cost"].sum()
                            .reset_index().sort_values("total_cost", ascending=False).head(10)
                        )
                        top_inv.columns = ["Item", "Ending Value"]
                        st.caption(f"Total ending inventory value: **{_fmt(df_ac_inv['total_cost'].sum())}**")
                        top_inv["Ending Value"] = top_inv["Ending Value"].map(lambda x: f"{x:,.2f}")
                        st.dataframe(top_inv, use_container_width=True, hide_index=True)
                else:
                    st.info("No ending inventory data for this period.")

        with purch_col:
            st.markdown("##### 🛒 Purchases")
            if is_live:
                if not df_purch.empty:
                    amt_col = next((c for c in ("total_amount", "amount", "total", "net_amount") if c in df_purch.columns), None)
                    if amt_col:
                        df_purch[amt_col] = _to_num(df_purch[amt_col])
                        # Convert to USD using sidebar rate
                        if "currency" in df_purch.columns:
                            usd_sum = df_purch[df_purch["currency"].str.upper() == "USD"][amt_col].sum()
                            lbp_sum = df_purch[df_purch["currency"].str.upper() == "LBP"][amt_col].sum()
                            total_p_usd = usd_sum + (lbp_sum / lbp_rate)
                            lbp_count   = int((df_purch["currency"].str.upper() == "LBP").sum())
                            usd_count   = int((df_purch["currency"].str.upper() == "USD").sum())
                            st.caption(
                                f"Total: **$ {_fmt(total_p_usd)}** USD equiv. across {len(df_purch):,} invoices "
                                f"({usd_count} USD · {lbp_count} LBP @ {lbp_rate:,})"
                            )
                        else:
                            total_p_usd = df_purch[amt_col].sum()
                            st.caption(f"Total invoices logged: **{_fmt(total_p_usd)}** across {len(df_purch):,} records")
                        # invoices_log uses created_at not date
                        sort_col = "created_at" if "created_at" in df_purch.columns else (next((c for c in ("date",) if c in df_purch.columns), None))
                        show_cols = [c for c in ("created_at", "date", "supplier_name", "invoice_number", amt_col, "currency", "outlet") if c in df_purch.columns]
                        df_show = df_purch[show_cols].sort_values(sort_col, ascending=False).head(50) if sort_col else df_purch[show_cols].head(50)
                        st.dataframe(df_show, use_container_width=True, hide_index=True, height=350)
                    else:
                        st.dataframe(df_purch.head(10), use_container_width=True, hide_index=True)
                else:
                    st.info("No invoices logged for this period.")
            else:
                if not df_ac_purch.empty and "raw_materials" in df_ac_purch.columns:
                    df_ac_purch["total_cost"] = _to_num(df_ac_purch["total_cost"]) if "total_cost" in df_ac_purch.columns else 0.0
                    if multi_period:
                        purch_trend = df_ac_purch.groupby("period_label")["total_cost"].sum().reset_index()
                        purch_trend.columns = ["Period", "Total Cost"]
                        period_order = [date_to_label[d] for d in sorted(selected_dates)]
                        purch_trend["Period"] = pd.Categorical(purch_trend["Period"], categories=period_order, ordered=True)
                        fig_p = px.bar(purch_trend.sort_values("Period"), x="Period", y="Total Cost",
                                       text_auto=".0f", title="Total Purchases by Period")
                        fig_p.update_traces(marker_color=EK_SAND)
                        fig_p.update_layout(xaxis_title="", yaxis_title="Cost")
                        st.plotly_chart(_chart_layout(fig_p), use_container_width=True)
                    else:
                        top_purch = (
                            df_ac_purch.groupby("raw_materials")["total_cost"].sum()
                            .reset_index().sort_values("total_cost", ascending=False).head(10)
                        )
                        top_purch.columns = ["Raw Material", "Total Cost"]
                        st.caption(f"Total purchases: **{_fmt(df_ac_purch['total_cost'].sum())}** across {len(df_ac_purch):,} line items")
                        top_purch["Total Cost"] = top_purch["Total Cost"].map(lambda x: f"{x:,.2f}")
                        st.dataframe(top_purch, use_container_width=True, hide_index=True)
                else:
                    st.info("No purchase data for this period.")

        # ══════════════════════════════════════════
        # EXCEPTIONS — Live only
        # ══════════════════════════════════════════
        if is_live:
            st.divider()
            st.markdown("##### ⚠️ Exceptions & Discrepancies")
            exc1, exc2 = st.columns(2)
            with exc1:
                st.markdown("**Cash Shortages**")
                if not df_cash.empty and "over_short" in df_cash.columns:
                    shortages = df_cash[df_cash["over_short"] < 0]
                    if not shortages.empty:
                        show = [c for c in ("date", "outlet", "over_short", "reported_by") if c in shortages.columns]
                        st.dataframe(shortages[show].sort_values("over_short").head(5),
                                     use_container_width=True, hide_index=True)
                    else:
                        st.success("All registers balanced! ✅")
                else:
                    st.caption("No cash data.")
            with exc2:
                st.markdown("**Largest Spoilage Events**")
                if not df_waste.empty and "qty" in df_waste.columns:
                    show = [c for c in ("date", "item_name", "qty", "remarks", "reported_by") if c in df_waste.columns]
                    st.dataframe(df_waste[show].sort_values("qty", ascending=False).head(5),
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No waste data.")

        # ══════════════════════════════════════════
        # EXPORT — Admin only
        # ══════════════════════════════════════════
        if is_admin:
            st.divider()
            st.markdown("### 📥 Deep-Dive Data Export")
            st.info("Download raw database logs for pivot analysis in Excel.")

            if is_live:
                export_options = {
                    "Waste Logs":     "waste_logs",
                    "Inventory Logs": "inventory_logs",
                    "Daily Cash":     "daily_cash",
                    "Invoices":       "invoices_log",
                }
            else:
                export_options = {
                    "AC Waste":       "ac_waste_inventory",
                    "AC Sales":       "ac_sales",
                    "AC COGS":        "ac_cogs",
                    "AC Ending Inv.": "ac_ending",
                    "AC Purchase":    "ac_purchase",
                    "AC Variance":    "ac_variance",
                }

            exp_col1, _ = st.columns([1, 2])
            with exp_col1:
                table_label = st.selectbox("Select Table", list(export_options.keys()), key="export_table_select")
            db_table = export_options[table_label]

            period_key = "_".join(selected_dates) if not is_live else f"{start_date}_{end_date}"
            fp_key = f"{db_table}|{final_client}|{final_outlet}|{period_key}"
            if st.session_state.get("export_fingerprint") != fp_key:
                for k in ("export_csv", "export_row_count", "export_file_name"):
                    st.session_state.pop(k, None)
                st.session_state["export_fingerprint"] = fp_key

            if st.button(f"🔍 Generate {table_label} Export", type="primary", key="export_generate_btn"):
                with st.spinner(f"Pulling {table_label}..."):
                    if is_live:
                        q = supabase.table(db_table).select("*") \
                            .gte("date", str(start_date)).lte("date", str(end_date))
                        if final_client != "All":
                            q = q.ilike("client_name", f"%{final_client}%")
                        if final_outlet != "All":
                            q = q.ilike("outlet", f"%{final_outlet}%")
                        df_exp = pd.DataFrame(q.limit(50000).execute().data or [])
                    else:
                        if active_branch_ids and selected_dates:
                            df_exp = _ac_query_multi(db_table, active_branch_ids, selected_dates, limit=50000)
                        else:
                            df_exp = pd.DataFrame()

                    if not df_exp.empty:
                        st.session_state["export_csv"]       = df_exp.to_csv(index=False).encode("utf-8")
                        st.session_state["export_row_count"] = len(df_exp)
                        st.session_state["export_file_name"] = f"{db_table}_{final_client}_{period_key}.csv"
                    else:
                        for k in ("export_csv", "export_row_count", "export_file_name"):
                            st.session_state.pop(k, None)
                        st.warning("No records found.")

            if st.session_state.get("export_csv") is not None:
                st.success(f"✅ {st.session_state['export_row_count']:,} records ready.")
                st.download_button(
                    label=f"💾 Download {table_label} as CSV",
                    data=st.session_state["export_csv"],
                    file_name=st.session_state["export_file_name"],
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key="export_download_btn",
                )

    except Exception as e:
        st.error(f"❌ Dashboard error: {e}")