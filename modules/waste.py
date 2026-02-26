import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def add_waste_entry(dict_key, row_dict, qty_key, rem_key):
    added_qty = st.session_state.get(qty_key, 0.0)
    added_rem = st.session_state.get(rem_key, "")
    
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

# ---> THE CLEAN UI RENDER FUNCTION <---
def render_waste(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 🗑️ Daily Waste & Events")
    supabase = get_supabase()
    
    if 'waste_notepad' not in st.session_state:
        st.session_state['waste_notepad'] = {}

    try:
        # ==========================================
        # 1. VIEW MODE
        # ==========================================
        if str(assigned_client).lower() != 'all':
            archive_res = supabase.table("waste_logs").select("*").ilike("client_name", f"%{str(assigned_client).strip()}%").order("date", desc=True).limit(100).execute()
        else:
            archive_res = supabase.table("waste_logs").select("*").order("date", desc=True).limit(100).execute()
            
        df_archive = pd.DataFrame(archive_res.data)

        if role.lower() == "viewer":
            st.info("👁️ Viewer Mode: Showing Daily Waste Logs")
            if not df_archive.empty:
                st.dataframe(df_archive, use_container_width=True, hide_index=True)
            else:
                st.write("No logs found.")
            return

        # ==========================================
        # 2. SMART ROUTING & CLEAN SIDEBAR
        # ==========================================
        nav_res = supabase.table("master_items").select("outlet, client_name").execute()
        df_nav = pd.DataFrame(nav_res.data)
        
        # Sanitizer
        if not df_nav.empty:
            df_nav['client_name'] = df_nav['client_name'].astype(str).str.strip().str.title()
            df_nav['outlet'] = df_nav['outlet'].astype(str).str.strip().str.title()
            
        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        st.sidebar.markdown("### 📍 Location Details")

        # --- A. BRANCH ROUTING (Formerly Client) ---
        if clean_client.lower() != 'all':
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
        else:
            c_list = sorted(df_nav['client_name'].unique()) if not df_nav.empty else ["All"]
            final_client = st.sidebar.selectbox("🏢 Select Branch", c_list)

        # --- B. OUTLET ROUTING ---
        if not df_nav.empty:
            outlets_for_client = sorted(df_nav[df_nav['client_name'] == final_client]['outlet'].unique())
        else:
            outlets_for_client = []

        if clean_outlet.lower() != 'all':
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if outlets_for_client:
                final_outlet = st.sidebar.selectbox("🏠 Select Outlet", outlets_for_client)
            else:
                st.sidebar.warning(f"No outlets found for branch '{final_client}'")
                final_outlet = "None"

        # ==========================================
        # 3. MEGA-FETCH LOOP
        # ==========================================
        all_items = []
        page_size, start_row = 1000, 0
        
        if final_outlet != "None":
            while True:
                res = supabase.table("master_items").select("*").ilike("outlet", f"%{final_outlet}%").range(start_row, start_row + page_size - 1).execute()
                if not res.data: break
                all_items.extend(res.data)
                if len(res.data) < page_size: break
                start_row += page_size

        if not all_items:
            df_items = pd.DataFrame(columns=['item_name', 'category', 'sub_category', 'count_unit', 'location', 'product_code'])
            st.error(f"⚠️ No master items found for outlet '{final_outlet}'.")
        else:
            df_items = pd.DataFrame(all_items)
            df_items.columns = [str(c).strip().lower() for c in df_items.columns]
            if 'location' not in df_items.columns:
                df_items['location'] = "Main Store"

        # --- C. LOCATION ROUTING ---
        db_locs = sorted(df_items['location'].dropna().astype(str).str.title().unique())
        clean_loc = str(assigned_location).strip().title()

        if clean_loc.lower() != 'all':
            loc_filter = clean_loc
            st.sidebar.markdown(f"**📍 Location:** {loc_filter}")
        else:
            loc_options = ["All"] + db_locs if db_locs else ["All"]
            loc_filter = st.sidebar.selectbox("📍 Select Location", loc_options)
            
        declaration = st.radio("Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event"], horizontal=True, label_visibility="collapsed")
        waste_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))

        st.divider()

        # ==========================================
        # 4. FILTERS
        # ==========================================
        st.subheader("🔍 Find Items")
        search_q = st.text_input("🔍 Quick Search", placeholder="Find items...")

        col1, col2 = st.columns(2)
        with col1:
            cats = sorted(df_items['category'].dropna().unique())
            cat_filter = st.selectbox("📂 Category", ["None"] + cats, index=0)
        with col2:
            df_temp = df_items if cat_filter == "None" else df_items[df_items['category'] == cat_filter]
            sub_filter = st.selectbox("🏷️ Sub Category", ["All"] + sorted(df_temp['sub_category'].dropna().unique()))

        if search_q:
            filtered_df = df_items[df_items['item_name'].str.contains(search_q, case=False, na=False)]
        elif cat_filter != "None":
            filtered_df = df_items[df_items['category'] == cat_filter]
            if sub_filter != "All": filtered_df = filtered_df[filtered_df['sub_category'] == sub_filter]
        else:
            filtered_df = pd.DataFrame() 

        # ==========================================
        # 5. RENDER CARDS
        # ==========================================
        st.info(f"📊 System Status: Loaded {len(df_items)} items for {final_outlet}.")
        
        if not filtered_df.empty:
            for idx, row in filtered_df.head(60).iterrows():
                item_name = row['item_name']
                unit = row.get('count_unit', 'Unit')
                if not unit or str(unit).lower() == 'none': unit = "Unit"
                
                dict_key = f"{final_outlet}_{loc_filter}_{item_name}"
                qty_key, rem_key = f"q_{idx}", f"r_{idx}"
                
                cart = st.session_state['waste_notepad'].get(dict_key)
                current_total = cart['qty'] if cart else 0.0
                live_input_val = st.session_state.get(qty_key, 0.0)

                with st.container(border=True):
                    c_t, c_u = st.columns([8, 2])
                    with c_t:
                        if current_total > 0:
                            st.markdown(f"🟢 **{item_name}** | ✅ **Total: {current_total} {unit}**")
                        elif live_input_val > 0:
                            st.markdown(f"🟠 **{item_name}** | ⚠️ *Ready to add {live_input_val} {unit}...*")
                        else:
                            st.markdown(f"⚪ **{item_name}** | {unit}")
                    
                    if current_total > 0 and c_u.button("🗑️ Undo", key=f"un_{idx}"):
                        undo_waste_entry(dict_key)
                        st.rerun()

                    cq, cr, cb = st.columns([2, 5, 3], vertical_alignment="bottom")
                    cq.number_input("Qty", 0.0, step=1.0, key=qty_key)
                    cr.text_input("Remark", key=rem_key, placeholder="Reason...")
                    cb.button("➕ Add", key=f"b_{idx}", on_click=add_waste_entry, 
                              args=(dict_key, row.to_dict(), qty_key, rem_key), 
                              type="primary" if live_input_val > 0 else "secondary", 
                              use_container_width=True)

        elif not search_q and cat_filter == "None":
            st.warning("👆 Please use the search bar or select a category to see items.")

        # ==========================================
        # 6. SUBMIT
        # ==========================================
        st.divider()
        if st.session_state['waste_notepad']:
            if st.button("🚀 SUBMIT WASTE TICKET", type="primary", use_container_width=True):
                submission_data = []
                for k, v in st.session_state['waste_notepad'].items():
                    r = v['row_data']
                    item_unit_val = str(r.get('count_unit', 'Unit'))
                    if item_unit_val.lower() == 'none': item_unit_val = "Unit"

                    submission_data.append({
                        "date": str(waste_date),
                        "client_name": final_client,  # Even though we call it Branch in UI, DB uses client_name
                        "outlet": final_outlet,
                        "location": loc_filter,
                        "item_name": r['item_name'],
                        "product_code": str(r.get('product_code', '')),
                        "category": r.get('category'),
                        "sub_category": r.get('sub_category'),
                        "qty": float(v['qty']), 
                        "count_unit": item_unit_val,
                        "remarks": v['remark'],
                        "reported_by": user,
                        "status": "Submitted"
                    })
                
                try:
                    supabase.table("waste_logs").insert(submission_data).execute()
                    st.session_state['waste_notepad'] = {}
                    st.success("✅ Logged Successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Database Error: {e}")

    except Exception as e:
        st.error(f"❌ System Error: {e}")