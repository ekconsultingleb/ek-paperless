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
EK_DARK   = "#1B252C"   # PANTONE 433 C — charcoal navy
EK_SAND   = "#E3C5AD"   # PANTONE 4685 C — warm sand
EK_RED    = "#ff4b4b"
EK_GREEN  = "#2ecc71"
CHART_BG  = "rgba(0,0,0,0)"

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
        **kwargs,
    )
    return fig


def _fmt(val, prefix="", suffix="", decimals=2):
    try:
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    except Exception:
        return str(val)


# ─────────────────────────────────────────────
# BRANCH RESOLUTION
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def _get_branches_for_client(client_name: str):
    """Return list of (branch_id, outlet) for a given client_name."""
    sb = get_supabase()
    res = sb.table("branches").select("id, outlet, client_name").eq("client_name", client_name).execute()
    return res.data or []


@st.cache_data(ttl=300)
def _get_all_clients():
    sb = get_supabase()
    res = sb.table("clients").select("id, client_name").eq("status", "active").order("client_name").execute()
    return res.data or []


@st.cache_data(ttl=300)
def _get_ac_periods(branch_ids: list):
    """Return sorted list of distinct report_date strings from ac_cogs for given branch_ids."""
    if not branch_ids:
        return []
    sb = get_supabase()
    res = (
        sb.table("ac_cogs")
        .select("report_date")
        .in_("branch_id", branch_ids)
        .execute()
    )
    if not res.data:
        return []
    dates = sorted(set(r["report_date"] for r in res.data if r.get("report_date")), reverse=True)
    return dates


def _label_period(date_str: str) -> str:
    """Convert '2025-01-01' → 'January 2025'."""
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%B %Y")
    except Exception:
        return date_str


# ─────────────────────────────────────────────
# LIVE DATA FETCHERS
# ─────────────────────────────────────────────
def _live_query(table, client_name, outlet, start, end, limit=5000):
    sb = get_supabase()
    q = (
        sb.table(table)
        .select("*")
        .gte("date", str(start))
        .lte("date", str(end))
    )
    if client_name and client_name != "All":
        q = q.ilike("client_name", f"%{client_name}%")
    if outlet and outlet != "All":
        q = q.ilike("outlet", f"%{outlet}%")
    return pd.DataFrame(q.limit(limit).execute().data or [])


# ─────────────────────────────────────────────
# AC DATA FETCHERS  (filter by branch_id list)
# ─────────────────────────────────────────────
def _ac_query(table, branch_ids: list, report_date: str, extra_cols: str = "*", limit=10000):
    sb = get_supabase()
    q = (
        sb.table(table)
        .select(extra_cols)
        .in_("branch_id", branch_ids)
        .eq("report_date", report_date)
    )
    return pd.DataFrame(q.limit(limit).execute().data or [])


# ═══════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═══════════════════════════════════════════════════════════════════
def render_dashboard(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 📈 Executive Operations Dashboard")
    supabase = get_supabase()

    try:
        user_role    = role.lower()
        is_admin     = user_role in ("admin", "admin_all")
        is_manager   = user_role == "manager"

        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        locked_client = clean_client.lower() not in ("all", "", "none", "nan")
        locked_outlet = clean_outlet.lower() not in ("all", "", "none", "nan")

        # ══════════════════════════════════════════
        # SIDEBAR — Branch / Outlet selection
        # ══════════════════════════════════════════
        st.sidebar.markdown("### 📍 Filter Dashboard")

        if locked_client:
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Client:** {final_client}")
        else:
            all_clients = _get_all_clients()
            c_names = [c["client_name"] for c in all_clients]
            sel = st.sidebar.selectbox("🏢 Select Client", ["All Clients"] + c_names, key="dash_client")
            final_client = "All" if sel == "All Clients" else sel

        # Resolve branches for this client
        if final_client != "All":
            branches_data = _get_branches_for_client(final_client)
            outlet_names  = [b["outlet"] for b in branches_data]
            branch_id_map = {b["outlet"]: b["id"] for b in branches_data}
        else:
            branches_data = []
            outlet_names  = []
            branch_id_map = {}

        if locked_outlet:
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if outlet_names:
                multi_branch = len(outlet_names) > 1
                if multi_branch:
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

        # Resolve active branch_ids for AC queries
        if final_outlet == "All":
            active_branch_ids = list(branch_id_map.values())
        else:
            bid = branch_id_map.get(final_outlet)
            active_branch_ids = [bid] if bid else []

        # ══════════════════════════════════════════
        # DATA SOURCE TOGGLE
        # ══════════════════════════════════════════
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📊 Data Source")

        ac_periods = _get_ac_periods(active_branch_ids) if active_branch_ids else []
        period_labels = {d: _label_period(d) for d in ac_periods}

        source_options = ["🟢 Live"] + [f"📋 {period_labels[d]}" for d in ac_periods]
        selected_source = st.sidebar.radio("View", source_options, key="dash_source", label_visibility="collapsed")

        is_live = selected_source == "🟢 Live"

        # Resolve which report_date is selected
        selected_report_date = None
        if not is_live and ac_periods:
            label_to_date = {f"📋 {v}": k for k, v in period_labels.items()}
            selected_report_date = label_to_date.get(selected_source, ac_periods[0])

        # ══════════════════════════════════════════
        # DATE RANGE (Live only)
        # ══════════════════════════════════════════
        today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()

        if is_live:
            st.sidebar.markdown("---")
            default_start = today - timedelta(days=30)
            date_range = st.sidebar.date_input(
                "📅 Date Range", value=(default_start, today), max_value=today, key="dash_daterange"
            )
            if len(date_range) != 2:
                st.warning("Please select both a start and end date.")
                return
            start_date, end_date = date_range
        else:
            start_date = end_date = None

        # ══════════════════════════════════════════
        # HEADER STRIP
        # ══════════════════════════════════════════
        st.divider()
        mode_label = "Live Operations" if is_live else f"Report Period — {period_labels.get(selected_report_date, '')}"
        outlet_label = final_outlet if final_outlet != "All" else "All Branches"
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
                # invoices_log uses created_at (timestamp) not a date column
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

                if active_branch_ids and selected_report_date:
                    df_ac_waste  = _ac_query("ac_waste_inventory", active_branch_ids, selected_report_date)
                    df_ac_sales  = _ac_query("ac_sales",           active_branch_ids, selected_report_date)
                    df_ac_cogs   = _ac_query("ac_cogs",            active_branch_ids, selected_report_date)
                    df_ac_inv    = _ac_query("ac_ending",          active_branch_ids, selected_report_date)
                    df_ac_purch  = _ac_query("ac_purchase",        active_branch_ids, selected_report_date)
                else:
                    df_ac_waste = df_ac_sales = df_ac_cogs = df_ac_inv = df_ac_purch = pd.DataFrame()

        # ══════════════════════════════════════════
        # KPI RIBBON
        # ══════════════════════════════════════════
        st.markdown("##### 🏆 Performance Snapshot")
        k1, k2, k3, k4, k5 = st.columns(5)

        if is_live:
            # Revenue
            total_rev = 0.0
            if not df_cash.empty and "revenue" in df_cash.columns:
                total_rev = _to_num(df_cash["revenue"]).sum()

            # Cash variance
            total_var = 0.0
            if not df_cash.empty and "over_short" in df_cash.columns:
                total_var = _to_num(df_cash["over_short"]).sum()

            # Waste qty
            total_waste_qty = 0.0
            if not df_waste.empty and "qty" in df_waste.columns:
                total_waste_qty = _to_num(df_waste["qty"]).sum()

            # Inventory count
            inv_count = len(df_inv) if not df_inv.empty else 0

            # Purchases
            total_purch = 0.0
            if not df_purch.empty:
                for col in ("total_amount", "amount", "total", "net_amount"):
                    if col in df_purch.columns:
                        total_purch = _to_num(df_purch[col]).sum()
                        break

            k1.metric("💵 Revenue",       _fmt(total_rev))
            var_color = "normal" if total_var >= 0 else "inverse"
            k2.metric("⚖️ Cash Variance", _fmt(total_var), delta=_fmt(total_var), delta_color=var_color)
            k3.metric("🗑️ Waste (Qty)",   _fmt(total_waste_qty, decimals=0))
            k4.metric("📋 Inv. Counts",   f"{inv_count:,}")
            k5.metric("🛒 Purchases",     _fmt(total_purch) if total_purch else "—")

        else:
            # AC Revenue — from ac_cogs gross_sales
            total_rev = 0.0
            if not df_ac_cogs.empty and "gross_sales" in df_ac_cogs.columns:
                total_rev = _to_num(df_ac_cogs["gross_sales"]).sum()

            # AC Net Cost %
            cost_pct = None
            if not df_ac_cogs.empty:
                net_sales = _to_num(df_ac_cogs["net_sales"]).sum() if "net_sales" in df_ac_cogs.columns else 0.0
                net_cogs  = _to_num(df_ac_cogs["net_cogs"]).sum()  if "net_cogs"  in df_ac_cogs.columns else 0.0
                if net_sales > 0:
                    cost_pct = (net_cogs / net_sales) * 100

            # AC Waste cost
            total_waste_cost = 0.0
            if not df_ac_waste.empty and "total_cost" in df_ac_waste.columns:
                total_waste_cost = _to_num(df_ac_waste["total_cost"]).sum()

            # AC Ending Inventory value
            inv_value = 0.0
            if not df_ac_inv.empty and "total_cost" in df_ac_inv.columns:
                inv_value = _to_num(df_ac_inv["total_cost"]).sum()

            # AC Purchases
            total_purch = 0.0
            if not df_ac_purch.empty and "total_cost" in df_ac_purch.columns:
                total_purch = _to_num(df_ac_purch["total_cost"]).sum()

            k1.metric("💵 Gross Sales",    _fmt(total_rev))
            k2.metric("📊 Net Cost %",     f"{cost_pct:.1f}%" if cost_pct is not None else "—")
            k3.metric("🗑️ Waste Cost",     _fmt(total_waste_cost))
            k4.metric("📦 Ending Inv.",    _fmt(inv_value))
            k5.metric("🛒 Purchases",      _fmt(total_purch))

        st.divider()

        # ══════════════════════════════════════════
        # WIDGET 1 — TOP 5 WASTE ITEMS
        # ══════════════════════════════════════════
        w_col1, w_col2 = st.columns([1, 1])

        with w_col1:
            st.markdown("##### 🚨 Top 5 Waste Items")
            if is_live:
                if not df_waste.empty and "item_name" in df_waste.columns and "qty" in df_waste.columns:
                    df_waste["qty"] = _to_num(df_waste["qty"])
                    top5 = (
                        df_waste.groupby("item_name")["qty"]
                        .sum().reset_index()
                        .sort_values("qty", ascending=False)
                        .head(5)
                    )
                    fig = px.bar(top5, x="qty", y="item_name", orientation="h", text_auto=".0f")
                    fig.update_traces(marker_color=EK_RED)
                    fig.update_layout(
                        yaxis={"categoryorder": "total ascending"},
                        xaxis_title="Qty", yaxis_title="",
                    )
                    st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.success("✅ No waste logged for this period.")
            else:
                # AC: rank by total_cost (more meaningful than qty across different units)
                if not df_ac_waste.empty and "product_description" in df_ac_waste.columns:
                    df_ac_waste["total_cost"] = _to_num(df_ac_waste["total_cost"]) if "total_cost" in df_ac_waste.columns else 0.0
                    df_ac_waste["qty"]        = _to_num(df_ac_waste["qty"])        if "qty"        in df_ac_waste.columns else 0.0
                    top5_ac = (
                        df_ac_waste.groupby("product_description")
                        .agg(total_cost=("total_cost", "sum"), qty=("qty", "sum"))
                        .reset_index()
                        .sort_values("total_cost", ascending=False)
                        .head(5)
                    )
                    top5_ac.columns = ["Item", "Total Cost", "Qty"]
                    fig = px.bar(top5_ac, x="Total Cost", y="Item", orientation="h",
                                 text_auto=".0f", hover_data=["Qty"])
                    fig.update_traces(marker_color=EK_RED)
                    fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_title="Cost", yaxis_title="")
                    st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.success("✅ No waste data for this period.")

        # ══════════════════════════════════════════
        # WIDGET 2 — SALES SUMMARY
        # ══════════════════════════════════════════
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
                        fig.update_traces(line_color=EK_SAND, fill="tozeroy",
                                          fillcolor=f"rgba(227,197,173,0.15)")
                        fig.update_layout(xaxis_title="", yaxis_title="Revenue")
                        st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.info("No sales data logged for this period.")
            else:
                if not df_ac_sales.empty and "description" in df_ac_sales.columns:
                    df_ac_sales["gross_sales"] = _to_num(df_ac_sales["gross_sales"]) if "gross_sales" in df_ac_sales.columns else 0.0
                    df_ac_sales["qty_sold"]    = _to_num(df_ac_sales["qty_sold"])    if "qty_sold"    in df_ac_sales.columns else 0.0
                    top_items = (
                        df_ac_sales.groupby("description")["gross_sales"]
                        .sum().reset_index()
                        .sort_values("gross_sales", ascending=False)
                        .head(8)
                    )
                    fig = px.bar(top_items, x="gross_sales", y="description",
                                 orientation="h", text_auto=".0f")
                    fig.update_traces(marker_color=EK_SAND)
                    fig.update_layout(yaxis={"categoryorder": "total ascending"},
                                      xaxis_title="Gross Sales", yaxis_title="")
                    st.plotly_chart(_chart_layout(fig), use_container_width=True)
                else:
                    st.info("No sales data for this period.")

        st.divider()

        # ══════════════════════════════════════════
        # WIDGET 3 — COST % / FLASH FOOD COST
        # ══════════════════════════════════════════
        st.markdown("##### 📊 Cost % Breakdown")

        if is_live:
            if not df_cash.empty and not df_waste.empty:
                col_cost1, col_cost2 = st.columns(2)
                with col_cost1:
                    # Cash variance trend
                    if "over_short" in df_cash.columns and "date" in df_cash.columns:
                        var_trend = df_cash.groupby("date")["over_short"].sum().reset_index().sort_values("date")
                        fig_var = px.bar(var_trend, x="date", y="over_short",
                                         title="Daily Cash Variance (Over/Short)")
                        fig_var.update_traces(marker_color=[EK_GREEN if v >= 0 else EK_RED
                                                            for v in var_trend["over_short"]])
                        fig_var.update_layout(xaxis_title="", yaxis_title="Amount")
                        st.plotly_chart(_chart_layout(fig_var), use_container_width=True)
                with col_cost2:
                    st.info("💡 Flash food cost will be available once daily invoice entry is active for this outlet.")
            else:
                st.info("Not enough data to compute cost %.")

        else:
            if not df_ac_cogs.empty and "category" in df_ac_cogs.columns:
                df_ac_cogs["net_sales"]   = _to_num(df_ac_cogs["net_sales"])   if "net_sales"   in df_ac_cogs.columns else 0.0
                df_ac_cogs["net_cogs"]    = _to_num(df_ac_cogs["net_cogs"])    if "net_cogs"    in df_ac_cogs.columns else 0.0
                df_ac_cogs["gross_sales"] = _to_num(df_ac_cogs["gross_sales"]) if "gross_sales" in df_ac_cogs.columns else 0.0

                col_cost1, col_cost2 = st.columns(2)

                with col_cost1:
                    # Cost % per category
                    cat_data = df_ac_cogs[df_ac_cogs["net_sales"] > 0].copy()
                    if not cat_data.empty:
                        cat_data["cost_pct"] = (cat_data["net_cogs"] / cat_data["net_sales"] * 100).round(1)
                        fig_cat = px.bar(cat_data.sort_values("cost_pct", ascending=False),
                                         x="category", y="cost_pct",
                                         text_auto=".1f",
                                         title="Net Cost % by Category")
                        fig_cat.update_traces(marker_color=EK_SAND,
                                              texttemplate="%{text}%", textposition="outside")
                        fig_cat.update_layout(xaxis_title="", yaxis_title="Cost %",
                                              yaxis_range=[0, cat_data["cost_pct"].max() * 1.2])
                        st.plotly_chart(_chart_layout(fig_cat), use_container_width=True)
                    else:
                        st.info("No cost % data available.")

                with col_cost2:
                    # Sales vs COGS waterfall summary
                    total_gross = df_ac_cogs["gross_sales"].sum()
                    total_net   = df_ac_cogs["net_sales"].sum()
                    total_cogs  = df_ac_cogs["net_cogs"].sum()
                    discount   = _to_num(df_ac_cogs["discount"]).sum() if "discount" in df_ac_cogs.columns else 0.0
                    waste_cost = _to_num(df_ac_cogs["waste"]).sum()    if "waste"    in df_ac_cogs.columns else 0.0

                    summary_df = pd.DataFrame({
                        "Item":  ["Gross Sales", "Discount", "Net Sales", "Net COGS", "Waste"],
                        "Value": [total_gross, -abs(discount), total_net, -abs(total_cogs), -abs(waste_cost)],
                    })
                    fig_sum = px.bar(summary_df, x="Item", y="Value", text_auto=".0f",
                                     title="Period P&L Summary")
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
        # WIDGET 4 — INVENTORY VALUE
        # ══════════════════════════════════════════
        inv_col, purch_col = st.columns(2)

        with inv_col:
            st.markdown("##### 📦 Inventory")
            if is_live:
                if not df_inv.empty:
                    st.caption(f"{len(df_inv):,} count records in selected period.")
                    # Show last count per item if qty/unit_cost available
                    if "item_name" in df_inv.columns:
                        st.dataframe(
                            df_inv[["date", "item_name", "qty", "outlet"]].sort_values("date", ascending=False).head(10),
                            use_container_width=True, hide_index=True
                        )
                else:
                    st.info("No inventory counts logged for this period.")
            else:
                if not df_ac_inv.empty:
                    df_ac_inv["total_cost"] = _to_num(df_ac_inv["total_cost"]) if "total_cost" in df_ac_inv.columns else 0.0
                    df_ac_inv["qty"]            = _to_num(df_ac_inv["qty"])            if "qty"            in df_ac_inv.columns else 0.0

                    # Top 10 by value
                    top_inv = (
                        df_ac_inv.groupby("product_description")["total_cost"]
                        .sum().reset_index()
                        .sort_values("total_cost", ascending=False)
                        .head(10)
                    )
                    top_inv.columns = ["Item", "Ending Value"]
                    top_inv["Ending Value"] = top_inv["Ending Value"].map(lambda x: f"{x:,.2f}")

                    total_inv_val = _to_num(df_ac_inv["total_cost"]).sum()
                    st.caption(f"Total ending inventory value: **{total_inv_val:,.2f}**")
                    st.dataframe(top_inv, use_container_width=True, hide_index=True)
                else:
                    st.info("No ending inventory data for this period.")

        # ══════════════════════════════════════════
        # WIDGET 5 — PURCHASES
        # ══════════════════════════════════════════
        with purch_col:
            st.markdown("##### 🛒 Purchases")
            if is_live:
                if not df_purch.empty:
                    # Try to find the right amount column
                    amt_col = next((c for c in ("total_amount", "amount", "total", "net_amount")
                                    if c in df_purch.columns), None)
                    if amt_col:
                        df_purch[amt_col] = _to_num(df_purch[amt_col])
                        total_p = df_purch[amt_col].sum()
                        st.caption(f"Total invoices logged: **{_fmt(total_p)}** across {len(df_purch):,} records")
                        show_cols = [c for c in ("date", "supplier_name", "invoice_number", amt_col, "outlet")
                                     if c in df_purch.columns]
                        st.dataframe(
                            df_purch[show_cols].sort_values("date", ascending=False).head(10),
                            use_container_width=True, hide_index=True
                        )
                    else:
                        st.dataframe(df_purch.head(10), use_container_width=True, hide_index=True)
                else:
                    st.info("No invoices logged for this period.")
            else:
                if not df_ac_purch.empty and "raw_materials" in df_ac_purch.columns:
                    df_ac_purch["total_cost"] = _to_num(df_ac_purch["total_cost"]) if "total_cost" in df_ac_purch.columns else 0.0

                    # Top 10 purchased items by cost
                    top_purch = (
                        df_ac_purch.groupby("raw_materials")["total_cost"]
                        .sum().reset_index()
                        .sort_values("total_cost", ascending=False)
                        .head(10)
                    )
                    top_purch.columns = ["Raw Material", "Total Cost"]

                    total_p = df_ac_purch["total_cost"].sum()
                    st.caption(f"Total purchases: **{total_p:,.2f}** across {len(df_ac_purch):,} line items")
                    top_purch["Total Cost"] = top_purch["Total Cost"].map(lambda x: f"{x:,.2f}")
                    st.dataframe(top_purch, use_container_width=True, hide_index=True)
                else:
                    st.info("No purchase data for this period.")

        # ══════════════════════════════════════════
        # EXCEPTIONS (Live only — cash shortages + big waste)
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
        # EXPORT (Admin only)
        # ══════════════════════════════════════════
        if is_admin:
            st.divider()
            st.markdown("### 📥 Deep-Dive Data Export")
            st.info("Download raw database logs for pivot analysis in Excel.")

            if is_live:
                export_options = {
                    "Waste Logs":       "waste_logs",
                    "Inventory Logs":   "inventory_logs",
                    "Daily Cash":       "daily_cash",
                    "Invoices":         "invoices_log",
                }
            else:
                export_options = {
                    "AC Waste":         "ac_waste_inventory",
                    "AC Sales":         "ac_sales",
                    "AC COGS":          "ac_cogs",
                    "AC Ending Inv.":   "ac_ending",
                    "AC Purchase":      "ac_purchase",
                    "AC Variance":      "ac_variance",
                }

            exp_col1, _ = st.columns([1, 2])
            with exp_col1:
                table_label = st.selectbox("Select Table", list(export_options.keys()), key="export_table_select")
            db_table = export_options[table_label]

            fp_key = f"{db_table}|{final_client}|{final_outlet}|{start_date}|{end_date}|{selected_report_date}"
            if st.session_state.get("export_fingerprint") != fp_key:
                for k in ("export_csv", "export_row_count", "export_file_name"):
                    st.session_state.pop(k, None)
                st.session_state["export_fingerprint"] = fp_key

            if st.button(f"🔍 Generate {table_label} Export", type="primary", key="export_generate_btn"):
                with st.spinner(f"Pulling {table_label}..."):
                    if is_live:
                        q = supabase.table(db_table).select("*") \
                            .gte("date", str(start_date)).lte("date", str(end_date))
                        if final_client not in ("All",):
                            q = q.ilike("client_name", f"%{final_client}%")
                        if final_outlet not in ("All",):
                            q = q.ilike("outlet", f"%{final_outlet}%")
                        df_exp = pd.DataFrame(q.limit(50000).execute().data or [])
                    else:
                        if active_branch_ids and selected_report_date:
                            df_exp = _ac_query(db_table, active_branch_ids, selected_report_date, limit=50000)
                        else:
                            df_exp = pd.DataFrame()

                    if not df_exp.empty:
                        st.session_state["export_csv"]       = df_exp.to_csv(index=False).encode("utf-8")
                        st.session_state["export_row_count"] = len(df_exp)
                        st.session_state["export_file_name"] = f"{db_table}_{final_client}_{start_date or selected_report_date}.csv"
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