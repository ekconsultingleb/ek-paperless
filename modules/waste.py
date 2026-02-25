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
    # Get values from session state using the unique keys
    added_qty = st.session_state.get(qty_key, 0.0)
    added_rem = st.session_state.get(rem_key, "")
    
    if added_qty > 0:
        # Initialize item in notepad if not present
        if dict_key not in st.session_state['waste_notepad']:
            st.session_state['waste_notepad'][dict_key] = {
                'row_data': row_dict,
                'qty': 0.0,
                'remark': ""
            }
        
        # Add the quantity cumulatively
        st.session_state['waste_notepad'][dict_key]['qty'] += added_qty
        
        # Append remarks with a separator
        current_rem = st.session_state['waste_notepad'][dict_key]['remark']
        if added_rem.strip():
            if current_rem:
                st.session_state['waste_notepad'][dict_key]['remark'] = f"{current_rem} | {added_rem.strip()}"
            else:
                st.session_state['waste_notepad'][dict_key]['remark'] = added_rem.strip()
                
        # Reset the local input fields so they clear after clicking Add
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
        # 1. SIDEBAR: NAVIGATION & OUTLET SELECTION
        nav_res = supabase.table("master_items").select("outlet, client_name").execute()
        df_nav = pd.DataFrame(nav_res.data)
        client_filter = st.sidebar.selectbox("🏢 Client", sorted(df_nav['client_name'].unique()))
        outlet_options = sorted(df_nav[df_nav['client_name'] == client_filter]['outlet'].unique())
        final_outlet = assigned_outlet if assigned_outlet.lower() != 'all' else st.sidebar.selectbox("🏠 Outlet", outlet_options)

        # 2. MEGA-FETCH LOOP (PAGINATION)
        # This bypasses the 1,000 row limit to reach all items (Inventory + Menu Items)
        all_items = []
        page_size, start_row = 1000, 0
        while True:
            res = supabase.table("master_items").select("*").eq("outlet", final_outlet).range(start_row, start_row + page_size - 1).execute()
            if not res.data: break
            all_items.extend(res.data)
            if len(res.data) < page_size: break
            start_row += page_size

        df_items = pd.DataFrame(all_items)
        df_items.columns = [c.lower() for c in df_items.columns]
        
        # Location & Date
        db_locs = sorted(df_items['location'].dropna().astype(str).str.upper().unique())
        loc_filter = st.sidebar.selectbox("📍 Location", [assigned_location.upper()] if assigned_location.lower() != 'all' else db_locs)
        waste_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))

        st.divider()

        # 3. FILTERS (UX: START WITH SEARCH/CATEGORY)
        st.subheader("🔍 Find Items")
        search_q = st.text_input("🔍 Quick Search", placeholder="Search Inventory or Menu Items...")

        col1, col2 = st.columns(2)
        with col1:
            cats = sorted(df_items['category'].dropna().unique())
            cat_filter = st.selectbox("📂 Category", ["None"] + cats, index=0)
        with col2:
            df_temp = df_items if cat_filter == "None" else df_items[df_items['category'] == cat_filter]
            sub_cats = sorted(df_temp['sub_category'].dropna().unique())
            sub_filter = st.selectbox("🏷️ Sub Category", ["All"] + sub_cats)

        # 4. FILTERING LOGIC
        if search_q:
            filtered_df = df_items[df_items['item_name'].str.contains(search_q, case=False, na=False)]
        elif cat_filter != "None":
            filtered_df = df_items[df_items['category'] == cat_filter]
            if sub_filter != "All":
                filtered_df = filtered_df[filtered_df['sub_category'] == sub_filter]
        else:
            filtered_df = pd.DataFrame() 

        # 5. RENDER LIST (LIVE STATUS & UNIT FIX)
        st.info(f"📊 System Status: Loaded {len(df_items)} items for {final_outlet}.")
        
        if not filtered_df.empty:
            for idx, row in filtered_df.head(60).iterrows():
                item_name = row['item_name']
                
                # UNIT FIX: Handle 'None' or empty values
                unit = row.get('count_unit')
                if not unit or str(unit).lower() == 'none' or str(unit).strip() == "":
                    unit = "Unit"
                
                dict_key = f"{final_outlet}_{loc_filter}_{item_name}"
                cart = st.session_state['waste_notepad'].get(dict_key)
                current_total = cart['qty'] if cart else 0.0

                with st.container(border=True):
                    c_t, c_u = st.columns([8, 2])
                    with c_t:
                        # DYNAMIC COLOR & TOTAL DISPLAY
                        if current_total > 0:
                            st.markdown(f"🟢 **{item_name}** | ✅ **Total Added: {current_total} {unit}**")
                        else:
                            st.markdown(f"⚪ **{item_name}** | {unit}")
                    
                    if current_total > 0:
                        if c_u.button("🗑️ Undo", key=f"un_{idx}", use_container_width=True):
                            undo_waste_entry(dict_key)
                            st.rerun()

                    # Inputs for adding more waste
                    cq, cr, cb = st.columns([2, 5, 3], vertical_alignment="bottom")
                    qty_key, rem_key = f"q_{idx}", f"r_{idx}"
                    cq.number_input("Qty", 0.0, step=1.0, key=qty_key)
                    cr.text_input("Remark", key=rem_key, placeholder="Reason...", label_visibility="collapsed")
                    cb.button("➕ Add", key=f"b_{idx}", on_click=add_waste_entry, 
                              args=(dict_key, row.to_dict(), qty_key, rem_key), 
                              type="primary", use_container_width=True)

        elif not search_q and cat_filter == "None":
            st.warning("👆 Please use the search bar or select a category to see items.")

        # 6. SUBMIT (FIXED COLUMN NAMES FOR SUPABASE)
        st.divider()
        if st.session_state['waste_notepad']:
            st.success(f"🛒 {len(st.session_state['waste_notepad'])} items in current ticket.")
            if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                submission_data = []
                for k, v in st.session_state['waste_notepad'].items():
                    r = v['row_data']
                    # Use exact column names from your Supabase waste_logs table
                    submission_data.append({
                        "date": str(waste_date),
                        "client_name": client_filter,
                        "outlet": final_outlet,
                        "location": loc_filter,
                        "item_name": r['item_name'],
                        "product_code": str(r.get('product_code', '')),
                        "category": r.get('category'),
                        "sub_category": r.get('sub_category'),
                        "qty": float(v['qty']), # MATCHES DB COLUMN 'qty'
                        "count_unit": r.get('count_unit') if r.get('count_unit') and str(r.get('count_unit')).lower() != 'none' else "Unit",
                        "remarks": v['remark'],
                        "reported_by": user,
                        "status": "Submitted"
                    })
                
                try:
                    supabase.table("waste_logs").insert(submission_data).execute()
                    st.session_state['waste_notepad'] = {}
                    st.success("✅ Logged Successfully to Supabase!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Database Submission Error: {e}")

    except Exception as e:
        st.error(f"❌ System Error: {e}")