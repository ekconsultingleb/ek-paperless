import streamlit as st
import pandas as pd
from supabase import create_client, Client
import streamlit.components.v1 as components

# --- IMPORT YOUR MODULES ---
from modules.main import render_main
from modules.dashboard import render_dashboard
from modules.daily_cash import render_daily_cash
from modules.inventory import render_inventory
from modules.waste import render_waste
from modules.transfers import render_transfers
from modules.invoices import render_invoices

# --- INITIALIZE SUPABASE ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

st.set_page_config(page_title="EK Consulting Portal", layout="wide")

# --- BULLETPROOF MOBILE BACK BUTTON PROTECTION ---
def inject_back_button_protection():
    components.html(
        """
        <script>
        // 1. Standard protection for refreshing or closing the tab
        window.parent.addEventListener('beforeunload', function (e) {
            e.preventDefault();
            e.returnValue = '';
        });

        // 2. Mobile Hardware Back Button trick (History API)
        // Push a fake state into the phone's memory
        window.parent.history.pushState('fake-route', null, '');
        
        // Listen for the user hitting the Android back button
        window.parent.addEventListener('popstate', function (e) {
            // Ask for confirmation
            var stay = window.parent.confirm("⚠️ Warning: Leaving this page will erase unsaved work! Do you want to stay?");
            if (stay) {
                // If they want to stay, push the fake state again to trap the back button
                window.parent.history.pushState('fake-route', null, '');
            } else {
                // If they want to leave, let them go back again
                window.parent.history.back();
            }
        });
        </script>
        """,
        height=0,
        width=0,
    )

# Run the protection immediately so it guards every page
inject_back_button_protection()

# --- BRANDING & LOGO ---
st.sidebar.image("https://hgvubaohmgvesblfvdps.supabase.co/storage/v1/object/public/assets/EK-Logo.png", use_container_width=True)
st.sidebar.divider()
st.sidebar.caption("Partner Portal v1.0")

custom_css = """
            <style>
            .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
            #MainMenu {visibility: visible;}
            header {visibility: visible;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(custom_css, unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'module': None, 'link': None,
        'role': None, 'assigned_outlet': 'All', 'assigned_location': 'All',
        'client_name': 'All', 'current_page': 'home'
    })

# ==========================================
# 🚀 MAIN APP ROUTING (LOGIN & SECURITY)
# ==========================================

if not st.session_state.get('logged_in', False):
    st.markdown("""
        <h1 style='text-align: center; margin-bottom: 0;'> EK Consulting</h1>
        <p style='text-align: center; color: gray; font-size: 18px; margin-top: 0;'>Partner Portal</p>
    """, unsafe_allow_html=True)
    
    with st.container(border=True):
        u_input = st.text_input("Username").strip()
        p_input = st.text_input("Password", type="password").strip()
        
        if st.button("Sign In", use_container_width=True):
            try:
                # Search Supabase for the user
                response = supabase.table("users").select("*").eq("username", u_input).eq("password", p_input).execute()
                
                if len(response.data) > 0:
                    match = response.data[0]
                    
                    # Clean up data from database
                    assigned_out = str(match.get('outlet', 'All')).strip()
                    assigned_loc = str(match.get('location', 'All')).strip()
                    assigned_cli = str(match.get('client_name', 'All')).strip()

                    # Save EVERYTHING to Session State
                    st.session_state.update({
                        'logged_in': True,
                        'user': match.get('username', u_input),
                        'role': str(match.get('role', 'staff')).lower().strip(),
                        'module': match.get('module', 'All'),
                        'link': None,
                        'assigned_outlet': assigned_out,
                        'assigned_location': assigned_loc,
                        'client_name': assigned_cli,
                        'current_page': 'home'
                    })
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Password")
            except Exception as e:
                st.error(f"Login Error: {e}")

else:
    # --- SIDEBAR & USER INFO ---
    st.sidebar.title(f"👤 {st.session_state['user'].title()}")
    st.sidebar.write(f"**Role:** {st.session_state['role'].title()}")
    
    # Show specifics in sidebar if not 'All'
    if st.session_state['client_name'].lower() != 'all':
        st.sidebar.write(f"🏢 **Client:** {st.session_state['client_name']}")
    if st.session_state['assigned_outlet'].lower() != 'all':
        st.sidebar.write(f"🏠 **Outlet:** {st.session_state['assigned_outlet']}")
    if st.session_state['assigned_location'].lower() != 'all':
        st.sidebar.write(f"📍 **Location:** {st.session_state['assigned_location']}")
    
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # --- TRAFFIC COP (NAVIGATION LOGIC) ---
    role = st.session_state['role']
    user = st.session_state['user']
    
    # CRITICAL FIX: If assigned 'All', we send 'All' to the module to unlock dropdowns
    if role == "admin" or st.session_state['client_name'].lower() == "all":
        client = "All"
    else:
        client = st.session_state['client_name']

    if role == "admin" or st.session_state['assigned_outlet'].lower() == "all":
        outlet = "All"
    else:
        outlet = st.session_state['assigned_outlet']
        
    location = st.session_state['assigned_location']
    
    # Parse allowed modules
    raw_modules = str(st.session_state.get('module', '')).lower().strip()
    if raw_modules == "all_modules" or role == "admin":
        allowed_modules = ["dashboard", "cash", "inventory", "waste", "transfers", "invoices"]
    else:
        allowed_modules = [m.strip() for m in raw_modules.split(",") if m.strip()]

    # Secret Admin Panel Button (Double-Locked!)
    if role in ["admin", "admin_all"] or (role == "manager" and st.session_state['client_name'].lower() == 'all'):
        st.sidebar.divider()
        if st.sidebar.button("⚙️ Control Panel", type="primary"):
            st.session_state['current_page'] = "main"
            st.rerun()

    # ==========================================
    # PAGE: HOME MENU
    # ==========================================
    if st.session_state['current_page'] == 'home':
        st.markdown("""
            <style>
            div[data-testid="stButton"] > button {
                height: 100px !important;
                width: 100% !important;
                border-radius: 15px !important;
                border: 2px solid rgba(255,255,255,0.2) !important;
                transition: all 0.3s ease-in-out !important;
                padding: 0px !important;
            }
            div[data-testid="stButton"] > button:hover {
                border-color: #00ff00 !important;
                box-shadow: 0 0 20px rgba(0, 255, 0, 0.3) !important;
                transform: translateY(-5px) !important;
            }
            div[data-testid="stButton"] > button p {
                font-size: 24px !important;
                font-weight: 500 !important;
                margin: 0 !important;
            }
            </style>
        """, unsafe_allow_html=True)

        st.markdown(f"## Welcome back, {user.title()}! 👋")
        st.markdown("<h4 style='color: #888888; font-weight: 400; margin-bottom: 30px;'>Explore</h4>", unsafe_allow_html=True)
        
        col_a, col_b, col_c, col_d = st.columns(4)
        
        if "dashboard" in allowed_modules:
            with col_a:
                if st.button("📊 Dashboard", use_container_width=True):
                    st.session_state['current_page'] = 'dashboard'
                    st.rerun()
                    
        if "inventory" in allowed_modules:
            with col_b:
                if st.button("📦 Inventory", use_container_width=True):
                    st.session_state['current_page'] = 'inventory'
                    st.rerun()
                    
        if "waste" in allowed_modules:
            with col_c:
                if st.button("🗑️ Waste", use_container_width=True):
                    st.session_state['current_page'] = 'waste'
                    st.rerun()
                    
        if "transfers" in allowed_modules or "transfer" in allowed_modules:
            with col_d:
                if st.button("🔄 Transfers", use_container_width=True):
                    st.session_state['current_page'] = 'transfers'
                    st.rerun()

        # --- ROW 2 BUTTONS ---
        st.write("") # Spacer for the second row
        col_e, col_f, col_g, col_h = st.columns(4)
        
        if "cash" in allowed_modules:
            with col_e:
                if st.button("🏦 Daily Cash", use_container_width=True):
                    st.session_state['current_page'] = 'cash'
                    st.rerun()

        # 👇 THE NEW INVOICE BUTTON 👇
        if "invoices" in allowed_modules:
            with col_f:
                if st.button("📸 Snap Invoice", use_container_width=True):
                    st.session_state['current_page'] = 'invoices'
                    st.rerun()

    # ==========================================
    # PAGE ROUTING (INSIDE MODULES)
    # ==========================================
    else:
        if st.button("⬅️ Back to Main Menu"):
            st.session_state['current_page'] = 'home'
            st.rerun()
        st.divider()

        # Route to the correct module file
        if st.session_state['current_page'] == 'dashboard':
            render_dashboard(None, None, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'cash':
            render_daily_cash(None, None, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'inventory':
            render_inventory(None, None, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'waste':
            render_waste(None, None, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'transfers':
            render_transfers(None, None, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'invoices':
            render_invoices(None, None, user, role)
            
        elif st.session_state['current_page'] == 'main':
            render_main(None, None, user, role)