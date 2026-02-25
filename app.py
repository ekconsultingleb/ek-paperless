import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from supabase import create_client, Client  # <-- Add this right here!

# --- IMPORT YOUR NEW MODULES ---
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
st.sidebar.success("✅ Supabase is LIVE!") # Quick test!
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
        'role': None, 'assigned_outlet': 'All', 'assigned_location': 'All', 'current_page': 'home'
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
        p_input = st.text_input("Password", type="password").strip() # Added .strip() here too
        
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
                        'client_name': match.get('client_name', 'All'), # This is the key!
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
    
    if st.session_state.get('assigned_outlet', 'All').lower() != 'all':
        st.sidebar.write(f"🏢 **Outlet:** {st.session_state['assigned_outlet']}")
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
    
    # 1. PAGE: HOME MENU
    if st.session_state['current_page'] == 'home':
        if role == "admin":
            st.markdown(f"## 👑 Welcome, {user.title()}")
            st.subheader("📱 App Modules")
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                if st.button("📊 Dashboard", use_container_width=True):
                    st.session_state['current_page'] = 'dashboard'
                    st.rerun()
            with col_b:
                if st.button("📦 Inventory", use_container_width=True):
                    st.session_state['current_page'] = 'inventory'
                    st.rerun()
            with col_c:
                if st.button("🗑️ Waste", use_container_width=True):
                    st.session_state['current_page'] = 'waste'
                    st.rerun()
            with col_d:
                if st.button("🔄 Transfers", use_container_width=True):
                    st.session_state['current_page'] = 'transfers'
                    st.rerun()

            st.divider()
            st.subheader("🔗 Master Database Links")
            # ... (Your existing code for the Google Sheet links goes here)

        else:
            # Logic for STAFF menu buttons goes here
            st.markdown(f"## 👨‍🍳 Welcome, {user.title()}")
            # (Show buttons based on allowed_modules)

    # 2. PAGE: INVENTORY
    elif st.session_state['current_page'] == 'inventory':
        if st.button("⬅️ Back to Menu"):
            st.session_state['current_page'] = 'home'
            st.rerun()
        # This calls your new Supabase module!
        render_inventory(supabase, None, user, role, outlet, location)

    # 3. PAGE: WASTE
    elif st.session_state['current_page'] == 'waste':
        if st.button("⬅️ Back to Menu"):
            st.session_state['current_page'] = 'home'
            st.rerun()
        # This still calls the Google Sheets version
        render_waste(conn, sheet, user, role, outlet, location)

    # 4. PAGE: DASHBOARD
    elif st.session_state['current_page'] == 'dashboard':
        if st.button("⬅️ Back to Menu"):
            st.session_state['current_page'] = 'home'
            st.rerun()
        render_dashboard(conn, sheet)
        
        # --- THE MASTER DIRECTORY ---
        st.subheader("🔗 Master Database Links")
        st.info("Direct access to client Google Sheets:")
        
        try:
            # We still read the Master Hub for the links
            users_df = conn.read(spreadsheet=MASTER_HUB_URL, worksheet="users", ttl=600)
            users_df.columns = [str(c).strip().lower() for c in users_df.columns]
            
            clients_with_links = users_df[users_df['client_sheet_link'].notna()]
            unique_links = clients_with_links['client_sheet_link'].unique()
            
            with st.container(border=True):
                for link in unique_links:
                    # Get the client name associated with this link
                    c_name = clients_with_links[clients_with_links['client_sheet_link'] == link]['clients'].iloc[0]
                    st.markdown(f"🔹 [{str(c_name).title()} Master Database]({link})")
            
        except Exception as e:
            st.error(f"Could not load Master Hub links: {e}")

    # 2. DYNAMIC APP MENU
    elif role != "admin":
        if len(allowed_modules) == 1 and st.session_state['current_page'] == 'home':
            st.session_state['current_page'] = allowed_modules[0]

        if st.session_state['current_page'] == 'home':
            st.markdown("## 📱 Main Menu")
            st.write("Select a module below to begin:")
            st.write("") 
            
            if "dashboard" in allowed_modules:
                if st.button("📊 Management Dashboard", use_container_width=True):
                    st.session_state['current_page'] = 'dashboard'
                    st.rerun()
                st.write("")
            
            if "daily_cash" in allowed_modules:
                if st.button("🏦 Daily Cash Report", use_container_width=True):
                    st.session_state['current_page'] = 'daily_cash'
                    st.rerun()
                st.write("")
                
            if "waste" in allowed_modules:
                if st.button("🗑️ Daily Waste & Events", use_container_width=True):
                    st.session_state['current_page'] = 'waste'
                    st.rerun()
                st.write("")
                
            if "inventory" in allowed_modules:
                if st.button("📦 Inventory Count", use_container_width=True):
                    st.session_state['current_page'] = 'inventory'
                    st.rerun()
                st.write("")
            
            # --- THE NEW TRANSFERS BUTTON ---
            if "transfers" in allowed_modules:
                if st.button("🔄 Warehouse Transfers", use_container_width=True):
                    st.session_state['current_page'] = 'transfers'
                    st.rerun()
                st.write("")
                    
        else:
            if len(allowed_modules) > 1:
                if st.button("⬅️ Back to Main Menu"):
                    st.session_state['current_page'] = 'home'
                    st.rerun()
                st.divider()
            
            # --- ROUTING TO THE NEW FILES ---
            if st.session_state['current_page'] == 'dashboard':
                render_dashboard(conn, sheet, outlet)
            elif st.session_state['current_page'] == 'daily_cash':
                render_daily_cash(conn, sheet, outlet)
            elif st.session_state['current_page'] == 'inventory':
                render_inventory(conn, sheet, user, role, outlet, location)
            elif st.session_state['current_page'] == 'waste':
                render_waste(conn, sheet, user, role, outlet, location)
            elif st.session_state['current_page'] == 'transfers':
                render_transfers(conn, sheet, user, role, outlet, location)