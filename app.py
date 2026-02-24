import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- IMPORT YOUR NEW MODULES ---
from modules.dashboard import render_dashboard
from modules.daily_cash import render_daily_cash
from modules.inventory import render_inventory
from modules.waste import render_waste
from modules.transfers import render_transfers

# --- CONFIGURATION ---
MASTER_HUB_URL = "https://docs.google.com/spreadsheets/d/1Bwk2UYwtLrg5bOzAbzF834aIlnCPBVYU4hAiaW26Fec"

st.set_page_config(page_title="EK Consulting Portal", layout="wide")
# --- BRANDING & LOGO ---
st.sidebar.image("EK-Logo.png", use_container_width=True)
st.sidebar.divider()
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

if not st.session_state['logged_in']:
    st.markdown("""
        <h1 style='text-align: center; margin-bottom: 0;'> EK Consulting</h1>
        <p style='text-align: center; color: gray; font-size: 18px; margin-top: 0;'>Partner Portal</p>
    """, unsafe_allow_html=True)
    with st.container(border=True):
        u_input = st.text_input("Username").strip().lower()
        p_input = st.text_input("Password", type="password").strip()
        
        if st.button("Sign In", use_container_width=True):
            try:
                users_df = conn.read(spreadsheet=MASTER_HUB_URL, worksheet="users", ttl=600)
                users_df.columns = [str(c).strip().lower() for c in users_df.columns]
                users_df['username'] = users_df['username'].astype(str).str.strip().str.lower()
                users_df['password'] = users_df['password'].astype(str).str.strip()

                match = users_df[(users_df['username'] == u_input) & (users_df['password'] == p_input)]
                
                if not match.empty:
                    # Capture assigned Outlet and Location from the Master Hub
                    assigned_out = "All"
                    if 'assigned_outlet' in match.columns and pd.notna(match.iloc[0]['assigned_outlet']):
                        assigned_out = str(match.iloc[0]['assigned_outlet']).strip()
                        
                    assigned_loc = "All"
                    if 'assigned_location' in match.columns and pd.notna(match.iloc[0]['assigned_location']):
                        assigned_loc = str(match.iloc[0]['assigned_location']).strip()

                    st.session_state.update({
                        'logged_in': True,
                        'user': u_input,
                        'role': str(match.iloc[0]['role']).lower().strip(),
                        'module': match.iloc[0]['module'],
                        'link': match.iloc[0]['client_sheet_link'],
                        'assigned_outlet': assigned_out,
                        'assigned_location': assigned_loc,
                        'current_page': 'home'
                    })
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")
            except Exception as e:
                st.exception(e)

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
    
    raw_modules = str(st.session_state['module']).lower().strip()
    if raw_modules == "all_modules" or role == "manager":
        allowed_modules = ["dashboard", "daily_cash", "inventory", "waste", "transfers"]
    else:
        allowed_modules = [m.strip() for m in raw_modules.split(",")]

    # 1. ADMIN COMMAND CENTER
    if role == "admin":
        st.markdown("## 👑 EK Consulting Command Center")
        st.info("Select a client below to instantly open their Google Sheet database.")
        
        try:
            users_df = conn.read(spreadsheet=MASTER_HUB_URL, worksheet="users", ttl=600)
            users_df.columns = [str(c).strip().lower() for c in users_df.columns]
            
            clients = users_df[(users_df['client_sheet_link'].notna()) & (users_df['role'] != 'admin')]
            unique_links = clients['client_sheet_link'].unique()
            
            with st.container(border=True):
                for link in unique_links:
                    client_name = str(clients[clients['client_sheet_link'] == link]['clients'].iloc[0]).title()
                    st.markdown(f"#### 🔗 [{client_name} Master Database]({link})")
            
            st.divider()
            st.subheader("👥 Active User Directory")
            cols_to_show = ['username', 'role', 'module', 'clients']
            if 'assigned_outlet' in users_df.columns: cols_to_show.append('assigned_outlet')
            if 'assigned_location' in users_df.columns: cols_to_show.append('assigned_location')
            st.dataframe(users_df[cols_to_show], use_container_width=True)
            
        except Exception as e:
            st.error(f"Could not load Master Hub data. Details: {e}")

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