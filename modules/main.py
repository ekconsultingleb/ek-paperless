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

    # --- DYNAMIC TABS BASED ON HIERARCHY ---
    if is_super_admin:
        st.info("👑 Super Admin Mode: Full access to all database and user controls.")
        tab_sync, tab_create, tab_view = st.tabs(["📤 Master Items Sync", "➕ Create New User", "👥 Manage Existing Users"])
        
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: You can sync databases and onboard new users.")
        tabs = st.tabs(["📤 Master Items Sync", "➕ Create New User"])
        tab_sync, tab_create = tabs[0], tabs[1]
        tab_view = None # Locked out of managing existing users
        
    elif is_hq_manager:
        st.info("🏢 HQ Manager Mode: You have access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Items Sync"])
        tab_sync = tabs[0]
        tab_create = None # Locked out of creating users
        tab_view = None   # Locked out of managing users

    # ==========================================
    # TAB 1: SMART EXCEL/CSV IMPORTER (Visible to All Authorized Roles)
    # ==========================================
    with tab_sync:
        st.markdown("#### 🔄 Smart Database Importer (Upsert)")
        st.info(
            "💡 **How this works:** Upload your latest CSV or Excel file. "
            "If the Product Code + Location already exists, the system will **UPDATE** the item's name and details. "
            "If it does not exist, it will **INSERT** it as a new item. No duplicate errors!"
        )

        uploaded_file = st.file_uploader("Upload Master Items List", type=["csv", "xlsx"])

        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)

                df.columns = [str(c).strip().lower() for c in df.columns]

                st.write(f"**Previewing {len(df)} rows:**")
                st.dataframe(df.head(5), use_container_width=True)

                required_cols = ['client_name', 'outlet', 'location', 'item_type', 'product_code', 'item_name']
                missing_cols = [c for c in required_cols if c not in df.columns]

                if missing_cols:
                    st.error(f"❌ Your file is missing these required columns: {', '.join(missing_cols)}")
                    st.caption("Please rename your Excel headers to match the database exactly.")
                else:
                    if st.button("🚀 Run Smart Sync", type="primary", use_container_width=True):
                        with st.spinner("Syncing to the Cloud... Do not refresh..."):
                            df = df.fillna('')
                            records = df.to_dict(orient='records')

                            batch_size = 500
                            for i in range(0, len(records), batch_size):
                                batch = records[i:i + batch_size]
                                supabase.table("master_items").upsert(
                                    batch,
                                    on_conflict="client_name,outlet,location,item_type,product_code"
                                ).execute()

                            st.success(f"✅ Successfully synced {len(records)} items!")
                            st.balloons()

            except Exception as e:
                st.error(f"❌ Error processing file: {e}")

    # ==========================================
    # TAB 2: CREATE USER FORM (Super Admins & Normal Admins Only)
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
                    # Notice we limit what role a normal admin can create if we wanted to, but we'll leave it flexible
                    new_role = st.selectbox("🛡️ Role", ["staff", "chef","manager", "viewer", "admin", "admin_all"])
                
                with col2:
                    available_modules = ["waste", "cash", "inventory", "transfers", "dashboard"]
                    new_modules = st.multiselect("📱 App Access (Modules)", available_modules, default=["waste"])

                st.divider()
                st.subheader("Routing & Security Assignments")
                col3, col4, col5 = st.columns(3)
                with col3:
                    new_client = st.text_input("🏢 Client Name", placeholder="e.g. La Siesta or 'All'", value="All")
                with col4:
                    new_outlet = st.text_input("🏠 Outlet", placeholder="e.g. Main or 'All'", value="All")
                with col5:
                    new_location = st.text_input("📍 Location(s)", placeholder="e.g. Main Store, Warehouse", value="All")

                st.caption("💡 *Note: To assign multiple locations, separate them with a comma (e.g. Main Store, Kitchen).*")
                
                submit_user = st.form_submit_button("🚀 CREATE USER", type="primary", use_container_width=True)

                if submit_user:
                    if not new_username.strip() or not new_password.strip():
                        st.error("❌ Username and Password are required!")
                    else:
                        module_string = ", ".join(new_modules) if new_modules else ""
                        
                        new_user_data = {
                            "username": new_username.strip(),
                            "password": new_password.strip(),
                            "full_name": new_fullname.strip(),
                            "role": new_role,
                            "client_name": new_client.strip().title() if new_client.strip().lower() != 'all' else 'All',
                            "outlet": new_outlet.strip().title() if new_outlet.strip().lower() != 'all' else 'All',
                            "location": new_location.strip().title() if new_location.strip().lower() != 'all' else 'All',
                            "module": module_string
                        }
                        try:
                            supabase.table("users").insert([new_user_data]).execute()
                            st.success(f"✅ User '{new_username}' has been successfully created and deployed!")
                            st.balloons()
                        except Exception as e:
                            st.error(f"❌ Database Error: {e}. Check if that username already exists.")

    # ==========================================
    # TAB 3: MANAGE EXISTING USERS (Super Admins ONLY)
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
                                r_idx = roles.index(current_role) if current_role in roles else 0
                                e_role = st.selectbox("🛡️ Role", roles, index=r_idx)
                                
                            with e_col2:
                                current_modules = str(user_data.get('module', ''))
                                all_mods = ["waste", "cash", "inventory", "transfers", "dashboard"]
                                selected_mods = [m.strip() for m in current_modules.split(',')] if current_modules else []
                                valid_selected_mods = [m for m in selected_mods if m in all_mods]
                                
                                e_modules = st.multiselect("📱 App Access (Modules)", all_mods, default=valid_selected_mods)
                                
                            st.divider()
                            st.subheader("Routing & Security Assignments")
                            e_col3, e_col4, e_col5 = st.columns(3)
                            
                            with e_col3:
                                e_client = st.text_input("🏢 Client Name", value=user_data.get('client_name', 'All'))
                            with e_col4:
                                e_outlet = st.text_input("🏠 Outlet", value=user_data.get('outlet', 'All'))
                            with e_col5:
                                e_location = st.text_input("📍 Location(s)", value=user_data.get('location', 'All'))
                                
                            update_btn = st.form_submit_button("💾 Update User Settings", type="primary", use_container_width=True)
                            
                            if update_btn:
                                mod_str = ", ".join(e_modules) if e_modules else ""
                                update_payload = {
                                    "password": e_password.strip(),
                                    "full_name": e_fullname.strip(),
                                    "role": e_role,
                                    "client_name": e_client.strip().title() if e_client.strip().lower() != 'all' else 'All',
                                    "outlet": e_outlet.strip().title() if e_outlet.strip().lower() != 'all' else 'All',
                                    "location": e_location.strip().title() if e_location.strip().lower() != 'all' else 'All',
                                    "module": mod_str
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