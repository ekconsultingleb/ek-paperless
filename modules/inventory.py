import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo

def render_inventory(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown(f"### 📦 Inventory Count")
    try:
        # ==========================================
        # 👁️ VIEWER MODE (KHALDOUN / MANAGERS)
        # ==========================================
        if role == "viewer":
            st.info("👁️ **Data Entry Mode:** View Consolidated Inventory Logs.")
            df_logs = conn.read(spreadsheet=sheet_link, worksheet="inventory_logs", ttl=0)
            
            # --- OUTLET & LOCATION SECURITY LOCKS ---
            if assigned_outlet.lower() != 'all' and assigned_outlet != '' and 'Outlet' in df_logs.columns:
                df_logs = df_logs[df_logs['Outlet'] == assigned_outlet]
                
            if assigned_location.lower() != 'all' and assigned_location != '' and 'Location' in df_logs.columns:
                allowed_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
                df_logs = df_logs[df_logs['Location'].astype(str).str.lower().isin(allowed_locs)]
            
            # Date Range Picker
            today = datetime.now().date()
            date_selection = st.date_input("📅 Select Date Range", value=(today, today))
            
            if 'Date' in df_logs.columns:
                if len(date_selection) == 2: start_date, end_date = date_selection
                elif len(date_selection) == 1: start_date = end_date = date_selection[0]
                else: start_date = end_date = today
                
                df_logs['Date'] = pd.to_datetime(df_logs['Date'], errors='coerce').dt.date
                mask = (df_logs['Date'] >= start_date) & (df_logs['Date'] <= end_date)
                filtered_logs = df_logs.loc[mask].copy()
                
                if filtered_logs.empty: st.warning("No counts found for these dates.")
                else: 
                    filtered_logs['Date'] = filtered_logs['Date'].astype(str)
                    st.dataframe(filtered_logs, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_logs, use_container_width=True, hide_index=True)
            return

        # ==========================================
        # 📝 COUNTING MODE (THE MULTI-USER LEDGER)
        # ==========================================
        df_inv = conn.read(spreadsheet=sheet_link, worksheet="inventory", ttl=600)
        
        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filter & Search")
        
        # --- 1. OUTLET FILTER (LOCKED OR OPEN) ---
        all_outlets = list(df_inv['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_inv.columns else ["Main"]
        if assigned_outlet.lower() != 'all' and assigned_outlet != '':
            allowed_outlets = [assigned_outlet]
        else:
            allowed_outlets = all_outlets
            
        outlet_filter = st.sidebar.selectbox("🏢 Select Outlet", allowed_outlets, key="inv_out")

        # --- 2. LOCATION FILTER (LOCKED OR OPEN) ---
        if 'Location' in df_inv.columns:
            outlet_locs = list(df_inv[df_inv['Outlet'] == outlet_filter]['Location'].dropna().astype(str).unique())
        else:
            outlet_locs = []

        if assigned_location.lower() != 'all' and assigned_location != '':
            user_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
            allowed_locs = [loc for loc in outlet_locs if loc.lower() in user_locs]
        else:
            allowed_locs = outlet_locs

        loc_filter = st.sidebar.selectbox("📍 Select Location", allowed_locs, key="inv_loc") if allowed_locs else None
        
        # --- 3. STANDARD FILTERS ---
        categories = list(df_inv[(df_inv.get('Outlet') == outlet_filter) & (df_inv.get('Location') == loc_filter)]['Category'].dropna().unique()) if 'Category' in df_inv.columns else []
        cat_filter = st.sidebar.selectbox("Category", categories, key="inv_cat") if categories else None
        
        groups = list(df_inv[(df_inv.get('Outlet') == outlet_filter) & (df_inv.get('Location') == loc_filter) & (df_inv.get('Category') == cat_filter)]['Group'].dropna().unique()) if 'Group' in df_inv.columns else []
        grp_filter = st.sidebar.selectbox("Group", groups, key="inv_grp") if groups else None
        
        search_query = st.sidebar.text_input("Search Item", "", key="inv_search")
        
        # --- APPLY FILTERS ---
        filtered_df = df_inv.copy()
        if 'Outlet' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Outlet'] == outlet_filter]
        if 'Location' in filtered_df.columns and loc_filter:
            filtered_df = filtered_df[filtered_df['Location'] == loc_filter]
            
        if search_query:
            filtered_df = filtered_df[filtered_df['Product Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
        else:
            if cat_filter: filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
            if grp_filter: filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
            
        # --- THE TICKET FORM ---
        with st.form("mobile_inventory_form", clear_on_submit=True):
            st.info("💡 Enter quantities below. Only items with a quantity > 0 will be logged.")
            new_quantities = {}
            
            # THE FIX: This loop was missing in your pasted code!
            for index, row in filtered_df.iterrows():
                with st.container(border=True):
                    
                    col1, col2 = st.columns([1, 1], vertical_alignment="center")
                    with col1:
                        # THE FIX: Clean display, no Product Code shown on screen
                        st.markdown(f"**{row.get('Product Description', 'Unknown Item')}**")
                        st.caption(f"📦 Unit: {row.get('Unit', '')}")
                    with col2:
                        # step=0.1 allows for partial kg/liters
                        new_quantities[index] = st.number_input("Qty", value=0.0, min_value=0.0, step=0.1, key=f"qty_{index}", label_visibility="collapsed")
                        
            if st.form_submit_button("🚀 Submit Count Ticket", type="primary", use_container_width=True):
                # Grab the exact time in Lebanon right now!
                leb_tz = zoneinfo.ZoneInfo("Asia/Beirut")
                leb_time = datetime.now(leb_tz)
                records = []
                for idx, row in filtered_df.iterrows():
                    qty = new_quantities[idx]
                    if qty > 0:
                        records.append({
                            "Date": leb_time.strftime("%Y-%m-%d"),
                            "Time": leb_time.strftime("%H:%M:%S"),
                            "User": user,
                            "Outlet": outlet_filter,
                            "Location": loc_filter,
                            "Category": row.get('Category', ''),
                            "Group": row.get('Group', ''),
                            # THE FIX: The Product Code is still secretly saved to the database here!
                            "Product Code": row.get('Product Code', ''),
                            "Product Description": row.get('Product Description', ''),
                            "Qty": qty,
                            "Unit": row.get('Unit', '')
                        })
                
                if records:
                    df_logs = conn.read(spreadsheet=sheet_link, worksheet="inventory_logs", ttl=0)
                    df_new = pd.DataFrame(records)
                    updated_logs = pd.concat([df_logs, df_new], ignore_index=True)
                    conn.update(spreadsheet=sheet_link, worksheet="inventory_logs", data=updated_logs)
                    st.success(f"✅ Successfully logged {len(records)} items to the master ledger for {loc_filter}!")
                else:
                    st.warning("⚠️ No quantities entered. Nothing to save.")
    except Exception as e:
        st.error(f"Error loading Inventory module: {e}")