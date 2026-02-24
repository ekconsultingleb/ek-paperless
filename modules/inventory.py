import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo

def update_cart_item(item_key, item_data, widget_key):
    new_qty = st.session_state[widget_key]
    if new_qty is not None and new_qty > 0:
        item_data['Qty'] = new_qty
        st.session_state['inv_notepad'][item_key] = item_data
    else:
        if item_key in st.session_state['inv_notepad']:
            del st.session_state['inv_notepad'][item_key]

def render_inventory(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown(f"### 📦 Inventory Count")
    
    if 'inv_notepad' not in st.session_state:
        st.session_state['inv_notepad'] = {}

    try:
        # ==========================================
        # 👁️ VIEWER MODE
        # ==========================================
        if role == "viewer":
            st.info("👁️ **Data Entry Mode:** View Consolidated Inventory Logs.")
            df_logs = conn.read(spreadsheet=sheet_link, worksheet="inventory_logs", ttl=0)
            
            if assigned_outlet.lower() != 'all' and assigned_outlet != '' and 'Outlet' in df_logs.columns:
                df_logs = df_logs[df_logs['Outlet'] == assigned_outlet]
            if assigned_location.lower() != 'all' and assigned_location != '' and 'Location' in df_logs.columns:
                allowed_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
                df_logs = df_logs[df_logs['Location'].astype(str).str.lower().isin(allowed_locs)]
            
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
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
        # 📝 COUNTING MODE
        # ==========================================
        df_inv = conn.read(spreadsheet=sheet_link, worksheet="inventory", ttl=0)
        
        st.sidebar.subheader("🔍 Filter Location")
        all_outlets = list(df_inv['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_inv.columns else ["Main"]
        allowed_outlets = [assigned_outlet] if assigned_outlet.lower() != 'all' and assigned_outlet != '' else all_outlets
        outlet_filter = st.sidebar.selectbox("🏢 Select Outlet", allowed_outlets, key="inv_out")

        outlet_locs = list(df_inv[df_inv['Outlet'] == outlet_filter]['Location'].dropna().astype(str).unique()) if 'Location' in df_inv.columns else []
        if assigned_location.lower() != 'all' and assigned_location != '':
            user_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
            allowed_locs = [loc for loc in outlet_locs if loc.lower() in user_locs]
        else:
            allowed_locs = outlet_locs

        loc_filter = st.sidebar.selectbox("📍 Select Location", allowed_locs, key="inv_loc") if allowed_locs else None
        
        categories = list(df_inv[(df_inv.get('Outlet') == outlet_filter) & (df_inv.get('Location') == loc_filter)]['Category'].dropna().unique()) if 'Category' in df_inv.columns else []
        cat_filter = st.sidebar.selectbox("Category", categories, key="inv_cat") if categories else None
        
        col_f1, col_f2 = st.columns(2)
        groups = list(df_inv[(df_inv.get('Outlet') == outlet_filter) & (df_inv.get('Location') == loc_filter) & (df_inv.get('Category') == cat_filter)]['Group'].dropna().unique()) if 'Group' in df_inv.columns else []
        
        with col_f1:
            grp_filter = st.selectbox("Group", groups, key="main_grp", label_visibility="collapsed") if groups else None
        with col_f2:
            search_query = st.text_input("Search", "", placeholder="🔍 Search...", key="main_search", label_visibility="collapsed")
            
        st.divider()
        
        filtered_df = df_inv.copy()
        if 'Outlet' in filtered_df.columns: filtered_df = filtered_df[filtered_df['Outlet'] == outlet_filter]
        if 'Location' in filtered_df.columns and loc_filter: filtered_df = filtered_df[filtered_df['Location'] == loc_filter]
        if cat_filter: filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
            
        if search_query:
            filtered_df = filtered_df[filtered_df['Product Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
        elif grp_filter:
            filtered_df = filtered_df[filtered_df['Group'] == grp_filter]

        # --- 🚨 HISTORY ALERT ---
        leb_tz = zoneinfo.ZoneInfo("Asia/Beirut")
        today_str = datetime.now(leb_tz).strftime("%Y-%m-%d")
        df_logs = conn.read(spreadsheet=sheet_link, worksheet="inventory_logs", ttl=0)
        
        if not search_query and grp_filter and 'Date' in df_logs.columns:
            already_logged = df_logs[(df_logs['Date'].astype(str) == today_str) & 
                                     (df_logs['Outlet'] == outlet_filter) & 
                                     (df_logs['Location'] == loc_filter) & 
                                     (df_logs['Group'] == grp_filter)]
            if not already_logged.empty:
                st.warning(f"⚠️ **Heads up!** '{grp_filter}' was already submitted today ({len(already_logged)} items logged).")

        # --- 🟢 PROGRESS TRACKER ---
        total_items = len(filtered_df)
        counted_items = 0
        for _, row in filtered_df.iterrows():
            if f"{outlet_filter}_{loc_filter}_{row.get('Product Description', '')}" in st.session_state['inv_notepad']:
                counted_items += 1
        
        st.markdown(f"**Progress:** 🟢 {counted_items} / {total_items} Items Counted")

        # --- LIVE COUNT FORM ---
        for index, row in filtered_df.iterrows():
            item_name = row.get('Product Description', 'Unknown Item')
            dict_key = f"{outlet_filter}_{loc_filter}_{item_name}"
            in_cart_qty = st.session_state['inv_notepad'].get(dict_key, {}).get('Qty', 0)

            with st.container(border=True):
                col1, col2 = st.columns([1, 1], vertical_alignment="center")
                with col1:
                    if in_cart_qty > 0:
                        st.markdown(f"🟢 **{item_name}**")
                        st.caption(f"📦 {row.get('Unit', '')} &nbsp;|&nbsp; ✅ **{in_cart_qty}**")
                    else:
                        st.markdown(f"**{item_name}**")
                        st.caption(f"📦 {row.get('Unit', '')}")
                with col2:
                    current_val = in_cart_qty if in_cart_qty > 0 else None
                    item_data = {
                        "Outlet": outlet_filter, "Location": loc_filter, "Category": row.get('Category', ''),
                        "Group": row.get('Group', ''), "Product Code": row.get('Product Code', ''),
                        "Product Description": item_name, "Qty": 0, "Unit": row.get('Unit', '')
                    }
                    widget_key = f"qty_{index}_{dict_key}"
                    st.number_input("Qty", value=current_val, min_value=0.0, step=1.0, format="%.1f", 
                                    placeholder="0.0", key=widget_key, label_visibility="collapsed",
                                    on_change=update_cart_item, args=(dict_key, item_data, widget_key))

        # --- 🛒 BOTTOM CART & SUBMIT ---
        st.divider()
        cart_size = len(st.session_state['inv_notepad'])
        if cart_size > 0:
            st.success(f"🛒 **{cart_size} items** ready in cart.")
            with st.expander("👀 Review & Submit Cart", expanded=True):
                df_cart = pd.DataFrame(list(st.session_state['inv_notepad'].values()))
                st.dataframe(df_cart[['Location', 'Product Description', 'Qty']], use_container_width=True, hide_index=True)
                
                colA, colB = st.columns(2)
                with colA:
                    if st.button("🚀 SUBMIT TO DATABASE", type="primary", use_container_width=True):
                        leb_time = datetime.now(leb_tz)
                        records = []
                        for key, v in st.session_state['inv_notepad'].items():
                            v['Date'] = leb_time.strftime("%Y-%m-%d")
                            v['Time'] = leb_time.strftime("%H:%M:%S")
                            v['User'] = user
                            records.append(v)
                        
                        df_new = pd.DataFrame(records)
                        updated_logs = pd.concat([df_logs, df_new], ignore_index=True)
                        conn.update(spreadsheet=sheet_link, worksheet="inventory_logs", data=updated_logs)
                        st.session_state['inv_notepad'] = {} 
                        st.success(f"✅ {len(records)} items synced!")
                        st.rerun()
                with colB:
                    if st.button("🗑️ Clear Cart", use_container_width=True):
                        st.session_state['inv_notepad'] = {}
                        st.rerun()

        # --- ADD MISSING ITEM ---
        with st.expander("➕ Missing an Item? Add it to Database"):
            all_db_cats = list(df_inv['Category'].dropna().unique()) if 'Category' in df_inv.columns else ["Food", "Beverage"]
            all_db_grps = list(df_inv['Group'].dropna().unique()) if 'Group' in df_inv.columns else ["General"]
            all_db_units = list(df_inv['Unit'].dropna().unique()) if 'Unit' in df_inv.columns else ["KG", "PCS", "LITRE"]
            
            with st.form("add_new_item_form", clear_on_submit=False):
                new_item_name = st.text_input("Product Name", placeholder="e.g. Red Bull")
                cA, cB = st.columns(2)
                with cA:
                    new_cat = st.selectbox("Category", all_db_cats)
                    new_unit = st.selectbox("Unit", all_db_units)
                with cB:
                    new_grp = st.selectbox("Group", all_db_grps)
                    new_code = st.text_input("Product Code (Optional)")
                    
                if st.form_submit_button("💾 Add to Database", type="primary", use_container_width=True):
                    if not new_item_name.strip():
                        st.error("🛑 Enter a Product Name.")
                    else:
                        clean_input = new_item_name.strip().lower().replace(" ", "")
                        existing_items_clean = df_inv['Product Description'].astype(str).str.lower().str.replace(" ", "").tolist()
                        
                        if clean_input in existing_items_clean:
                            st.error(f"🛑 **{new_item_name}** already exists! Use the search bar.")
                        else:
                            new_row = pd.DataFrame([{
                                "Outlet": outlet_filter, "Location": loc_filter, "Category": new_cat,
                                "Group": new_grp, "Product Code": new_code, 
                                "Product Description": new_item_name.strip().title(), "Unit": new_unit
                            }])
                            updated_inv = pd.concat([df_inv, new_row], ignore_index=True)
                            conn.update(spreadsheet=sheet_link, worksheet="inventory", data=updated_inv)
                            st.success(f"✅ {new_item_name.title()} added! Refresh to count it.")

    except Exception as e:
        st.error(f"Error: {e}")
