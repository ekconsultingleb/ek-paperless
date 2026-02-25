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
                
        # Reset inputs
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
        # 1. FETCH OUTLETS FOR SIDEBAR
        nav_res = supabase.table("master_items").select("outlet, client_name").execute()
        df_nav = pd.DataFrame(nav_res.data)
        
        client_list = sorted(df_nav['client_name'].dropna().unique())
        client_filter = st.sidebar.selectbox("🏢 Client", client_list)
        
        outlet_options = sorted(df_nav[df_nav['client_name'] == client_filter]['outlet'].dropna().unique())
        final_outlet = assigned_outlet if assigned_outlet.lower() != 'all' else st.sidebar.selectbox("🏠 Outlet", outlet_options)

        # 2. MEGA-FETCH LOOP (PAGINATION)
        # This bypasses the 1,000 row limit to reach row 2,000+
        all_items = []
        page_size = 1000
        start_row = 0
        
        while True:
            res = supabase.table("master_items").select("*").eq("outlet", final_outlet).range(start_row, start_row + page_size - 1).execute()
            if not res.data:
                break
            all_items.extend(res.data)
            if len(res.data) < page_size:
                break
            start_row += page_size

        df_items = pd.DataFrame(all_items)
        df_items.columns = [c.lower() for c in df_items.columns]

        # 3. LOCATION SETUP
        db_locs = sorted(df_items['location'].dropna().astype(str).str.upper().unique())
        loc_filter = st.sidebar.selectbox("📍 Location", [assigned_location.upper()] if assigned_location.lower() != 'all' else db_locs)

        # 4. ENTRY TYPE & DATE
        declaration = st.radio("Declaration Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event / Function"], horizontal=True, label_visibility="collapsed")
        waste_date = st.date_input("📅 Date of Event / Waste", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
        event_name = st.text_input("🏆 Event Name") if declaration == "🎉 Event / Function" else ""

        st.divider()

        # 5. FILTERS
        st.subheader("🔍 Find Items")
        search_query = st.text_input("🔍 Quick Search", placeholder="Type item name...")

        col1, col2 = st.columns(2)
        with col1:
            cats = sorted(df_items['category'].dropna().astype(str).unique())
            cat_filter = st.selectbox("📂 Category", ["All"] + cats, index=0)
        with col2:
            df_sub = df_items if cat_filter == "All" else df_items[df_items['category'] == cat_filter]
            sub_cats = sorted(df_sub['sub_category'].dropna().astype(str).unique())
            sub_filter = st.selectbox("🏷️ Sub Category", ["All"] + sub_cats, index=0)

        # 6. FILTERING LOGIC
        if search_query:
            filtered_df = df_items[df_items['item_name'].str.contains(search_query, case=False, na=False)]
        else:
            filtered_df = df_items.copy()
            if cat_filter != "All":
                filtered_df = filtered_df[filtered_df['category'] == cat_filter]
            if sub_filter != "All":
                filtered_df = filtered_df[filtered_df['sub_category'] == sub_filter]

        # 7. SYSTEM STATUS BADGE
        st.info(f"⚡ System Status: Loaded {len(df_items)} items for {final_outlet}. Showing {len(filtered_df)}.")

        # 8. RENDER LIST
        if filtered_df.empty:
            st.warning("No items found.")
        else:
            for idx, row in filtered_df.iterrows():
                item_name = row['item_name']
                dict_key = f"{final_outlet}_{loc_filter}_{item_name}"
                cart = st.session_state['waste_notepad'].get(dict_key)
                current_total = cart['qty'] if cart else 0.0

                with st.container(border=True):
                    c_n, c_u = st.columns([8, 2])
                    with c_n:
                        st.markdown(f"{'🟢' if current_total > 0 else '⚪'} **{item_name}** | {row.get('count_unit', 'pcs')}")
                        if current_total > 0 and cart['remark']:
                            st.caption(f"📝 {cart['remark']}")
                    with c_u:
                        if current_total > 0:
                            if st.button("🗑️ Undo", key=f"un_{idx}"):
                                undo_waste_entry(dict_key)
                                st.rerun()

                    cq, cr, cb = st.columns([1.5, 3, 1], vertical_alignment="bottom")
                    qty_key, rem_key = f"q_{idx}", f"r_{idx}"
                    cq.number_input("+ Qty", 0.0, step=1.0, key=qty_key, label_visibility="collapsed")
                    cr.text_input("Reason", key=rem_key, placeholder="Reason (Optional)", label_visibility="collapsed")
                    cb.button("➕ Add", key=f"b_{idx}", on_click=add_waste_entry, args=(dict_key, row.to_dict(), qty_key, rem_key), use_container_width=True)

        # 9. FINAL SUBMIT
        st.divider()
        if st.session_state['waste_notepad']:
            st.success(f"🛒 {len(st.session_state['waste_notepad'])} items in ticket.")
            if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                logs = []
                today_str = waste_date.strftime("%Y-%m-%d")
                for k, v in st.session_state['waste_notepad'].items():
                    r = v['row_data']
                    cat_lower = str(r.get('category')).lower()
                    is_bev = any(x in cat_lower for x in ['bev', 'drink', 'bar'])
                    
                    if declaration == "🗑️ Daily Waste": tag = "wb" if is_bev else "wf"
                    elif declaration == "🍽️ Staff Meal": tag = "smb" if is_bev else "sm" 
                    else: tag = f"event - {event_name}"

                    logs.append({
                        "date": today_str,
                        "client_name": client_filter,
                        "outlet": final_outlet,
                        "location": loc_filter,
                        "item_name": r['item_name'],
                        "product_code": str(r.get('product_code', '')),
                        "item_type": r.get('item_type'),
                        "category": r.get('category'),
                        "sub_category": r.get('sub_category'),
                        "quantity": float(v['qty']),
                        "count_unit": r.get('count_unit', 'pcs'),
                        "remarks": f"{tag} | {v['remark']}".strip(" | "),
                        "reported_by": user,
                        "status": "Submitted"
                    })
                
                supabase.table("waste_logs").insert(logs).execute()
                st.session_state['waste_notepad'] = {}
                st.success("✅ Success! Logs pushed to Supabase.")
                st.rerun()

    except Exception as e:
        st.error(f"❌ System Error: {e}")