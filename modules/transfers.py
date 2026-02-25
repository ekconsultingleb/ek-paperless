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
    st.markdown("### 🔄 Transfers & Requisitions")
    
    supabase = get_supabase()
    
    try:
        # Load active transfers
        res_transfers = supabase.table("transfers").select("*").execute()
        df_transfers = pd.DataFrame(res_transfers.data)
        
        # Load master items to get DYNAMIC locations and search items
        res_inv = supabase.table("master_items").select("*").execute()
        df_inv = pd.DataFrame(res_inv.data)
        
        # Standardize columns
        if not df_transfers.empty:
            df_transfers.columns = [c.lower() for c in df_transfers.columns]
        else:
            df_transfers = pd.DataFrame(columns=['transfer_id', 'date', 'status', 'requester', 'from_outlet', 'from_location', 'to_outlet', 'to_location', 'request_type', 'details', 'action_by'])
            
        if not df_inv.empty:
            df_inv.columns = [c.lower() for c in df_inv.columns]

        # --- DYNAMIC LOCATION LOGIC ---
        # Get all outlets and locations directly from your database
        all_outlets = sorted(list(df_inv['outlet'].dropna().astype(str).unique()))
        
        # --- SECURITY & NOTIFICATIONS ---
        user_locs = [loc.strip().lower() for loc in assigned_location.split(',')]
        # Warehouse staff or Admins can dispatch
        can_dispatch = (assigned_location.lower() == 'all' or 'warehouse' in assigned_location.lower())
        
        if can_dispatch:
            my_pending = df_transfers[df_transfers['status'] == 'Pending']
            my_incoming = df_transfers[df_transfers['status'] == 'In Transit']
        else:
            my_pending = pd.DataFrame() 
            my_incoming = df_transfers[(df_transfers['status'] == 'In Transit') & 
                                       (df_transfers['to_location'].astype(str).str.lower().isin(user_locs))]

        if can_dispatch and not my_pending.empty:
            st.warning(f"🔔 **Alert:** {len(my_pending)} pending requests to dispatch!")
        if not my_incoming.empty:
            st.info(f"🚚 **Alert:** {len(my_incoming)} shipments arriving soon.")

        # --- TABS ---
        if can_dispatch:
            tabs = st.tabs([f"🛒 Request", f"📤 Dispatch ({len(my_pending)})", f"✅ Receive ({len(my_incoming)})"])
            tab_req, tab_out, tab_in = tabs
        else:
            tabs = st.tabs([f"🛒 Request", f"✅ Receive ({len(my_incoming)})"])
            tab_req, tab_in = tabs
            tab_out = None

        # ==========================================
        # TAB 1: REQUEST STOCK (DYNAMIC LOCATIONS)
        # ==========================================
        with tab_req:
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                from_outlet = st.selectbox("Request From (Outlet)", all_outlets, key="t_from_out")
            with col_o2:
                # Default to user's assigned outlet
                to_outlet_options = [assigned_outlet] if assigned_outlet.lower() != 'all' else all_outlets
                to_outlet = st.selectbox("Request For (Outlet)", to_outlet_options, key="t_to_out")
            
            # PULL LOCATIONS DYNAMICALLY FROM DATABASE
            from_loc_options = sorted(list(df_inv[df_inv['outlet'] == from_outlet]['location'].dropna().astype(str).str.upper().unique()))
            to_loc_options = sorted(list(df_inv[df_inv['outlet'] == to_outlet]['location'].dropna().astype(str).str.upper().unique()))
            
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                from_location = st.selectbox("From Location", from_loc_options if from_loc_options else ["MAIN"], key="t_from_loc")
            with col_l2:
                # If user is locked to a location, they can only request FOR that location
                if not can_dispatch and assigned_location.lower() != 'all':
                    to_location = st.selectbox("To Location", [assigned_location.upper()], disabled=True, key="t_to_loc")
                else:
                    # Filter out the 'From' location so they don't transfer to themselves
                    filtered_to_locs = [l for l in to_loc_options if l != from_location]
                    to_location = st.selectbox("To Location", filtered_to_locs if filtered_to_locs else to_loc_options, key="t_to_loc")
            
            st.divider()
            req_style = st.radio("Style", ["📝 Quick Note", "🎯 Pick Exact Items"], horizontal=True, label_visibility="collapsed")
            
            if req_style == "📝 Quick Note":
                with st.form("text_req_form", clear_on_submit=True):
                    text_request = st.text_area("What do you need?", placeholder="e.g. 5kg Chicken, 2 boxes Arak...", height=100)
                    if st.form_submit_button("🚀 Send Request", type="primary", use_container_width=True):
                        if text_request.strip():
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
                            st.success("✅ Request sent!")
                            st.rerun()

            elif req_style == "🎯 Pick Exact Items":
                search_q = st.text_input("🔍 Search Item...", placeholder="e.g. Almaza", label_visibility="collapsed")
                with st.form("item_req_form", clear_on_submit=True):
                    req_quants = {}
                    if search_q:
                        filtered_items = df_inv[df_inv['item_name'].str.contains(search_q, case=False, na=False)].head(15)
                        for idx, row in filtered_items.iterrows():
                            c1, c2 = st.columns([3, 1])
                            c1.markdown(f"**{row['item_name']}** ({row.get('count_unit', 'pcs')})")
                            req_quants[idx] = c2.number_input("Qty", value=0.0, min_value=0.0, step=1.0, key=f"q_{idx}", label_visibility="collapsed")
                    
                    if st.form_submit_button("🚀 Send Itemized Request", type="primary", use_container_width=True):
                        details_list = [f"{qty}x {df_inv.loc[i, 'item_name']}" for i, qty in req_quants.items() if qty > 0]
                        if details_list:
                            new_req = {
                                "transfer_id": str(uuid.uuid4())[:8],
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "status": "Pending",
                                "requester": user,
                                "from_outlet": from_outlet, "from_location": from_location,
                                "to_outlet": to_outlet, "to_location": to_location,
                                "request_type": "Exact Items",
                                "details": "\n".join(details_list), "action_by": ""
                            }
                            supabase.table("transfers").insert(new_req).execute()
                            st.success("✅ Items Requested!")
                            st.rerun()

        # ==========================================
        # TAB 2: DISPATCH
        # ==========================================
        if tab_out:
            with tab_out:
                if my_pending.empty:
                    st.info("No pending requests.")
                else:
                    for _, row in my_pending.iterrows():
                        with st.expander(f"📦 Order for {row['to_location']} ({row['requester']})"):
                            edited_details = st.text_area("Fulfillment Details:", value=row['details'], key=f"e_{row['transfer_id']}")
                            if st.button("Approve & Dispatch", key=f"d_{row['transfer_id']}", type="primary"):
                                supabase.table("transfers").update({
                                    "details": edited_details, "status": "In Transit", "action_by": f"Sent by {user}"
                                }).eq("transfer_id", row['transfer_id']).execute()
                                st.rerun()

        # ==========================================
        # TAB 3: RECEIVE
        # ==========================================
        with tab_in:
            if my_incoming.empty:
                st.info("No shipments to receive.")
            else:
                for _, row in my_incoming.iterrows():
                    with st.container(border=True):
                        st.write(f"**From:** {row['from_location']} | **ID:** {row['transfer_id']}")
                        st.info(row['details'])
                        if st.button("✅ Confirm Receipt", key=f"r_{row['transfer_id']}", type="primary", use_container_width=True):
                            supabase.table("transfers").update({
                                "status": "Received", "action_by": f"Received by {user}"
                            }).eq("transfer_id", row['transfer_id']).execute()
                            st.rerun()

    except Exception as e:
        st.error(f"Critical Error in Transfers: {e}")