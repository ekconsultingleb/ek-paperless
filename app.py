import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# --- CONFIGURATION ---
# This is your Master Hub link
MASTER_HUB_URL = "https://docs.google.com/spreadsheets/d/1Bwk2UYwtLrg5bOzAbzF834aIlnCPBVYU4hAiaW26Fec"

st.set_page_config(page_title="EK Consulting Portal", layout="wide")

# --- CUSTOM CSS: REDUCE TOP PADDING & HIDE BRANDING ---
custom_css = """
            <style>
            /* 1. Shrink the massive empty space at the very top of the page */
            .block-container {
                padding-top: 2rem !important;
                padding-bottom: 1rem !important;
            }
            
            /* 2. Hide the default Streamlit footer */
            footer {visibility: hidden;}
            </style>
            """
st.markdown(custom_css, unsafe_allow_html=True)

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
                users_df = conn.read(spreadsheet=MASTER_HUB_URL,ttl=0)
                users_df.columns = [str(c).strip().lower() for c in users_df.columns]
                users_df['username'] = users_df['username'].astype(str).str.strip().str.lower()
                users_df['password'] = users_df['password'].astype(str).str.strip()

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

                revenue = cash_val + visa_val + exp_val + on_acc_val
                over_short = revenue - m_reading
                
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

            st.subheader("Month History")
            st.dataframe(df_cash.tail(31), use_container_width=True)

        except Exception as e:
            st.error(f"Error: {e}")

    # --- MODULE: INVENTORY ---
    elif st.session_state['module'] == "inventory":
        st.title(f"📦 Inventory Count: {st.session_state['user'].capitalize()}")
        
        try:
            df_inv = conn.read(spreadsheet=st.session_state['link'], worksheet="inventory", ttl=0)
            
            # --- NEW FILTERS & SEARCH ---
            st.sidebar.divider()
            st.sidebar.subheader("🔍 Filter & Search")
            
            locations = list(df_inv['Location'].dropna().unique())
            categories = list(df_inv['Category'].dropna().unique())
            groups = list(df_inv['Group'].dropna().unique())
            
            loc_filter = st.sidebar.selectbox("Location", locations)
            cat_filter = st.sidebar.selectbox("Category", categories)
            grp_filter = st.sidebar.selectbox("Group", groups)
            
            search_query = st.sidebar.text_input("Search Item (e.g. tomato, beef)", "")
            
            filtered_df = df_inv.copy()
            
            if search_query:
                filtered_df = filtered_df[filtered_df['Product Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
            else:
                filtered_df = filtered_df[filtered_df['Location'] == loc_filter]
                filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
                filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
                
            st.info(f"Showing {len(filtered_df)} matching items.")

            # --- END OF MONTH ARCHIVE BUTTON ---
            st.sidebar.divider()
            st.sidebar.subheader("📅 End of Month")
            with st.sidebar.expander("Submit Monthly Count"):
                st.warning("⚠️ Only click this when the ENTIRE count is 100% finished!")
                archive_date = st.date_input("Select Month/Date", datetime.today())
                
                if st.button("🚨 Archive & Reset to Zero", type="primary", use_container_width=True):
                    # 1. Pull the historical archive
                    df_archive = conn.read(spreadsheet=st.session_state['link'], worksheet="archive", ttl=0)
                    
                    # 2. Take a snapshot of current inventory and stamp it
                    df_snapshot = df_inv.copy()
                    df_snapshot['Archive Date'] = archive_date.strftime("%Y-%m-%d")
                    
                    # 3. Save to archive tab
                    updated_archive = pd.concat([df_archive, df_snapshot], ignore_index=True)
                    conn.update(spreadsheet=st.session_state['link'], worksheet="archive", data=updated_archive)
                    
                    # 4. Wipe the live inventory Qty to 0 and save
                    df_inv['Qty'] = 0.0
                    conn.update(spreadsheet=st.session_state['link'], worksheet="inventory", data=df_inv)
                    
                    st.success("✅ Month archived and board wiped clean!")
                    st.rerun()
            
            # --- MOBILE-FIRST UI (CARDS) ---
            st.write("### 📝 Enter Quantities")
            
            with st.form("mobile_inventory_form"):
                st.warning("⚠️ **IMPORTANT:** You MUST click the 'Save All Changes' button below BEFORE changing the Location or Category!")
                new_quantities = {}
                
                for index, row in filtered_df.iterrows():
                    with st.container(border=True):
                        col1, col2 = st.columns([1, 1], vertical_alignment="center")
                        with col1:
                            st.markdown(f"**{row['Product Description']}**")
                            st.caption(f"📦 Unit: {row['Unit']}")
                        with col2:
                            current_qty = float(row['Qty']) if pd.notna(row['Qty']) and str(row['Qty']).strip() != "" else 0.0
                            new_quantities[index] = st.number_input(
                                "Qty", value=current_qty, min_value=0.0, step=1.0,
                                key=f"qty_{index}", label_visibility="collapsed" 
                            )
                            
                submit_button = st.form_submit_button("💾 Save All Changes to Cloud", use_container_width=True)
                
                if submit_button:
                    for idx, new_val in new_quantities.items():
                        df_inv.at[idx, 'Qty'] = new_val
                    
                    conn.update(spreadsheet=st.session_state['link'], worksheet="inventory", data=df_inv)
                    st.success("✅ Inventory successfully updated!")
                    st.rerun()

            # --- ADD MISSING ITEM FORM ---
            st.divider()
            with st.expander("➕ Item Not Found? Add it here"):
                with st.form("add_new_item_form", clear_on_submit=True):
                    st.write("Fill out the details to add a new item to the master list.")
                    new_desc = st.text_input("Product Description (e.g. Red Bull)")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        new_loc = st.selectbox("Location", locations)
                        new_cat = st.selectbox("Category", categories)
                    with c2:
                        new_grp = st.selectbox("Group", groups)
                        new_unit = st.text_input("Unit (e.g. Btl, Kg, Box)")
                    
                    if st.form_submit_button("Add Item to Database"):
                        if new_desc and new_unit:
                            
                            # --- THE DUPLICATE CHECKER ---
                            # Make a hidden list of all existing items in lowercase
                            existing_items = df_inv['Product Description'].astype(str).str.lower().str.strip().tolist()
                            
                            # If their new item is already in the list, stop and show an error!
                            if new_desc.lower().strip() in existing_items:
                                st.error(f"🛑 Hold on! '{new_desc}' is already somewhere in the database. Try using the Global Search bar to find it!")
                            
                            # If it's truly a new item, proceed with saving it
                            else:
                                new_item_row = pd.DataFrame([{
                                    "Location": new_loc,
                                    "Category": new_cat,
                                    "Group": new_grp,
                                    "Product Description": new_desc,
                                    "Unit": new_unit,
                                    "Qty": 0.0
                                }])
                                
                                updated_inv = pd.concat([df_inv, new_item_row], ignore_index=True)
                                conn.update(spreadsheet=st.session_state['link'], worksheet="inventory", data=updated_inv)
                                
                                st.success(f"✅ {new_desc} added to the database!")
                                st.rerun()
                                
                        else:
                            st.error("Please fill in the Product Description and Unit.")

        except Exception as e:
            st.error(f"Error loading Inventory Sheet: {e}")

    # --- MODULE: ADMIN ---
    elif st.session_state['role'] == "admin":
        st.title("👑 Master Admin Dashboard")
        st.write("Overview of all connected client sheets will appear here.")

        # --- MODULE: WASTE TRACKER ---
    elif st.session_state['module'] == "waste":
        st.markdown(f"## 🗑️ Daily Waste Tracker: {st.session_state['user'].capitalize()}")
        
        try:
            # Load the 'waste' tab live
            df_waste = conn.read(spreadsheet=st.session_state['link'], worksheet="waste", ttl=0)
            
          # --- SIDEBAR FILTERS (SMART CASCADING DROPDOWNS) ---
            st.sidebar.divider()
            st.sidebar.subheader("🔍 Filter & Search")
            
            # 1. Get the Statuses and create the first dropdown
            statuses = list(df_waste['Status'].dropna().unique())
            stat_filter = st.sidebar.selectbox("Status (Menu/Inventory)", statuses)
            
            # 2. Filter the data based on the Status BEFORE building the Category list
            valid_categories = list(df_waste[df_waste['Status'] == stat_filter]['Category'].dropna().unique())
            cat_filter = st.sidebar.selectbox("Category", valid_categories)
            
            # 3. Filter the data based on Status AND Category BEFORE building the Group list
            valid_groups = list(df_waste[(df_waste['Status'] == stat_filter) & (df_waste['Category'] == cat_filter)]['Group'].dropna().unique())
            grp_filter = st.sidebar.selectbox("Group", valid_groups)
            
            # 4. The Global Search Box
            search_query = st.sidebar.text_input("Search Item (e.g. bread, salmon)", "")
            
            # Apply the final filters to the cards shown on screen
            filtered_df = df_waste.copy()
            
            if search_query:
                # Global search overrides dropdowns
                filtered_df = filtered_df[filtered_df['Description'].astype(str).str.lower().str.contains(search_query.lower(), na=False)]
            else:
                filtered_df = filtered_df[filtered_df['Status'] == stat_filter]
                filtered_df = filtered_df[filtered_df['Category'] == cat_filter]
                filtered_df = filtered_df[filtered_df['Group'] == grp_filter]
                
            st.info(f"Showing {len(filtered_df)} matching items.")

            # --- END OF DAY ARCHIVE BUTTON ---
            st.sidebar.divider()
            st.sidebar.subheader("📅 End of Day")
            with st.sidebar.expander("Submit Daily Waste"):
                st.warning("⚠️ Ready to close the day? This will save today's waste and reset the board.")
                archive_date = st.date_input("Select Date", datetime.today(), key="waste_date")
                
                if st.button("🚨 Archive & Reset to Zero", type="primary", use_container_width=True):
                    # 1. Pull the historical archive
                    df_archive = conn.read(spreadsheet=st.session_state['link'], worksheet="archive", ttl=0)
                    
                    # 2. Take a snapshot of ONLY items that were actually wasted today (Qty > 0)
                    df_snapshot = df_waste[df_waste['Qty'] > 0].copy()
                    
                    if not df_snapshot.empty:
                        df_snapshot['Archive Date'] = archive_date.strftime("%Y-%m-%d")
                        
                        # 3. Save to archive tab
                        updated_archive = pd.concat([df_archive, df_snapshot], ignore_index=True)
                        conn.update(spreadsheet=st.session_state['link'], worksheet="archive", data=updated_archive)
                    
                    # 4. Wipe the live waste Qty to 0 and clear Remarks
                    df_waste['Qty'] = 0.0
                    df_waste['Remarks'] = ""
                    conn.update(spreadsheet=st.session_state['link'], worksheet="waste", data=df_waste)
                    
                    st.success("✅ Daily waste archived and board wiped clean for tomorrow!")
                    st.rerun()

            # --- MOBILE UI (CARDS WITH REMARKS) ---
            st.write("### 📝 Enter Waste Quantities")
            
            with st.form("mobile_waste_form"):
                st.warning("⚠️ **IMPORTANT:** Hit 'Save' below before changing filters!")
                new_quantities = {}
                new_remarks = {}
                
                for index, row in filtered_df.iterrows():
                    with st.container(border=True):
                        # Top half: Info and Number Input
                        col1, col2 = st.columns([1, 1], vertical_alignment="center")
                        with col1:
                            st.markdown(f"**{row['Description']}**")
                            st.caption(f"📦 Unit: {row['Unit']}")
                        with col2:
                            current_qty = float(row['Qty']) if pd.notna(row['Qty']) and str(row['Qty']).strip() != "" else 0.0
                            new_quantities[index] = st.number_input(
                                "Qty", value=current_qty, min_value=0.0, step=1.0,
                                key=f"w_qty_{index}", label_visibility="collapsed" 
                            )
                            
                        # Bottom half: The Remark box
                        current_remark = str(row.get('Remarks', ''))
                        if current_remark == 'nan': current_remark = ""
                        new_remarks[index] = st.text_input(
                            "Remark", value=current_remark, key=f"w_rem_{index}",
                            placeholder="Reason for waste...", label_visibility="collapsed"
                        )
                            
                submit_button = st.form_submit_button("💾 Save All Changes to Cloud", use_container_width=True)
                
                if submit_button:
                    # Update master dataframe with quantities AND remarks
                    for idx, new_val in new_quantities.items():
                        df_waste.at[idx, 'Qty'] = new_val
                        df_waste.at[idx, 'Remarks'] = new_remarks[idx]
                    
                    conn.update(spreadsheet=st.session_state['link'], worksheet="waste", data=df_waste)
                    st.success("✅ Waste successfully updated!")
                    st.rerun()

        except Exception as e:
            st.error(f"Error loading Waste Sheet: {e}. Are you sure your headers match exactly?")