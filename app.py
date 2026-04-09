import streamlit as st
import pandas as pd
import time
from supabase import create_client, Client
import streamlit.components.v1 as components

# --- IMPORT YOUR MODULES ---
from modules.overview import render_overview
from modules.recipe_report import render_recipe_report
from modules.ledger import render_ledger
from modules.main import render_main
from modules.dashboard import render_dashboard
from modules.daily_cash import render_daily_cash
from modules.inventory import render_inventory
from modules.waste import render_waste
from modules.transfers import render_transfers
from modules.invoices import render_invoices
from modules.recipes import render_recipes
from modules.nav_helper import hash_password, verify_password
from modules.dpos import show_dpos

# --- INITIALIZE SUPABASE ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

st.set_page_config(page_title="Paperless", layout="wide")

# --- BULLETPROOF MOBILE BACK BUTTON PROTECTION ---
def inject_back_button_protection():
    components.html(
        """
        <script>
        window.parent.addEventListener('beforeunload', function (e) {
            e.preventDefault();
            e.returnValue = '';
        });
        window.parent.history.pushState('fake-route', null, '');
        window.parent.addEventListener('popstate', function (e) {
            var stay = window.parent.confirm("⚠️ Warning: Leaving this page will erase unsaved work! Do you want to stay?");
            if (stay) {
                window.parent.history.pushState('fake-route', null, '');
            } else {
                window.parent.history.back();
            }
        });
        </script>
        """,
        height=0,
        width=0,
    )

inject_back_button_protection()

# --- BRANDING & LOGO ---
st.sidebar.image("https://hgvubaohmgvesblfvdps.supabase.co/storage/v1/object/public/assets/EK-Logo.png", width=240)
st.sidebar.divider()
st.sidebar.markdown(
    "<div style='color:#8a9eaa; font-size:11px; text-align:center; padding:4px 0; letter-spacing:0.06em;'>PAPERLESS v2.0</div>",
    unsafe_allow_html=True
)

custom_css = """
<style>
/* ── EK CONSULTING — GLOBAL BRAND THEME ─────────────────────────────────────
   PANTONE 433 C  →  #1B252C  (charcoal)
   PANTONE 4685 C →  #E3C5AD  (warm sand)
   ──────────────────────────────────────────────────────────────────────── */

:root {
    --ek-dark:  #1B252C;
    --ek-dark2: #2E3D47;
    --ek-sand:  #E3C5AD;
    --ek-sand2: #F5EDE4;
    --ek-sand3: #c9a98a;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 5rem !important;
    max-width: 1100px !important;
}

#MainMenu { visibility: visible; }
header    { visibility: visible; }
footer    { visibility: hidden;  }

/* ── SIDEBAR ─────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--ek-dark) !important;
    border-right: 1px solid var(--ek-dark2) !important;
}
[data-testid="stSidebar"] * { color: var(--ek-sand) !important; }
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown h3,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption {
    color: var(--ek-sand) !important;
    opacity: 0.9;
}
[data-testid="stSidebar"] hr { border-color: var(--ek-dark2) !important; opacity: 0.6; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background-color: var(--ek-dark2) !important;
    border-color: var(--ek-sand3) !important;
    color: var(--ek-sand) !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button {
    background-color: var(--ek-dark2) !important;
    border: 1px solid var(--ek-sand3) !important;
    color: var(--ek-sand) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover {
    background-color: var(--ek-sand) !important;
    color: var(--ek-dark) !important;
}

/* ── PRIMARY BUTTONS ─────────────────────────────────────────────────────── */
[data-testid="stButton"] > button[kind="primary"] {
    background-color: var(--ek-dark) !important;
    color: var(--ek-sand) !important;
    border: 1px solid var(--ek-sand3) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background-color: var(--ek-dark2) !important;
    border-color: var(--ek-sand) !important;
    box-shadow: 0 0 12px rgba(227,197,173,0.25) !important;
    transform: translateY(-1px) !important;
}

/* ── SECONDARY BUTTONS ───────────────────────────────────────────────────── */
[data-testid="stButton"] > button:not([kind="primary"]) {
    border-radius: 8px !important;
    border: 1px solid rgba(227,197,173,0.3) !important;
    transition: all 0.2s !important;
}
[data-testid="stButton"] > button:not([kind="primary"]):hover {
    border-color: var(--ek-sand) !important;
    color: var(--ek-sand) !important;
}

/* ── TABS ────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    border-bottom: 2px solid rgba(227,197,173,0.2) !important;
    gap: 4px !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    padding: 8px 18px !important;
    font-weight: 500 !important;
    transition: all 0.2s !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background-color: var(--ek-dark) !important;
    color: var(--ek-sand) !important;
    border-bottom: 2px solid var(--ek-sand) !important;
}

/* ── METRIC CARDS ────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, var(--ek-dark) 0%, var(--ek-dark2) 100%) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    border: 1px solid rgba(227,197,173,0.15) !important;
}
[data-testid="stMetric"] label {
    color: var(--ek-sand3) !important;
    font-size: 12px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--ek-sand) !important;
    font-size: 24px !important;
    font-weight: 600 !important;
}

/* ── CONTAINERS / CARDS ──────────────────────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(227,197,173,0.2) !important;
    border-radius: 12px !important;
    padding: 4px !important;
}

/* ── INPUTS ──────────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stDateInput"] input {
    border-radius: 8px !important;
    border-color: rgba(227,197,173,0.3) !important;
    transition: border-color 0.2s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: var(--ek-sand) !important;
    box-shadow: 0 0 0 2px rgba(227,197,173,0.15) !important;
}

/* ── DATAFRAMES ──────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] thead tr th {
    background-color: var(--ek-dark) !important;
    color: var(--ek-sand) !important;
}

/* ── DIVIDERS ────────────────────────────────────────────────────────────── */
hr { border-color: rgba(227,197,173,0.15) !important; }

/* ── HOME MENU BUTTONS ───────────────────────────────────────────────────── */
.ek-home-btn > [data-testid="stButton"] > button {
    height: 120px !important;
    border-radius: 14px !important;
    background: linear-gradient(160deg, var(--ek-dark) 0%, var(--ek-dark2) 100%) !important;
    border: 1px solid rgba(227,197,173,0.2) !important;
    color: var(--ek-sand) !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    transition: all 0.25s ease !important;
}
.ek-home-btn > [data-testid="stButton"] > button:hover {
    border-color: var(--ek-sand) !important;
    box-shadow: 0 4px 20px rgba(227,197,173,0.2) !important;
    transform: translateY(-3px) !important;
    background: linear-gradient(160deg, var(--ek-dark2) 0%, #3a4f5c 100%) !important;
}
.ek-home-btn > [data-testid="stButton"] > button p {
    font-size: 16px !important;
    font-weight: 500 !important;
    line-height: 1.5 !important;
}

/* ── MOBILE ──────────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
    .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
    .ek-home-btn > [data-testid="stButton"] > button { height: 115px !important; font-size: 15px !important; }
    [data-testid="stMetric"] [data-testid="stMetricValue"] { font-size: 20px !important; }
}

/* ── SCROLLBAR ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--ek-dark2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--ek-sand3); }

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
# Rate limiting state (persists independently of logged_in)
if 'login_attempts' not in st.session_state:
    st.session_state['login_attempts'] = 0
if 'login_locked_until' not in st.session_state:
    st.session_state['login_locked_until'] = 0

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS    = 900  # 15 minutes

# ==========================================
# 🚀 MAIN APP ROUTING (LOGIN & SECURITY)
# ==========================================

if not st.session_state.get('logged_in', False):
    st.markdown("""
        <div style="text-align:center; padding:32px 0 24px;">
            <div style="
                display:inline-block;
                background:linear-gradient(135deg,#1B252C 0%,#2E3D47 100%);
                border-radius:20px; padding:28px 48px;
                border:1px solid rgba(227,197,173,0.2); margin-bottom:8px;
            ">
                <div style="color:#E3C5AD;font-size:28px;font-weight:700;letter-spacing:0.04em;">Paperless</div>
                <div style="color:#8a9eaa;font-size:13px;margin-top:6px;letter-spacing:0.08em;">by EK Consulting</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    with st.container(border=True):
        u_input = st.text_input("Username").strip()
        p_input = st.text_input("Password", type="password").strip()

        # Show lockout message above button if active
        _now = time.time()
        if st.session_state['login_locked_until'] > _now:
            _remaining = int(st.session_state['login_locked_until'] - _now)
            st.error(f"🔒 Too many failed attempts. Try again in {_remaining // 60}m {_remaining % 60}s.")

        if st.button("Sign In", width="stretch", type="primary"):
            _now = time.time()
            if st.session_state['login_locked_until'] > _now:
                _remaining = int(st.session_state['login_locked_until'] - _now)
                st.error(f"🔒 Account locked. Try again in {_remaining // 60}m {_remaining % 60}s.")
            else:
                try:
                    # Fetch by username only — verify password in Python (supports hashing)
                    response = supabase.table("users").select("*").eq("username", u_input).execute()
                    match = next((u for u in (response.data or []) if verify_password(p_input, u.get('password', ''))), None)
                    if match:
                        # Auto-upgrade legacy plaintext password to hash on first login
                        if not str(match.get('password', '')).startswith('pbkdf2:'):
                            supabase.table("users").update({"password": hash_password(p_input)}).eq("username", u_input).execute()
                        st.session_state['login_attempts'] = 0
                        st.session_state['login_locked_until'] = 0
                        st.session_state.update({
                            'logged_in': True,
                            'user': match.get('username', u_input),
                            'role': str(match.get('role', 'staff')).lower().strip(),
                            'module': match.get('module', 'All'),
                            'link': None,
                            'assigned_outlet':   str(match.get('outlet',      'All')).strip(),
                            'assigned_location': str(match.get('location',    'All')).strip(),
                            'client_name':       str(match.get('client_name', 'All')).strip(),
                            'current_page': 'home'
                        })
                        st.rerun()
                    else:
                        st.session_state['login_attempts'] += 1
                        if st.session_state['login_attempts'] >= _MAX_LOGIN_ATTEMPTS:
                            st.session_state['login_locked_until'] = time.time() + _LOCKOUT_SECONDS
                            st.error("🔒 Too many failed attempts. Account locked for 15 minutes.")
                        else:
                            _left = _MAX_LOGIN_ATTEMPTS - st.session_state['login_attempts']
                            st.error(f"❌ Invalid Username or Password. {_left} attempt(s) remaining.")
                except Exception as e:
                    st.error(f"Login Error: {e}")

else:
    # --- SIDEBAR & USER INFO ---
    st.sidebar.title(f"👤 {st.session_state['user'].title()}")
    st.sidebar.write(f"**Role:** {st.session_state['role'].title()}")

    if st.session_state['client_name'].lower() != 'all':
        st.sidebar.write(f"🏢 **Client:** {st.session_state['client_name']}")
    if st.session_state['assigned_outlet'].lower() != 'all':
        st.sidebar.write(f"🏠 **Outlet:** {st.session_state['assigned_outlet']}")
    if st.session_state['assigned_location'].lower() != 'all':
        st.sidebar.write(f"📍 **Location:** {st.session_state['assigned_location']}")

    if st.sidebar.button("Logout", width="stretch"):
        st.session_state.clear()
        st.rerun()

    # --- NAVIGATION LOGIC ---
    role = st.session_state['role']
    user = st.session_state['user']

    client = "All" if (role in ["admin", "admin_all"] or st.session_state['client_name'].lower() == "all") else st.session_state['client_name']
    outlet = "All" if (role in ["admin", "admin_all"] or st.session_state['assigned_outlet'].lower() == "all") else st.session_state['assigned_outlet']

    # Normalize location — same treatment as client and outlet
    raw_location = str(st.session_state.get('assigned_location', 'All')).strip()
    location = "All" if raw_location.lower() in ['all', '', 'none', 'nan'] else raw_location

    # Parse allowed modules
    raw_modules = str(st.session_state.get('module', '')).lower().strip()
    if raw_modules == "all_modules" or role in ["admin", "admin_all"]:
        allowed_modules = ["dashboard", "cash", "inventory", "waste", "transfers", "invoices", "ledger", "overview", "recipes", "recipes report", "pricing studio"]
    else:
        allowed_modules = [m.strip() for m in raw_modules.split(",") if m.strip()]

    # ── Sidebar back button (visible on every module page) ───────────────────
    if st.session_state.get('current_page', 'home') != 'home':
        st.sidebar.divider()
        if st.sidebar.button("⬅️ Back to Menu", width="stretch", key="sidebar_back_btn"):
            st.session_state['current_page'] = 'home'
            st.rerun()

    # Control Panel button (admin only)
    if role in ["admin", "admin_all"] or (role == "manager" and st.session_state['client_name'].lower() == 'all'):
        if st.session_state.get('current_page', 'home') == 'home':
            st.sidebar.divider()
        if st.sidebar.button("⚙️ Control Panel", type="primary"):
            st.session_state['current_page'] = "main"
            st.rerun()

    # Pricing Studio button (ek_team / admin only)
    if role in ["admin", "admin_all", "ek_team"]:
        if st.session_state.get('current_page', 'home') == 'home':
            st.sidebar.divider()
        if st.sidebar.button("💲 Pricing Studio", type="primary"):
            st.session_state['current_page'] = "pricing studio"
            st.rerun()
    # ==========================================
    # PAGE: HOME MENU
    # ==========================================
    if st.session_state['current_page'] == 'home':

        client_label = f" · {st.session_state['client_name']}" if st.session_state['client_name'].lower() != 'all' else ""
        st.markdown(f"""
            <div style="
                background:linear-gradient(135deg,#1B252C 0%,#2E3D47 100%);
                border-radius:16px; padding:24px 28px; margin-bottom:28px;
                border:1px solid rgba(227,197,173,0.15);
            ">
                <div style="color:#E3C5AD;font-size:22px;font-weight:600;margin-bottom:4px;">
                    Welcome back, {user.title()} 👋
                </div>
                <div style="color:#8a9eaa;font-size:14px;">
                    {role.title()}{client_label} · Paperless
                </div>
            </div>
        """, unsafe_allow_html=True)

        col_a, col_b, col_c, col_d = st.columns(4)

        if "cash" in allowed_modules:
            with col_a:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("🏦\nDaily Cash", width="stretch", key="btn_cash"):
                    st.session_state['current_page'] = 'cash'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "inventory" in allowed_modules:
            with col_b:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("📦\nInventory", width="stretch", key="btn_inventory"):
                    st.session_state['current_page'] = 'inventory'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "waste" in allowed_modules:
            with col_c:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("🗑️\nWaste", width="stretch", key="btn_waste"):
                    st.session_state['current_page'] = 'waste'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "invoices" in allowed_modules:
            with col_d:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("📸\nInvoices", width="stretch", key="btn_invoices"):
                    st.session_state['current_page'] = 'invoices'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        st.write("")
        col_e, col_f, col_g, col_h = st.columns(4)

        if "transfers" in allowed_modules or "transfer" in allowed_modules:
            with col_e:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("🔄\nTransfers", width="stretch", key="btn_transfers"):
                    st.session_state['current_page'] = 'transfers'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "dashboard" in allowed_modules:
            with col_f:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("📊\nDashboard", width="stretch", key="btn_dashboard"):
                    st.session_state['current_page'] = 'dashboard'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "ledger" in allowed_modules:
            with col_g:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("💸\nDebt Control", width="stretch", key="btn_ledger"):
                    st.session_state['current_page'] = 'ledger'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "overview" in allowed_modules:
            with col_h:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("📊\nOverview", width="stretch", key="btn_overview"):
                    st.session_state['current_page'] = 'overview'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        
        # --- ROW 3 ---
        st.write("")
        col_i, col_j, col_k, col_l = st.columns(4)

        if "recipes" in allowed_modules:
            with col_i:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("🍳\nRecipes", width="stretch", key="btn_recipes"):
                    st.session_state['current_page'] = 'recipes'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "recipes report" in allowed_modules:
            with col_j:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("📋\nRecipe Report", width="stretch", key="btn_recipe_report"):
                    st.session_state['current_page'] = 'recipes report'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        if "pricing studio" in allowed_modules:
            with col_k:
                st.markdown('<div class="ek-home-btn">', unsafe_allow_html=True)
                if st.button("💲\nPricing Studio", width="stretch", key="btn_pricing_studio"):
                    st.session_state['current_page'] = 'pricing studio'; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)


    # ==========================================
    # PAGE ROUTING (INSIDE MODULES)
    # ==========================================
    else:

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
        elif st.session_state['current_page'] == 'ledger':
            render_ledger(None, None, user, role)
        elif st.session_state['current_page'] == 'main':
            render_main(None, None, user, role)
        elif st.session_state['current_page'] == 'overview':
            render_overview(None, None, user, role, client, outlet, location)
        elif st.session_state['current_page'] == 'recipes':
            render_recipes(supabase, user, role)
        elif st.session_state['current_page'] == 'recipes report':
            render_recipe_report(supabase, user, role)
        elif st.session_state['current_page'] == 'pricing studio':
            show_dpos(supabase)