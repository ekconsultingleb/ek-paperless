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
            st.session_state['waste_notepad'][dict_key] = {'row_data': row_dict, 'qty': 0.0, 'remark': ""}
        st.session_state['waste_notepad'][dict_key]['qty'] += added_qty
        current_rem = st.session_state['waste_notepad'][dict_key]['remark']
        if added_rem.strip():
            st.session_state['waste_notepad'][dict_key]['remark'] = f"{current_rem} | {added_rem.strip()}" if current_rem else added_rem.strip()
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
        # 1. FETCH DATA
        items_res = supabase.table("master_items").select("*").execute()
        df_master = pd.DataFrame(items_res.data)
        df_master.columns = [c.lower() for c in df_master.columns]

        archive_res = supabase.table("waste_logs").select("*").order("date", desc=True).limit(100).execute()
        df_archive = pd.DataFrame(archive_res.data)

        if role == "viewer":
            st.info("👁️ Viewer Mode")
            if not df_archive.empty: st.dataframe(df_archive, use_container_width=True, hide_index=True)
            return

        # 2. ENTRY MODE SETUP
        declaration = st.radio("Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event / Function"], horizontal=True, label_visibility="collapsed")
        waste_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
        event_name = st.text_input("🏆 Event Name") if declaration == "🎉 Event / Function" else ""

        # --- SIDEBAR ---
        clients = list(df_master['client_name'].dropna().unique())
        client_filter = st.sidebar.selectbox("🏢 Client", clients)
        all_outlets = list(df_master[df_master['client_name'] == client_filter]['outlet'].dropna().unique())
        allowed_outlets = [assigned_outlet] if assigned_outlet.lower() != 'all' else all_outlets
        outlet_filter = st.sidebar.selectbox("🏠 Outlet", allowed_outlets)

        # 3. FILTER BY OUTLET IMMEDIATELY (Case-Insensitive)
        df_outlet_items = df_master[df_master['outlet'].astype(str).str.lower() == outlet_filter.lower()].copy()

        db_locations = sorted(list(df_outlet_items['location'].dropna().astype(str).str.upper().unique()))
        loc_filter = st.sidebar.selectbox("📍 Location", [assigned_location.upper()] if assigned_location.lower() != "all" else db_locations, disabled=(assigned_location.lower() != "all"))

        st.divider()

        # --- MAIN FILTERS ---
        st.subheader("🔍 Find Items")
        search_query = st.text_input("🔍 Quick Search", placeholder="Search item name...")

        col_cat, col_grp = st.columns(2)
        with col_cat:
            cats = sorted(list(df_outlet_items['category'].dropna().astype(str).unique()))
            cat_filter = st.selectbox("📂 Category", ["All"] + cats, index=0)
        with col_grp:
            df_temp = df_outlet_items if cat_filter == "All" else df_outlet_items[df_outlet_items['category'] == cat_filter]
            grps = sorted(list(df_temp['sub_category'].dropna().astype(str).unique()))
            grp_filter = st.selectbox("🏷️ Sub Category", ["All"] + grps, index=0)

        # 4. FINAL FILTERING LOGIC (ONLY ONE BLOCK)
        if search_query:
            filtered_df = df_outlet_items[df_outlet_items['item_name'].str.contains(search_query, case=False, na=False)]
        else:
            filtered_df = df_outlet_items.copy()
            if cat_filter != "All":
                filtered_df = filtered_df[filtered_df['category'] == cat_filter]
            if grp_filter != "All":
                filtered_df = filtered_df[filtered_df['sub_category'] == grp_filter]

        # --- DISPLAY ---
        total_items = len(filtered_df)
        counted_in_view = sum(1 for item in filtered_df['item_name'] if f"{outlet_filter}_{loc_filter}_{item}" in st.session_state['waste_notepad'])
        
        st.markdown(f"<div style='background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px; color: white;'>✅ {counted_in_view} Logged | 📝 {total_items} Items shown</div>", unsafe_allow_html=True)

        if filtered_df.empty:
            st.info("No items found. Try selecting 'All' in categories.")
        else:
            for index, row in filtered_df.iterrows():
                item_name = row.get('item_name', 'Unknown')
                dict_key = f"{outlet_filter}_{loc_filter}_{item_name}"
                cart_data = st.session_state['waste_notepad'].get(dict_key)
                current_total = cart_data['qty'] if cart_data else 0.0

                with st.container(border=True):
                    c_n, c_u = st.columns([8, 2])
                    c_n.markdown(f"{'🟢' if current_total > 0 else '🔴'} **{item_name}** | {row.get('count_unit', 'pcs')}")
                    if current_total > 0 and c_u.button("🗑️ Undo", key=f"un_{index}"):
                        undo_waste_entry(dict_key)
                        st.rerun()

                    cq, cr, cb = st.columns([1.5, 3, 1], vertical_alignment="bottom")
                    qty_key, rem_key = f"q_{index}", f"r_{index}"
                    cq.number_input("+ Qty", 0.0, step=1.0, key=qty_key)
                    cr.text_input("Reason", key=rem_key)
                    cb.button("➕ Add", key=f"b_{index}", on_click=add_waste_entry, args=(dict_key, row.to_dict(), qty_key, rem_key))

        # --- SUBMIT ---
        st.divider()
        if st.session_state['waste_notepad']:
            if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                logs = []
                for k, v in st.session_state['waste_notepad'].items():
                    r = v['row_data']
                    tag = "wb" if "bev" in str(r.get('category')).lower() else "wf"
                    logs.append({
                        "date": str(waste_date), "client_name": client_filter, "outlet": outlet_filter,
                        "location": loc_filter, "item_name": r.get('item_name'), "product_code": str(r.get('product_code', '')),
                        "item_type": r.get('item_type'), "category": r.get('category'), "sub_category": r.get('sub_category'),
                        "quantity": float(v['qty']), "count_unit": r.get('count_unit', 'pcs'),
                        "remarks": f"{tag} | {v['remark']}".strip(" | "), "reported_by": user, "status": "Submitted"
                    })
                supabase.table("waste_logs").insert(logs).execute()
                st.session_state['waste_notepad'] = {}
                st.success("✅ Logged!")
                st.rerun()

    except Exception as e:
        st.error(f"❌ Error: {e}")