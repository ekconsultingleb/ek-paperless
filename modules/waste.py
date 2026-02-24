import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo

def update_waste_cart(item_key, row_data, qty_key, rem_key):
    qty = st.session_state[qty_key]
    rem = st.session_state[rem_key]
    if qty is not None and qty > 0:
        st.session_state['waste_notepad'][item_key] = {
            'row_data': row_data, 'Qty': qty, 'Remark': rem
        }
    else:
        if item_key in st.session_state['waste_notepad']:
            del st.session_state['waste_notepad'][item_key]

def render_waste(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown(f"### 🗑️ Daily Waste & Events")
    
    if 'waste_notepad' not in st.session_state:
        st.session_state['waste_notepad'] = {}

    try:
        # ==========================================
        # 👁️ VIEWER MODE
        # ==========================================
        if role == "viewer":
            st.info("👁️ **Data Entry Mode:** View Daily Tickets.")
            df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=0)
            if assigned_outlet.lower() != 'all' and assigned_outlet != '' and 'Outlet' in df_archive.columns:
                df_archive = df_archive[df_archive['Outlet'] == assigned_outlet]
            if assigned_location.lower() != 'all' and assigned_location != '' and 'Location' in df_archive.columns:
                allowed_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
                df_archive = df_archive[df_archive['Location'].astype(str).str.lower().isin(allowed_locs)]
            
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            date_selection = st.date_input("📅 Select Date Range", value=(today, today))
            if 'Archive Date' in df_archive.columns:
                if len(date_selection) == 2: start_date, end_date = date_selection
                elif len(date_selection) == 1: start_date = end_date = date_selection[0]
                else: start_date = end_date = today
                df_archive['Archive Date'] = pd.to_datetime(df_archive['Archive Date'], errors='coerce').dt.date
                mask = (df_archive['Archive Date'] >= start_date) & (df_archive['Archive Date'] <= end_date)
                filtered_archive = df_archive.loc[mask].copy()
                if filtered_archive.empty: st.warning("No waste logged for these dates.")
                else: 
                    filtered_archive['Archive Date'] = filtered_archive['Archive Date'].astype(str)
                    st.dataframe(filtered_archive, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_archive, use_container_width=True, hide_index=True)
            return

        # ==========================================
        # 📝 COUNTING MODE
        # ==========================================
        df_waste = conn.read(spreadsheet=sheet_link, worksheet="waste", ttl=60)
        
        declaration = st.radio("Declaration Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event / Function"], horizontal=True, label_visibility="collapsed")
        waste_date = st.date_input("📅 Date of Event / Waste", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
        event_name = st.text_input("🏆 Enter Event Name (if applicable)") if declaration == "🎉 Event / Function" else ""

        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filter Location")
        all_outlets = list(df_waste['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_waste.columns else ["Main"]
        allowed_outlets = [assigned_outlet] if assigned_outlet.lower() != 'all' and assigned_outlet != '' else all_outlets
        outlet_filter = st.sidebar.selectbox("🏢 Select Outlet", allowed_outlets, key="w_out")

        outlet_locs = list(df_waste[df_waste['Outlet'] == outlet_filter]['Location'].dropna().astype(str).unique()) if 'Location' in df_waste.columns else []
        if assigned_location.lower() != 'all' and assigned_location != '':
            user_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
            allowed_locs = [loc for loc in outlet_locs if loc.lower() in user_locs]
        else:
            allowed_locs = outlet_locs

        loc_filter = st.sidebar.selectbox("📍 Select Location", allowed_locs, key="w_loc") if allowed_locs else None

        statuses = list(df_waste[(df_waste.get('Outlet') == outlet_filter) & (df_waste.get('Location') == loc_filter)]['Status'].dropna().unique()) if 'Status' in df_waste.columns else []
        stat_filter = st.sidebar.selectbox("Status", statuses, key="w_stat") if statuses else None
        
        valid_cats = list(df_waste[(df_waste.get('Outlet') == outlet_filter) & (df_waste.get('Location') == loc_filter) & (df_waste.get('Status') == stat_filter)]['Category'].dropna().unique()) if 'Category' in df_waste.columns else []
        cat_filter = st.sidebar.selectbox("Category", valid_cats, key="w_cat") if valid_cats else None
        
        col_f1, col_f2 = st.columns(2)
        valid_grps = list(df_waste[(df_waste.get('Outlet') == outlet_filter) & (df_waste.get('Location') == loc_filter) & (df_waste.get('Status') == stat_filter) & (df_waste.get('Category') == cat_filter)]['Group'].dropna().unique()) if 'Group' in df_waste.columns else []
        
        with col_f1:
            grp_filter = st.selectbox("Group", valid_grps, key="w_main_grp", label_visibility="collapsed") if valid_grps else None
        with col_f2:
            search_query = st.text_input("Search", "", placeholder="🔍 Search...", key="w_main_search", label_visibility="collapsed")
        
        st.divider()

        filtered_df = df_waste.copy()
        if 'Outlet' in filtered_df.columns: filtered_df = filtered_df[filtered_df['Outlet'] == outlet_filter]
        if 'Location' in filtered_df.columns and loc_filter: filtered_df = filtered_df[filtered_df['Location'] == loc_filter]

        if search_query:
            filtered_df = filtered_df[filtered_df['Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
        else:
            if stat_filter: filtered_df = filtered_df[filtered_df['Status'] == stat_filter]
            if cat_filter: filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
            if grp_filter: filtered_df = filtered_df[filtered_df['Group'] == grp_filter]

        # --- 🚨 HISTORY ALERT ---
        leb_tz = zoneinfo.ZoneInfo("Asia/Beirut")
        today_str = waste_date.strftime("%Y-%m-%d")
        df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=0)
        
        if not search_query and grp_filter and 'Archive Date' in df_archive.columns:
            already_logged = df_archive[(df_archive['Archive Date'].astype(str) == today_str) & 
                                        (df_archive['Outlet'] == outlet_filter) & 
                                        (df_archive['Location'] == loc_filter) & 
                                        (df_archive['Group'] == grp_filter)]
            if not already_logged.empty:
                st.warning(f"⚠️ **Heads up!** '{grp_filter}' was already submitted for this date ({len(already_logged)} items).")

        # --- 🟢 PROGRESS TRACKER ---
        total_items = len(filtered_df)
        counted_items = sum(1 for _, row in filtered_df.iterrows() if f"{outlet_filter}_{loc_filter}_{row.get('Description', '')}" in st.session_state['waste_notepad'])
        st.markdown(f"**Progress:** 🟢 {counted_items} / {total_items} Items Logged")

        # --- LIVE TICKET FORM ---
        for index, row in filtered_df.iterrows():
            item_name = row.get('Description', 'Unknown Item')
            dict_key = f"{outlet_filter}_{loc_filter}_{item_name}"
            
            cart_item = st.session_state['waste_notepad'].get(dict_key, {})
            in_cart_qty = cart_item.get('Qty', 0)
            in_cart_rem = cart_item.get('Remark', "")

            with st.container(border=True):
                p_code = row.get('Product Code / Menu Code', '')
                code_display = f"**[{p_code}]** " if pd.notna(p_code) and str(p_code).strip() != "" else ""
                
                if in_cart_qty > 0:
                    st.markdown(f"🟢 {code_display}**{item_name}** &nbsp;|&nbsp; ✅ **{in_cart_qty}**")
                else:
                    st.markdown(f"{code_display}**{item_name}** &nbsp;|&nbsp; 📦 {row.get('Unit', '')}")
                
                col1, col2 = st.columns([1, 1.5], vertical_alignment="center")
                qty_key = f"w_qty_{index}_{dict_key}"
                rem_key = f"w_rem_{index}_{dict_key}"
                
                row_data_dict = row.to_dict()
                
                with col1:
                    st.number_input("Qty", value=in_cart_qty if in_cart_qty > 0 else None, min_value=0.0, step=1.0, 
                                    placeholder="0.0", key=qty_key, label_visibility="collapsed",
                                    on_change=update_waste_cart, args=(dict_key, row_data_dict, qty_key, rem_key))
                with col2:
                    st.text_input("Remark", value=in_cart_rem, key=rem_key, placeholder="Optional remark...", 
                                  label_visibility="collapsed",
                                  on_change=update_waste_cart, args=(dict_key, row_data_dict, qty_key, rem_key))

        # --- 🛒 BOTTOM CART & SUBMIT ---
        st.divider()
        cart_size = len(st.session_state['waste_notepad'])
        if cart_size > 0:
            st.success(f"🛒 **{cart_size} items** ready to submit.")
            with st.expander("👀 Review & Submit Ticket", expanded=True):
                if st.button("🚀 SUBMIT TICKET", type="primary", use_container_width=True):
                    if declaration == "🎉 Event / Function" and not event_name:
                        st.error("🛑 Please enter the Event Name.")
                    else:
                        ticket_items = []
                        for dict_key, data in st.session_state['waste_notepad'].items():
                            qty = data['Qty']
                            rem = data['Remark']
                            base_row = data['row_data']
                            
                            cat_text = str(base_row.get('Category', '')).lower()
                            is_bev = 'bev' in cat_text or 'drink' in cat_text or 'bar' in cat_text
                            
                            if declaration == "🗑️ Daily Waste": tag = "wb" if is_bev else "wf"
                            elif declaration == "🍽️ Staff Meal": tag = "smb" if is_bev else "sm" 
                            elif declaration == "🎉 Event / Function": tag = f"theo b - {event_name}" if is_bev else f"theo f - {event_name}"
                            
                            new_row = base_row.copy()
                            new_row['Qty'] = qty
                            chef_remark = rem.strip()
                            new_row['Remarks'] = f"{tag} - {chef_remark}" if chef_remark else tag
                            new_row['Archive Date'] = waste_date.strftime("%Y-%m-%d") 
                            new_row['Outlet'] = outlet_filter 
                            new_row['Location'] = loc_filter
                            ticket_items.append(new_row)
                        
                        df_ticket = pd.DataFrame(ticket_items)
                        updated_archive = pd.concat([df_archive, df_ticket], ignore_index=True)
                        conn.update(spreadsheet=sheet_link, worksheet="archive_waste", data=updated_archive)
                        
                        st.session_state['waste_notepad'] = {}
                        st.success(f"✅ {declaration} logged successfully!")
                        st.rerun()

                if st.button("🗑️ Clear Ticket", use_container_width=True):
                    st.session_state['waste_notepad'] = {}
                    st.rerun()

    except Exception as e:
        st.error(f"Error loading Waste module: {e}")
