import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from fpdf import FPDF
from modules.nav_helper import build_outlet_location_sidebar

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
    
    pdf.set_font("helvetica", "B", 9)
    pdf.set_fill_color(255, 200, 200)
    pdf.cell(70, 8, "Item Name", border=1, fill=True)
    pdf.cell(30, 8, "Item Type", border=1, fill=True)
    pdf.cell(20, 8, "Qty", border=1, align="C", fill=True)
    pdf.cell(20, 8, "Unit", border=1, align="C", fill=True)
    pdf.cell(50, 8, "Remarks", border=1, fill=True)
    pdf.ln()
    
    pdf.set_font("helvetica", "", 8)
    for _, row in df.iterrows():
        item = str(row.get('item_name', ''))[:35]
        i_type = str(row.get('item_type', ''))[:15]
        qty = str(row.get('qty', '0'))
        unit = str(row.get('count_unit', 'Unit'))[:10]
        remarks = str(row.get('remarks', ''))[:35]
        
        pdf.cell(70, 8, item, border=1)
        pdf.cell(30, 8, i_type, border=1)
        pdf.cell(20, 8, qty, border=1, align="C")
        pdf.cell(20, 8, unit, border=1, align="C")
        pdf.cell(50, 8, remarks, border=1)
        pdf.ln()
        
    return bytes(pdf.output())

def add_waste_qty(item_key, row_dict, input_key):
    added_val = st.session_state.get(input_key, 0.0)
    if added_val > 0:
        unit = str(row_dict.get('count_unit', '')).strip().lower()
        
        # --- 🛡️ THE FRIENDLY GUARD ---
        if unit in ['kg', 'ltr'] and added_val > 50:
            st.toast(f"⚠️ {added_val} {unit} added! If this was a typo, please use the Undo button.", icon="👀")
        
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
    if 'waste_remarks' not in st.session_state:
        st.session_state['waste_remarks'] = {}

    _SYSTEM_REMARKS = ["WF", "WB", "SM", "Damaged"]

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
        # ── Sidebar navigation (shared helper handles users→master_items fallback) ──
        final_client, final_outlet, final_location_sidebar = build_outlet_location_sidebar(
            assigned_client, assigned_outlet, assigned_location,
            outlet_key="waste_outlet", location_key="waste_location"
        )

        if 'last_waste_receipt' in st.session_state:
            st.success("✅ **Success!** Waste ticket has been logged.")
            st.download_button(label="🖨️ Download Waste Ticket (PDF)", data=st.session_state['last_waste_receipt']['bytes'], file_name=st.session_state['last_waste_receipt']['filename'], mime="application/pdf", type="primary")
            if st.button("Log More Waste", width="stretch"):
                del st.session_state['last_waste_receipt']
                st.rerun()
            return

        all_items = []
        page_size, start_row = 1000, 0
        
        if final_outlet and str(final_outlet).strip() != "" and final_outlet != "None":
            while True:
                query = supabase.table("master_items").select("*")
                if final_client and final_client not in ["All", "Select Branch", "All Branches"]:
                    query = query.ilike("client_name", f"%{final_client}%")
                query = query.ilike("outlet", f"%{final_outlet}%")
                res = query.range(start_row, start_row + page_size - 1).execute()
                
                if not res.data: break
                all_items.extend(res.data)
                if len(res.data) < page_size: break
                start_row += page_size

        if not all_items:
            df_items = pd.DataFrame(columns=['item_name', 'category', 'sub_category', 'count_unit', 'location', 'item_type'])
        else:
            df_items = pd.DataFrame(all_items)
            df_items.columns = [str(c).strip().lower() for c in df_items.columns]
            
            if 'item_type' not in df_items.columns: df_items['item_type'] = "inventory"
            if 'count_unit' in df_items.columns:
                df_items['count_unit'] = df_items['count_unit'].apply(
                    lambda x: "Unit" if pd.isna(x) or str(x).strip().lower() in ['none', 'nan', ''] else str(x)
                )

        # Filter df_items by the sidebar-selected location
        loc_filter = final_location_sidebar
        if not df_items.empty and loc_filter and loc_filter.lower() not in ['all', 'none', '']:
            df_items = df_items[df_items['location'].str.strip().str.title() == loc_filter]
            df_items = df_items.drop_duplicates(subset=['item_name', 'item_type']).copy()

        waste_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))

        # ── Load remarks from Supabase ────────────────────────────────────────
        try:
            _rem_res = supabase.table("waste_remark_options").select("remark").eq("client_name", final_client).execute()
            _custom_remarks = [r["remark"] for r in (_rem_res.data or [])]
        except Exception:
            _custom_remarks = []
        _REMARK_OPTIONS = _SYSTEM_REMARKS + [r for r in _custom_remarks if r not in _SYSTEM_REMARKS] + ["+ Add New..."]

        # ── Manage Remarks (managers+) ────────────────────────────────────────
        if role.lower() in ["manager", "admin", "admin_all"]:
            with st.expander("⚙️ Manage Remark Options"):
                col_nr, col_nb = st.columns([4, 1])
                with col_nr:
                    new_remark = st.text_input("New Remark", placeholder="e.g. DJ, John...", label_visibility="collapsed", key="new_remark_input")
                with col_nb:
                    if st.button("➕ Add", width="stretch", key="add_remark_btn"):
                        nr = new_remark.strip().upper()
                        if nr and nr not in _SYSTEM_REMARKS and nr not in _custom_remarks:
                            try:
                                supabase.table("waste_remark_options").insert({"client_name": final_client, "remark": nr, "created_by": user}).execute()
                                st.success(f"✅ '{nr}' added.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ {e}")
                        elif not nr:
                            st.warning("Please type a remark first.")
                        else:
                            st.warning("Already exists.")
                if _custom_remarks:
                    st.markdown("**Custom remarks:**")
                    for _cr in _custom_remarks:
                        col_cl, col_cd = st.columns([5, 1])
                        col_cl.markdown(f"• {_cr}")
                        if col_cd.button("✕", key=f"del_rem_{_cr}"):
                            supabase.table("waste_remark_options").delete().eq("client_name", final_client).eq("remark", _cr).execute()
                            st.rerun()

        st.divider()

        st.markdown("**Select Ticket Context:**")
        ticket_type = st.radio("Select Ticket Context:", ["Daily Waste", "Staff Meal", "Event"], horizontal=True, label_visibility="collapsed")
        event_name_val = st.text_input("📝 Event Name", placeholder="e.g. Wedding Booking") if ticket_type == "Event" else ""

        st.markdown("**Item Type:**")
        item_type_filter = st.radio("Item Type", ["📦 Inventory Items", "🍔 Menu Items", "All Items"], horizontal=True, label_visibility="collapsed")
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
            df_filtered_type = pd.DataFrame(columns=['item_name', 'category', 'sub_category', 'count_unit', 'location', 'item_type'])

        if df_items.empty:
            st.warning(f"⚠️ No items found for location **{loc_filter}**. This location may not have any items uploaded yet in the master list.")

        c1, c2 = st.columns(2)
        with c1:
            cats = sorted(list(df_filtered_type['category'].astype(str).unique())) if not df_filtered_type.empty else []
            cats = [c for c in cats if c.lower() != 'all'] # Prevent duplicate "All"s
            cat_options = ["All"] + cats
            
            # Added a unique key to force Streamlit to forget its old memory
            selected_category = st.selectbox("📂 Category", cat_options, index=1 if len(cat_options) > 1 else 0, key="waste_cat_box")
            
        with c2:
            df_grp_list = df_filtered_type if selected_category == "All" else df_filtered_type[df_filtered_type['category'] == selected_category]
            grps = sorted(list(df_grp_list['sub_category'].astype(str).unique())) if not df_grp_list.empty else []
            grps = [g for g in grps if g.lower() != 'all'] # Prevent duplicate "All"s
            grp_options = ["All"] + grps
            
            # Added a unique key here too
            selected_group = st.selectbox("🏷️ Sub Category", grp_options, index=1 if len(grp_options) > 1 else 0, key="waste_grp_box")

        if search_query:
            # Search overrides item type radio AND category filters — find the item anywhere
            df_display = df_items[df_items['item_name'].str.contains(search_query, case=False, na=False)].copy()
        else:
            df_display = df_filtered_type.copy()
            if selected_category != "All":
                df_display = df_display[df_display['category'] == selected_category]
            if selected_group != "All":
                df_display = df_display[df_display['sub_category'] == selected_group]

        total_items = len(df_display)
        wasted_in_view = sum(1 for item in df_display['item_name'] if item in st.session_state['waste_cart'])

        st.markdown(f'''
            <div style='display: flex; justify-content: space-between; background-color: #3b1c1c; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
                <span style='color: #ff6b6b;'>🗑️ {wasted_in_view} Selected</span>
                <span style='color: white;'>📝 {total_items} Items in View</span>
            </div>
        ''', unsafe_allow_html=True)

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
                    if input_key not in st.session_state:
                        st.session_state[input_key] = 0.0

                    # Auto-determine default remark
                    _cat_lower = str(row.get('category', '')).lower()
                    if ticket_type == "Daily Waste":
                        _auto_remark = "WB" if any(x in _cat_lower for x in ['bev', 'drink', 'alcohol']) else "WF"
                    elif ticket_type == "Staff Meal":
                        _auto_remark = "SM"
                    else:
                        _auto_remark = "WF"
                    _rem_key = f"waste_rem_{item_name}"
                    _rem_default = st.session_state['waste_remarks'].get(item_name, _auto_remark)
                    _rem_index = _REMARK_OPTIONS.index(_rem_default) if _rem_default in _REMARK_OPTIONS else len(_REMARK_OPTIONS) - 1

                    col_add, col_rem, col_btn = st.columns([2, 2, 1], vertical_alignment="center")
                    with col_add:
                        st.caption("Qty")
                        st.number_input("+ Add Qty", min_value=0.0, step=1.0, format="%g", key=input_key, on_change=add_waste_qty, args=(item_name, row.to_dict(), input_key), label_visibility="collapsed")
                    with col_rem:
                        st.caption("Remark")
                        if ticket_type == "Staff Meal":
                            st.markdown("**SM**")
                            st.session_state['waste_remarks'][item_name] = "SM"
                        elif ticket_type == "Event":
                            _ev_label = event_name_val.strip() if event_name_val.strip() else "Event"
                            st.markdown(f"**{_ev_label}**")
                            st.session_state['waste_remarks'][item_name] = _ev_label
                        else:
                            _daily_options = [r for r in _REMARK_OPTIONS if r not in ["SM"]]
                            _rem_index = _daily_options.index(_rem_default) if _rem_default in _daily_options else 0
                            _sel_remark = st.selectbox("Remark", _daily_options, index=_rem_index, key=_rem_key, label_visibility="collapsed")
                            if _sel_remark == "+ Add New...":
                                st.info("Use ⚙️ Manage Remark Options above to add new remarks.")
                                st.session_state['waste_remarks'][item_name] = _auto_remark
                            else:
                                st.session_state['waste_remarks'][item_name] = _sel_remark
                    with col_btn:
                        st.caption(" ")
                        if current_total > 0:
                            if st.button("♻️ Undo", key=f"undo_{index}_{item_name}"):
                                undo_waste_count(item_name)
                                st.rerun()

        st.divider()
        if len(st.session_state['waste_cart']) > 0:
            with st.expander("👀 Review & Submit Ticket", expanded=True):
                preview_list = [{"Item Name": v['row_data'].get('item_name', k), "Type": v['row_data'].get('item_type', 'Inventory'), "Qty Wasted": v['qty'], "Unit": v['row_data'].get('count_unit', 'Unit')} for k, v in st.session_state['waste_cart'].items()]
                st.dataframe(pd.DataFrame(preview_list), use_container_width=True, hide_index=True)

                # --- 🧠 THE SMART "SPEED BUMP" ---
                has_massive_waste = False
                for _, v in st.session_state['waste_cart'].items():
                    cart_unit = str(v['row_data'].get('count_unit', '')).strip().lower()
                    if cart_unit in ['kg', 'ltr'] and v['qty'] > 50:
                        has_massive_waste = True
                        break
                
                if has_massive_waste:
                    st.error("⚠️ **Massive Waste Detected!** You have items exceeding 50 kg or 50 ltr in your cart.")
                    confirm_huge = st.checkbox("🛑 These unusually large amounts are 100% correct.", value=False)
                else:
                    confirm_huge = True # Auto-approve normal amounts

                if st.button("🚀 SUBMIT TICKET TO CLOUD", type="primary", width="stretch"):
                    if ticket_type == "Event" and not event_name_val.strip():
                        st.error("❌ Please provide an Event Name before submitting.")
                    elif not confirm_huge:
                        st.error("❌ Please check the red confirmation box above to verify the massive quantities!")
                    else:
                        logs = []
                        for i_name, data in st.session_state['waste_cart'].items():
                            r_data = data['row_data']
                            _cat_lower = str(r_data.get('category', '')).lower()
                            if ticket_type == "Daily Waste":
                                _auto = "WB" if any(x in _cat_lower for x in ['bev', 'drink', 'alcohol']) else "WF"
                            elif ticket_type == "Staff Meal":
                                _auto = "SM"
                            elif ticket_type == "Event":
                                _auto = f"Event: {event_name_val}"
                            else:
                                _auto = ""
                            reason_code = st.session_state['waste_remarks'].get(i_name, _auto)
                            
                            logs.append({
                                "date": str(waste_date), "client_name": final_client, "outlet": final_outlet,
                                "location": str(assigned_location), "reported_by": user,
                                "item_name": i_name, "item_type": r_data.get('item_type', 'inventory'),
                                "category": r_data.get('category', ''),
                                "sub_category": r_data.get('sub_category', ''),
                                "product_code": r_data.get('product_code', ''),
                                "qty": float(data['qty']), "count_unit": r_data.get('count_unit', 'Unit'), "remarks": reason_code
                            })
                        
                        try:
                            supabase.table("waste_logs").insert(logs).execute()
                            st.session_state['last_waste_receipt'] = {"bytes": generate_waste_pdf(pd.DataFrame(logs), str(waste_date), final_client, final_outlet, str(assigned_location), user, ticket_type, event_name_val), "filename": f"{ticket_type}_{waste_date}.pdf"}
                            st.session_state['waste_cart'] = {}
                            st.session_state['waste_remarks'] = {}
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Database Error: {e}")

    except Exception as e:
        st.error(f"❌ Error: {e}")