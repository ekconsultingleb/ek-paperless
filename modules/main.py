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

    # --- INTELLIGENT ROUTING OPTION FETCHER ---
    # Grabs every existing branch/location from the database to build the dropdowns!
    def get_routing_options():
        clients, outlets, locations = set(["All"]), set(["All"]), set(["All"])
        try:
            # Check Master Items
            res = supabase.table("master_items").select("client_name, outlet, location").execute()
            if res.data:
                for row in res.data:
                    if row.get('client_name'): clients.add(str(row['client_name']).strip().title())
                    if row.get('outlet'): outlets.add(str(row['outlet']).strip().title())
                    if row.get('location'): locations.add(str(row['location']).strip().title())
            # Check existing Users
            res_u = supabase.table("users").select("client_name, outlet, location").execute()
            if res_u.data:
                for row in res_u.data:
                    if row.get('client_name'): clients.add(str(row['client_name']).strip().title())
                    if row.get('outlet'): outlets.add(str(row['outlet']).strip().title())
                    if row.get('location'): 
                        for loc in str(row['location']).split(','):
                            locations.add(loc.strip().title())
        except: pass
        
        c_list, o_list, l_list = sorted(list(clients)), sorted(list(outlets)), sorted(list(locations))
        # Move 'All' to the top
        c_list.insert(0, c_list.pop(c_list.index("All")))
        o_list.insert(0, o_list.pop(o_list.index("All")))
        l_list.insert(0, l_list.pop(l_list.index("All")))
        return c_list, o_list, l_list

    c_opts, o_opts, l_opts = get_routing_options()

    # --- DYNAMIC TABS BASED ON HIERARCHY ---
    if is_super_admin:
        st.info("👑 Super Admin Mode: Full access to all database and user controls.")
        tab_sync, tab_create, tab_view = st.tabs(["📤 Master Items Sync", "➕ Create New User", "👥 Manage Existing Users"])
        
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: You can sync databases and onboard new users.")
        tabs = st.tabs(["📤 Master Items Sync", "➕ Create New User"])
        tab_sync, tab_create = tabs[0], tabs[1]
        tab_view = None 
        
    elif is_hq_manager:
        st.info("🏢 HQ Manager Mode: You have access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Items Sync"])
        tab_sync = tabs[0]
        tab_create, tab_view = None, None

    # ==========================================
    # TAB 1: SMART EXCEL/CSV IMPORTER
    # ==========================================
    with tab_sync:
        st.markdown("#### 🔄 Smart Database Importer (Upsert)")
        st.info("💡 **How this works:** Upload your CSV/Excel. The system will UPDATE existing items and INSERT new ones.")

        uploaded_file = st.file_uploader("Upload Master Items List", type=["csv", "xlsx"])
        if uploaded_file:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                df.columns = [str(c).strip().lower() for c in df.columns]

                st.write(f"**Previewing {len(df)} rows:**")
                st.dataframe(df.head(5), use_container_width=True)

                required_cols = ['client_name', 'outlet', 'location', 'item_type', 'product_code', 'item_name']
                missing_cols = [c for c in required_cols if c not in df.columns]

                if missing_cols:
                    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                else:
                    if st.button("🚀 Run Smart Sync", type="primary", use_container_width=True):
                        with st.spinner("Syncing to the Cloud... Do not refresh..."):
                            df = df.fillna('')
                            records = df.to_dict(orient='records')
                            batch_size = 500
                            for i in range(0, len(records), batch_size):
                                supabase.table("master_items").upsert(
                                    records[i:i + batch_size],
                                    on_conflict="client_name,outlet,location,item_type,product_code"
                                ).execute()
                            st.success(f"✅ Successfully synced {len(records)} items!")
                            st.balloons()
            except Exception as e:
                st.error(f"❌ Error processing file: {e}")

    # ==========================================
    # TAB 2: CREATE USER FORM
    # ==========================================
    if tab_create:
        with tab_create:
            with st.form("create_user_form", clear_on_submit=True):
                st.subheader("Account Details")
                col1, col2 = st.columns(2)
                with col1:
                    new_username = st.text_input("👤 Username", placeholder="e.g. Sami_LaSiesta")
                    new_password = st.text_input("🔑 Password", placeholder="Enter password")
                    new_fullname = st.text_input("📝 Full Name", placeholder="e.g. Jacob Joshua")
                    role_options = ["staff", "chef", "manager", "viewer", "admin", "admin_all"] if is_super_admin else ["staff", "chef", "manager", "viewer", "admin"]
                    new_role = st.selectbox("🛡️ Role", role_options)
                
                with col2:
                    available_modules = ["waste", "cash", "inventory", "transfers", "dashboard"]
                    new_modules = st.multiselect("📱 App Access (Modules)", available_modules, default=["waste"])

                st.divider()
                st.subheader("Routing & Security Assignments")
                col3, col4, col5 = st.columns(3)
                with col3:
                    new_client = st.selectbox("🏢 Select Client", c_opts)
                with col4:
                    new_outlet = st.selectbox("🏠 Select Outlet", o_opts)
                with col5:
                    new_locations = st.multiselect("📍 Select Location(s)", l_opts, default=["All"])

                # Failsafe Manual Override 
                with st.expander("➕ Not in the list? Add a brand new branch manually"):
                    m_client = st.text_input("New Client Name")
                    m_outlet = st.text_input("New Outlet Name")
                    m_loc = st.text_input("New Location Name")
                
                submit_user = st.form_submit_button("🚀 CREATE USER", type="primary", use_container_width=True)

                if submit_user:
                    if not new_username.strip() or not new_password.strip():
                        st.error("❌ Username and Password are required!")
                    else:
                        # Decide whether to use the dropdown or the manual override
                        final_client = m_client.strip().title() if m_client.strip() else new_client
                        final_outlet = m_outlet.strip().title() if m_outlet.strip() else new_outlet
                        final_loc = m_loc.strip().title() if m_loc.strip() else (", ".join(new_locations) if new_locations else "All")

                        new_user_data = {
                            "username": new_username.strip(),
                            "password": new_password.strip(),
                            "full_name": new_fullname.strip(),
                            "role": new_role,
                            "client_name": final_client,
                            "outlet": final_outlet,
                            "location": final_loc,
                            "module": ", ".join(new_modules) if new_modules else ""
                        }
                        try:
                            supabase.table("users").insert([new_user_data]).execute()
                            st.success(f"✅ User '{new_username}' created successfully!")
                            st.balloons()
                        except Exception as e:
                            st.error(f"❌ Database Error: {e}. Username might already exist.")

    # ==========================================
    # TAB 3: MANAGE EXISTING USERS
    # ==========================================
    if tab_view:
        with tab_view:
            st.subheader("Edit User Profiles")
            try:
                res = supabase.table("users").select("*").execute()
                if res.data:
                    df_users = pd.DataFrame(res.data)
                    user_list = sorted(df_users['username'].tolist())
                    selected_user = st.selectbox("👤 Select a User to Edit", options=["-- Select a User --"] + user_list)
                    
                    if selected_user != "-- Select a User --":
                        user_data = df_users[df_users['username'] == selected_user].iloc[0]
                        
                        with st.form("edit_user_form"):
                            st.markdown(f"**Editing Profile:** `{selected_user}`")
                            e_col1, e_col2 = st.columns(2)
                            
                            with e_col1:
                                e_password = st.text_input("🔑 Password", value=user_data.get('password', ''))
                                e_fullname = st.text_input("📝 Full Name", value=user_data.get('full_name', ''))
                                current_role = str(user_data.get('role', 'staff')).lower()
                                roles = ["staff", "chef", "manager", "viewer", "admin", "admin_all"]
                                e_role = st.selectbox("🛡️ Role", roles, index=roles.index(current_role) if current_role in roles else 0)
                                
                            with e_col2:
                                current_modules = str(user_data.get('module', ''))
                                all_mods = ["waste", "cash", "inventory", "transfers", "dashboard"]
                                selected_mods = [m.strip() for m in current_modules.split(',')] if current_modules else []
                                valid_selected_mods = [m for m in selected_mods if m in all_mods]
                                e_modules = st.multiselect("📱 App Access (Modules)", all_mods, default=valid_selected_mods)
                                
                            st.divider()
                            st.subheader("Routing & Security Assignments")
                            
                            # Safely handle the user's current values so selectbox doesn't crash if it's missing
                            curr_c = user_data.get('client_name', 'All').title()
                            curr_o = user_data.get('outlet', 'All').title()
                            curr_l_list = [l.strip().title() for l in user_data.get('location', 'All').split(',')]
                            
                            safe_c_opts = c_opts if curr_c in c_opts else c_opts + [curr_c]
                            safe_o_opts = o_opts if curr_o in o_opts else o_opts + [curr_o]
                            safe_l_opts = l_opts.copy()
                            for l in curr_l_list: 
                                if l not in safe_l_opts: safe_l_opts.append(l)

                            e_col3, e_col4, e_col5 = st.columns(3)
                            with e_col3:
                                e_client = st.selectbox("🏢 Client Name", safe_c_opts, index=safe_c_opts.index(curr_c))
                            with e_col4:
                                e_outlet = st.selectbox("🏠 Outlet", safe_o_opts, index=safe_o_opts.index(curr_o))
                            with e_col5:
                                e_locations = st.multiselect("📍 Location(s)", safe_l_opts, default=curr_l_list)
                                
                            update_btn = st.form_submit_button("💾 Update User Settings", type="primary", use_container_width=True)
                            if update_btn:
                                update_payload = {
                                    "password": e_password.strip(),
                                    "full_name": e_fullname.strip(),
                                    "role": e_role,
                                    "client_name": e_client,
                                    "outlet": e_outlet,
                                    "location": ", ".join(e_locations) if e_locations else "All",
                                    "module": ", ".join(e_modules) if e_modules else ""
                                }
                                try:
                                    supabase.table("users").update(update_payload).eq("username", selected_user).execute()
                                    st.success(f"✅ Changes for '{selected_user}' saved successfully!")
                                    st.rerun() 
                                except Exception as e:
                                    st.error(f"❌ Database Error: {e}")
                else:
                    st.info("No users found in database.")
            except Exception as e:
                st.error(f"❌ Error loading users: {e}")