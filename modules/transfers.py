import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_transfers(conn, sheet_link, user, role, assigned_outlet, assigned_location):
    st.markdown("### 🔄 Warehouse Transfers & Requisitions")
    
    supabase = get_supabase()
    
    try:
        # Load data from Supabase instead of Google Sheets
        res_transfers = supabase.table("transfers").select("*").execute()
        df_transfers = pd.DataFrame(res_transfers.data)
        
        # Load master items for the "Pick Exact Items" search
        res_inv = supabase.table("master_items").select("*").execute()
        df_inv = pd.DataFrame(res_inv.data)
        
        # Ensure lowercase columns to prevent errors
        if not df_transfers.empty:
            df_transfers.columns = [c.lower() for c in df_transfers.columns]
        else:
            # Create empty DF with proper columns if table is completely empty
            df_transfers = pd.DataFrame(columns=['transfer_id', 'date', 'status', 'requester', 'from_outlet', 'from_location', 'to_outlet', 'to_location', 'request_type', 'details', 'action_by'])
            
        if not df_inv.empty:
            df_inv.columns = [c.lower() for c in df_inv.columns]

        all_outlets = list(df_inv['outlet'].dropna().astype(str).unique()) if 'outlet' in df_inv.columns else ["Main Warehouse", "Branch 1"]
        
        # --- LOCATION-BASED SECURITY FILTERS ---
        user_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
        can_dispatch = (assigned_location.lower() == 'all' or assigned_location == '' or 'warehouse' in assigned_location.lower())
        
        if can_dispatch:
            my_pending = df_transfers[df_transfers['status'] == 'Pending']
            my_incoming = df_transfers[df_transfers['status'] == 'In Transit']
        else:
            my_pending = pd.DataFrame() 
            my_incoming = df_transfers[(df_transfers['status'] == 'In Transit') & 
                                       (df_transfers['to_location'].astype(str).str.lower().isin(user_locs))]

        # --- IN-APP NOTIFICATIONS ---
        if can_dispatch and not my_pending.empty:
            st.warning(f"🔔 **Alert:** You have {len(my_pending)} pending requests to dispatch!")
        if not my_incoming.empty:
            st.info(f"🚚 **Alert:** You have {len(my_incoming)} shipments arriving soon. Waiting for you to receive them.")

        # --- DYNAMIC TABS ---
        if can_dispatch:
            tab_req, tab_out, tab_in = st.tabs([
                "🛒 1. Request Stock", 
                f"📤 2. Dispatch ({len(my_pending)})", 
                f"✅ 3. Receive ({len(my_incoming)})"
            ])
        else:
            tab_req, tab_in = st.tabs([
                "🛒 1. Request Stock", 
                f"✅ 2. Receive ({len(my_incoming)})"
            ])
            tab_out = None

        # ==========================================
        # TAB 1: REQUEST STOCK
        # ==========================================
        with tab_req:
            st.info("Where are you requesting items from, and where are they going?")
            
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                from_outlet = st.selectbox("Request From (Sender Outlet)", all_outlets, key="t_from_out")
            with col_o2:
                to_outlet = assigned_outlet if assigned_outlet.lower() != 'all' else st.selectbox("Request For (Receiver Outlet)", all_outlets, key="t_to_out")
            
            from_locs = list(df_inv[df_inv['outlet'] == from_outlet]['location'].dropna().astype(str).unique()) if 'location' in df_inv.columns else ["Warehouse"]
            to_locs = list(df_inv[df_inv['outlet'] == to_outlet]['location'].dropna().astype(str).unique()) if 'location' in df_inv.columns else ["Kitchen"]
            
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                from_location = st.selectbox("From Location", from_locs if from_locs else ["Warehouse"], key="t_from_loc")
            with col_l2:
                if not can_dispatch and assigned_location.lower() != 'all':
                    user_exact_loc = [loc for loc in to_locs if loc.lower() in user_locs]
                    to_location = st.selectbox("To Location", user_exact_loc if user_exact_loc else [assigned_location], key="t_to_loc")
                else:
                    to_location = st.selectbox("To Location", to_locs if to_locs else ["Kitchen"], key="t_to_loc")
            
            st.divider()
            st.write("#### How would you like to request items?")
            req_style = st.radio("Request Style", ["📝 Quick Text Note", "🎯 Pick Exact Items"], horizontal=True, label_visibility="collapsed")
            
            if req_style == "📝 Quick Text Note":
                with st.form("text_req_form", clear_on_submit=True):
                    text_request = st.text_area("Example: I need 5kg chicken, 2 boxes halawe...", height=100, label_visibility="collapsed")
                    
                    if st.form_submit_button("🚀 Send Request", type="primary", use_container_width=True):
                        if text_request.strip() == "":
                            st.error("Please type something before sending.")
                        else:
                            new_req = {
                                "transfer_id": str(uuid.uuid4())[:8],
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "status": "Pending",
                                "requester": user,
                                "from_outlet": from_outlet,
                                "from_location": from_location,
                                "to_outlet": to_outlet,
                                "to_location": to_location,
                                "request_type": "Text Note",
                                "details": text_request,
                                "action_by": ""
                            }
                            supabase.table("transfers").insert(new_req).execute()
                            st.success(f"✅ Request sent to {from_location}!")
                            st.rerun()

            elif req_style == "🎯 Pick Exact Items":
                search_q = st.text_input("🔍 Search for item (e.g., chicken, rice)...", placeholder="Search...", label_visibility="collapsed")
                with st.form("item_req_form", clear_on_submit=True):
                    filtered_items = df_inv.copy()
                    if search_q:
                        filtered_items = filtered_items[filtered_items['item_name'].astype(str).str.lower().str.contains(search_q.lower(), na=False)]
                        
                        req_quants = {}
                        for idx, row in filtered_items.head(15).iterrows():
                            colA, colB = st.columns([2, 1])
                            with colA:
                                st.markdown(f"**{row.get('item_name', '')}** | 📦 {row.get('count_unit', '')}")
                            with colB:
                                req_quants[idx] = st.number_input("Qty", value=None, min_value=0.0, step=1.0, placeholder="0.0", key=f"treq_{idx}", label_visibility="collapsed")
                                
                        if st.form_submit_button("🚀 Send Request for Selected Items", type="primary", use_container_width=True):
                            selected_details = []
                            for idx, qty in req_quants.items():
                                if qty is not None and qty > 0:
                                    item_name = filtered_items.loc[idx, 'item_name']
                                    selected_details.append(f"{qty}x {item_name}")
                            
                            if selected_details:
                                combined_details = "\n".join(selected_details)
                                new_req = {
                                    "transfer_id": str(uuid.uuid4())[:8],
                                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "status": "Pending",
                                    "requester": user,
                                    "from_outlet": from_outlet,
                                    "from_location": from_location,
                                    "to_outlet": to_outlet,
                                    "to_location": to_location,
                                    "request_type": "Exact Items",
                                    "details": combined_details,
                                    "action_by": ""
                                }
                                supabase.table("transfers").insert(new_req).execute()
                                st.success(f"✅ Exact items requested from {from_location}!")
                                st.rerun()
                            else:
                                st.warning("No quantities entered.")

        # ==========================================
        # TAB 2: DISPATCH (WAREHOUSE ONLY)
        # ==========================================
        if tab_out is not None:
            with tab_out:
                st.subheader("📤 Pending Requests to Fulfill")
                
                if my_pending.empty:
                    st.success("No pending requests! You are all caught up.")
                else:
                    for idx, row in my_pending.iterrows():
                        with st.expander(f"🚨 Request from {row['requester']} at {row['to_location']}", expanded=True):
                            st.markdown(f"**Transfer ID:** {row['transfer_id']} &nbsp;|&nbsp; 🗓️ {row['date']}")
                            
                            st.caption("Edit the quantities below if you are out of stock before dispatching:")
                            edited_details = st.text_area("Adjust Items:", value=row['details'], key=f"edit_{row['transfer_id']}", height=100)
                            
                            if st.button(f"📦 Approve & Dispatch", key=f"send_{row['transfer_id']}", type="primary", use_container_width=True):
                                # Update Supabase instead of Google Sheets
                                supabase.table("transfers").update({
                                    "details": edited_details,
                                    "status": "In Transit",
                                    "action_by": f"Dispatched by {user}"
                                }).eq("transfer_id", row['transfer_id']).execute()
                                
                                st.success("Items dispatched! Receiver will now see the updated quantities.")
                                st.rerun()

        # ==========================================
        # TAB 3: RECEIVE (CHEF ACCEPTS ITEMS)
        # ==========================================
        with tab_in:
            st.subheader("📥 Incoming Shipments")
            
            if my_incoming.empty:
                st.info("No incoming shipments for your location right now.")
            else:
                for idx, row in my_incoming.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**Transfer ID:** {row['transfer_id']} &nbsp;|&nbsp; 🚚 Coming from **{row['from_location']}**")
                        
                        st.warning(row['details'])
                        
                        if st.button(f"✅ I Physically Received This", key=f"recv_{row['transfer_id']}", type="primary", use_container_width=True):
                            # Update Supabase instead of Google Sheets
                            supabase.table("transfers").update({
                                "status": "Received",
                                "action_by": f"Received by {user}"
                            }).eq("transfer_id", row['transfer_id']).execute()
                            
                            st.success("Transfer Complete! Inventory perfectly tracked.")
                            st.rerun()
                            
    except Exception as e:
        st.error(f"Error loading Transfers module: {e}")