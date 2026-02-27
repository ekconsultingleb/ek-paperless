import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from fpdf import FPDF

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def generate_waste_pdf(df, report_date, client, outlet, location, user_name, waste_type, event_name=""):
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Official Waste & Spoilage Ticket", ln=True, align="C")
    
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {report_date}", ln=True)
    pdf.cell(0, 6, f"Branch: {client} | Outlet: {outlet} | Location: {location}", ln=True)
    pdf.cell(0, 6, f"Reported By: {user_name} | Ticket Type: {waste_type}", ln=True)
    
    if waste_type == "Event" and event_name:
        pdf.cell(0, 6, f"Event Name: {event_name}", ln=True)
        
    pdf.cell(0, 6, f"Generated: {datetime.now(zoneinfo.ZoneInfo('Asia/Beirut')).strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(255, 200, 200)
    pdf.cell(80, 8, "Item Name", border=1, fill=True)
    pdf.cell(40, 8, "Item Type", border=1, fill=True)
    pdf.cell(30, 8, "Qty", border=1, align="C", fill=True)
    pdf.cell(30, 8, "Unit", border=1, align="C", fill=True)
    pdf.ln()
    
    pdf.set_font("helvetica", "", 9)
    for _, row in df.iterrows():
        item = str(row.get('item_name', ''))[:40]
        i_type = str(row.get('item_type', ''))[:20]
        qty = str(row.get('qty', '0'))
        unit = str(row.get('count_unit', 'Unit'))[:10]
        
        pdf.cell(80, 8, item, border=1)
        pdf.cell(40, 8, i_type, border=1)
        pdf.cell(30, 8, qty, border=1, align="C")
        pdf.cell(30, 8, unit, border=1, align="C")
        pdf.ln()
        
    return bytes(pdf.output())

def add_waste_qty(item_key, row_dict, input_key):
    added_val = st.session_state.get(input_key, 0.0)
    if added_val > 0:
        if item_key not in st.session_state['waste_cart']:
            st.session_state['waste_cart'][item_key] = {'row_data': row_dict, 'qty': 0.0}
        st.session_state['waste_cart'][item_key]['qty'] += added_val
        st.session_state[input_key] = 0.0

def undo_waste_count(item_key):
    if item_key in st.session_state['waste_cart']:
        del st.session_state['waste_cart'][item_key]

def render_waste(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 🗑️ Log Waste, Meals & Events")
    supabase = get_supabase()

    if 'waste_cart' not in st.session_state:
        st.session_state['waste_cart'] = {}

    try:
        # --- VIEWER MODE ---
        if role.lower() == "viewer":
            st.info("👁️ Viewer Mode: Showing Waste Logs")
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=7)
            date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                query = supabase.table("waste_logs").select("*").gte("date", str(start_date)).lte("date", str(end_date))
                if str(assigned_client).lower() != 'all':
                    query = query.ilike("client_name", f"%{str(assigned_client).strip()}%")
                archive_res = query.order("date", desc=True).limit(2000).execute()
                df_archive = pd.DataFrame(archive_res.data)

                if not df_archive.empty:
                    pdf_bytes = generate_waste_pdf(df_archive, f"{start_date} to {end_date}", assigned_client, assigned_outlet, "Multiple Locations", "System Report", "Historical Report")
                    st.download_button(label="🖨️ Download Waste Report (PDF)", data=pdf_bytes, file_name=f"Waste_Report_{start_date}_to_{end_date}.pdf", mime="application/pdf", type="primary")
                    st.dataframe(df_archive, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No waste logs found between {start_date} and {end_date}.")
            return

        # ==========================================
        # 1. DATA FETCHING & DYNAMIC NAVIGATION
        # ==========================================
        # PRO TIP: Query the small users table for instant navigation
        nav_res = supabase.table("users").select("client_name, outlet").execute()
        df_nav = pd.DataFrame(nav_res.data)
        if not df_nav.empty:
            df_nav['client_name'] = df_nav['client_name'].astype(str).str.strip().str.title()
            df_nav['outlet'] = df_nav['outlet'].astype(str).str.strip().str.title()
        
        # Admin/Manager "All" Logic
        user_client_access = str(assigned_client).strip().title()
        if user_client_access != 'All':
            final_client = user_client_access
            st.sidebar.info(f"🏢 Branch: {final_client}")
        else:
            c_list = sorted([c for c in df_nav['client_name'].unique() if c.lower() != 'all']) if not df_nav.empty else ["All Branches"]
            final_client = st.sidebar.selectbox("🏢 Select Branch", c_list)

        user_outlet_access = str(assigned_outlet).strip().title()
        if user_outlet_access != 'All':
            final_outlet = user_outlet_access
            st.sidebar.info(f"🏠 Outlet: {final_outlet}")
        else:
            if final_client != "All Branches" and not df_nav.empty:
                outlets_for_client = sorted([o for o in df_nav[df_nav['client_name'] == final_client]['outlet'].unique() if o.lower() != 'all'])
            elif not df_nav.empty:
                outlets_for_client = sorted([o for o in df_nav['outlet'].unique() if o.lower() != 'all'])
            else:
                outlets_for_client = []
                
            final_outlet = st.sidebar.selectbox("🏠 Select Outlet", outlets_for_client) if outlets_for_client else "None"

        if 'last_waste_receipt' in st.session_state:
            st.success("✅ **Success!** Waste ticket has been logged.")
            st.download_button(label="🖨️ Download Waste Ticket (PDF)", data=st.session_state['last_waste_receipt']['bytes'], file_name=st.session_state['last_waste_receipt']['filename'], mime="application/pdf", type="primary")
            if st.button("Log More Waste", use_container_width=True):
                del st.session_state['last_waste_receipt']
                st.rerun()
            return

        all_items = []
        page_size, start_row = 1000, 0
        if final_outlet != "None":
            while True:
                # The pagination loop handles big data perfectly without a single limit trap
                res = supabase.table("master_items").select("*").ilike("outlet", f"%{final_outlet}%").range(start_row, start_row + page_size - 1).execute()
                if not res.data: break
                all_items.extend(res.data)
                if len(res.data) < page_size: break
                start_row += page_size

        if not all_items:
            df_items = pd.DataFrame(columns=['item_name', 'category', 'sub_category', 'count_unit', 'location', 'item_type'])
        else:
            df_items = pd.DataFrame(all_items)
            df_items.columns = [str(c).strip().lower() for c in df_items.columns]
            
            # Case-Insensitive Multi-Location Filter
            user_loc_raw = str(assigned_location).strip().lower()
            if user_loc_raw != 'all':
                allowed_locs = [loc.strip().lower() for loc in user_loc_raw.split(',')]
                df_items = df_items[df_items['location'].str.lower().isin(allowed_locs)]
            
            if 'item_type' not in df_items.columns: df_items['item_type'] = "inventory"
            if 'count_unit' in df_items.columns:
                df_items['count_unit'] = df_items['count_unit'].apply(
                    lambda x: "Unit" if pd.isna(x) or str(x).strip().lower() in ['none', 'nan', ''] else str(x)
                )

        waste_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
        st.divider()

        # STEP 1: Details
        st.subheader("📝 Step 1: Ticket Details")
        ticket_type = st.radio("Select Ticket Context:", ["Daily Waste", "Staff Meal", "Event"], horizontal=True)
        event_name_val = st.text_input("📝 Event Name", placeholder="e.g. Wedding Booking") if ticket_type == "Event" else ""
            
        st.divider()

        # STEP 2: Find Items
        st.subheader("🔍 Step 2: Find Items")
        item_type_filter = st.radio("Item Type", ["📦 Inventory Items", "🍔 Menu Items", "All Items"], horizontal=True)
        search_query = st.text_input("🔍 Quick Search")

        if not df_items.empty:
            if item_type_filter == "📦 Inventory Items":
                df_filtered_type = df_items[df_items['item_type'].str.lower().str.contains('inventory', na=False)].copy()
            elif item_type_filter == "🍔 Menu Items":
                df_filtered_type = df_items[df_items['item_type'].str.lower().str.contains('menu', na=False)].copy()
            else:
                df_filtered_type = df_items.copy()
            
            df_filtered_type['category'] = df_filtered_type['category'].replace(['', 'nan', 'None'], 'Uncategorized').fillna('Uncategorized')
            df_filtered_type['sub_category'] = df_filtered_type['sub_category'].replace(['', 'nan', 'None'], 'Uncategorized').fillna('Uncategorized')
        else:
            df_filtered_type = pd.DataFrame()

        c1, c2 = st.columns(2)
        with c1:
            cats = sorted(list(df_filtered_type['category'].astype(str).unique())) if not df_filtered_type.empty else []
            cat_options = ["All"] + cats
            selected_category = st.selectbox("📂 Category", cat_options, index=0)
        with c2:
            df_grp_list = df_filtered_type if selected_category == "All" else df_filtered_type[df_filtered_type['category'] == selected_category]
            grps = sorted(list(df_grp_list['sub_category'].astype(str).unique())) if not df_grp_list.empty else []
            grp_options = ["All"] + grps
            selected_group = st.selectbox("🏷️ Sub Category", grp_options, index=0)

        df_display = df_filtered_type.copy()
        if search_query:
            df_display = df_display[df_display['item_name'].str.contains(search_query, case=False, na=False)]
        if selected_category != "All":
            df_display = df_display[df_display['category'] == selected_category]
        if selected_group != "All":
            df_display = df_display[df_display['sub_category'] == selected_group]

        total_items = len(df_display)
        wasted_in_view = sum(1 for item in df_display['item_name'] if item in st.session_state['waste_cart'])

        st.markdown(f"""
            <div style='display: flex; justify-content: space-between; background-color: #3b1c1c; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
                <span style='color: #ff6b6b;'>🗑️ {wasted_in_view} Selected</span>
                <span style='color: white;'>📝 {total_items} Items in View</span>
            </div>
        """, unsafe_allow_html=True)

        if df_display.empty:
            st.info("No items found. Check if the Location spelling matches the database.")
        else:
            for index, row in df_display.iterrows():
                item_name = row['item_name']
                cart_data = st.session_state['waste_cart'].get(item_name)
                current_total = cart_data['qty'] if cart_data else 0.0
                
                with st.container(border=True):
                    if current_total > 0:
                        st.markdown(f"🟢 **{item_name}** &nbsp;|&nbsp; <span style='color:#00ff00; font-weight:bold;'>✅ Qty: {current_total} {row.get('count_unit', 'Unit')}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"⚪ **{item_name}** &nbsp;|&nbsp; 📦 {row.get('count_unit', 'Unit')}")
                        
                    input_key = f"waste_add_{index}_{item_name}"
                    col_add, col_btn = st.columns([3, 1], vertical_alignment="center")
                    with col_add:
                        st.number_input("+ Add Qty", value=0.0, min_value=0.0, step=1.0, format="%g", key=input_key, on_change=add_waste_qty, args=(item_name, row.to_dict(), input_key), label_visibility="collapsed")
                    with col_btn:
                        if current_total > 0:
                            if st.button("♻️ Undo", key=f"undo_{index}_{item_name}"):
                                undo_waste_count(item_name)
                                st.rerun()

        st.divider()
        if len(st.session_state['waste_cart']) > 0:
            with st.expander("👀 Review & Submit Ticket", expanded=True):
                preview_list = [{"Item Name": v['row_data'].get('item_name', k), "Type": v['row_data'].get('item_type', 'Inventory'), "Qty Wasted": v['qty'], "Unit": v['row_data'].get('count_unit', 'Unit')} for k, v in st.session_state['waste_cart'].items()]
                st.dataframe(pd.DataFrame(preview_list), use_container_width=True, hide_index=True)

                if st.button("🚀 SUBMIT TICKET TO CLOUD", type="primary", use_container_width=True):
                    if ticket_type == "Event" and not event_name_val.strip():
                        st.error("❌ Please provide an Event Name before submitting.")
                    else:
                        logs = []
                        for i_name, data in st.session_state['waste_cart'].items():
                            r_data = data['row_data']
                            reason_code = ticket_type
                            if ticket_type == "Daily Waste":
                                cat_lower = str(r_data.get('category','')).lower()
                                reason_code = "WB" if any(x in cat_lower for x in ['bev','drink','alcohol']) else "WF"
                            elif ticket_type == "Staff Meal": reason_code = "SM"
                            elif ticket_type == "Event": reason_code = f"Event: {event_name_val}"
                            
                            logs.append({
                                "date": str(waste_date), "client_name": final_client, "outlet": final_outlet, 
                                "location": str(assigned_location), "reported_by": user,
                                "item_name": i_name, "item_type": r_data.get('item_type', 'inventory'), "category": r_data.get('category', ''),
                                "qty": float(data['qty']), "count_unit": r_data.get('count_unit', 'Unit'), "remarks": reason_code
                            })
                        
                        try:
                            supabase.table("waste_logs").insert(logs).execute()
                            st.session_state['last_waste_receipt'] = {"bytes": generate_waste_pdf(pd.DataFrame(logs), str(waste_date), final_client, final_outlet, str(assigned_location), user, ticket_type, event_name_val), "filename": f"{ticket_type}_{waste_date}.pdf"}
                            st.session_state['waste_cart'] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Database Error: {e}")

    except Exception as e:
        st.error(f"❌ Error: {e}")