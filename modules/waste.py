import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

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

        # --- SIDEBAR FILTERS (Only High-Level Locations) ---
        st.sidebar.subheader("🔍 Location")
        clients = list(df_master['client_name'].dropna().unique())
        client_filter = st.sidebar.selectbox("🏢 Client", clients)
        
        all_outlets = list(df_master[df_master['client_name'] == client_filter]['outlet'].dropna().unique())
        allowed_outlets = [assigned_outlet] if assigned_outlet.lower() != 'all' else all_outlets
        outlet_filter = st.sidebar.selectbox("🏠 Outlet", allowed_outlets)

        locations = ["MED", "WAREHOUSE", "CHALET", "BAR"]
        if str(assigned_location).lower() != "all":
            loc_filter = st.sidebar.selectbox("📍 Location", [assigned_location], disabled=True)
        else:
            loc_filter = st.sidebar.selectbox("📍 Location", locations)

        st.divider()

        # --- MAIN PAGE FILTERS (Category & Group in the middle!) ---
        st.subheader("🔍 Find Items")
        col_cat, col_grp = st.columns(2)
        
        with col_cat:
            cats = list(df_master[(df_master['client_name'] == client_filter) & (df_master['outlet'] == outlet_filter)]['category'].dropna().unique())
            cat_filter = st.selectbox("📂 Category", cats)
            
        with col_grp:
            grps = list(df_master[(df_master['outlet'] == outlet_filter) & (df_master['category'] == cat_filter)]['sub_category'].dropna().unique())
            grp_filter = st.selectbox("🏷️ Sub Category", grps)

        search_query = st.text_input("Search", "", placeholder="🔍 Quick search item name...", label_visibility="collapsed")

        # Apply Filters to Display
        filtered_df = df_master[
            (df_master['outlet'] == outlet_filter) & 
            (df_master['category'] == cat_filter) & 
            (df_master['sub_category'] == grp_filter)
        ].copy()

        if search_query:
            filtered_df = df_master[df_master['item_name'].str.contains(search_query, case=False, na=False)]

        # --- 🚨 HISTORY ALERT ---
        today_str = waste_date.strftime("%Y-%m-%d")
        if not df_archive.empty and 'item_name' in df_archive.columns:
            already_logged = df_archive[(df_archive['date'] == today_str) & (df_archive['item_name'].isin(filtered_df['item_name']))]
            if not already_logged.empty:
                st.warning(f"⚠️ {len(already_logged)} items already logged for today.")

        # --- LIVE TICKET FORM ---
        if filtered_df.empty:
            st.info("No items found matching the filters.")
        else:
            for index, row in filtered_df.iterrows():
                item_name = row.get('item_name', 'Unknown')
                dict_key = f"{outlet_filter}_{item_name}"
                
                cart_item = st.session_state['waste_notepad'].get(dict_key, {})
                in_cart_qty = cart_item.get('Qty', 0.0)
                in_cart_rem = cart_item.get('Remark', "")

                with st.container(border=True):
                    col_n, col_q, col_r = st.columns([2, 1, 1.5])
                    with col_n:
                        st.markdown(f"**{item_name}**")
                        st.caption(f"Unit: {row.get('count_unit', 'pcs')} | Code: {row.get('product_code', 'N/A')}")
                    
                    qty_key = f"w_qty_{row.get('id', index)}"
                    rem_key = f"w_rem_{row.get('id', index)}"
                    
                    with col_q:
                        st.number_input("Qty", value=float(in_cart_qty) if in_cart_qty > 0 else 0.0, min_value=0.0, key=qty_key, 
                                        on_change=update_waste_cart, args=(dict_key, row.to_dict(), qty_key, rem_key), label_visibility="collapsed")
                    with col_r:
                        st.text_input("Remark", value=in_cart_rem, key=rem_key, placeholder="Reason...", 
                                      on_change=update_waste_cart, args=(dict_key, row.to_dict(), qty_key, rem_key), label_visibility="collapsed")

        # --- 🛒 SUBMIT ---
        st.divider()
        if st.session_state['waste_notepad']:
            with st.expander("👀 Review & Submit Ticket", expanded=True):
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
                        "quantity": float(v['Qty']),
                        "count_unit": row.get('count_unit', 'pcs'), 
                        "remarks": f"{tag} | {v['Remark']}".strip(" | "),
                        "reported_by": user,
                        "status": "Submitted"
                    })
                
                st.table(pd.DataFrame(cart_data)[['item_name', 'quantity', 'remarks']])
                
                if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                    supabase.table("waste_logs").insert(cart_data).execute()
                    st.session_state['waste_notepad'] = {}
                    st.success("✅ Ticket Logged Successfully!")
                    st.rerun()

    except Exception as e:
        st.error(f"❌ Error: {e}")