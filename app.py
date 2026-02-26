import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from supabase import create_client, Client

# --- IMPORT YOUR NEW MODULES ---
from modules.main import render_main
from modules.dashboard import render_dashboard
from modules.daily_cash import render_daily_cash
from modules.inventory import render_inventory
from modules.waste import render_waste
from modules.transfers import render_transfers

# --- INITIALIZE SUPABASE ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

# --- CONFIGURATION ---
MASTER_HUB_URL = "https://docs.google.com/spreadsheets/d/1Bwk2UYwtLrg5bOzAbzF834aIlnCPBVYU4hAiaW26Fec"

st.set_page_config(page_title="EK Consulting Portal", layout="wide")

# --- BRANDING & LOGO ---
st.sidebar.image("EK-Logo.png", use_container_width=True)
st.sidebar.divider()
st.sidebar.success("✅ LIVE!")
custom_css = """
            <style>
            .block-container { padding-top: 2rem !important; padding-bottom: 1rem !important; }
            #MainMenu {visibility: visible;}
            header {visibility: visible;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(custom_css, unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

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
                    
                    # 1. Clean up Outlet and Location
                    assigned_out = str(match.get('outlet', 'All')).strip() if match.get('outlet') else "All"
                    assigned_loc = str(match.get('location', 'All')).strip() if match.get('location') else "All"

                    # 2. Save EVERYTHING to Session State
                    st.session_state.update({
                        'logged_in': True,
                        'user': match.get('username', u_input),
                        'role': str(match.get('role', 'staff')).lower().strip(),
                        'module': match.get('module', 'All'), 
                        'link': match.get('client_sheet_link', ''), 
                        'assigned_outlet': assigned_out,
                        'assigned_location': assigned_loc,
                        'client_name': match.get('client_name', 'All'), # Passes Hajj Nasr or La Siesta
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
    
    if st.session_state.get('client_name', 'All').lower() != 'all':
        st.sidebar.write(f"🏢 **Client:** {st.session_state['client_name']}")
    if st.session_state.get('assigned_outlet', 'All').lower() != 'all':
        st.sidebar.write(f"🏠 **Outlet:** {st.session_state['assigned_outlet']}")
    if st.session_state.get('assigned_location', 'All').lower() != 'all':
        st.sidebar.write(f"📍 **Location:** {st.session_state['assigned_location']}")
    
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # --- TRAFFIC COP (NAVIGATION) ---
    role = st.session_state['role']
    sheet = st.session_state['link']
    user = st.session_state['user']
    outlet = st.session_state['assigned_outlet']
    location = st.session_state['assigned_location']
    client = st.session_state.get('client_name', 'All') 
    
    # 1. PARSE ALLOWED MODULES
    raw_modules = str(st.session_state.get('module', '')).lower().strip()
    
    if raw_modules == "all_modules" or role == "admin":
        allowed_modules = ["dashboard", "cash", "inventory", "waste", "transfers"]
    else:
        allowed_modules = [m.strip() for m in raw_modules.split(",") if m.strip()]

    # Secret Admin Panel Button
    if role == "admin":
        st.sidebar.divider()
        if st.sidebar.button("⚙️ Admin Panel", type="primary"):
            st.session_state['current_page'] = "main"
            st.rerun()

    # ==========================================
    # 2. PAGE: HOME MENU
    # ==========================================
    if st.session_state['current_page'] == 'home':
        
        # --- CSS MAGIC: Make the home buttons massive and interactive ---
        st.markdown("""
            <style>
            /* Force the button and its container to accept the new height */
            div[data-testid="stButton"] > button {
                height: 50px !important;
                width: 100% !important;
                border-radius: 15px !important;
                border: 2px solid rgba(255,255,255,0.2) !important;
                transition: all 0.3s ease-in-out !important;
                padding: 0px !important;
            }
            
            /* The Hover Glow Effect */
            div[data-testid="stButton"] > button:hover {
                border-color: #00ff00 !important;
                box-shadow: 0 0 20px rgba(0, 255, 0, 0.3) !important;
                transform: translateY(-5px) !important;
            }
            
            /* The Text inside the button */
            div[data-testid="stButton"] > button p {
                font-size: 24px !important; 
                font-weight: 500 !important;
                margin: 0 !important;
            }
            </style>
        """, unsafe_allow_html=True)
        # --- A Clean, Modern Greeting ---
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

        if "cash" in allowed_modules:
            st.write("") # Adds a tiny bit of spacing before the next row
            col_e, _, _, _ = st.columns(4)
            with col_e:
                if st.button("🏦 Daily Cash", use_container_width=True):
                    st.session_state['current_page'] = 'cash'
                    st.rerun()

        # 👑 ADMIN ONLY: MASTER HUB LINKS
        if role == "admin":
            st.divider()
            st.subheader("🔗 Master Database Links")
            st.info("Direct access to client Google Sheets:")
            try:
                users_df = conn.read(spreadsheet=MASTER_HUB_URL, worksheet="users", ttl=600)
                users_df.columns = [str(c).strip().lower() for c in users_df.columns]
                
                clients_with_links = users_df[users_df['client_sheet_link'].notna()]
                unique_links = clients_with_links['client_sheet_link'].unique()
                
                with st.container(border=True):
                    for link in unique_links:
                        c_name = clients_with_links[clients_with_links['client_sheet_link'] == link]['client_name'].iloc[0]
                        st.markdown(f"🔹 [{str(c_name).title()} Master Database]({link})")
            except Exception as e:
                st.error(f"Could not load Master Hub links: {e}")

    # ==========================================
    # 3. PAGE ROUTING (INSIDE MODULES)
    # ==========================================
    else:
        if st.button("⬅️ Back to Main Menu"):
            st.session_state['current_page'] = 'home'
            st.rerun()
        st.divider()

        # Route to the correct file
        if st.session_state['current_page'] == 'dashboard':
            render_dashboard(conn, sheet, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'cash':
            render_daily_cash(conn, sheet, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'inventory':
            render_inventory(conn, sheet, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'waste':
            render_waste(conn, sheet, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'transfers':
            render_transfers(conn, sheet, user, role, client, outlet, location)
            
        elif st.session_state['current_page'] == 'main':
            render_main(conn, sheet, user, role)