import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURATION ---
# This is your Master Hub link
MASTER_HUB_URL = "https://docs.google.com/spreadsheets/d/1Bwk2UYwtLrg5bOzAbzF834aIlnCPBVYU4hAiaW26Fec"

st.set_page_config(page_title="EK Consulting Portal", layout="wide")
# --- HIDE STREAMLIT BRANDING & MENU ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            [data-testid="stToolbar"] {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)
# --- DIAGNOSTIC TEST ---
if not st.secrets:
    st.error("🚨 STREAMLIT CANNOT FIND SECRETS.TOML!")
else:
    st.success("✅ Secrets loaded successfully!")
conn = st.connection("gsheets", type=GSheetsConnection)

# Initialize Session State
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False, 
        'user': None, 
        'module': None, 
        'link': None, 
        'role': None
    })

# --- 1. LOGIN INTERFACE ---
if not st.session_state['logged_in']:
    st.title("🛡️ EK Consulting Partner Portal")
    with st.container(border=True):
        u_input = st.text_input("Username").strip().lower()
        p_input = st.text_input("Password", type="password").strip()
        
        if st.button("Sign In", use_container_width=True):
            try:
                # 1. Read the sheet
                users_df = conn.read(spreadsheet=MASTER_HUB_URL,ttl=0)
                
                # 2. CLEANING: Remove spaces and make headers lowercase
                users_df.columns = [str(c).strip().lower() for c in users_df.columns]
                
                # 3. CLEANING: Remove spaces from the data itself
                users_df['username'] = users_df['username'].astype(str).str.strip().str.lower()
                users_df['password'] = users_df['password'].astype(str).str.strip()

                # 4. Check for match
                match = users_df[(users_df['username'] == u_input) & (users_df['password'] == p_input)]
                
                if not match.empty:
                    st.session_state.update({
                        'logged_in': True,
                        'user': u_input,
                        'role': match.iloc[0]['role'],
                        'module': match.iloc[0]['module'],
                        'link': match.iloc[0]['client_sheet_link']
                    })
                    st.rerun()
                else:
                    st.error("Invalid Username or Password")
            except Exception as e:
                st.exception(e)

# --- 2. THE APP DASHBOARD ---
else:
    # Sidebar Navigation
    st.sidebar.title(f"👤 {st.session_state['user'].upper()}")
    st.sidebar.write(f"Role: {st.session_state['role']}")
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.update({'logged_in': False})
        st.rerun()

# --- MODULE: DAILY CASH  ---
    if st.session_state['module'] == "daily_cash":
        st.title(f"🏦 Daily Cash Report: {st.session_state['user'].capitalize()}")
        
        try:
            df_cash = conn.read(spreadsheet=st.session_state['link'], worksheet="cash")
            
            with st.form("cash_entry_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    outlet_name = st.text_input("Outlet Name")
                    m_reading = st.number_input("Main Reading", min_value=0.0, step=0.1)
                    cash_val = st.number_input("Cash", min_value=0.0, step=0.1)
                    visa_val = st.number_input("Visa", min_value=0.0, step=0.1)
                with col2:
                    exp_val = st.number_input("Expenses", min_value=0.0, step=0.1)
                    on_acc_val = st.number_input("On Account", min_value=0.0, step=0.1)
                    entry_date = st.date_input("Report Date", datetime.now())

                # --- LIVE CALCULATIONS ---
                revenue = cash_val + visa_val + exp_val + on_acc_val
                over_short = revenue - m_reading
                
                # Show results in a nice box
                c1, c2 = st.columns(2)
                c1.metric("Total Revenue", f"{revenue:,.2f}")
                c2.metric("Over / Short", f"{over_short:,.2f}", delta=over_short)

                if st.form_submit_button("Submit Daily Report"):
                    new_row = pd.DataFrame([{
                        "Date": entry_date.strftime("%Y-%m-%d"),
                        "Outlet": outlet_name,
                        "Main Reading": m_reading,
                        "Over / Short": over_short,
                        "Revenue": revenue,
                        "Cash": cash_val,
                        "Visa": visa_val,
                        "Expenses": exp_val,
                        "On Account": on_acc_val
                    }])
                    
                    updated_cash = pd.concat([df_cash, new_row], ignore_index=True)
                    conn.update(spreadsheet=st.session_state['link'], worksheet="cash", data=updated_cash)
                    st.success(f"✅ Data saved! Variance: {over_short:,.2f}")
                    st.rerun()

            st.subheader("Previous 5 Days History")
            st.dataframe(df_cash.tail(5), use_container_width=True)

        except Exception as e:
            st.error(f"Error: {e}")

    # --- MODULE: INVENTORY
    elif st.session_state['module'] == "inventory":
        st.title(f"📦 Inventory Count: {st.session_state['user'].capitalize()}")
        
        try:
            # Load the 'inventory' tab
            df_inv = conn.read(spreadsheet=st.session_state['link'])
            
            # Filters to handle the 400+ items
            
# --- NEW FILTERS & SEARCH ---
            st.sidebar.divider()
            st.sidebar.subheader("🔍 Filter & Search")
            
            # 1. Create dropdown lists (Removed "All" from Location and Category)
            locations = list(df_inv['Location'].dropna().unique())
            categories = list(df_inv['Category'].dropna().unique())
            
            # We will keep "All" for the Group filter, just in case they want to see a whole category at once
            groups = ["All"] + list(df_inv['Group'].dropna().unique())
            
            # 2. Show the dropdowns in the sidebar
            loc_filter = st.sidebar.selectbox("Location", locations)
            cat_filter = st.sidebar.selectbox("Category", categories)
            grp_filter = st.sidebar.selectbox("Group", groups)
            
            # 3. Add a search box for mobile users
            search_query = st.sidebar.text_input("Search Item (e.g. tomato, beef)", "")
            
            # 4. Start with the full list of items
            filtered_df = df_inv.copy()
            
            # 5. Apply the strict filters automatically
            filtered_df = filtered_df[filtered_df['Location'] == loc_filter]
            filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
                
            # Apply the Group filter ONLY if they didn't select "All"
            if grp_filter != "All":
                filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
                
            # 6. Apply the Search filter
            if search_query:
                filtered_df = filtered_df[filtered_df['Product Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
            
            st.info(f"Showing {len(filtered_df)} matching items.")
            
            # Interactive Data Editor
            # --- MOBILE-FIRST UI (CARDS) ---
            st.write("### 📝 Enter Quantities")
            
            # We wrap the whole list in a form so they can hit Save once at the very bottom
            with st.form("mobile_inventory_form"):
                
                # We will store all their new typed numbers in this hidden dictionary
                new_quantities = {}
                
                # Loop through every item in their filtered list and draw a "Card"
                for index, row in filtered_df.iterrows():
                    with st.container(border=True):
                        # Item Name in bold
                        st.markdown(f"**{row['Product Description']}**")
                        
                        # Split the card into two columns: Details on left, Input on right
                        col1, col2 = st.columns([3, 2], vertical_alignment="center")
                        
                        with col1:
                            # 🎯 UPDATED: Shows only the Unit, Product Code is completely hidden!
                            st.caption(f"📦 Unit: {row['Unit']}")
                            
                        with col2:
                            # Pre-fill with the existing quantity if there is one
                            current_qty = float(row['Qty']) if pd.notna(row['Qty']) and str(row['Qty']).strip() != "" else 0.0
                            
                            # The big, touch-friendly number input
                            new_quantities[index] = st.number_input(
                                "Qty", 
                                value=current_qty, 
                                min_value=0.0, 
                                step=1.0,
                                key=f"qty_{index}",
                                label_visibility="collapsed" # Hides the word "Qty" to save screen space
                            )

                # The massive save button at the bottom of the feed
                submit_button = st.form_submit_button("💾 Save All Changes to Cloud", use_container_width=True)
                
                if submit_button:
                    # 1. Update our master dataframe with the new numbers ONLY
                    for idx, new_val in new_quantities.items():
                        df_inv.at[idx, 'Qty'] = new_val
                    
                    # 2. Shoot the updated data straight to Google Sheets
                    conn.update(spreadsheet=st.session_state['link'], worksheet="inventory", data=df_inv)
                    st.balloons()
                    st.success("✅ Inventory successfully updated!")

        except Exception as e:
            st.error(f"Error loading Inventory Sheet: {e}")

    # --- MODULE: ADMIN ---
    elif st.session_state['role'] == "admin":
        st.title("👑 Master Admin Dashboard")
        st.write("Overview of all connected client sheets will appear here.")
        # We can build a global summary table here later.