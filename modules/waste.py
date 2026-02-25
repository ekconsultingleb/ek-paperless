import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import create_client, Client

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def add_waste_entry(dict_key, row_dict, qty_key, rem_key):
    added_qty = st.session_state[qty_key]
    added_rem = st.session_state[rem_key]
    if added_qty > 0:
        if dict_key not in st.session_state['waste_notepad']:
            st.session_state['waste_notepad'][dict_key] = {'row_data': row_dict, 'qty': 0.0, 'remark': ""}
        st.session_state['waste_notepad'][dict_key]['qty'] += added_qty
        current_rem = st.session_state['waste_notepad'][dict_key]['remark']
        st.session_state['waste_notepad'][dict_key]['remark'] = f"{current_rem} | {added_rem.strip()}" if current_rem and added_rem.strip() else (added_rem.strip() or current_rem)
        st.session_state[qty_key] = 0.0
        st.session_state[rem_key] = ""

def render_waste(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown("### 🗑️ Daily Waste & Events")
    supabase = get_supabase()
    if 'waste_notepad' not in st.session_state:
        st.session_state['waste_notepad'] = {}

    try:
        # 1. FETCH OUTLETS (To build the sidebar)
        nav_res = supabase.table("master_items").select("outlet, client_name").execute()
        df_nav = pd.DataFrame(nav_res.data)

        # --- SIDEBAR ---
        client_list = sorted(df_nav['client_name'].dropna().unique())
        client_filter = st.sidebar.selectbox("🏢 Client", client_list)
        
        outlet_options = sorted(df_nav[df_nav['client_name'] == client_filter]['outlet'].dropna().unique())
        # Use the assigned outlet or let admin choose
        final_outlet = assigned_outlet if assigned_outlet.lower() != 'all' else st.sidebar.selectbox("🏠 Outlet", outlet_options)

        # 2. THE BIG FETCH (10,000 ROWS + OUTLET FILTER)
        # We filter by Outlet INSIDE the query to ensure we get ALL matching rows
        items_res = supabase.table("master_items").select("*").eq("outlet", final_outlet).limit(10000).execute()
        df_items = pd.DataFrame(items_res.data)
        df_items.columns = [c.lower() for c in df_items.columns]

        # 3. LOCATION SELECT
        db_locs = sorted(df_items['location'].dropna().astype(str).str.upper().unique())
        loc_filter = st.sidebar.selectbox("📍 Location", [assigned_location.upper()] if assigned_location.lower() != 'all' else db_locs)

        st.divider()

        # --- FILTERS ---
        st.subheader("🔍 Find Items")
        search_query = st.text_input("🔍 Quick Search", placeholder="Type any part of the name...")

        col1, col2 = st.columns(2)
        with col1:
            # We use UPPERCASE for categories to merge "food" and "Food"
            cats = sorted(df_items['category'].dropna().astype(str).str.upper().unique())
            cat_filter = st.selectbox("📂 Category", ["ALL"] + cats, index=0)
        with col2:
            df_sub = df_items if cat_filter == "ALL" else df_items[df_items['category'].astype(str).str.upper() == cat_filter]
            sub_cats = sorted(df_sub['sub_category'].dropna().astype(str).str.upper().unique())
            sub_filter = st.selectbox("🏷️ Sub Category", ["ALL"] + sub_cats, index=0)

        # 4. FILTERING THE DATAFRAME
        if search_query:
            filtered_df = df_items[df_items['item_name'].str.contains(search_query, case=False, na=False)]
        else:
            filtered_df = df_items.copy()
            if cat_filter != "ALL":
                filtered_df = filtered_df[filtered_df['category'].astype(str).str.upper() == cat_filter]
            if sub_filter != "ALL":
                filtered_df = filtered_df[filtered_df['sub_category'].astype(str).str.upper() == sub_filter]

        # --- DEBUG BADGE (Remove this after it works) ---
        st.info(f"⚡ System Status: Reading {len(df_items)} items from database. Showing {len(filtered_df)} items.")

        if filtered_df.empty:
            st.warning("No items found. Make sure the items in the database have the correct Outlet name.")
        else:
            # 5. RENDER CARDS
            for idx, row in filtered_df.iterrows():
                item_name = row['item_name']
                dict_key = f"{final_outlet}_{loc_filter}_{item_name}"
                cart = st.session_state['waste_notepad'].get(dict_key, {'qty': 0.0})

                with st.container(border=True):
                    st.markdown(f"{'🟢' if cart['qty'] > 0 else '⚪'} **{item_name}** | {row.get('count_unit', 'pcs')}")
                    
                    c1, c2, c3 = st.columns([1, 2, 1], vertical_alignment="bottom")
                    q_key, r_key = f"q_{idx}", f"r_{idx}"
                    c1.number_input("Qty", 0.0, step=1.0, key=q_key, label_visibility="collapsed")
                    c2.text_input("Reason", key=r_key, placeholder="Optional", label_visibility="collapsed")
                    c3.button("Add", key=f"b_{idx}", on_click=add_waste_entry, args=(dict_key, row.to_dict(), q_key, r_key), use_container_width=True)

        # 6. SUBMIT
        st.divider()
        if st.session_state['waste_notepad']:
            if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                logs = []
                for k, v in st.session_state['waste_notepad'].items():
                    r = v['row_data']
                    logs.append({
                        "date": str(datetime.now().date()), "client_name": client_filter,
                        "outlet": final_outlet, "location": loc_filter, "item_name": r['item_name'],
                        "quantity": float(v['qty']), "count_unit": r.get('count_unit', 'pcs'),
                        "remarks": v['remark'], "reported_by": user, "status": "Submitted",
                        "category": r.get('category'), "sub_category": r.get('sub_category'),
                        "item_type": r.get('item_type')
                    })
                supabase.table("waste_logs").insert(logs).execute()
                st.session_state['waste_notepad'] = {}
                st.success("✅ Logged Successfully!")
                st.rerun()

    except Exception as e:
        st.error(f"❌ System Error: {e}")