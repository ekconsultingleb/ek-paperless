import streamlit as st
import pandas as pd
from datetime import datetime
import uuid

def render_transfers(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown("### 🔄 Warehouse Transfers & Requisitions")
    
    try:
        # Load data
        df_transfers = conn.read(spreadsheet=sheet_link, worksheet="transfers", ttl=0)
        df_inv = conn.read(spreadsheet=sheet_link, worksheet="inventory", ttl=600)
        
        all_outlets = list(df_inv['Outlet'].dropna().astype(str).unique()) if 'Outlet' in df_inv.columns else ["Main Warehouse", "Branch 1"]
        
        # --- SECURITY FILTERS FOR TABS ---
        # Find exactly what THIS user is allowed to Dispatch and Receive
        is_global = (assigned_outlet.lower() == 'all' or assigned_outlet == '')
        
        my_pending = df_transfers[(df_transfers['Status'] == 'Pending') & 
                                  ((df_transfers['From Outlet'] == assigned_outlet) | is_global)]
                                  
        my_incoming = df_transfers[(df_transfers['Status'] == 'In Transit') & 
                                   ((df_transfers['To Outlet'] == assigned_outlet) | is_global)]

        # --- IN-APP NOTIFICATIONS ---
        if not my_pending.empty:
            st.warning(f"🔔 **Alert:** You have {len(my_pending)} pending requests to dispatch!")
        if not my_incoming.empty:
            st.info(f"🚚 **Alert:** You have {len(my_incoming)} shipments arriving soon. Waiting for you to receive them.")

        # --- DYNAMIC TABS WITH BADGES ---
        tab_req, tab_out, tab_in = st.tabs([
            "🛒 1. Request Stock", 
            f"📤 2. Dispatch ({len(my_pending)})", 
            f"✅ 3. Receive ({len(my_incoming)})"
        ])
        
        # ==========================================
        # TAB 1: REQUEST STOCK
        # ==========================================
        with tab_req:
            st.info("Where are you requesting items from, and where are they going?")
            
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                from_outlet = st.selectbox("Request From (Sender Outlet)", all_outlets, key="t_from_out")
            with col_o2:
                to_outlet = assigned_outlet if not is_global else st.selectbox("Request For (Receiver Outlet)", all_outlets, key="t_to_out")
            
            from_locs = list(df_inv[df_inv['Outlet'] == from_outlet]['Location'].dropna().astype(str).unique()) if 'Location' in df_inv.columns else ["Main Store"]
            to_locs = list(df_inv[df_inv['Outlet'] == to_outlet]['Location'].dropna().astype(str).unique()) if 'Location' in df_inv.columns else ["Kitchen"]
            
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                from_location = st.selectbox("From Location", from_locs if from_locs else ["Main Store"], key="t_from_loc")
            with col_l2:
                to_location = st.selectbox("To Location", to_locs if to_locs else ["Kitchen"], key="t_to_loc")
            
            st.divider()
            st.write("#### How would you like to request items?")
            req_style = st.radio("Request Style", ["📝 Quick Text Note", "🎯 Pick Exact Items"], horizontal=True, label_visibility="collapsed")
            
            if req_style == "📝 Quick Text Note":
                with st.form("text_req_form", clear_on_submit=True):
                    text_request = st.text_area("Example: I need 5kg chicken, 2 boxes halawe, and some rice ASAP.", height=100, label_visibility="collapsed")
                    
                    if st.form_submit_button("🚀 Send Request", type="primary", use_container_width=True):
                        if text_request.strip() == "":
                            st.error("Please type something before sending.")
                        else:
                            new_req = pd.DataFrame([{
                                "Transfer ID": str(uuid.uuid4())[:8],
                                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "Status": "Pending",
                                "Requester": user,
                                "From Outlet": from_outlet,
                                "From Location": from_location,
                                "To Outlet": to_outlet,
                                "To Location": to_location,
                                "Request Type": "Text Note",
                                "Details": text_request,
                                "Action By": ""
                            }])
                            updated_df = pd.concat([df_transfers, new_req], ignore_index=True)
                            conn.update(spreadsheet=sheet_link, worksheet="transfers", data=updated_df)
                            st.success(f"✅ Request sent to {from_outlet} ({from_location})!")
                            st.rerun()

            elif req_style == "🎯 Pick Exact Items":
                search_q = st.text_input("🔍 Search for item (e.g., chicken, rice)...", placeholder="Search...", label_visibility="collapsed")
                with st.form("item_req_form", clear_on_submit=True):
                    filtered_items = df_inv.copy()
                    if search_q:
                        filtered_items = filtered_items[filtered_items['Product Description'].astype(str).str.lower().str.contains(search_q.lower(), na=False)]
                        
                        req_quants = {}
                        for idx, row in filtered_items.head(15).iterrows():
                            colA, colB = st.columns([2, 1])
                            with colA:
                                st.markdown(f"**{row.get('Product Description', '')}** | 📦 {row.get('Unit', '')}")
                            with colB:
                                req_quants[idx] = st.number_input("Qty", value=None, min_value=0.0, step=1.0, placeholder="0.0", key=f"treq_{idx}", label_visibility="collapsed")
                                
                        if st.form_submit_button("🚀 Send Request for Selected Items", type="primary", use_container_width=True):
                            selected_details = []
                            for idx, qty in req_quants.items():
                                if qty is not None and qty > 0:
                                    item_name = filtered_items.loc[idx, 'Product Description']
                                    selected_details.append(f"{qty}x {item_name}")
                            
                            if selected_details:
                                combined_details = "\n".join(selected_details)
                                new_req = pd.DataFrame([{
                                    "Transfer ID": str(uuid.uuid4())[:8],
                                    "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "Status": "Pending",
                                    "Requester": user,
                                    "From Outlet": from_outlet,
                                    "From Location": from_location,
                                    "To Outlet": to_outlet,
                                    "To Location": to_location,
                                    "Request Type": "Exact Items",
                                    "Details": combined_details,
                                    "Action By": ""
                                }])
                                updated_df = pd.concat([df_transfers, new_req], ignore_index=True)
                                conn.update(spreadsheet=sheet_link, worksheet="transfers", data=updated_df)
                                st.success(f"✅ Exact items requested from {from_outlet} ({from_location})!")
                                st.rerun()
                            else:
                                st.warning("No quantities entered.")

        # ==========================================
        # TAB 2: DISPATCH (WAREHOUSE SENDS ITEMS)
        # ==========================================
        with tab_out:
            st.subheader("📤 Pending Requests to Fulfill")
            
            if my_pending.empty:
                st.success("No pending requests for your outlet! You are all caught up.")
            else:
                for idx, row in my_pending.iterrows():
                    with st.expander(f"🚨 Request from {row['Requester']} at {row['To Outlet']} ({row['To Location']})", expanded=True):
                        st.markdown(f"**Transfer ID:** {row['Transfer ID']} &nbsp;|&nbsp; 🗓️ {row['Date']}")
                        
                        # --- THE WAREHOUSE EDIT BOX ---
                        st.caption("You can edit the quantities below if you are out of stock before dispatching:")
                        edited_details = st.text_area("Adjust Items:", value=row['Details'], key=f"edit_{idx}", height=100)
                        
                        if st.button(f"📦 Approve & Dispatch", key=f"send_{idx}", type="primary", use_container_width=True):
                            df_transfers.at[idx, 'Details'] = edited_details # Save the edited text!
                            df_transfers.at[idx, 'Status'] = 'In Transit'
                            df_transfers.at[idx, 'Action By'] = f"Dispatched by {user}"
                            conn.update(spreadsheet=sheet_link, worksheet="transfers", data=df_transfers)
                            st.success("Items dispatched! Receiver will now see the updated quantities.")
                            st.rerun()

        # ==========================================
        # TAB 3: RECEIVE (CHEF ACCEPTS ITEMS)
        # ==========================================
        with tab_in:
            st.subheader("📥 Incoming Shipments")
            
            if my_incoming.empty:
                st.info("No incoming shipments for your outlet right now.")
            else:
                for idx, row in my_incoming.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**Transfer ID:** {row['Transfer ID']} &nbsp;|&nbsp; 🚚 Coming from **{row['From Outlet']} ({row['From Location']})**")
                        
                        # Show what Khaldoun actually sent (the edited details)
                        st.warning(row['Details'])
                        
                        if st.button(f"✅ I Physically Received This", key=f"recv_{idx}", type="primary", use_container_width=True):
                            df_transfers.at[idx, 'Status'] = 'Received'
                            df_transfers.at[idx, 'Action By'] = f"Received by {user}"
                            conn.update(spreadsheet=sheet_link, worksheet="transfers", data=df_transfers)
                            st.success("Transfer Complete! Inventory perfectly tracked.")
                            st.rerun()
                            
    except Exception as e:
        st.error(f"Error loading Transfers module: {e}")
