import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_main(conn, sheet_link, user, role):
    # 🚨 SECURITY LOCK: Only Admins can see this page
    if role.lower() != "admin":
        st.error("🚫 Access Denied. You must be an Administrator to view this page.")
        return

    st.markdown("### ⚙️ Admin Control Panel")
    st.info("Create new users, assign branches, and manage module access.")
    supabase = get_supabase()

    # --- TABS FOR ORGANIZATION ---
    tab_create, tab_view = st.tabs(["➕ Create New User", "👥 Manage Existing Users"])

    # ==========================================
    # TAB 1: CREATE USER FORM
    # ==========================================
    with tab_create:
        with st.form("create_user_form", clear_on_submit=True):
            st.subheader("Account Details")
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("👤 Username", placeholder="e.g. Sami_LaSiesta")
                new_password = st.text_input("🔑 Password", placeholder="Enter password")
                new_fullname = st.text_input("📝 Full Name", placeholder="e.g. Jacob Joshua")
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
    # TAB 2: MANAGE EXISTING USERS (FORM EDITOR)
    # ==========================================
    with tab_view:
        st.subheader("Edit User Profiles")
        
        try:
            # Fetch all users
            res = supabase.table("users").select("*").execute()
            
            if res.data:
                df_users = pd.DataFrame(res.data)
                
                # 1. Dropdown to select which user to edit
                user_list = sorted(df_users['username'].tolist())
                selected_user = st.selectbox("👤 Select a User to Edit", options=["-- Select a User --"] + user_list)
                
                if selected_user != "-- Select a User --":
                    # Get the current data for the selected user
                    user_data = df_users[df_users['username'] == selected_user].iloc[0]
                    
                    # 2. Open the edit form populated with their current data
                    with st.form("edit_user_form"):
                        st.markdown(f"**Editing Profile:** `{selected_user}`")
                        
                        e_col1, e_col2 = st.columns(2)
                        with e_col1:
                            e_password = st.text_input("🔑 Password", value=user_data.get('password', ''))
                            e_fullname = st.text_input("📝 Full Name", value=user_data.get('full_name', ''))
                            
                            # Handle role dropdown safely
                            current_role = str(user_data.get('role', 'staff')).lower()
                            roles = ["staff", "chef", "manager", "viewer", "admin", "admin_all"]
                            r_idx = roles.index(current_role) if current_role in roles else 0
                            e_role = st.selectbox("🛡️ Role", roles, index=r_idx)
                            
                        with e_col2:
                            # Handle modules multiselect safely
                            current_modules = str(user_data.get('module', ''))
                            all_mods = ["waste", "cash", "inventory", "transfers", "dashboard"]
                            selected_mods = [m.strip() for m in current_modules.split(',')] if current_modules else []
                            # Filter out any weird strings that aren't in the official list
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
                            
                        # Submit Button
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
                                st.rerun() # Refresh to show the updated data
                            except Exception as e:
                                st.error(f"❌ Database Error: {e}")
            else:
                st.info("No users found in database.")
                
        except Exception as e:
            st.error(f"❌ Error loading users: {e}")