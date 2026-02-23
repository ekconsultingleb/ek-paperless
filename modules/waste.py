import streamlit as st
import pandas as pd
from datetime import datetime

def render_waste(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown(f"### 🗑️ Daily Waste & Events")
    try:
        # ==========================================
        # 👁️ VIEWER MODE (KHALDOUN / MANAGERS)
        # ==========================================
        if role == "viewer":
            st.info("👁️ **Data Entry Mode:** View Daily Tickets for POS/Omega Entry.")
            df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=0)
            
            # --- OUTLET & LOCATION SECURITY LOCKS ---
            if assigned_outlet.lower() != 'all' and assigned_outlet != '' and 'Outlet' in df_archive.columns:
                df_archive = df_archive[df_archive['Outlet'] == assigned_outlet]
                
            if assigned_location.lower() != 'all' and assigned_location != '' and 'Location' in df_archive.columns:
                # Splits "Med, Warehouse" into a list the app can read perfectly
                allowed_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
                df_archive = df_archive[df_archive['Location'].astype(str).str.lower().isin(allowed_locs)]
            
            # Date Range Picker
            today = datetime.now().date()
            date_selection = st.date_input("📅 Select Date Range (From - To)", value=(today, today))
            
            if 'Archive Date' in df_archive.columns:
                if len(date_selection) == 2:
                    start_date, end_date = date_selection
                elif len(date_selection) == 1:
                    start_date = end_date = date_selection[0]
                else:
                    start_date = end_date = today
                
                df_archive['Archive Date'] = pd.to_datetime(df_archive['Archive Date'], errors='coerce').dt.date
                mask = (df_archive['Archive Date'] >= start_date) & (df_archive['Archive Date'] <= end_date)
                filtered_archive = df_archive.loc[mask].copy()
                
                if filtered_archive.empty:
                    st.warning(f"No waste logged between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}.")
                else:
                    filtered_archive['Archive Date'] = filtered_archive['Archive Date'].astype(str)
                    st.dataframe(filtered_archive, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_archive, use_container_width=True, hide_index=True)
            return

        # ==========================================
        # 📝 COUNTING MODE (THE LEDGER TICKETS)
        # ==========================================
        df_waste = conn.read(spreadsheet=sheet_link, worksheet="waste", ttl=60)
        
        st.info("👇 **Step 1: What are you logging?**")
        declaration = st.radio("Declaration Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event / Function"], horizontal=True, label_visibility="collapsed")
        
        waste_date = st.date_input("📅 Date of Event / Waste", datetime.now())

        event_name = ""
        if declaration == "🎉 Event / Function":
            event_name = st.text_input("🏆 Enter Event Name (e.g. Smith Wedding)")

        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filter & Search")
        
        # --- 1. OUTLET FILTER (LOCKED OR OPEN) ---
        all_outlets = list(df_waste['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_waste.columns else ["Main"]
        if assigned_outlet.lower() != 'all' and assigned_outlet != '':
            allowed_outlets = [assigned_outlet]
        else:
            allowed_outlets = all_outlets
            
        outlet_filter = st.sidebar.selectbox("🏢 Select Outlet", allowed_outlets, key="w_out")

        # --- 2. LOCATION FILTER (LOCKED OR OPEN) ---
        if 'Location' in df_waste.columns:
            outlet_locs = list(df_waste[df_waste['Outlet'] == outlet_filter]['Location'].dropna().astype(str).unique())
        else:
            outlet_locs = []

        if assigned_location.lower() != 'all' and assigned_location != '':
            user_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
            allowed_locs = [loc for loc in outlet_locs if loc.lower() in user_locs]
        else:
            allowed_locs = outlet_locs

        loc_filter = st.sidebar.selectbox("📍 Select Location", allowed_locs, key="w_loc") if allowed_locs else None

        # --- 3. STANDARD FILTERS ---
        statuses = list(df_waste[(df_waste.get('Outlet') == outlet_filter) & (df_waste.get('Location') == loc_filter)]['Status'].dropna().unique()) if 'Status' in df_waste.columns else []
        stat_filter = st.sidebar.selectbox("Status", statuses, key="w_stat") if statuses else None
        
        valid_cats = list(df_waste[(df_waste.get('Outlet') == outlet_filter) & (df_waste.get('Location') == loc_filter) & (df_waste.get('Status') == stat_filter)]['Category'].dropna().unique()) if 'Category' in df_waste.columns else []
        cat_filter = st.sidebar.selectbox("Category", valid_cats, key="w_cat") if valid_cats else None
        
        valid_grps = list(df_waste[(df_waste.get('Outlet') == outlet_filter) & (df_waste.get('Location') == loc_filter) & (df_waste.get('Status') == stat_filter) & (df_waste.get('Category') == cat_filter)]['Group'].dropna().unique()) if 'Group' in df_waste.columns else []
        grp_filter = st.sidebar.selectbox("Group", valid_grps, key="w_grp") if valid_grps else None
        
        search_query = st.sidebar.text_input("Search Item", "", key="w_search")
        
        # --- APPLY FILTERS ---
        filtered_df = df_waste.copy()
        if 'Outlet' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Outlet'] == outlet_filter]
        if 'Location' in filtered_df.columns and loc_filter:
            filtered_df = filtered_df[filtered_df['Location'] == loc_filter]

        if search_query:
            filtered_df = filtered_df[filtered_df['Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
        else:
            if stat_filter: filtered_df = filtered_df[filtered_df['Status'] == stat_filter]
            if cat_filter: filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
            if grp_filter: filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
            
        # --- THE TICKET FORM ---
        with st.form("waste_ticket_form", clear_on_submit=True):
            st.info("💡 Enter quantities below. Only items with a quantity > 0 will be logged.")
            new_quantities = {}
            new_remarks = {}
            for index, row in filtered_df.iterrows():
                with st.container(border=True):
                    
                    # Beautifully formats the Product Code if it exists!
                    p_code = row.get('Product Code / Menu Code', '')
                    code_display = f"**[{p_code}]** " if pd.notna(p_code) and str(p_code).strip() != "" else ""
                    
                    st.markdown(f"{code_display}**{row.get('Description', 'Unknown')}** &nbsp;|&nbsp; 📦 {row.get('Unit', '')}")
                    col1, col2 = st.columns([1, 1.5], vertical_alignment="center")
                    with col1:
                        new_quantities[index] = st.number_input("Qty", value=0.0, min_value=0.0, step=1.0, key=f"w_qty_{index}", label_visibility="collapsed")
                    with col2:
                        new_remarks[index] = st.text_input("Remark", value="", key=f"w_rem_{index}", placeholder="Optional remark...", label_visibility="collapsed")
                        
            if st.form_submit_button("🚀 Submit Ticket", type="primary", use_container_width=True):
                if declaration == "🎉 Event / Function" and not event_name:
                    st.error("🛑 Please enter the Event Name.")
                else:
                    ticket_items = []
                    for idx, row in filtered_df.iterrows():
                        qty = new_quantities[idx]
                        if qty > 0:
                            cat_text = str(row.get('Category', '')).lower()
                            is_bev = 'bev' in cat_text or 'drink' in cat_text or 'bar' in cat_text
                            
                            # TAG GENERATION
                            if declaration == "🗑️ Daily Waste": tag = "wb" if is_bev else "wf"
                            elif declaration == "🍽️ Staff Meal": tag = "smb" if is_bev else "sm" 
                            elif declaration == "🎉 Event / Function": tag = f"theo b - {event_name}" if is_bev else f"theo f - {event_name}"
                            
                            new_row = row.copy()
                            new_row['Qty'] = qty
                            
                            chef_remark = new_remarks[idx].strip()
                            if chef_remark:
                                new_row['Remarks'] = f"{tag} - {chef_remark}"
                            else:
                                new_row['Remarks'] = tag
                                
                            new_row['Archive Date'] = waste_date.strftime("%Y-%m-%d") 
                            new_row['Outlet'] = outlet_filter 
                            new_row['Location'] = loc_filter
                            ticket_items.append(new_row)
                    
                    if ticket_items:
                        df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=0)
                        df_ticket = pd.DataFrame(ticket_items)
                        updated_archive = pd.concat([df_archive, df_ticket], ignore_index=True)
                        conn.update(spreadsheet=sheet_link, worksheet="archive_waste", data=updated_archive)
                        st.success(f"✅ {declaration} logged successfully to {outlet_filter} ({loc_filter})!")
                    else:
                        st.warning("⚠️ No quantities entered. Nothing to save.")
                        
    except Exception as e:
        st.error(f"Error loading Waste module: {e}")