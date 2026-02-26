import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_dashboard(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 📊 Management Dashboard")
    st.info("Live overview of daily operations and financial metrics.")
    supabase = get_supabase()
    
    try:
        # ==========================================
        # 1. GLOBAL DATE FILTER
        # ==========================================
        today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
        default_start = today - timedelta(days=7) # Default to last 7 days
        
        col_date, col_blank = st.columns([1, 2])
        with col_date:
            date_range = st.date_input("📅 Select Timeframe", value=(default_start, today), max_value=today)
            
        if len(date_range) != 2:
            st.warning("Please select both a Start Date and an End Date to view metrics.")
            return
            
        start_date, end_date = date_range
        st.divider()

        # ==========================================
        # 2. FETCH SECURE DATA
        # ==========================================
        # Determine the security bounds
        clean_client = str(assigned_client).strip().lower()
        clean_outlet = str(assigned_outlet).strip().lower()
        
        # Helper function to apply security to Supabase queries
        def secure_query(table_name):
            query = supabase.table(table_name).select("*").gte("date", str(start_date)).lte("date", str(end_date))
            if clean_client != 'all':
                query = query.ilike("client_name", f"%{str(assigned_client).strip()}%")
            if clean_outlet != 'all':
                query = query.ilike("outlet", f"%{str(assigned_outlet).strip()}%")
            return query

        with st.spinner("⏳ Fetching live analytics..."):
            # Fetch Cash
            res_cash = secure_query("daily_cash").limit(5000).execute()
            df_cash = pd.DataFrame(res_cash.data)
            
            # Fetch Waste
            res_waste = secure_query("waste_logs").limit(5000).execute()
            df_waste = pd.DataFrame(res_waste.data)
            
            # Fetch Inventory (Just counting rows, so we don't need a massive limit)
            res_inv = secure_query("inventory_logs").limit(5000).execute()
            df_inv = pd.DataFrame(res_inv.data)

        # ==========================================
        # 3. TOP-LEVEL METRICS
        # ==========================================
        col1, col2, col3, col4 = st.columns(4)
        
        # Cash Math
        if not df_cash.empty:
            total_rev = pd.to_numeric(df_cash['revenue'], errors='coerce').sum()
            total_variance = pd.to_numeric(df_cash['over_short'], errors='coerce').sum()
        else:
            total_rev, total_variance = 0.0, 0.0
            
        col1.metric("Total Revenue", f"{total_rev:,.2f}")
        col2.metric("Cash Variance", f"{total_variance:,.2f}", delta=f"{total_variance:,.2f}", delta_color="normal")
            
        # Waste Math
        if not df_waste.empty:
            total_waste_qty = pd.to_numeric(df_waste['qty'], errors='coerce').sum()
        else:
            total_waste_qty = 0.0
            
        col3.metric("Waste (Qty)", f"{total_waste_qty:,.0f}")

        # Inventory Math
        items_counted = len(df_inv) if not df_inv.empty else 0
        col4.metric("Inventory Items Logged", f"{items_counted:,.0f}")
            
        st.divider()
        
        # ==========================================
        # 4. REVENUE BREAKDOWN BY OUTLET
        # ==========================================
        if not df_cash.empty:
            st.subheader("🏢 Revenue Breakdown")
            
            # Group by outlet
            df_cash['revenue'] = pd.to_numeric(df_cash['revenue'], errors='coerce').fillna(0)
            df_cash['over_short'] = pd.to_numeric(df_cash['over_short'], errors='coerce').fillna(0)
            
            outlet_summary = df_cash.groupby('outlet')[['revenue', 'over_short']].sum().reset_index()
            outlets_list = outlet_summary.to_dict('records')
            
            if outlets_list:
                # Dynamically create columns based on number of outlets
                cols_per_row = 4
                for i in range(0, len(outlets_list), cols_per_row):
                    row_cols = st.columns(cols_per_row)
                    for j, out_data in enumerate(outlets_list[i:i+cols_per_row]):
                        with row_cols[j]:
                            with st.container(border=True):
                                st.markdown(f"**{out_data['outlet'].title()}**")
                                st.metric(
                                    label="Revenue", 
                                    value=f"{out_data['revenue']:,.2f}", 
                                    delta=f"Var: {out_data['over_short']:,.2f}",
                                    delta_color="normal"
                                )
        else:
            st.info("No revenue data logged for this timeframe.")
            
        st.divider()
        
        # ==========================================
        # 5. REVENUE TREND CHART
        # ==========================================
        st.subheader("📈 Revenue Trend")
        if not df_cash.empty:
            # Group by date for the chart
            chart_data = df_cash.groupby('date')['revenue'].sum().reset_index()
            # Ensure dates are sorted chronologically
            chart_data = chart_data.sort_values(by='date')
            st.bar_chart(chart_data, x='date', y='revenue', color="#00ff00")
        else:
            st.info("Not enough data to generate trend chart.")
            
    except Exception as e:
        st.error(f"❌ Error loading Dashboard analytics: {e}")