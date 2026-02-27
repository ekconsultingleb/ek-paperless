import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- IMPORT YOUR MODULES ---
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

st.set_page_config(page_title="EK Consulting Portal", layout="wide")

# --- BRANDING & LOGO ---
st.sidebar.image("EK-Logo.png", use_container_width=True)
st.sidebar.divider()
st.sidebar.success("✅ LIVE!")

# --- SESSION STATE INITIALIZATION ---
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 'user': None, 'module': None, 
        'role': None, 'assigned_outlet': 'All', 'assigned_location': 'All', 
        'client_name': 'All', 'current_page': 'home'
    })

# --- LOGIN LOGIC ---
if not st.session_state.get('logged_in', False):
    st.markdown("<h1 style='text-align: center;'>EK Consulting</h1>", unsafe_allow_html=True)
    with st.container(border=True):
        u_input = st.text_input("Username").strip()
        p_input = st.text_input("Password", type="password").strip()
        if st.button("Sign In", use_container_width=True):
            try:
                response = supabase.table("users").select("*").eq("username", u_input).eq("password", p_input).execute()
                if response.data:
                    match = response.data[0] 
                    st.session_state.update({
                        'logged_in': True,
                        'user': match.get('username'),
                        'role': str(match.get('role')).lower().strip(),
                        'module': match.get('module', 'All'), 
                        'assigned_outlet': str(match.get('outlet', 'All')).strip(),
                        'assigned_location': str(match.get('location', 'All')).strip(),
                        'client_name': str(match.get('client_name', 'All')).strip(),
                        'current_page': 'home'
                    })
                    st.rerun()
                else:
                    st.error("❌ Invalid Credentials")
            except Exception as e:
                st.error(f"Error: {e}")
else:
    # --- SIDEBAR INFO ---
    st.sidebar.title(f"👤 {st.session_state['user'].title()}")
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # --- TRAFFIC COP (NAVIGATION LOGIC) ---
    role = st.session_state['role']
    # Power User Logic: If assigned 'All', send 'All' to modules to unlock dropdowns
    client = "All" if (role == "admin" or st.session_state['client_name'].lower() == "all") else st.session_state['client_name']
    outlet = "All" if (role == "admin" or st.session_state['assigned_outlet'].lower() == "all") else st.session_state['assigned_outlet']
    location = st.session_state['assigned_location']
    
    # Module permissions
    raw_modules = str(st.session_state.get('module', '')).lower()
    allowed_modules = ["dashboard", "cash", "inventory", "waste", "transfers"] if (role == "admin" or "all" in raw_modules) else [m.strip() for m in raw_modules.split(",")]

    if role == "admin":
        st.sidebar.divider()
        if st.sidebar.button("⚙️ Admin Panel"): st.session_state['current_page'] = "main"; st.rerun()

    # Page Routing
    page = st.session_state['current_page']
    if page == 'home':
        # ... (Massive Button CSS remains same) ...
        st.markdown(f"## Welcome, {st.session_state['user'].title()}!")
        cols = st.columns(4)
        if "dashboard" in allowed_modules: 
            if cols[0].button("📊 Dashboard"): st.session_state['current_page'] = 'dashboard'; st.rerun()
        if "inventory" in allowed_modules:
            if cols[1].button("📦 Inventory"): st.session_state['current_page'] = 'inventory'; st.rerun()
        if "waste" in allowed_modules:
            if cols[2].button("🗑️ Waste"): st.session_state['current_page'] = 'waste'; st.rerun()
        if "cash" in allowed_modules:
            if cols[3].button("🏦 Daily Cash"): st.session_state['current_page'] = 'cash'; st.rerun()
    else:
        if st.button("⬅️ Back"): st.session_state['current_page'] = 'home'; st.rerun()
        if page == 'dashboard': render_dashboard(None, None, st.session_state['user'], role, client, outlet, location)
        elif page == 'cash': render_daily_cash(None, None, st.session_state['user'], role, client, outlet, location)
        elif page == 'inventory': render_inventory(None, None, st.session_state['user'], role, client, outlet, location)
        elif page == 'waste': render_waste(None, None, st.session_state['user'], role, client, outlet, location)
        elif page == 'transfers': render_transfers(None, None, st.session_state['user'], role, client, outlet, location)
        elif page == 'main': render_main(None, None, st.session_state['user'], role)