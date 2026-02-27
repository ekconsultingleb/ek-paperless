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
                new_role = st.selectbox("🛡️ Role", ["Staff", "Manager", "Viewer", "Admin", "Admin_All"])
            
            with col2:
                available_modules = ["waste", "cash", "inventory", "transfers", "dashboard"]
                new_modules = st.multiselect("📱 App Access (Modules)", available_modules, default=["waste"])
                # Removed the Google Sheet link input entirely

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
                    
                    # Cleaned dictionary - no sheet links
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
    # TAB 2: VIEW EXISTING USERS
    # ==========================================
    with tab_view:
        st.subheader("Registered Users Directory")
        try:
            res = supabase.table("users").select("username, full_name, role, client_name, outlet, location, module").execute()
            if res.data:
                df_users = pd.DataFrame(res.data)
                df_users.columns = [col.replace("_", " ").title() for col in df_users.columns]
                st.dataframe(df_users, use_container_width=True, hide_index=True)
            else:
                st.info("No users found.")
        except Exception as e:
            st.error(f"❌ Could not load user directory: {e}")