import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURATION ---
MASTER_HUB_URL = "https://docs.google.com/spreadsheets/d/1Bwk2UYwtLrg5bOzAbzF834aIlnCPBVYU4hAiaW26Fec"

st.set_page_config(page_title="EK Consulting Portal", layout="wide")

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
    st.session_state.update({'logged_in': False, 'user': None, 'module': None, 'link': None, 'role': None, 'current_page': 'home'})

# ==========================================
# 📦 MODULE PACKAGES (FUNCTIONS)
# ==========================================

def render_dashboard(sheet_link):
    st.markdown(f"### 📊 Management Dashboard")
    st.info("High-level overview of daily operations and metrics.")
    try:
        with st.spinner("⏳ Fetching live data from Google Servers..."):
            df_cash = conn.read(spreadsheet=sheet_link, worksheet="cash", ttl=60)
            df_waste = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=60)
        
        # --- BULLETPROOF COLUMN FIX ---
        # This scrubs any hidden spaces or lowercase letters in your Google Sheet headers!
        cash_rename = {}
        for col in df_cash.columns:
            clean = str(col).strip().lower()
            if clean == 'outlet': cash_rename[col] = 'Outlet'
            if clean == 'revenue': cash_rename[col] = 'Revenue'
            if clean == 'over / short' or clean == 'over/short': cash_rename[col] = 'Over / Short'
            if clean == 'date': cash_rename[col] = 'Date'
        df_cash.rename(columns=cash_rename, inplace=True)
        
        waste_rename = {}
        for col in df_waste.columns:
            if str(col).strip().lower() == 'qty': waste_rename[col] = 'Qty'
        df_waste.rename(columns=waste_rename, inplace=True)

        col1, col2, col3 = st.columns(3)
        
        # --- 1. GRAND TOTAL METRICS ---
        if not df_cash.empty and 'Revenue' in df_cash.columns:
            total_rev = df_cash['Revenue'].sum()
            total_variance = df_cash['Over / Short'].sum() if 'Over / Short' in df_cash.columns else 0
            
            col1.metric("Grand Total Revenue", f"{total_rev:,.2f}")
            col2.metric("Grand Total Cash Variance", f"{total_variance:,.2f}", delta=total_variance)
        else:
            col1.metric("Grand Total Revenue", "0.00")
            col2.metric("Grand Total Cash Variance", "0.00")
            
        # --- WASTE METRICS ---
        if not df_waste.empty and 'Qty' in df_waste.columns:
            total_waste_items = df_waste['Qty'].sum()
            col3.metric("Total Waste Items Logged", f"{total_waste_items:,.0f}")
        else:
            col3.metric("Total Waste Items Logged", "0")
            
        st.divider()
        
        # --- 2. OUTLET BREAKDOWN ---
        if not df_cash.empty and 'Outlet' in df_cash.columns and 'Revenue' in df_cash.columns:
            st.subheader("🏢 Revenue Breakdown by Outlet")
            
            # Fill empty outlets so the math doesn't crash
            df_cash['Outlet'] = df_cash['Outlet'].fillna("Unknown Outlet")
            
            # Ensure Over/Short exists for the math
            if 'Over / Short' not in df_cash.columns:
                df_cash['Over / Short'] = 0.0
            
            outlet_summary = df_cash.groupby('Outlet')[['Revenue', 'Over / Short']].sum().reset_index()
            outlets_list = outlet_summary.to_dict('records')
            
            if outlets_list:
                outlet_cols = st.columns(len(outlets_list))
                for i, out_data in enumerate(outlets_list):
                    with outlet_cols[i]:
                        st.metric(
                            label=f"{out_data['Outlet']} Revenue", 
                            value=f"{out_data['Revenue']:,.2f}", 
                            delta=f"Var: {out_data['Over / Short']:,.2f}",
                            delta_color="normal" if out_data['Over / Short'] >= 0 else "inverse"
                        )
        
        st.divider()
        
        # --- 3. TREND CHART ---
        st.subheader("📈 Total Revenue Trend")
        if not df_cash.empty and 'Date' in df_cash.columns and 'Revenue' in df_cash.columns:
            chart_data = df_cash.groupby('Date')['Revenue'].sum().reset_index()
            st.line_chart(chart_data, x='Date', y='Revenue')
            
    except Exception as e:
        st.error(f"Error loading Dashboard data. Details: {e}")
        

def render_daily_cash(sheet_link):
    st.markdown(f"### 🏦 Daily Cash Report")
    try:
        df_cash = conn.read(spreadsheet=sheet_link, worksheet="cash", ttl=0)
        with st.form("cash_entry_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                outlet_name = st.text_input("🏢 Outlet Name (e.g., Main, Achrafieh)")
                m_reading = st.number_input("Main Reading", min_value=0.0, step=0.1)
                cash_val = st.number_input("Cash", min_value=0.0, step=0.1)
                visa_val = st.number_input("Visa", min_value=0.0, step=0.1)
            with col2:
                exp_val = st.number_input("Expenses", min_value=0.0, step=0.1)
                on_acc_val = st.number_input("On Account", min_value=0.0, step=0.1)
                entry_date = st.date_input("📅 Report Date", datetime.now())

            revenue = cash_val + visa_val + exp_val + on_acc_val
            over_short = revenue - m_reading
            
            c1, c2 = st.columns(2)
            c1.metric("Total Revenue", f"{revenue:,.2f}")
            c2.metric("Over / Short", f"{over_short:,.2f}", delta=over_short)

            if st.form_submit_button("Submit Daily Report", use_container_width=True):
                new_row = pd.DataFrame([{
                    "Date": entry_date.strftime("%Y-%m-%d"), "Outlet": outlet_name,
                    "Main Reading": m_reading, "Over / Short": over_short, "Revenue": revenue,
                    "Cash": cash_val, "Visa": visa_val, "Expenses": exp_val, "On Account": on_acc_val
                }])
                updated_cash = pd.concat([df_cash, new_row], ignore_index=True)
                conn.update(spreadsheet=sheet_link, worksheet="cash", data=updated_cash)
                st.success(f"✅ Data saved for {outlet_name}! Variance: {over_short:,.2f}")
    except Exception as e:
        st.error(f"Error loading Cash module: {e}")

def render_inventory(sheet_link):
    st.markdown(f"### 📦 Inventory Count")
    try:
        df_inv = conn.read(spreadsheet=sheet_link, worksheet="inventory", ttl=0)
        
        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filter & Search")
        
        outlets = list(df_inv['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_inv.columns else ["Main"]
        outlet_filter = st.sidebar.selectbox("🏢 Select Outlet", outlets, key="inv_out")

        locations = list(df_inv[df_inv.get('Outlet', 'Main') == outlet_filter]['Location'].dropna().unique()) if 'Location' in df_inv.columns else []
        loc_filter = st.sidebar.selectbox("Location", locations, key="inv_loc") if locations else None
        
        categories = list(df_inv[(df_inv.get('Outlet', 'Main') == outlet_filter) & (df_inv.get('Location') == loc_filter)]['Category'].dropna().unique()) if 'Category' in df_inv.columns else []
        cat_filter = st.sidebar.selectbox("Category", categories, key="inv_cat") if categories else None
        
        groups = list(df_inv[(df_inv.get('Outlet', 'Main') == outlet_filter) & (df_inv.get('Location') == loc_filter) & (df_inv.get('Category') == cat_filter)]['Group'].dropna().unique()) if 'Group' in df_inv.columns else []
        grp_filter = st.sidebar.selectbox("Group", groups, key="inv_grp") if groups else None
        
        search_query = st.sidebar.text_input("Search Item", "", key="inv_search")
        
        filtered_df = df_inv.copy()
        if 'Outlet' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Outlet'] == outlet_filter]
            
        if search_query:
            filtered_df = filtered_df[filtered_df['Product Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
        else:
            if loc_filter: filtered_df = filtered_df[filtered_df['Location'] == loc_filter]
            if cat_filter: filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
            if grp_filter: filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
            
        with st.sidebar.expander("📅 End of Month Archive"):
            archive_date = st.date_input("Select Month/Date", datetime.today(), key="inv_date")
            if st.button("🚨 Archive & Reset to Zero", type="primary", use_container_width=True):
                df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_inv", ttl=0)
                df_snapshot = df_inv.copy()
                df_snapshot['archive date'] = archive_date.strftime("%Y-%m-%d")
                updated_archive = pd.concat([df_archive, df_snapshot], ignore_index=True)
                conn.update(spreadsheet=sheet_link, worksheet="archive_inv", data=updated_archive)
                df_inv['Qty'] = 0.0
                conn.update(spreadsheet=sheet_link, worksheet="inventory", data=df_inv)
                st.success("✅ Month archived!")
                st.rerun()
        
        with st.form("mobile_inventory_form"):
            new_quantities = {}
            for index, row in filtered_df.iterrows():
                with st.container(border=True):
                    col1, col2 = st.columns([1, 1], vertical_alignment="center")
                    with col1:
                        st.markdown(f"**{row.get('Product Description', 'Unknown Item')}**")
                        st.caption(f"📦 Unit: {row.get('Unit', '')}")
                    with col2:
                        current_qty = float(row['Qty']) if 'Qty' in row and pd.notna(row['Qty']) and str(row['Qty']).strip() != "" else 0.0
                        new_quantities[index] = st.number_input("Qty", value=current_qty, min_value=0.0, step=1.0, key=f"qty_{index}", label_visibility="collapsed")
                        
            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                for idx, new_val in new_quantities.items():
                    df_inv.at[idx, 'Qty'] = new_val
                conn.update(spreadsheet=sheet_link, worksheet="inventory", data=df_inv)
                st.success("✅ Inventory updated!")
                st.rerun()
    except Exception as e:
        st.error(f"Error loading Inventory module: {e}")

def render_waste(sheet_link, role="staff"):
    st.markdown(f"### 🗑️ Daily Waste & Events")
    try:
        # --- VIEWER MODE (KHALDOUN / DATA ENTRY) ---
        if role == "viewer":
            st.info("👁️ **Data Entry Mode:** View Daily Tickets for POS/Omega Entry.")
            df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=0)
            
            today = datetime.now().date()
            date_selection = st.date_input("📅 Select Date Range (From - To)", value=(today, today))
            
            if 'Archive Date' in df_archive.columns:
                if len(date_selection) == 2:
                    start_date, end_date = date_selection
                elif len(date_selection) == 1:
                    start_date = end_date = date_selection[0]
                else:
                    start_date = end_date = today
                
                df_archive['Archive Date'] = pd.to_datetime(df_archive['Archive Date'], errors='coerce').dt.date
                mask = (df_archive['Archive Date'] >= start_date) & (df_archive['Archive Date'] <= end_date)
                filtered_archive = df_archive.loc[mask].copy()
                
                if filtered_archive.empty:
                    st.warning(f"No waste logged between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}.")
                else:
                    filtered_archive['Archive Date'] = filtered_archive['Archive Date'].astype(str)
                    st.dataframe(filtered_archive, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_archive, use_container_width=True, hide_index=True)
                
            return

        # --- NORMAL STAFF/MANAGER MODE ---
        df_waste = conn.read(spreadsheet=sheet_link, worksheet="waste", ttl=0)
        
        st.info("👇 **Step 1: What are you logging?**")
        declaration = st.radio("Declaration Type", ["🗑️ Daily Waste", "🍽️ Staff Meal", "🎉 Event / Function"], horizontal=True, label_visibility="collapsed")
        
        waste_date = st.date_input("📅 Date of Event / Waste", datetime.now())

        event_name = ""
        if declaration == "🎉 Event / Function":
            event_name = st.text_input("🏆 Enter Event Name (e.g. Smith Wedding)")

        st.sidebar.divider()
        st.sidebar.subheader("🔍 Filter & Search")
        
        outlets = list(df_waste['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_waste.columns else ["Main"]
        outlet_filter = st.sidebar.selectbox("🏢 Select Outlet", outlets, key="w_out")

        statuses = list(df_waste[df_waste.get('Outlet', 'Main') == outlet_filter]['Status'].dropna().unique()) if 'Status' in df_waste.columns else []
        stat_filter = st.sidebar.selectbox("Status", statuses, key="w_stat") if statuses else None
        
        valid_cats = list(df_waste[(df_waste.get('Outlet', 'Main') == outlet_filter) & (df_waste.get('Status') == stat_filter)]['Category'].dropna().unique()) if 'Category' in df_waste.columns else []
        cat_filter = st.sidebar.selectbox("Category", valid_cats, key="w_cat") if valid_cats else None
        
        valid_grps = list(df_waste[(df_waste.get('Outlet', 'Main') == outlet_filter) & (df_waste.get('Status') == stat_filter) & (df_waste.get('Category') == cat_filter)]['Group'].dropna().unique()) if 'Group' in df_waste.columns else []
        grp_filter = st.sidebar.selectbox("Group", valid_grps, key="w_grp") if valid_grps else None
        
        search_query = st.sidebar.text_input("Search Item", "", key="w_search")
        
        filtered_df = df_waste.copy()
        if 'Outlet' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Outlet'] == outlet_filter]

        if search_query:
            filtered_df = filtered_df[filtered_df['Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
        else:
            if stat_filter: filtered_df = filtered_df[filtered_df['Status'] == stat_filter]
            if cat_filter: filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
            if grp_filter: filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
            
        with st.form("waste_ticket_form", clear_on_submit=True):
            new_quantities = {}
            new_remarks = {}
            for index, row in filtered_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row.get('Description', 'Unknown')}** &nbsp;|&nbsp; 📦 {row.get('Unit', '')}")
                    col1, col2 = st.columns([1, 1.5], vertical_alignment="center")
                    with col1:
                        new_quantities[index] = st.number_input("Qty", value=0.0, min_value=0.0, step=1.0, key=f"w_qty_{index}", label_visibility="collapsed")
                    with col2:
                        new_remarks[index] = st.text_input("Remark", value="", key=f"w_rem_{index}", placeholder="Optional remark...", label_visibility="collapsed")
                        
            if st.form_submit_button("🚀 Submit Ticket", type="primary", use_container_width=True):
                if declaration == "🎉 Event / Function" and not event_name:
                    st.error("🛑 Please enter the Event Name.")
                else:
                    ticket_items = []
                    for idx, row in filtered_df.iterrows():
                        qty = new_quantities[idx]
                        if qty > 0:
                            cat_text = str(row.get('Category', '')).lower()
                            is_bev = 'bev' in cat_text or 'drink' in cat_text or 'bar' in cat_text
                            
                            # TAG GENERATION
                            if declaration == "🗑️ Daily Waste": tag = "wb" if is_bev else "wf"
                            elif declaration == "🍽️ Staff Meal": tag = "smb" if is_bev else "sm" 
                            elif declaration == "🎉 Event / Function": tag = f"theo b - {event_name}" if is_bev else f"theo f - {event_name}"
                            
                            new_row = row.copy()
                            new_row['Qty'] = qty
                            
                            chef_remark = new_remarks[idx].strip()
                            if chef_remark:
                                new_row['Remarks'] = f"{tag} - {chef_remark}"
                            else:
                                new_row['Remarks'] = tag
                                
                            new_row['Archive Date'] = waste_date.strftime("%Y-%m-%d") 
                            new_row['Outlet'] = outlet_filter 
                            ticket_items.append(new_row)
                    
                    if ticket_items:
                        df_archive = conn.read(spreadsheet=sheet_link, worksheet="archive_waste", ttl=0)
                        df_ticket = pd.DataFrame(ticket_items)
                        updated_archive = pd.concat([df_archive, df_ticket], ignore_index=True)
                        conn.update(spreadsheet=sheet_link, worksheet="archive_waste", data=updated_archive)
                        st.success(f"✅ {declaration} logged successfully to {outlet_filter}!")
    except Exception as e:
        st.error(f"Error loading Waste module: {e}")

# ==========================================
# 🚀 MAIN APP ROUTING & LOGIC
# ==========================================

if not st.session_state['logged_in']:
    st.markdown("## 🛡️ EK Consulting Partner Portal")
    with st.container(border=True):
        u_input = st.text_input("Username").strip().lower()
        p_input = st.text_input("Password", type="password").strip()
        
        if st.button("Sign In", use_container_width=True):
            try:
                users_df = conn.read(spreadsheet=MASTER_HUB_URL, ttl=600)
                users_df.columns = [str(c).strip().lower() for c in users_df.columns]
                users_df['username'] = users_df['username'].astype(str).str.strip().str.lower()
                users_df['password'] = users_df['password'].astype(str).str.strip()

                match = users_df[(users_df['username'] == u_input) & (users_df['password'] == p_input)]
                
                if not match.empty:
                    st.session_state.update({
                        'logged_in': True,
                        'user': u_input,
                        'role': str(match.iloc[0]['role']).lower().strip(), # <--- THIS FIXES THE CAPITALIZATION BUG
                        'module': match.iloc[0]['module'],
                        'link': match.iloc[0]['client_sheet_link'],
                        'current_page': 'home'
                    })
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")
            except Exception as e:
                st.exception(e)

else:
    # --- SIDEBAR LOGOUT ---
    st.sidebar.title(f"👤 {st.session_state['user'].upper()}")
    st.sidebar.write(f"Role: {st.session_state['role'].capitalize()}")
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # --- ROUTING ENGINE ---
    role = st.session_state['role']
    sheet = st.session_state['link']
    
    # Convert the module string from the Google Sheet into a list we can read
    raw_modules = str(st.session_state['module']).lower().strip()
    if raw_modules == "all_modules" or role == "manager":
        allowed_modules = ["dashboard", "daily_cash", "inventory", "waste"] # ADDED DASHBOARD HERE
    else:
        allowed_modules = [m.strip() for m in raw_modules.split(",")]

    # 1. ADMIN DASHBOARD
    if role == "admin":
        st.markdown("## 👑 EK Consulting Command Center")
        st.info("Select a client below to instantly open their Google Sheet database.")
        
        try:
            users_df = conn.read(spreadsheet=MASTER_HUB_URL, ttl=600)
            
            # THE FIX: Force all columns to lowercase so Python never gets confused!
            users_df.columns = [str(c).strip().lower() for c in users_df.columns]
            
            # Filter out empty links AND filter out the admin row itself
            clients = users_df[(users_df['client_sheet_link'].notna()) & (users_df['role'] != 'admin')]
            unique_links = clients['client_sheet_link'].unique()
            
            with st.container(border=True):
                for link in unique_links:
                    # Pulls the exact restaurant name from your new 'clients' column
                    client_name = str(clients[clients['client_sheet_link'] == link]['clients'].iloc[0]).title()
                    st.markdown(f"#### 🔗 [{client_name} Master Database]({link})")
            
            st.divider()
            st.subheader("👥 Active User Directory")
            # Added your new 'clients' column to the directory view too!
            st.dataframe(users_df[['username', 'role', 'module', 'clients']], use_container_width=True)
            
        except Exception as e:
            # If it ever fails again, this will tell us exactly WHY it failed
            st.error(f"Could not load Master Hub data. Details: {e}")

    # 2. DYNAMIC APP ROUTING
    elif role != "admin":
        if len(allowed_modules) == 1 and st.session_state['current_page'] == 'home':
            st.session_state['current_page'] = allowed_modules[0]

        if st.session_state['current_page'] == 'home':
            st.markdown("## 📱 Main Menu")
            st.write("Select a module below to begin:")
            st.write("") 
            
            # THE NEW DASHBOARD BUTTON
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
                    
        else:
            if len(allowed_modules) > 1:
                if st.button("⬅️ Back to Main Menu"):
                    st.session_state['current_page'] = 'home'
                    st.rerun()
                st.divider()
            
            # Execute the function for the chosen page
            if st.session_state['current_page'] == 'dashboard':
                render_dashboard(sheet)
            elif st.session_state['current_page'] == 'daily_cash':
                render_daily_cash(sheet)
            elif st.session_state['current_page'] == 'inventory':
                render_inventory(sheet)
            elif st.session_state['current_page'] == 'waste':
                render_waste(sheet, role)