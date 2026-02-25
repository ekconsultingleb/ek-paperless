import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- THE CUMULATIVE WASTE LOGIC ---
def add_waste_entry(dict_key, row_dict, qty_key, rem_key):
    added_qty = st.session_state[qty_key]
    added_rem = st.session_state[rem_key]
    
    if added_qty > 0:
        if dict_key not in st.session_state['waste_notepad']:
            st.session_state['waste_notepad'][dict_key] = {
                'row_data': row_dict,
                'qty': 0.0,
                'remark': ""
            }
        
        st.session_state['waste_notepad'][dict_key]['qty'] += added_qty
        
        current_rem = st.session_state['waste_notepad'][dict_key]['remark']
        if added_rem.strip():
            if current_rem:
                st.session_state['waste_notepad'][dict_key]['remark'] = f"{current_rem} | {added_rem.strip()}"
            else:
                st.session_state['waste_notepad'][dict_key]['remark'] = added_rem.strip()
                
        st.session_state[qty_key] = 0.0
        st.session_state[rem_key] = ""

def undo_waste_entry(dict_key):
    if dict_key in st.session_state['waste_notepad']:
        del st.session_state['waste_notepad'][dict_key]


def render_waste(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown("### 🗑️ Daily Waste & Events")
    
    supabase = get_supabase()
    
    if 'waste_notepad' not in st.session_state:
        st.session_state['waste_notepad'] = {}

    try:
        # ==========================================
        # 1. FETCH DATA FROM DATABASE
        # ==========================================
        items_res = supabase.table("master_items").select("*").execute()
        df_master = pd.DataFrame(items_res.data)
        df_master.columns = [c.lower() for c in df_master.columns]

        archive_res = supabase.table("waste_logs").select("*").order("date", desc=True).limit(100).execute()
        df_archive = pd.DataFrame(archive_res.data)

        # ==========================================
        # 👁️ VIEWER MODE
        # ==========================================
        if role == "viewer":
            st.info("👁️ Viewer Mode: Showing Daily Waste Logs")
            if not df_archive.empty:
                st.dataframe(df_archive, use_container_width=True, hide_index=True)
            return

        # ==========================================
        # 📝 ENTRY MODE
        # ==========================================
        declaration = st.radio("Declaration Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event / Function"], horizontal=True, label_visibility="collapsed")
        waste_date = st.date_input("📅 Date of Event / Waste", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
        event_name = st.text_input("🏆 Enter Event Name") if declaration == "🎉 Event / Function" else ""

        # --- SIDEBAR FILTERS ---
        st.sidebar.subheader("🔍 Location")
        clients = list(df_master['client_name'].dropna().unique())
        client_filter = st.sidebar.selectbox("🏢 Client", clients)
        
        all_outlets = list(df_master[df_master['client_name'] == client_filter]['outlet'].dropna().unique())
        allowed_outlets = [assigned_outlet] if assigned_outlet.lower() != 'all' else all_outlets
        outlet_filter = st.sidebar.selectbox("🏠 Outlet", allowed_outlets)

        db_locations = sorted(list(df_master[df_master['outlet'] == outlet_filter]['location'].dropna().astype(str).str.upper().unique()))
        
        if str(assigned_location).lower() != "all":
            loc_filter = st.sidebar.selectbox("📍 Location", [assigned_location.upper()], disabled=True)
        else:
            loc_filter = st.sidebar.selectbox("📍 Location", db_locations)

        st.divider()

        # --- MAIN PAGE FILTERS ---
        st.subheader("🔍 Find Items to Log")
        
        # 🔴 CRITICAL FIX 1: Lowercase safety for Outlet
        df_outlet_items = df_master[df_master['outlet'].str.lower() == outlet_filter.lower()].copy()

        search_query = st.text_input("🔍 Quick Search", placeholder="Search any item (Overrides filters below)...")

        col_type, col_cat, col_grp = st.columns(3)
        
        with col_type:
            # This pulls unique types (e.g., 'Inventory', 'Menu Items')
            types = sorted(list(df_outlet_items['item_type'].dropna().astype(str).unique()))
            type_options = ["All"] + types
            type_filter = st.selectbox("📦 Item Type", type_options, index=0)

        with col_cat:
            # 🔴 CRITICAL FIX 2: Partial Matching for the "s" issue
            if type_filter == "All":
                df_cat_list = df_outlet_items
            else:
                # Use .str.contains to find "Menu" whether it has an 's' or not
                df_cat_list = df_outlet_items[df_outlet_items['item_type'].str.contains(type_filter, case=False, na=False)]
            
            cats = sorted(list(df_cat_list['category'].dropna().astype(str).unique()))
            cat_options = ["All"] + cats
            cat_filter = st.selectbox("📂 Category", cat_options, index=1 if cats else 0)
            
        with col_grp:
            df_grp_list = df_cat_list if cat_filter == "All" else df_cat_list[df_cat_list['category'] == cat_filter]
            grps = sorted(list(df_grp_list['sub_category'].dropna().astype(str).unique()))
            grp_options = ["All"] + grps
            grp_filter = st.selectbox("🏷️ Sub Category", grp_options, index=1 if grps else 0)

        # ==========================================
        # 🔴 THE SMART FILTERING LOGIC (CLEANED)
        # ==========================================
        if search_query:
            # Search override: Ignore dropdowns if user is typing
            filtered_df = df_outlet_items[df_outlet_items['item_name'].str.contains(search_query, case=False, na=False)]
        else:
            # Start with the full list and narrow it down
            filtered_df = df_outlet_items.copy()
            
            if type_filter != "All":
                # Partial match for "Menu" / "Inventory" safety
                filtered_df = filtered_df[filtered_df['item_type'].str.contains(type_filter, case=False, na=False)]
            
            if cat_filter != "All":
                filtered_df = filtered_df[filtered_df['category'] == cat_filter]
            
            if grp_filter != "All":
                filtered_df = filtered_df[filtered_df['sub_category'] == grp_filter]

        # ==========================================
        # Rest of your logic (History, Badges, Form)
        # ==========================================

        # --- 🚨 HISTORY ALERT ---
        today_str = waste_date.strftime("%Y-%m-%d")
        if not df_archive.empty and 'item_name' in df_archive.columns:
            already_logged = df_archive[(df_archive['date'] == today_str) & (df_archive['item_name'].isin(filtered_df['item_name']))]
            if not already_logged.empty:
                st.warning(f"⚠️ {len(already_logged)} items from this list were already logged for today.")

        # --- 🟢 LIVE PROGRESS BADGES ---
        total_items = len(filtered_df)
        counted_in_view = sum(1 for item in filtered_df['item_name'] if f"{outlet_filter}_{loc_filter}_{item}" in st.session_state['waste_notepad'])
        
        st.markdown(f"""
            <div style='display: flex; justify-content: space-between; background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
                <span style='color: #00ff00;'>✅ {counted_in_view} Logged</span>
                <span style='color: white;'>📝 {total_items} Items in {grp_filter}</span>
            </div>
        """, unsafe_allow_html=True)

        # --- LIVE TICKET FORM ---
        if filtered_df.empty:
            st.info("No items found matching the filters.")
        else:
            for index, row in filtered_df.iterrows():
                item_name = row.get('item_name', 'Unknown')
                dict_key = f"{outlet_filter}_{loc_filter}_{item_name}"
                
                cart_data = st.session_state['waste_notepad'].get(dict_key)
                current_total = cart_data['qty'] if cart_data else 0.0
                current_remark = cart_data['remark'] if cart_data else ""

                with st.container(border=True):
                    col_n, col_undo = st.columns([8, 2])
                    with col_n:
                        if current_total > 0:
                            st.markdown(f"🟢 **{item_name}** &nbsp;|&nbsp; ✅ Total: **{current_total}**")
                            if current_remark:
                                st.caption(f"📝 Remarks: {current_remark}")
                        else:
                            st.markdown(f"🔴 **{item_name}** &nbsp;|&nbsp; 📦 {row.get('count_unit', 'pcs')}")
                            
                    with col_undo:
                        if current_total > 0:
                            if st.button("🗑️ Undo", key=f"w_undo_{row.get('id', index)}"):
                                undo_waste_entry(dict_key)
                                st.rerun()

                    col_q, col_r, col_btn = st.columns([1.5, 3, 1], vertical_alignment="bottom")
                    qty_key = f"w_add_qty_{row.get('id', index)}"
                    rem_key = f"w_add_rem_{row.get('id', index)}"
                    
                    with col_q:
                        st.number_input("+ Qty", value=0.0, min_value=0.0, step=1.0, format="%g", key=qty_key)
                    with col_r:
                        st.text_input("Reason (Optional)", value="", key=rem_key, placeholder="e.g. dropped")
                    with col_btn:
                        st.button("➕ Add", key=f"w_btn_{row.get('id', index)}", on_click=add_waste_entry, args=(dict_key, row.to_dict(), qty_key, rem_key), use_container_width=True)

        # --- 🛒 REVIEW & SUBMIT ---
        st.divider()
        cart_size = len(st.session_state['waste_notepad'])
        if cart_size > 0:
            st.success(f"🛒 **{cart_size} items** ready to submit.")
            with st.expander("👀 Review & Submit Ticket", expanded=True):
                
                preview_list = []
                for k, v in st.session_state['waste_notepad'].items():
                    preview_list.append({
                        "Item": v['row_data'].get('item_name'),
                        "Total Wasted": v['qty'],
                        "Unit": v['row_data'].get('count_unit', ''),
                        "Remarks": v['remark']
                    })
                st.dataframe(pd.DataFrame(preview_list), use_container_width=True, hide_index=True)
                
                if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                    cart_data = []
                    for k, v in st.session_state['waste_notepad'].items():
                        row = v['row_data']
                        cat_text = str(row.get('category', '')).lower()
                        is_bev = any(x in cat_text for x in ['bev', 'drink', 'bar'])
                        
                        if declaration == "🗑️ Daily Waste": tag = "wb" if is_bev else "wf"
                        elif declaration == "🍽️ Staff Meal": tag = "smb" if is_bev else "sm" 
                        else: tag = f"theo - {event_name}"

                        cart_data.append({
                            "date": str(today_str),
                            "client_name": client_filter,
                            "outlet": outlet_filter,
                            "location": loc_filter,
                            "item_name": row.get('item_name'), 
                            "product_code": str(row.get('product_code', '')), 
                            "item_type": row.get('item_type', ''), 
                            "category": row.get('category'), 
                            "sub_category": row.get('sub_category'), 
                            "quantity": float(v['qty']),
                            "count_unit": row.get('count_unit', 'pcs'), 
                            "remarks": f"{tag} | {v['remark']}".strip(" | "),
                            "reported_by": user,
                            "status": "Submitted"
                        })
                    
                    try:
                        supabase.table("waste_logs").insert(cart_data).execute()
                        st.session_state['waste_notepad'] = {}
                        st.success("✅ Ticket Logged Successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    except Exception as e:
        st.error(f"❌ Error: {e}")