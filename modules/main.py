import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_main(conn, sheet_link, user, role):
    # 🚨 ENTERPRISE TIER SECURITY LOCK 
    user_role = role.lower()
    user_client = st.session_state.get('client_name', '').lower()
    
    is_super_admin = (user_role == "admin_all")
    is_normal_admin = (user_role == "admin")
    is_hq_manager = (user_role == "manager" and user_client == "all")

    if not (is_super_admin or is_normal_admin or is_hq_manager):
        st.error("🚫 Access Denied. This area is restricted to Head Office and Administrators.")
        return

    st.markdown("### ⚙️ Control Panel")
    supabase = get_supabase()

    # --- 🧠 INTELLIGENT ROUTING DATA ---
    def get_routing_df():
        records = []
        try:
            res1 = supabase.table("master_items").select("client_name, outlet, location").execute()
            if res1.data: records.extend(res1.data)
            res2 = supabase.table("users").select("client_name, outlet, location").execute()
            if res2.data: records.extend(res2.data)
        except: pass
        
        if records:
            df = pd.DataFrame(records)
            df['client_name'] = df['client_name'].astype(str).str.strip().str.title()
            df['outlet'] = df['outlet'].astype(str).str.strip().str.title()
            return df
        return pd.DataFrame(columns=['client_name', 'outlet', 'location'])

    df_routing = get_routing_df()

    # ==========================================
    # 📑 DYNAMIC TAB DEFINITION
    # ==========================================
    if is_super_admin:
        st.info("👑 Super Admin Mode: Full access to all database and user controls.")
        tabs = st.tabs(["📤 Master Sync", "➕ Create User", "👥 Manage Users", "🚚 Manage Suppliers", "📝 Edit Data"])
        t_sync, t_create, t_view, t_supp, t_edit = tabs
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: Access to sync and onboard users/suppliers.")
        tabs = st.tabs(["📤 Master Sync", "➕ Create User", "🚚 Manage Suppliers", "📝 Edit Data"])
        t_sync, t_create, t_supp, t_edit = tabs[0], tabs[1], tabs[2], tabs[3]
        t_view = None 
    else:
        st.info("🏢 HQ Manager Mode: Access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Sync"])
        t_sync = tabs[0]
        t_create = t_view = t_supp = t_edit = None

    # ==========================================
    # TAB: MASTER ITEMS SYNC
    # ==========================================
    with t_sync:
        st.markdown("#### 🔄 Smart Database Importer")
        uploaded_file = st.file_uploader("Upload Master Items List", type=["csv", "xlsx"])
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                df.columns = [str(c).strip().lower() for c in df.columns]
                st.dataframe(df.head(5), use_container_width=True)
                required_cols = ['client_name', 'outlet', 'location', 'item_type', 'product_code', 'item_name']
                if all(c in df.columns for c in required_cols):
                    if st.button("🚀 Run Smart Sync", type="primary", use_container_width=True):
                        with st.spinner("Syncing..."):
                            df = df.fillna('')
                            records = df.to_dict(orient='records')
                            for i in range(0, len(records), 500):
                                supabase.table("master_items").upsert(records[i:i + 500], on_conflict="client_name,outlet,location,item_type,product_code").execute()
                            st.success(f"✅ Synced {len(records)} items!")
                else:
                    st.error("❌ Missing required columns.")
            except Exception as e:
                st.error(f"❌ Error: {e}")

    # ==========================================
    # TAB: CREATE USER
    # ==========================================
    if t_create:
        with t_create:
            st.subheader("Account Details")
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("👤 Username", key="c_usr")
                new_password = st.text_input("🔑 Password", key="c_pwd")
                new_fullname = st.text_input("📝 Full Name", key="c_name")
                role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                new_role = st.selectbox("🛡️ Role", role_options, key="c_role")
            with col2:
                available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices"]
                new_modules = st.multiselect("📱 App Access", available_modules, default=["waste"], key="c_mod")

            # 🚀 FILTER FIX: Remove "All" from the database pulls so it doesn't duplicate!
            c_list = ["All"] + sorted([c for c in df_routing['client_name'].unique() if c and str(c).lower() not in ['nan', 'all']])
            col3, col4, col5 = st.columns(3)
            with col3: new_client = st.selectbox("🏢 Select Client", c_list, key="c_client")
            
            f_outlets = df_routing['outlet'].unique() if new_client == "All" else df_routing[df_routing['client_name'] == new_client]['outlet'].unique()
            # 🚀 FILTER FIX
            o_list = ["All"] + sorted([o for o in f_outlets if o and str(o).lower() not in ['nan', 'all']])
            with col4: new_outlet = st.selectbox("🏠 Select Outlet", o_list, key="c_outlet")
            
            loc_df = df_routing.copy()
            if new_client != "All": loc_df = loc_df[loc_df['client_name'] == new_client]
            if new_outlet != "All": loc_df = loc_df[loc_df['outlet'] == new_outlet]
            loc_set = set()
            for loc_val in loc_df['location'].dropna():
                for l in str(loc_val).split(','):
                    if l.strip() and str(l).lower() not in ['nan', 'all']: loc_set.add(l.strip().title())
            # 🚀 FILTER FIX
            l_list = ["All"] + sorted(list(loc_set))
            with col5: new_locations = st.multiselect("📍 Select Location(s)", l_list, default=["All"], key="c_loc")

            if st.button("🚀 CREATE USER", type="primary", use_container_width=True):
                new_user_data = {
                    "username": new_username.strip(), "password": new_password.strip(), "full_name": new_fullname.strip(),
                    "role": new_role, "client_name": new_client, "outlet": new_outlet,
                    "location": ", ".join(new_locations), "module": ", ".join(new_modules)
                }
                supabase.table("users").insert([new_user_data]).execute()
                st.success("✅ User created!")

    # ==========================================
    # TAB: MANAGE USERS (Super Admin Only)
    # ==========================================
    if t_view:
        with t_view:
            try:
                res = supabase.table("users").select("*").execute()
                if res.data:
                    df_u = pd.DataFrame(res.data)
                    u_sel = st.selectbox("👤 Select User to Edit", sorted(df_u['username'].tolist()), key="e_user_sel")
                    u_data = df_u[df_u['username'] == u_sel].iloc[0]
                    
                    st.divider()
                    st.subheader(f"⚙️ Editing User: {u_sel}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        e_pass = st.text_input("🔑 Password", value=u_data.get('password', ''))
                        e_fullname = st.text_input("📝 Full Name", value=u_data.get('full_name', ''))
                        
                        role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                        e_role_index = role_options.index(u_data['role']) if u_data['role'] in role_options else 0
                        e_role = st.selectbox("🛡️ Role", role_options, index=e_role_index)
                        
                    with col2:
                        available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices"]
                        current_mods = [m.strip() for m in str(u_data.get('module', '')).split(',')] if str(u_data.get('module', '')) else ["waste"]
                        valid_mods = [m for m in current_mods if m in available_modules]
                        e_modules = st.multiselect("📱 App Access", available_modules, default=valid_mods)

                    # 🚀 FILTER FIX: Remove "All" from the database pulls so it doesn't duplicate!
                    c_list = ["All"] + sorted([c for c in df_routing['client_name'].unique() if c and str(c).lower() not in ['nan', 'all']])
                    col3, col4, col5 = st.columns(3)
                    with col3: 
                        c_index = c_list.index(u_data['client_name']) if u_data['client_name'] in c_list else 0
                        e_client = st.selectbox("🏢 Select Client", c_list, index=c_index, key="e_client_box")
                    
                    f_outlets = df_routing['outlet'].unique() if e_client == "All" else df_routing[df_routing['client_name'] == e_client]['outlet'].unique()
                    # 🚀 FILTER FIX
                    o_list = ["All"] + sorted([o for o in f_outlets if o and str(o).lower() not in ['nan', 'all']])
                    with col4: 
                        o_index = o_list.index(u_data['outlet']) if u_data['outlet'] in o_list else 0
                        e_outlet = st.selectbox("🏠 Select Outlet", o_list, index=o_index, key="e_outlet_box")
                    
                    loc_df = df_routing.copy()
                    if e_client != "All": loc_df = loc_df[loc_df['client_name'] == e_client]
                    if e_outlet != "All": loc_df = loc_df[loc_df['outlet'] == e_outlet]
                    loc_set = set()
                    for loc_val in loc_df['location'].dropna():
                        for l in str(loc_val).split(','):
                            if l.strip() and str(l).lower() not in ['nan', 'all']: loc_set.add(l.strip().title())
                    # 🚀 FILTER FIX
                    l_list = ["All"] + sorted(list(loc_set))
                    
                    current_locs = [l.strip() for l in str(u_data.get('location', '')).split(',')] if str(u_data.get('location', '')) else ["All"]
                    valid_locs = [l for l in current_locs if l in l_list]
                    if not valid_locs: valid_locs = ["All"]
                    
                    with col5: 
                        e_locations = st.multiselect("📍 Select Location(s)", l_list, default=valid_locs, key="e_loc_box")

                    st.write("") # Quick spacer
                    if st.button("💾 Save User Changes", type="primary", use_container_width=True):
                        update_payload = {
                            "password": e_pass, 
                            "full_name": e_fullname,
                            "role": e_role,
                            "module": ", ".join(e_modules),
                            "client_name": e_client,
                            "outlet": e_outlet,
                            "location": ", ".join(e_locations)
                        }
                        supabase.table("users").update(update_payload).eq("username", u_sel).execute()
                        st.success(f"✅ User '{u_sel}' updated successfully!")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Error loading user manager: {e}")

    # ==========================================
    # TAB: MANAGE SUPPLIERS
    # ==========================================
    if t_supp:
        with t_supp:
            st.markdown("#### 🚚 Supplier Management")
            try:
                s_res = supabase.table("suppliers").select("*").execute()
                existing_s = pd.DataFrame(s_res.data) if s_res.data else pd.DataFrame(columns=["supplier_name"])
                
                c1, c2 = st.columns(2)
                with c1:
                    with st.form("add_supp", clear_on_submit=True):
                        n_s = st.text_input("New Supplier Name")
                        if st.form_submit_button("➕ Add Supplier"):
                            clean_n = n_s.strip().lower()
                            existing_list = [x.lower() for x in existing_s['supplier_name'].tolist()]
                            if clean_n in existing_list:
                                st.warning("⚠️ Already exists!")
                            else:
                                supabase.table("suppliers").insert({"supplier_name": n_s.title()}).execute()
                                st.success("Added!")
                                st.rerun()
                with c2:
                    st.write("**Current List:**")
                    st.dataframe(existing_s[['supplier_name']].sort_values('supplier_name'), hide_index=True, use_container_width=True)
                    s_del = st.selectbox("Delete Supplier", existing_s['supplier_name'].tolist(), index=None)
                    if st.button("🗑️ Delete"):
                        supabase.table("suppliers").delete().eq("supplier_name", s_del).execute()
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # ==========================================
    # TAB: LIVE DATA EDITOR (The God Mode)
    # ==========================================
    if t_edit:
        with t_edit:
            st.markdown("#### 📝 Live Database Editor")
            st.info("💡 Double-click any cell to edit it. When you are finished, click the Save button at the bottom.")
            
            # Let the Admin choose which table they want to fix
            table_to_edit = st.selectbox("🗄️ Select Table to Edit:", ["waste_logs", "invoices_log"])
            
            try:
                # Fetch the last 150 records (we limit it so the app doesn't freeze on huge datasets)
                res = supabase.table(table_to_edit).select("*").order("id", desc=True).limit(150).execute()
                
                if res.data:
                    df_edit = pd.DataFrame(res.data)
                    
                    # 1. DISPLAY THE SPREADSHEET
                    edited_df = st.data_editor(
                        df_edit,
                        use_container_width=True,
                        disabled=["id", "created_at"], # Protect the ID so they don't break the database
                        hide_index=True,
                        key=f"editor_{table_to_edit}"
                    )
                    
                    # 2. THE SAVE LOGIC
                    st.write("")
                    if st.button(f"💾 Save Changes to {table_to_edit}", type="primary", use_container_width=True):
                        with st.spinner("Scanning for changes and updating cloud..."):
                            updates_made = 0
                            
                            # We fill empty cells to make comparing them easier
                            safe_edited_df = edited_df.fillna('')
                            safe_orig_df = df_edit.fillna('')
                            
                            for index, new_row in safe_edited_df.iterrows():
                                old_row = safe_orig_df.loc[index]
                                
                                # If the row was changed by the user:
                                if new_row.to_dict() != old_row.to_dict():
                                    row_id = new_row['id']
                                    
                                    # Prepare the update package (we strip out 'id' and 'created_at' to be safe)
                                    update_payload = edited_df.loc[index].drop(['id', 'created_at']).to_dict()
                                    
                                    # Send the update to Supabase
                                    supabase.table(table_to_edit).update(update_payload).eq("id", row_id).execute()
                                    updates_made += 1
                            
                            if updates_made > 0:
                                st.success(f"✅ Successfully updated {updates_made} record(s)!")
                                st.rerun()
                            else:
                                st.info("No changes were detected.")
                else:
                    st.warning("No records found in this table.")
            except Exception as e:
                st.error(f"❌ Error loading data: {e}")