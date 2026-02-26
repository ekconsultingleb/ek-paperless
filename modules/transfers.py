import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
import uuid
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# ---> THE UPGRADED RENDER FUNCTION <---
def render_transfers(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 🔄 Transfers & Requisitions")
    supabase = get_supabase()
    
    try:
        # ==========================================
        # 1. VIEWER MODE (WITH DATE RANGE)
        # ==========================================
        if role.lower() == "viewer":
            st.info("👁️ Viewer Mode: Showing Transfer History")
            
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=7)
            
            date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                
                # Note: Assuming your 'date' column in transfers table stores strings like "YYYY-MM-DD HH:MM"
                query = supabase.table("transfers").select("*").gte("date", f"{start_date} 00:00").lte("date", f"{end_date} 23:59")
                
                # In transfers, we check if either the 'to_outlet' or 'from_outlet' belongs to this client (though right now you don't track client_name in transfers. We will filter by the outlets belonging to the assigned client)
                res_archive = query.order("date", desc=True).limit(1000).execute()
                df_archive = pd.DataFrame(res_archive.data)

                if not df_archive.empty:
                    st.dataframe(df_archive, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No transfers found between {start_date} and {end_date}.")
            else:
                st.info("Please select both a Start Date and an End Date.")
            return

        # ==========================================
        # 2. SMART ROUTING & CLEAN SIDEBAR
        # ==========================================
        # Load master items to get dynamic outlets and locations
        res_inv = supabase.table("master_items").select("client_name, outlet, location, item_name, count_unit").execute()
        df_inv = pd.DataFrame(res_inv.data)
        
        if not df_inv.empty:
            df_inv['client_name'] = df_inv['client_name'].astype(str).str.strip().str.title()
            df_inv['outlet'] = df_inv['outlet'].astype(str).str.strip().str.title()
            df_inv['location'] = df_inv['location'].astype(str).str.strip().str.title()
            
        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        st.sidebar.markdown("### 📍 Location Details")

        if clean_client.lower() != 'all':
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
        else:
            c_list = sorted(df_inv['client_name'].unique()) if not df_inv.empty else ["All"]
            final_client = st.sidebar.selectbox("🏢 Select Branch", c_list)

        if not df_inv.empty:
            outlets_for_client = sorted(df_inv[df_inv['client_name'] == final_client]['outlet'].unique())
        else:
            outlets_for_client = []

        if clean_outlet.lower() != 'all':
            final_outlet = clean_outlet
            st.sidebar.markdown(f"**🏠 Outlet:** {final_outlet}")
        else:
            if outlets_for_client:
                final_outlet = st.sidebar.selectbox("🏠 Select Outlet", outlets_for_client)
            else:
                st.sidebar.warning(f"No outlets found for branch '{final_client}'")
                final_outlet = "None"
                
        # Handle multiple locations for the active user
        db_locs = sorted(list(df_inv[df_inv['outlet'] == final_outlet]['location'].dropna().unique())) if final_outlet != "None" else []
        raw_loc = str(assigned_location).strip()

        if raw_loc.lower() == 'all':
            active_locations = db_locs if db_locs else ["Main Store"]
            st.sidebar.markdown("**📍 Location:** All Authorized")
        else:
            allowed_locs = [l.strip().title() for l in raw_loc.split(',')]
            active_locations = [l for l in allowed_locs if l in db_locs] if db_locs else allowed_locs
            st.sidebar.markdown(f"**📍 Location(s):** {', '.join(active_locations)}")

        # ==========================================
        # 3. LOAD ACTIVE TRANSFERS
        # ==========================================
        res_transfers = supabase.table("transfers").select("*").execute()
        df_transfers = pd.DataFrame(res_transfers.data)
        
        if not df_transfers.empty:
            df_transfers.columns = [c.lower() for c in df_transfers.columns]
        else:
            df_transfers = pd.DataFrame(columns=['transfer_id', 'date', 'status', 'requester', 'from_outlet', 'from_location', 'to_outlet', 'to_location', 'request_type', 'details', 'action_by'])

        # --- SECURITY & NOTIFICATIONS ---
        user_locs_lower = [loc.lower() for loc in active_locations]
        
        # Determine if this user is allowed to dispatch (send items OUT)
        can_dispatch = (raw_loc.lower() == 'all' or any('warehouse' in loc for loc in user_locs_lower))

        # Determine pending and incoming logic based on the user's active locations
        if can_dispatch:
            my_pending = df_transfers[(df_transfers['status'] == 'Pending') & (df_transfers['from_outlet'].str.title() == final_outlet)]
            my_incoming = df_transfers[(df_transfers['status'] == 'In Transit') & (df_transfers['to_outlet'].str.title() == final_outlet)]
        else:
            my_pending = pd.DataFrame() 
            my_incoming = df_transfers[(df_transfers['status'] == 'In Transit') & 
                                       (df_transfers['to_outlet'].str.title() == final_outlet) &
                                       (df_transfers['to_location'].astype(str).str.title().isin([l.title() for l in active_locations]))]

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
        # TAB 1: REQUEST STOCK
        # ==========================================
        with tab_req:
            if final_outlet == "None":
                st.error("No valid outlet assigned. Cannot create requests.")
            else:
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    # In a multi-tenant setup, you usually only request FROM your own branch's outlets
                    from_outlet = st.selectbox("Request From (Outlet)", outlets_for_client, key="t_from_out")
                with col_o2:
                    to_outlet = st.selectbox("Request For (Outlet)", [final_outlet], disabled=True, key="t_to_out")
                
                # Dynamic Locations based on the selected Outlets
                from_loc_options = sorted(list(df_inv[df_inv['outlet'] == from_outlet]['location'].dropna().unique())) if not df_inv.empty else ["Main Store"]
                
                col_l1, col_l2 = st.columns(2)
                with col_l1:
                    from_location = st.selectbox("From Location", from_loc_options if from_loc_options else ["Main Store"], key="t_from_loc")
                with col_l2:
                    if raw_loc.lower() == 'all':
                        to_loc_options = sorted(list(df_inv[df_inv['outlet'] == to_outlet]['location'].dropna().unique())) if not df_inv.empty else ["Main Store"]
                        filtered_to_locs = [l for l in to_loc_options if l != from_location]
                        to_location = st.selectbox("To Location", filtered_to_locs if filtered_to_locs else to_loc_options, key="t_to_loc")
                    else:
                        to_location = st.selectbox("To Location", active_locations, key="t_to_loc")
                
                st.divider()
                req_style = st.radio("Style", ["📝 Quick Note", "🎯 Pick Exact Items"], horizontal=True, label_visibility="collapsed")
                
                if req_style == "📝 Quick Note":
                    with st.form("text_req_form", clear_on_submit=True):
                        text_request = st.text_area("What do you need?", placeholder="e.g. 5kg Chicken, 2 boxes Arak...", height=100)
                        if st.form_submit_button("🚀 Send Request", type="primary", use_container_width=True):
                            if text_request.strip():
                                new_req = {
                                    "transfer_id": str(uuid.uuid4())[:8],
                                    "date": datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d %H:%M"),
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
                        if search_q and not df_inv.empty:
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
                                    "date": datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d %H:%M"),
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
                    st.info("No pending requests to dispatch from your location.")
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
                st.info("No shipments to receive at your location.")
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
        st.error(f"❌ System Error in Transfers: {e}")