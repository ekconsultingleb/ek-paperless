import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
import uuid
from supabase import create_client, Client
from modules.nav_helper import build_outlet_location_sidebar, get_nav_data
from google import genai as google_genai
import json

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# Configure Gemini client once per app session
@st.cache_resource
def _get_gemini_client():
    return google_genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# --- AI HELPER FUNCTION ---
def analyze_chef_request(user_text):
    system_prompt = """
    You are an AI assistant for a Lebanese restaurant kitchen.
    Analyze the user's text (which may be in Lebanese Arabizi, Arabic, or English).
    Extract the requested inventory items and their quantities.
    Translate item names to standard English database names (e.g., 'batata' -> 'Potato', 'malfouf' -> 'Cabbage', 'shrim' -> 'Shrimp').
    Return ONLY a valid JSON array. Do not return markdown, do not return explanations.
    Format exactly like this: [{"item_name": "Shrimp", "qty": "5kg"}, {"item_name": "Potato", "qty": "2 box"}]
    """
    client = _get_gemini_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"{system_prompt}\n\nChef's request: {user_text}"
    )
    clean_text = response.text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean_text)
    except (json.JSONDecodeError, ValueError):
        return []

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

                query = supabase.table("transfers").select("*").gte("date", f"{start_date} 00:00").lte("date", f"{end_date} 23:59")
                res_archive = query.order("date", desc=True).limit(2000).execute()
                df_archive = pd.DataFrame(res_archive.data)

                # Filter to the viewer's assigned outlet — they should only see their own transfers
                _outlet = str(assigned_outlet).strip()
                if not df_archive.empty and _outlet.lower() not in ['all', '', 'none', 'nan']:
                    df_archive = df_archive[
                        (df_archive.get('from_outlet', pd.Series(dtype=str)).astype(str) == _outlet) |
                        (df_archive.get('to_outlet',   pd.Series(dtype=str)).astype(str) == _outlet)
                    ]

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
        # ── Sidebar navigation ──────────────────────────────────────────────────
        final_client, final_outlet, _ = build_outlet_location_sidebar(
            assigned_client, assigned_outlet, assigned_location,
            outlet_key="tr_outlet", location_key="tr_location"
        )

        # ==========================================
        # 3. MEGA-FETCH FOR MASTER ITEMS
        # ==========================================
        all_items = []
        page_size, start_row = 1000, 0
        
        if final_client != "Select Branch":
            while True:
                res = supabase.table("master_items").select("client_name, outlet, location, item_name, count_unit").ilike("client_name", f"%{final_client}%").range(start_row, start_row + page_size - 1).execute()
                if not res.data: break
                all_items.extend(res.data)
                if len(res.data) < page_size: break
                start_row += page_size

        if not all_items:
            df_inv = pd.DataFrame(columns=['client_name', 'outlet', 'location', 'item_name', 'count_unit'])
        else:
            df_inv = pd.DataFrame(all_items)
            df_inv['client_name'] = df_inv['client_name'].astype(str).str.strip().str.title()
            df_inv['outlet'] = df_inv['outlet'].astype(str).str.strip().str.title()
            df_inv['location'] = df_inv['location'].astype(str).str.strip().str.title()
            df_inv = df_inv.drop_duplicates().copy()

        # C. Determine active locations for this user
        df_nav = get_nav_data(final_client)
        db_locs = sorted(df_nav[df_nav['outlet'] == final_outlet]['location'].unique().tolist()) if not df_nav.empty and final_outlet not in ['None', 'All', ''] else []

        raw_loc = str(assigned_location).strip()
        if raw_loc.lower() in ['all', '', 'none', 'nan']:
            active_locations = db_locs if db_locs else ["Main Store"]
            st.sidebar.markdown("**📍 Location:** All Authorized")
        else:
            allowed_locs = [l.strip().title() for l in raw_loc.split(',') if l.strip()]
            active_locations = [l for l in allowed_locs if l in db_locs] if db_locs else allowed_locs
            st.sidebar.markdown(f"**📍 Location(s):** {', '.join(active_locations)}")

        # ==========================================
        # 4. LOAD ACTIVE TRANSFERS
        # ==========================================
        res_transfers = supabase.table("transfers").select("*").execute()
        df_transfers = pd.DataFrame(res_transfers.data)
        
        if not df_transfers.empty:
            df_transfers.columns = [c.lower() for c in df_transfers.columns]
        else:
            df_transfers = pd.DataFrame(columns=['transfer_id', 'date', 'status', 'requester', 'from_outlet', 'from_location', 'to_outlet', 'to_location', 'request_type', 'details', 'action_by'])

        user_locs_lower = [loc.lower() for loc in active_locations]
        can_dispatch = (raw_loc.lower() == 'all' or any('warehouse' in loc for loc in user_locs_lower))

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
                outlets_in_branch = sorted(df_inv['outlet'].unique()) if not df_inv.empty else []
                
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    from_outlet = st.selectbox("Request From (Outlet)", outlets_in_branch if outlets_in_branch else [final_outlet], key="t_from_out")
                with col_o2:
                    to_outlet = st.selectbox("Request For (Outlet)", [final_outlet], disabled=True, key="t_to_out")
                
                df_local_items = df_inv[(df_inv['client_name'] == final_client) & (df_inv['outlet'] == from_outlet)] if not df_inv.empty else pd.DataFrame()
                from_loc_options = sorted(list(df_local_items['location'].dropna().unique())) if not df_local_items.empty else ["Main Store"]
                
                col_l1, col_l2 = st.columns(2)
                with col_l1:
                    from_location = st.selectbox("From Location", from_loc_options if from_loc_options else ["Main Store"], key="t_from_loc")
                with col_l2:
                    if raw_loc.lower() == 'all':
                        df_to_items = df_inv[(df_inv['client_name'] == final_client) & (df_inv['outlet'] == to_outlet)] if not df_inv.empty else pd.DataFrame()
                        to_loc_options = sorted(list(df_to_items['location'].dropna().unique())) if not df_to_items.empty else ["Main Store"]
                        filtered_to_locs = [l for l in to_loc_options if l != from_location]
                        to_location = st.selectbox("To Location", filtered_to_locs if filtered_to_locs else to_loc_options, key="t_to_loc")
                    else:
                        to_location = st.selectbox("To Location", active_locations, key="t_to_loc")
                
                st.divider()
                
                # --- THE NEW 3-OPTION UI ---
                req_style = st.radio("Style", ["🤖 AI Smart Request", "📝 Quick Note", "🎯 Pick Exact Items"], horizontal=True, label_visibility="collapsed")
                
                # OPTION 1: THE AI CHATBOX
                if req_style == "🤖 AI Smart Request":
                    st.info("💡 **Type exactly how you speak!** I will understand Arabizi and translate it to stock items.")
                    ai_text = st.text_area("What do you need?", placeholder="e.g. Bade 5kg batata w 2 box arak...", height=100)
                    
                    if st.button("✨ Analyze & Send Request", type="primary", use_container_width=True):
                        if ai_text.strip():
                            with st.spinner("🤖 AI is reading your request..."):
                                try:
                                    parsed_items = analyze_chef_request(ai_text)
                                    
                                    if parsed_items:
                                        # Build the text for the database
                                        details_list = [f"{item['qty']}x {item['item_name']}" for item in parsed_items]
                                        final_details = "AI Extracted Items:\n" + "\n".join(details_list) + f"\n\n(Original Note: {ai_text})"
                                        
                                        new_req = {
                                            "transfer_id": str(uuid.uuid4())[:8],
                                            "date": datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d %H:%M"),
                                            "status": "Pending",
                                            "requester": user,
                                            "from_outlet": from_outlet, "from_location": from_location,
                                            "to_outlet": to_outlet, "to_location": to_location,
                                            "request_type": "AI Assisted",
                                            "details": final_details,
                                            "action_by": ""
                                        }
                                        supabase.table("transfers").insert(new_req).execute()
                                        st.toast("AI successfully processed your order!", icon="🤖")
                                        # st.rerun() # Uncomment if you want it to refresh instantly
                                    else:
                                        st.error("AI couldn't find any food items in your text. Try again!")
                                except Exception as e:
                                    st.error(f"❌ AI Error: {e}")

                # OPTION 2: QUICK NOTE
                elif req_style == "📝 Quick Note":
                    with st.form("text_req_form", clear_on_submit=True):
                        text_request = st.text_area("What do you need?", placeholder="e.g. 5kg Chicken, 2 boxes Arak...", height=100)
                        if st.form_submit_button("🚀 Send Request", type="primary", use_container_width=True):
                            if text_request.strip():
                                new_req = {
                                    "transfer_id": str(uuid.uuid4())[:8],
                                    "date": datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d %H:%M"),
                                    "status": "Pending",
                                    "requester": user,
                                    "from_outlet": from_outlet, "from_location": from_location,
                                    "to_outlet": to_outlet, "to_location": to_location,
                                    "request_type": "Text Note",
                                    "details": text_request,
                                    "action_by": ""
                                }
                                supabase.table("transfers").insert(new_req).execute()
                                st.success("✅ Request sent!")
                                st.rerun()

                # OPTION 3: EXACT ITEMS
                elif req_style == "🎯 Pick Exact Items":
                    search_q = st.text_input("🔍 Search Item...", placeholder="e.g. Almaza", label_visibility="collapsed")
                    with st.form("item_req_form", clear_on_submit=True):
                        req_quants = {}
                        if search_q and not df_local_items.empty:
                            filtered_items = df_local_items[df_local_items['item_name'].str.contains(search_q, case=False, na=False)].head(15)
                            for idx, row in filtered_items.iterrows():
                                c1, c2 = st.columns([3, 1])
                                c1.markdown(f"**{row['item_name']}** ({row.get('count_unit', 'pcs')})")
                                req_quants[idx] = c2.number_input("Qty", value=0.0, min_value=0.0, step=1.0, key=f"q_{idx}", label_visibility="collapsed")
                        
                        if st.form_submit_button("🚀 Send Itemized Request", type="primary", use_container_width=True):
                            details_list = [f"{qty}x {df_local_items.loc[i, 'item_name']}" for i, qty in req_quants.items() if qty > 0]
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
        # TAB 2 & 3: DISPATCH & RECEIVE
        # ==========================================
        if tab_out:
            with tab_out:
                if my_pending.empty:
                    st.info("No pending requests to dispatch from your location.")
                else:
                    for _, row in my_pending.iterrows():
                        with st.expander(f"📦 Order for {row['to_location']} ({row['requester']})"):
                            # This is where the Warehouse will see the AI's translation!
                            edited_details = st.text_area("Fulfillment Details:", value=row['details'], key=f"e_{row['transfer_id']}", height=150)
                            if st.button("Approve & Dispatch", key=f"d_{row['transfer_id']}", type="primary"):
                                supabase.table("transfers").update({
                                    "details": edited_details, "status": "In Transit", "action_by": f"Sent by {user}"
                                }).eq("transfer_id", row['transfer_id']).execute()
                                st.rerun()

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