import streamlit as st
import pandas as pd
from datetime import datetime

def render_dashboard(conn, sheet_link, assigned_outlet):
    st.markdown(f"### 📊 Management Dashboard")
    st.info("High-level overview of daily operations and metrics.")
    try:
        with st.spinner("⏳ Fetching live data from Google Servers..."):
            df_cash = conn.read(spreadsheet=sheet_link, worksheet="cash", ttl=60)
            df_waste = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=60)
            df_inv = conn.read(spreadsheet=sheet_link, worksheet="inventory_logs", ttl=60) # NEW: Pulling the ledger!
        
        # --- SCRUB COLUMNS TO PREVENT TYPO CRASHES ---
        cash_rename = {col: str(col).strip().title() for col in df_cash.columns}
        if 'Over / Short' not in cash_rename.values():
            for col in df_cash.columns:
                if str(col).strip().lower() in ['over / short', 'over/short']: cash_rename[col] = 'Over / Short'
        df_cash.rename(columns=cash_rename, inplace=True)
        
        waste_rename = {col: str(col).strip().title() for col in df_waste.columns}
        df_waste.rename(columns=waste_rename, inplace=True)

        inv_rename = {col: str(col).strip().title() for col in df_inv.columns}
        df_inv.rename(columns=inv_rename, inplace=True)

        # --- OUTLET SECURITY LOCK ---
        user_outlet = str(assigned_outlet).strip()
        if user_outlet.lower() != 'all' and user_outlet != '':
            if 'Outlet' in df_cash.columns: df_cash = df_cash[df_cash['Outlet'] == user_outlet]
            if 'Outlet' in df_waste.columns: df_waste = df_waste[df_waste['Outlet'] == user_outlet]
            if 'Outlet' in df_inv.columns: df_inv = df_inv[df_inv['Outlet'] == user_outlet]

        # Upgraded to 4 columns to fit the new Inventory metric!
        col1, col2, col3, col4 = st.columns(4)
        
        # --- 1. CASH METRICS ---
        if not df_cash.empty and 'Revenue' in df_cash.columns:
            total_rev = df_cash['Revenue'].sum()
            total_variance = df_cash['Over / Short'].sum() if 'Over / Short' in df_cash.columns else 0
            col1.metric("Total Revenue", f"{total_rev:,.2f}")
            col2.metric("Total Cash Variance", f"{total_variance:,.2f}", delta=total_variance)
        else:
            col1.metric("Total Revenue", "0.00")
            col2.metric("Total Cash Variance", "0.00")
            
        # --- 2. WASTE METRICS ---
        if not df_waste.empty and 'Qty' in df_waste.columns:
            total_waste_items = df_waste['Qty'].sum()
            col3.metric("Total Waste Items", f"{total_waste_items:,.0f}")
        else:
            col3.metric("Total Waste Items", "0")

        # --- 3. INVENTORY METRICS (NEW) ---
        if not df_inv.empty and 'Date' in df_inv.columns:
            today_str = datetime.now().strftime("%Y-%m-%d")
            # Count how many items were logged today
            today_counts = df_inv[df_inv['Date'].astype(str) == today_str]
            items_counted_today = len(today_counts)
            col4.metric("Inv Items Counted Today", f"{items_counted_today:,.0f}")
        else:
            col4.metric("Inv Items Counted Today", "0")
            
        st.divider()
        
        # --- 4. OUTLET BREAKDOWN ---
        if not df_cash.empty and 'Outlet' in df_cash.columns and 'Revenue' in df_cash.columns:
            st.subheader("🏢 Revenue Breakdown by Outlet")
            df_cash['Outlet'] = df_cash['Outlet'].fillna("Unknown")
            if 'Over / Short' not in df_cash.columns: df_cash['Over / Short'] = 0.0
            
            outlet_summary = df_cash.groupby('Outlet')[['Revenue', 'Over / Short']].sum().reset_index()
            outlets_list = outlet_summary.to_dict('records')
            
            if outlets_list:
                outlet_cols = st.columns(len(outlets_list))
                for i, out_data in enumerate(outlets_list):
                    with outlet_cols[i]:
                        st.metric(
                            label=f"{out_data['Outlet']}", 
                            value=f"{out_data['Revenue']:,.2f}", 
                            delta=f"Var: {out_data['Over / Short']:,.2f}",
                            delta_color="normal" if out_data['Over / Short'] >= 0 else "inverse"
                        )
        st.divider()
        
        # --- 5. TREND CHART ---
        st.subheader("📈 Total Revenue Trend")
        if not df_cash.empty and 'Date' in df_cash.columns and 'Revenue' in df_cash.columns:
            chart_data = df_cash.groupby('Date')['Revenue'].sum().reset_index()
            st.line_chart(chart_data, x='Date', y='Revenue')
            
    except Exception as e:
        st.error(f"Error loading Dashboard data. Details: {e}")