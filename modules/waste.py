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
    st.markdown(f"### 🗑️ Daily Waste & Events (Supabase Cloud)")
    
    supabase = get_supabase()
    
    if 'waste_notepad' not in st.session_state:
        st.session_state['waste_notepad'] = {}

    try:
        # ==========================================
        # 1. FETCH DATA FROM SUPABASE
        # ==========================================
        # Fetch Master Items
        items_res = supabase.table("master_items").select("*").execute()
        df_master = pd.DataFrame(items_res.data)
        # Standardize columns to match your logic
        df_master.columns = [c.title() if c.lower() != 'id' else 'id' for c in df_master.columns]

        # Fetch Archive for history alerts (last 100 rows to keep it fast)
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

        # Sidebar Filters
        st.sidebar.subheader("🔍 Filter")
        clients = list(df_master['Client_Name'].unique())
        client_filter = st.sidebar.selectbox("🏢 Client", clients)
        
        # Outlet filter logic
        all_outlets = list(df_master[df_master['Client_Name'] == client_filter]['Outlet'].unique())
        allowed_outlets = [assigned_outlet] if assigned_outlet.lower() != 'all' else all_outlets
        outlet_filter = st.sidebar.selectbox("🏠 Outlet", allowed_outlets)

        # Category/Group filters
        cats = list(df_master[(df_master['Client_Name'] == client_filter) & (df_master['Outlet'] == outlet_filter)]['Category'].unique())
        cat_filter = st.sidebar.selectbox("Category", cats)
        
        grps = list(df_master[(df_master['Outlet'] == outlet_filter) & (df_master['Category'] == cat_filter)]['Group'].unique())
        grp_filter = st.selectbox("Group", grps, label_visibility="collapsed")

        search_query = st.text_input("Search", "", placeholder="🔍 Search item description...", label_visibility="collapsed")

        # Apply Filters to Display
        filtered_df = df_master[
            (df_master['Outlet'] == outlet_filter) & 
            (df_master['Category'] == cat_filter) & 
            (df_master['Group'] == grp_filter)
        ].copy()

        if search_query:
            filtered_df = df_master[df_master['Description'].str.contains(search_query, case=False, na=False)]

        # --- 🚨 HISTORY ALERT ---
        today_str = waste_date.strftime("%Y-%m-%d")
        if not df_archive.empty:
            already_logged = df_archive[(df_archive['date'] == today_str) & (df_archive['item_description'].isin(filtered_df['Description']))]
            if not already_logged.empty:
                st.warning(f"⚠️ {len(already_logged)} items already logged for today.")

        # --- LIVE TICKET FORM ---
        for index, row in filtered_df.iterrows():
            item_name = row['Description']
            dict_key = f"{outlet_filter}_{item_name}"
            
            cart_item = st.session_state['waste_notepad'].get(dict_key, {})
            in_cart_qty = cart_item.get('Qty', 0.0)
            in_cart_rem = cart_item.get('Remark', "")

            with st.container(border=True):
                col_n, col_q, col_r = st.columns([2, 1, 1.5])
                with col_n:
                    st.markdown(f"**{item_name}**")
                    st.caption(f"Unit: {row.get('Unit', 'pcs')}")
                
                qty_key = f"w_qty_{index}"
                rem_key = f"w_rem_{index}"
                
                with col_q:
                    st.number_input("Qty", value=float(in_cart_qty) if in_cart_qty > 0 else 0.0, min_value=0.0, key=qty_key, 
                                    on_change=update_waste_cart, args=(dict_key, row.to_dict(), qty_key, rem_key), label_visibility="collapsed")
                with col_r:
                    st.text_input("Remark", value=in_cart_rem, key=rem_key, placeholder="Reason...", 
                                  on_change=update_waste_cart, args=(dict_key, row.to_dict(), qty_key, rem_key), label_visibility="collapsed")

        # --- 🛒 SUBMIT TO SUPABASE ---
        st.divider()
        if st.session_state['waste_notepad']:
            with st.expander("👀 Review & Submit Ticket", expanded=True):
                cart_data = []
                for k, v in st.session_state['waste_notepad'].items():
                    # Map to Supabase table columns
                    row = v['row_data']
                    cat_text = str(row.get('Category', '')).lower()
                    is_bev = any(x in cat_text for x in ['bev', 'drink', 'bar'])
                    
                    if declaration == "🗑️ Daily Waste": tag = "wb" if is_bev else "wf"
                    elif declaration == "🍽️ Staff Meal": tag = "smb" if is_bev else "sm" 
                    else: tag = f"theo - {event_name}"

                    cart_data.append({
                        "date": str(today_str),
                        "client_name": client_filter,
                        "outlet": outlet_filter,
                        "location": row.get('Location', 'Main'),
                        "item_description": row.get('Description'),
                        "category": row.get('Category'),
                        "item_group": row.get('Group'),
                        "product_code": str(row.get('Product Code / Menu Code', '')),
                        "quantity": float(v['Qty']),
                        "unit": row.get('Unit', 'pcs'),
                        "remarks": f"{tag} | {v['Remark']}".strip(" | "),
                        "reported_by": user,
                        "status": "Submitted"
                    })
                
                st.table(pd.DataFrame(cart_data)[['item_description', 'quantity', 'remarks']])
                
                if st.button("🚀 SUBMIT TO SUPABASE", type="primary", use_container_width=True):
                    supabase.table("waste_logs").insert(cart_data).execute()
                    st.session_state['waste_notepad'] = {}
                    st.success("✅ Waste Logged Successfully!")
                    st.rerun()

    except Exception as e:
        st.error(f"❌ Error: {e}")