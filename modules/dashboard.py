import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from modules.nav_helper import get_nav_data
import plotly.express as px
import plotly.graph_objects as go

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_dashboard(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 📈 Executive Operations Dashboard")
    supabase = get_supabase()
    
    try:
        # ==========================================
        # 1. SMART ROUTING & CLEAN SIDEBAR
        # ==========================================
        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        df_nav = get_nav_data("all")

        st.sidebar.markdown("### 📍 Filter Dashboard")

        if clean_client.lower() not in ['all', '', 'none', 'nan']:
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
        else:
            c_list = ["All Branches"] + sorted(df_nav['client_name'].unique().tolist()) if not df_nav.empty else ["All Branches"]
            selected_branch = st.sidebar.selectbox("🏢 Select Branch", c_list, key="dash_branch")
            final_client = "All" if selected_branch == "All Branches" else selected_branch

        if clean_outlet.lower() not in ['all', '', 'none', 'nan']:
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if final_client not in ["All Branches", "All", ""] and not df_nav.empty:
                outlets_for_client = sorted(df_nav[df_nav['client_name'] == final_client]['outlet'].unique().tolist())
            elif not df_nav.empty:
                outlets_for_client = sorted(df_nav['outlet'].unique().tolist())
            else:
                outlets_for_client = []

            o_list = ["All Outlets"] + outlets_for_client if outlets_for_client else ["All Outlets"]
            selected_outlet = st.sidebar.selectbox("🏠 Select Outlet", o_list, key="dash_outlet")
            final_outlet = "All" if selected_outlet == "All Outlets" else selected_outlet

        # ==========================================
        # 2. GLOBAL DATE FILTER
        # ==========================================
        today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
        default_start = today - timedelta(days=7) 
        
        col_date, col_blank = st.columns([1, 2])
        with col_date:
            date_range = st.date_input("📅 Select Timeframe", value=(default_start, today), max_value=today)
            
        if len(date_range) != 2:
            st.warning("Please select both a Start Date and an End Date to view metrics.")
            return
            
        start_date, end_date = date_range
        st.divider()

        # ==========================================
        # 3. FETCH SECURE DATA FOR CHARTS
        # ==========================================
        def secure_query(table_name):
            query = supabase.table(table_name).select("*").gte("date", str(start_date)).lte("date", str(end_date))
            if final_client != 'All':
                query = query.ilike("client_name", f"%{final_client}%")
            if final_outlet != 'All':
                query = query.ilike("outlet", f"%{final_outlet}%")
            return query

        with st.spinner("⏳ Fetching executive analytics..."):
            res_cash = secure_query("daily_cash").limit(5000).execute()
            df_cash = pd.DataFrame(res_cash.data)
            
            res_waste = secure_query("waste_logs").limit(5000).execute()
            df_waste = pd.DataFrame(res_waste.data)
            
            res_inv = secure_query("inventory_logs").limit(5000).execute()
            df_inv = pd.DataFrame(res_inv.data)

        # ==========================================
        # 4. HERO METRICS (THE KPI RIBBON)
        # ==========================================
        st.markdown("##### 🏆 Performance Snapshot")
        col1, col2, col3, col4 = st.columns(4)
        
        total_rev, total_variance, total_waste_qty = 0.0, 0.0, 0.0
        if not df_cash.empty:
            df_cash['revenue'] = pd.to_numeric(df_cash['revenue'], errors='coerce').fillna(0)
            df_cash['over_short'] = pd.to_numeric(df_cash['over_short'], errors='coerce').fillna(0)
            total_rev = df_cash['revenue'].sum()
            total_variance = df_cash['over_short'].sum()
            
        if not df_waste.empty:
            df_waste['qty'] = pd.to_numeric(df_waste['qty'], errors='coerce').fillna(0)
            total_waste_qty = df_waste['qty'].sum()

        items_counted = len(df_inv) if not df_inv.empty else 0

        col1.metric("💵 Total Revenue", f"{total_rev:,.2f}")
        var_color = "normal" if total_variance >= 0 else "inverse"
        col2.metric("⚖️ Cash Variance", f"{total_variance:,.2f}", delta=f"{total_variance:,.2f}", delta_color=var_color)
        col3.metric("🗑️ Total Waste (Qty)", f"{total_waste_qty:,.0f}")
        col4.metric("📋 Inventory Logs", f"{items_counted:,.0f} counts")
            
        st.divider()
        
        # ==========================================
        # 5. VISUAL ANALYTICS (PLOTLY)
        # ==========================================
        chart_col1, chart_col2 = st.columns([2, 1])
        
        with chart_col1:
            st.markdown("##### 📈 Revenue & Collection Trend")
            if not df_cash.empty:
                trend_data = df_cash.groupby('date')[['revenue', 'cash', 'visa']].sum().reset_index()
                trend_data = trend_data.sort_values('date')
                fig_rev = px.area(trend_data, x="date", y="revenue", markers=True, title="Daily Gross Revenue")
                fig_rev.update_traces(line_color="#00ff00", fill='tozeroy', fillcolor="rgba(0,255,0,0.1)")
                fig_rev.update_layout(xaxis_title="", yaxis_title="Amount", margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_rev, use_container_width=True)
            else:
                st.info("No revenue data logged for this timeframe.")

        with chart_col2:
            st.markdown("##### 🚨 Top 5 Wasted Items")
            if not df_waste.empty:
                top_waste = df_waste.groupby('item_name')['qty'].sum().reset_index().sort_values('qty', ascending=False).head(5)
                fig_waste = px.bar(top_waste, x='qty', y='item_name', orientation='h', text_auto='.0f')
                fig_waste.update_traces(marker_color='#ff4b4b')
                fig_waste.update_layout(yaxis={'categoryorder':'total ascending'}, xaxis_title="Qty Wasted", yaxis_title="", margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_waste, use_container_width=True)
            else:
                st.success("No waste logged! Excellent job.")

        # ==========================================
        # 6. EXCEPTION REPORTING (RED FLAGS)
        # ==========================================
        st.markdown("##### ⚠️ Exceptions & Discrepancies")
        exc_col1, exc_col2 = st.columns(2)
        
        with exc_col1:
            st.markdown("**Cash Shortages**")
            if not df_cash.empty:
                shortages = df_cash[df_cash['over_short'] < 0][['date', 'outlet', 'over_short', 'reported_by']]
                if not shortages.empty:
                    shortages = shortages.sort_values('over_short').head(5)
                    st.dataframe(shortages, use_container_width=True, hide_index=True)
                else:
                    st.success("All registers balanced perfectly!")
            else:
                st.caption("No cash data.")
                
        with exc_col2:
            st.markdown("**Largest Spoilage Events**")
            if not df_waste.empty:
                big_waste = df_waste.sort_values('qty', ascending=False)[['date', 'item_name', 'qty', 'remarks', 'reported_by']].head(5)
                st.dataframe(big_waste, use_container_width=True, hide_index=True)
            else:
                st.caption("No waste data.")

        # ==========================================
        # 7. 📥 GLOBAL DATA EXPORT (POWER USERS ONLY)
        # ==========================================
        if clean_client.lower() == 'all' or role.lower() == 'admin':
            st.divider()
            st.markdown("### 📥 Deep-Dive Data Export")
            st.info("Bypass visual limits. Download the raw database logs here and use Excel to run deep pivot tables.")
            
            exp_col1, exp_col2 = st.columns([1, 2])
            with exp_col1:
                table_to_export = st.selectbox(
                    "Select Database Table", 
                    ["Waste Logs", "Inventory Logs", "Daily Cash", "Transfers"],
                    key="export_table_select"
                )
            
            table_map = {
                "Waste Logs": "waste_logs",
                "Inventory Logs": "inventory_logs",
                "Daily Cash": "daily_cash",
                "Transfers": "transfers"
            }
            db_table_name = table_map[table_to_export]

            # ── FIX: clear cached export when filters change ───────────────
            # Build a key that represents the current query parameters.
            # If anything changes, we discard the old export so it doesn't
            # show a stale download button for the wrong table/dates.
            export_fingerprint = f"{db_table_name}|{final_client}|{final_outlet}|{start_date}|{end_date}"
            if st.session_state.get("export_fingerprint") != export_fingerprint:
                st.session_state.pop("export_csv",         None)
                st.session_state.pop("export_row_count",   None)
                st.session_state.pop("export_file_name",   None)
                st.session_state["export_fingerprint"] = export_fingerprint

            # ── Generate button: only fetches, never re-fetches on download ─
            if st.button(f"🔍 Generate {table_to_export} Export", type="primary", key="export_generate_btn"):
                with st.spinner(f"Pulling {table_to_export} records..."):
                    export_query = supabase.table(db_table_name).select("*") \
                        .gte("date", str(start_date)).lte("date", str(end_date))
                    if final_client not in ('All', 'All Branches'):
                        export_query = export_query.ilike("client_name", f"%{final_client}%")
                    if final_outlet not in ('All', 'All Outlets'):
                        export_query = export_query.ilike("outlet", f"%{final_outlet}%")
                        
                    export_res = export_query.limit(50000).execute()
                    df_export = pd.DataFrame(export_res.data)
                    
                    if not df_export.empty:
                        # ── Store in session_state so it survives the download rerun ──
                        st.session_state["export_csv"]       = df_export.to_csv(index=False).encode("utf-8")
                        st.session_state["export_row_count"] = len(df_export)
                        st.session_state["export_file_name"] = f"{db_table_name}_export_{final_client}_{start_date}_to_{end_date}.csv"
                    else:
                        st.session_state.pop("export_csv",       None)
                        st.session_state.pop("export_row_count", None)
                        st.session_state.pop("export_file_name", None)
                        st.warning("No records found for the selected filters and dates.")

            # ── Download button: always rendered when data is ready ────────
            # Because it reads from session_state (not from a button click),
            # it persists across reruns — including the rerun triggered by
            # tapping "Save" on mobile.
            if st.session_state.get("export_csv") is not None:
                st.success(f"✅ {st.session_state['export_row_count']:,} records ready.")
                st.download_button(
                    label=f"💾 Download {table_to_export} as CSV",
                    data=st.session_state["export_csv"],
                    file_name=st.session_state["export_file_name"],
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key="export_download_btn"
                )
                        
    except Exception as e:
        st.error(f"❌ Error loading Dashboard analytics: {e}")