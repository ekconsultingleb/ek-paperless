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
        # 1. SMART ROUTING & CLEAN SIDEBAR
        # ==========================================
        # PRO TIP: Query the small users table for instant navigation
        nav_res = supabase.table("users").select("client_name, outlet").execute()
        df_nav = pd.DataFrame(nav_res.data)
        
        if not df_nav.empty:
            df_nav['client_name'] = df_nav['client_name'].astype(str).str.strip().str.title()
            df_nav['outlet'] = df_nav['outlet'].astype(str).str.strip().str.title()
            
        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        st.sidebar.markdown("### 📍 Filter Dashboard")

        # --- Branch Selection ---
        if clean_client.lower() != 'all':
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
        else:
            c_list = ["All Branches"] + sorted([c for c in df_nav['client_name'].unique() if c.lower() != 'all']) if not df_nav.empty else ["All Branches"]
            selected_branch = st.sidebar.selectbox("🏢 Select Branch", c_list)
            final_client = "All" if selected_branch == "All Branches" else selected_branch

        # --- Outlet Selection ---
        if clean_outlet.lower() != 'all':
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if final_client != "All" and not df_nav.empty:
                outlets_for_client = sorted([o for o in df_nav[df_nav['client_name'] == final_client]['outlet'].unique() if o.lower() != 'all'])
            elif not df_nav.empty:
                outlets_for_client = sorted([o for o in df_nav['outlet'].unique() if o.lower() != 'all'])
            else:
                outlets_for_client = []
                
            o_list = ["All Outlets"] + outlets_for_client if outlets_for_client else ["All Outlets"]
            selected_outlet = st.sidebar.selectbox("🏠 Select Outlet", o_list)
            final_outlet = "All" if selected_outlet == "All Outlets" else selected_outlet

        # ==========================================
        # 2. GLOBAL DATE FILTER
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
        # 3. FETCH SECURE DATA FOR CHARTS
        # ==========================================
        def secure_query(table_name):
            query = supabase.table(table_name).select("*").gte("date", str(start_date)).lte("date", str(end_date))
            if final_client != 'All':
                query = query.ilike("client_name", f"%{final_client}%")
            if final_outlet != 'All':
                query = query.ilike("outlet", f"%{final_outlet}%")
            return query

        with st.spinner("⏳ Fetching live analytics..."):
            # Fetch Cash
            res_cash = secure_query("daily_cash").limit(5000).execute()
            df_cash = pd.DataFrame(res_cash.data)
            
            # Fetch Waste
            res_waste = secure_query("waste_logs").limit(5000).execute()
            df_waste = pd.DataFrame(res_waste.data)
            
            # Fetch Inventory (Just counting rows)
            res_inv = secure_query("inventory_logs").limit(5000).execute()
            df_inv = pd.DataFrame(res_inv.data)

        # ==========================================
        # 4. TOP-LEVEL METRICS
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
        # 5. REVENUE BREAKDOWN & CHARTS
        # ==========================================
        if not df_cash.empty:
            st.subheader("🏢 Revenue Breakdown")
            
            df_cash['revenue'] = pd.to_numeric(df_cash['revenue'], errors='coerce').fillna(0)
            df_cash['over_short'] = pd.to_numeric(df_cash['over_short'], errors='coerce').fillna(0)
            
            outlet_summary = df_cash.groupby('outlet')[['revenue', 'over_short']].sum().reset_index()
            outlets_list = outlet_summary.to_dict('records')
            
            if outlets_list:
                cols_per_row = 4
                for i in range(0, len(outlets_list), cols_per_row):
                    row_cols = st.columns(cols_per_row)
                    for j, out_data in enumerate(outlets_list[i:i+cols_per_row]):
                        with row_cols[j]:
                            with st.container(border=True):
                                st.markdown(f"**{str(out_data['outlet']).title()}**")
                                st.metric(
                                    label="Revenue", 
                                    value=f"{out_data['revenue']:,.2f}", 
                                    delta=f"Var: {out_data['over_short']:,.2f}",
                                    delta_color="normal"
                                )
                                
            st.subheader("📈 Revenue Trend")
            chart_data = df_cash.groupby('date')['revenue'].sum().reset_index()
            chart_data = chart_data.sort_values(by='date')
            st.bar_chart(chart_data, x='date', y='revenue', color="#00ff00")
        else:
            st.info("No revenue data logged for this timeframe.")

        # ==========================================
        # 6. 📥 GLOBAL DATA EXPORT (POWER USERS ONLY)
        # ==========================================
        if clean_client.lower() == 'all' or role.lower() == 'admin':
            st.divider()
            st.markdown("### 📥 Global Data Export (Excel/CSV)")
            st.info("Bypass all app limits. Download the raw database logs here and use Excel to filter by Client, Date, or Item.")
            
            exp_col1, exp_col2 = st.columns([1, 2])
            with exp_col1:
                table_to_export = st.selectbox(
                    "Select Database Table", 
                    ["Waste Logs", "Inventory Logs", "Daily Cash", "Transfers"]
                )
            
            table_map = {
                "Waste Logs": "waste_logs",
                "Inventory Logs": "inventory_logs",
                "Daily Cash": "daily_cash",
                "Transfers": "transfers"
            }
            db_table_name = table_map[table_to_export]
            
            if st.button(f"🔍 Fetch {table_to_export} Data", type="primary"):
                with st.spinner(f"Pulling {table_to_export} records..."):
                    
                    # 1. Start with the date filter
                    export_query = supabase.table(db_table_name).select("*").gte("date", str(start_date)).lte("date", str(end_date))
                    
                    # 2. Apply the sidebar Client filter
                    if final_client != 'All':
                        export_query = export_query.ilike("client_name", f"%{final_client}%")
                        
                    # 3. Apply the sidebar Outlet filter
                    if final_outlet != 'All':
                        export_query = export_query.ilike("outlet", f"%{final_outlet}%")
                        
                    # 4. Fetch the data with a massive limit to bypass limits
                    export_res = export_query.limit(50000).execute()
                    df_export = pd.DataFrame(export_res.data)
                    
                    if not df_export.empty:
                        st.success(f"✅ Found {len(df_export)} records.")
                        
                        # Generate CSV for download
                        csv_data = df_export.to_csv(index=False).encode('utf-8')
                        
                        st.download_button(
                            label=f"💾 Download {table_to_export} as CSV",
                            data=csv_data,
                            file_name=f"{db_table_name}_export_{final_client}_{start_date}_to_{end_date}.csv",
                            mime="text/csv",
                            type="primary",
                            use_container_width=True
                        )
                        
                        # Show a quick preview
                        with st.expander("👀 Preview Data"):
                            st.dataframe(df_export.head(10), use_container_width=True)
                    else:
                        st.warning(f"No records found for the selected filters and dates.")
                        
    except Exception as e:
        st.error(f"❌ Error loading Dashboard analytics: {e}")