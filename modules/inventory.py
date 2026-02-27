import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
from fpdf import FPDF
import io

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# --- PDF GENERATOR HELPER FUNCTION ---
def generate_inventory_pdf(df, report_date, client, outlet, location, user_name):
    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Official Inventory Count Report", ln=True, align="C")
    
    # Meta Data
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, f"Date: {report_date}", ln=True)
    pdf.cell(0, 6, f"Branch: {client} | Outlet: {outlet} | Location: {location}", ln=True)
    pdf.cell(0, 6, f"Counted By: {user_name} | Generated: {datetime.now(zoneinfo.ZoneInfo('Asia/Beirut')).strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(5)
    
    # Table Header
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(80, 8, "Item Name", border=1, fill=True)
    pdf.cell(50, 8, "Category", border=1, fill=True)
    pdf.cell(30, 8, "Quantity", border=1, align="C", fill=True)
    pdf.cell(30, 8, "Unit", border=1, align="C", fill=True)
    pdf.ln()
    
    # Table Rows
    pdf.set_font("helvetica", "", 9)
    for _, row in df.iterrows():
        # Clean up data strings and limit length to avoid text bleeding out of cells
        item = str(row.get('item_name', ''))[:40]
        cat = str(row.get('category', ''))[:25]
        qty = str(row.get('quantity', '0'))
        unit = str(row.get('count_unit', 'pcs'))[:10]
        
        pdf.cell(80, 8, item, border=1)
        pdf.cell(50, 8, cat, border=1)
        pdf.cell(30, 8, qty, border=1, align="C")
        pdf.cell(30, 8, unit, border=1, align="C")
        pdf.ln()
        
    return bytes(pdf.output())

# --- THE CUMULATIVE COUNTING LOGIC ---
def add_inventory_qty(item_key, row_dict, input_key):
    added_val = st.session_state.get(input_key, 0.0)
    if added_val > 0:
        if item_key not in st.session_state['mobile_counts']:
            st.session_state['mobile_counts'][item_key] = {'row_data': row_dict, 'qty': 0.0}
        st.session_state['mobile_counts'][item_key]['qty'] += added_val
        st.session_state[input_key] = 0.0

def undo_inventory_count(item_key):
    if item_key in st.session_state['mobile_counts']:
        del st.session_state['mobile_counts'][item_key]

# ---> THE UPGRADED RENDER FUNCTION <---
def render_inventory(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 📋 Inventory Count")
    supabase = get_supabase()

    if 'mobile_counts' not in st.session_state:
        st.session_state['mobile_counts'] = {}

    try:
        # ==========================================
        # 1. VIEW MODE (HISTORY & PDF EXPORT)
        # ==========================================
        if role.lower() == "viewer":
            st.info("👁️ Viewer Mode: Showing Inventory Logs")
            
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=7)
            
            date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today)
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                
                query = supabase.table("inventory_logs").select("*").gte("date", str(start_date)).lte("date", str(end_date))
                if str(assigned_client).lower() != 'all':
                    query = query.ilike("client_name", f"%{str(assigned_client).strip()}%")
                    
                archive_res = query.order("date", desc=True).limit(2000).execute()
                df_archive = pd.DataFrame(archive_res.data)

                if not df_archive.empty:
                    pdf_bytes = generate_inventory_pdf(
                        df_archive, f"{start_date} to {end_date}", 
                        assigned_client, assigned_outlet, "Multiple Locations", "System Report"
                    )
                    
                    st.download_button(
                        label="🖨️ Download PDF Report",
                        data=pdf_bytes,
                        file_name=f"Inventory_Report_{start_date}_to_{end_date}.pdf",
                        mime="application/pdf",
                        type="primary"
                    )
                    
                    st.dataframe(df_archive, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No logs found between {start_date} and {end_date}.")
            else:
                st.info("Please select both a Start Date and an End Date.")
            return

        # ==========================================
        # 2. SMART ROUTING & CLEAN SIDEBAR
        # ==========================================
        nav_res = supabase.table("master_items").select("client_name, outlet").execute()
        df_nav = pd.DataFrame(nav_res.data)
        
        if not df_nav.empty:
            df_nav['client_name'] = df_nav['client_name'].astype(str).str.strip().str.title()
            df_nav['outlet'] = df_nav['outlet'].astype(str).str.strip().str.title()
            
        clean_client = str(assigned_client).strip().title()
        clean_outlet = str(assigned_outlet).strip().title()

        st.sidebar.markdown("### 📍 Location Details")

        if clean_client.lower() != 'all':
            final_client = clean_client
            st.sidebar.markdown(f"**🏢 Branch:** {final_client}")
        else:
            c_list = sorted(df_nav['client_name'].unique()) if not df_nav.empty else ["All"]
            final_client = st.sidebar.selectbox("🏢 Select Branch", c_list)

        if not df_nav.empty:
            outlets_for_client = sorted(df_nav[df_nav['client_name'] == final_client]['outlet'].unique())
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

        # ==========================================
        # 3. POST-SUBMISSION RECEIPT (PDF)
        # ==========================================
        if 'last_inv_receipt' in st.session_state:
            st.success("✅ **Success!** Your count was safely stored in the cloud.")
            st.download_button(
                label="🖨️ Download Proof of Count (PDF Receipt)",
                data=st.session_state['last_inv_receipt']['bytes'],
                file_name=st.session_state['last_inv_receipt']['filename'],
                mime="application/pdf",
                type="primary"
            )
            if st.button("Start New Count", use_container_width=True):
                del st.session_state['last_inv_receipt']
                st.rerun()
            st.divider()
            return

        # ==========================================
        # 4. MEGA-FETCH LOOP
        # ==========================================
        all_items = []
        page_size, start_row = 1000, 0
        
        if final_outlet != "None":
            while True:
                res = supabase.table("master_items").select("*").ilike("outlet", f"%{final_outlet}%").range(start_row, start_row + page_size - 1).execute()
                if not res.data: break
                all_items.extend(res.data)
                if len(res.data) < page_size: break
                start_row += page_size

        if not all_items:
            df_items = pd.DataFrame(columns=['item_name', 'category', 'sub_category', 'count_unit', 'location', 'product_code', 'item_type'])
            st.warning(f"⚠️ No items found for {final_outlet}.")
        else:
            df_items = pd.DataFrame(all_items)
            df_items.columns = [str(c).strip().lower() for c in df_items.columns]
            if 'location' not in df_items.columns:
                df_items['location'] = "Main Store"
            if 'item_type' in df_items.columns:
                df_items = df_items[df_items['item_type'].astype(str).str.lower() == 'inventory']

        db_locs = sorted(df_items['location'].dropna().astype(str).str.title().unique())
        raw_loc = str(assigned_location).strip()

        if raw_loc.lower() == 'all':
            loc_options = ["All"] + db_locs if db_locs else ["All"]
            loc_filter = st.sidebar.selectbox("📍 Select Location", loc_options)
        elif "," in raw_loc:
            allowed_locs = [l.strip().title() for l in raw_loc.split(',')]
            valid_locs = [l for l in allowed_locs if l in db_locs]
            if valid_locs:
                loc_filter = st.sidebar.selectbox("📍 Select Location", valid_locs)
            else:
                st.sidebar.warning("Assigned locations not found in database.")
                loc_filter = allowed_locs[0] if allowed_locs else "Main Store"
        else:
            loc_filter = raw_loc.title()
            st.sidebar.markdown(f"**📍 Location:** {loc_filter}")
            
        # ---> THE DUPLICATE FIX IS HERE <---
        if not df_items.empty:
            # 1. First filter by the exact location (e.g. Med)
            if loc_filter != "All":
                df_items = df_items[df_items['location'].str.title() == loc_filter]
            
            # 2. Ultra-safe: Remove any accidental exact duplicates remaining
            df_items = df_items.drop_duplicates(subset=['item_name']).copy()

        count_date = st.date_input("📅 Date", datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")))
        st.divider()

        # ==========================================
        # 5. FILTERS & CARDS & MISSING ITEM
        # ==========================================
        with st.expander("➕ Missing an item? Add it manually here"):
            c_name = st.text_input("Item Name (e.g., Redbull)")
            col_cat, col_grp = st.columns(2)
            with col_cat:
                cat_options = list(df_items['category'].dropna().unique()) if not df_items.empty else ["General"]
                c_cat = st.selectbox("Category", cat_options, key="custom_cat")
            with col_grp:
                if not df_items.empty and c_cat in cat_options:
                    grp_options = list(df_items[df_items['category'] == c_cat]['sub_category'].dropna().unique())
                else:
                    grp_options = ["General"]
                c_grp = st.selectbox("Sub Category", grp_options, key="custom_grp")
                
            col_qty, col_unit = st.columns(2)
            with col_qty:
                c_qty = st.number_input("Quantity", min_value=0.0, step=1.0, format="%g", key="custom_qty")
            with col_unit:
                c_unit = st.text_input("Unit (e.g., Can, Kg)")
                
            if st.button("Save Custom Item", use_container_width=True):
                if c_name and c_qty > 0:
                    fake_row = {
                        "item_name": c_name.upper(), "category": c_cat, 
                        "sub_category": c_grp, "count_unit": c_unit.title() if c_unit else "Pcs"
                    }
                    st.session_state['mobile_counts'][f"CUSTOM_{c_name}"] = {'row_data': fake_row, 'qty': c_qty}
                    st.success(f"Added {c_name} to cart!")
                    st.rerun()

        st.subheader("🔍 Filter & Count")
        search_query = st.text_input("🔍 Quick Search", placeholder="Find items...")
        
        c1, c2 = st.columns(2)
        with c1:
            cats = sorted(list(df_items['category'].dropna().astype(str).unique())) if not df_items.empty else []
            cat_options = ["All"] + cats
            selected_category = st.selectbox("📂 Category", cat_options, index=1 if cats else 0)
        with c2:
            df_grp_list = df_items if selected_category == "All" else df_items[df_items['category'] == selected_category]
            grps = sorted(list(df_grp_list['sub_category'].dropna().astype(str).unique())) if not df_grp_list.empty else []
            grp_options = ["All"] + grps
            selected_group = st.selectbox("🏷️ Sub Category", grp_options, index=1 if grps else 0)

        if not df_items.empty:
            if search_query:
                df_display = df_items[df_items['item_name'].str.contains(search_query, case=False, na=False)].copy()
            else:
                df_display = df_items.copy()
                if selected_category != "All":
                    df_display = df_display[df_display['category'] == selected_category]
                if selected_group != "All":
                    df_display = df_display[df_display['sub_category'] == selected_group]
        else:
            df_display = pd.DataFrame()

        total_items = len(df_display)
        counted_in_view = sum(1 for item in df_display['item_name'] if item in st.session_state['mobile_counts']) if not df_display.empty else 0
        
        st.markdown(f"""
            <div style='display: flex; justify-content: space-between; background-color: #1e1e1e; padding: 10px; border-radius: 10px; margin-bottom: 20px;'>
                <span style='color: #00ff00;'>✅ {counted_in_view} Counted</span>
                <span style='color: white;'>📝 {total_items} Items in {selected_group}</span>
            </div>
        """, unsafe_allow_html=True)

        if df_display.empty:
            st.info("No items found.")
        else:
            for index, row in df_display.iterrows():
                item_name = row['item_name']
                cart_data = st.session_state['mobile_counts'].get(item_name)
                current_total = cart_data['qty'] if cart_data else 0.0
                
                with st.container(border=True):
                    if current_total > 0:
                        st.markdown(f"🟢 **{item_name}** &nbsp;|&nbsp; ✅ Total: **{current_total}** {row.get('count_unit', 'pcs')}")
                    else:
                        st.markdown(f"🔴 **{item_name}** &nbsp;|&nbsp; 📦 {row.get('count_unit', 'pcs')}")
                    
                    col_add, col_btn = st.columns([3, 1], vertical_alignment="center")
                    input_key = f"inv_add_{row.get('id', index)}_{item_name}"
                    
                    with col_add:
                        st.number_input(
                            "+ Add Qty", 
                            value=0.0, min_value=0.0, step=1.0, format="%g", 
                            key=input_key,
                            on_change=add_inventory_qty,
                            args=(item_name, row.to_dict(), input_key),
                            label_visibility="collapsed",
                            placeholder="Type amount and press Enter"
                        )
                    with col_btn:
                        if current_total > 0:
                            if st.button("🗑️ Undo", key=f"undo_{row.get('id', index)}_{item_name}"):
                                undo_inventory_count(item_name)
                                st.rerun()

        # ==========================================
        # 6. SUBMIT TO CLOUD & GENERATE RECEIPT
        # ==========================================
        st.divider()
        cart_size = len(st.session_state['mobile_counts'])
        if cart_size > 0:
            st.success(f"🛒 **{cart_size} items** ready to submit.")
            with st.expander("👀 Review & Submit Count", expanded=True):
                
                preview_list = []
                for k, v in st.session_state['mobile_counts'].items():
                    preview_list.append({
                        "Item": v['row_data'].get('item_name', k),
                        "Total Counted": v['qty'],
                        "Unit": v['row_data'].get('count_unit', '')
                    })
                st.dataframe(pd.DataFrame(preview_list), use_container_width=True, hide_index=True)

                if st.button("🚀 SUBMIT ALL COUNTS TO CLOUD", type="primary", use_container_width=True):
                    logs = []
                    for i_name, data in st.session_state['mobile_counts'].items():
                        r_data = data['row_data']
                        logs.append({
                            "date": str(count_date),
                            "client_name": final_client,
                            "outlet": final_outlet,
                            "location": loc_filter,
                            "counted_by": user,
                            "item_name": r_data.get('item_name', i_name),
                            "product_code": str(r_data.get('product_code', '')),
                            "item_type": r_data.get('item_type', ''),
                            "category": r_data.get('category', ''),
                            "sub_category": r_data.get('sub_category', ''),
                            "quantity": float(data['qty']),
                            "count_unit": r_data.get('count_unit', 'pcs')
                        })
                    
                    if logs:
                        try:
                            # 1. Insert to Database
                            supabase.table("inventory_logs").insert(logs).execute()
                            
                            # 2. Generate PDF Receipt Bytes
                            df_receipt = pd.DataFrame(logs)
                            pdf_bytes = generate_inventory_pdf(
                                df_receipt, str(count_date), final_client, final_outlet, loc_filter, user
                            )
                            
                            # 3. Save receipt to session state so it appears on next reload
                            st.session_state['last_inv_receipt'] = {
                                "bytes": pdf_bytes,
                                "filename": f"Inventory_Receipt_{final_outlet.replace(' ', '_')}_{str(count_date)}.pdf"
                            }
                            
                            # 4. Clear the shopping cart
                            st.session_state['mobile_counts'] = {}
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"❌ Database Error: {e}")

    except Exception as e:
        st.error(f"❌ System Error: {e}")