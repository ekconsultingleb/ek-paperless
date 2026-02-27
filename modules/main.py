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
                new_role = st.selectbox("🛡️ Role", ["staff", "manager", "viewer", "admin", "admin_all"])
            
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
    # TAB 2: MANAGE EXISTING USERS (LIVE EDITOR)
    # ==========================================
    with tab_view:
        st.subheader("Registered Users Directory")
        st.info("✏️ Edit user details directly in the table below, then click **Save Changes**.")
        
        try:
            # We pull ALL columns we want them to be able to edit, including password
            res = supabase.table("users").select("username, password, full_name, role, client_name, outlet, location, module").execute()
            
            if res.data:
                df_users = pd.DataFrame(res.data)
                
                # Display the data editor grid
                edited_df = st.data_editor(
                    df_users, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "username": st.column_config.TextColumn("Username", disabled=True), # Lock username so we don't break the DB link
                        "password": st.column_config.TextColumn("Password"),
                        "full_name": st.column_config.TextColumn("Full Name"),
                        "role": st.column_config.SelectboxColumn("Role", options=["staff", "manager", "viewer", "admin", "admin_all"]),
                        "client_name": st.column_config.TextColumn("Client (Branch)"),
                        "outlet": st.column_config.TextColumn("Outlet"),
                        "location": st.column_config.TextColumn("Location(s)"),
                        "module": st.column_config.TextColumn("Modules")
                    }
                )
                
                if st.button("💾 Save Changes", type="primary"):
                    with st.spinner("Pushing updates to cloud..."):
                        changes_made = 0
                        
                        # Loop through and compare the original data with the edited data
                        for i in range(len(df_users)):
                            orig_row = df_users.iloc[i]
                            new_row = edited_df.iloc[i]
                            
                            # If anything in this row changed, push the update to Supabase
                            if not orig_row.equals(new_row):
                                update_payload = {
                                    "password": new_row["password"],
                                    "full_name": new_row["full_name"],
                                    "role": new_row["role"],
                                    "client_name": new_row["client_name"],
                                    "outlet": new_row["outlet"],
                                    "location": new_row["location"],
                                    "module": new_row["module"]
                                }
                                # Update the specific user based on their unique username
                                supabase.table("users").update(update_payload).eq("username", orig_row["username"]).execute()
                                changes_made += 1
                                
                        if changes_made > 0:
                            st.success(f"✅ Successfully updated {changes_made} user(s)!")
                            st.rerun() # Refresh to show clean state
                        else:
                            st.warning("No changes were detected.")
            else:
                st.info("No users found in database.")
                
        except Exception as e:
            st.error(f"❌ Could not load user directory: {e}")