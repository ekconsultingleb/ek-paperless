import streamlit as st
import pandas as pd
import uuid
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_invoices(conn, sheet_link, user, role):
    supabase = get_supabase()
    
    # Grab the user's routing info from the session
    client_name = st.session_state.get('client_name', 'Unknown')
    outlet = st.session_state.get('assigned_outlet', 'Unknown')
    location = st.session_state.get('assigned_location', 'Unknown')
    user_role = str(role).lower()

    # 🚦 TRAFFIC COP: Who sees what?
    can_process_invoices = user_role in ["manager", "admin", "admin_all", "viewer"]

    # --- SET UP THE SPLIT SCREEN ---
    if can_process_invoices:
        st.markdown("### 🏢 Accounts Payable Dashboard")
        tab_process, tab_archive, tab_upload = st.tabs(["📋 Process Invoices", "🗄️ Archived Posted", "📸 Upload Invoice"])
    else:
        st.markdown("### 📸 Snap & Upload Invoice")
        tab_upload = st.container() # Staff only gets the upload screen, no tabs
        tab_process = None
        tab_archive = None

    # ==========================================
    # VIEW 1: DATA ENTRY DASHBOARD (Bassel's View)
    # ==========================================
    if tab_process:
        with tab_process:
            st.info("💡 **Scroll & Process Mode:** Click '⚙️ Process Invoice' below any record to expand it, view the image, and update its status.")
            
            try:
                # Fetch invoices that need attention
                query = supabase.table("invoices_log").select("*").in_("status", ["Pending", "On Hold"])
                
                if client_name != "All":
                    query = query.eq("client_name", client_name)
                if outlet != "All":
                    query = query.eq("outlet", outlet)
                    
                res = query.execute()
                
                if not res.data:
                    st.success("🎉 All caught up! There are no Pending or On Hold invoices to process.")
                else:
                    df = pd.DataFrame(res.data)
                    df = df.sort_values(by="created_at", ascending=True)
                    
                    # --- 🧠 SMART CLIENT FILTER FOR BASSEL ---
                    if client_name == "All":
                        active_clients = ["All Clients"] + sorted(df['client_name'].unique().tolist())
                        st.markdown("#### 🎯 Filter Workspace")
                        chosen_client = st.selectbox("Select a Client to focus on:", active_clients, key="process_filter")
                        if chosen_client != "All Clients":
                            df = df[df['client_name'] == chosen_client]
                    
                    if df.empty:
                        st.info("✅ No pending invoices for this specific client.")
                    else:
                        st.markdown("#### 📥 Pending Invoices Feed")
                        
                        # Build the scrolling interactive feed
                        for index, row in df.iterrows():
                            inv_id = row['id']
                            c_name = row['client_name']
                            
                            with st.container(border=True):
                                # Top summary row
                                col_date, col_sup, col_loc, col_stat = st.columns([1.5, 2.5, 2, 1], vertical_alignment="center")
                                col_date.write(f"📅 {str(row['created_at'])[:10]}")
                                col_sup.write(f"🧾 **{row['supplier']}**")
                                col_loc.write(f"🏢 {c_name} ({row['outlet']})")
                                
                                # Status badges
                                if row['status'] == 'On Hold':
                                    col_stat.error("⏸️ On Hold")
                                else:
                                    col_stat.warning("⏳ Pending")
                                    
                                # 🔒 THE INLINE EXPANDER
                                with st.expander("⚙️ Process Invoice"):
                                    col_img, col_form = st.columns([1.2, 1])
                                    
                                    with col_img:
                                        st.image(row['image_url'], use_container_width=True, output_format="JPEG")
                                        st.markdown(f"[🔍 Click here to open full size image in a new tab]({row['image_url']})")
                                        
                                    with col_form:
                                        st.write(f"**👤 Uploaded By:** {row['uploaded_by']}")
                                        
                                        with st.form(f"process_form_{inv_id}"):
                                            current_status = row.get('status', 'Pending')
                                            status_options = ["Pending", "On Hold", "Posted"]
                                            new_status = st.radio("Status", status_options, index=status_options.index(current_status) if current_status in status_options else 0, horizontal=True)
                                            
                                            new_notes = st.text_area("Data Entry Notes", value=row.get('data_entry_notes', '') or "")
                                            
                                            if st.form_submit_button("💾 Save & Update", type="primary", use_container_width=True):
                                                if user_role == "viewer":
                                                    st.error("🚫 Access Denied: Viewers cannot modify records.")
                                                else:
                                                    update_data = {
                                                        "status": new_status, 
                                                        "data_entry_notes": new_notes, 
                                                        "posted_by": user if new_status == "Posted" else row.get('posted_by', None)
                                                    }
                                                    supabase.table("invoices_log").update(update_data).eq("id", inv_id).eq("client_name", c_name).execute()
                                                    
                                                    st.success(f"✅ Invoice updated successfully!")
                                                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error loading dashboard: {e}")

    # ==========================================
    # VIEW 2: ARCHIVED POSTED INVOICES (Upgraded with Smart Filters)
    # ==========================================
    if tab_archive:
        with tab_archive:
            st.info("🗄️ **Archived Ledger:** View posted invoices. Filter by date, client, and supplier.")
            
            # --- 🚀 1. DATE SHIELD: Defaults to last 30 days so the app doesn't crash ---
            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=30)
            
            date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today, key="arch_dates")
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                
                try:
                    # --- 🚀 2. DATABASE FILTER: Only download what we need! ---
                    query = supabase.table("invoices_log").select("*").eq("status", "Posted").gte("created_at", f"{start_date}T00:00:00").lte("created_at", f"{end_date}T23:59:59")
                    
                    # Apply Security Routing
                    if client_name != "All":
                        query = query.eq("client_name", client_name)
                    if outlet != "All":
                        query = query.eq("outlet", outlet)
                        
                    res = query.execute()
                    
                    if not res.data:
                        st.warning(f"No posted invoices found between {start_date} and {end_date}.")
                    else:
                        df_arch = pd.DataFrame(res.data)
                        df_arch = df_arch.sort_values(by="created_at", ascending=False) # Show newest first!
                        
                        # --- 🚀 3. SECONDARY FILTERS (Client & Supplier) ---
                        col_f1, col_f2 = st.columns(2)
                        
                        with col_f1:
                            if client_name == "All":
                                active_clients = ["All Clients"] + sorted(df_arch['client_name'].unique().tolist())
                                chosen_client = st.selectbox("🎯 Filter by Client:", active_clients, key="archive_client_filter")
                                if chosen_client != "All Clients":
                                    df_arch = df_arch[df_arch['client_name'] == chosen_client]
                            else:
                                st.markdown(f"**🏢 Client:** {client_name}")
                                
                        with col_f2:
                            # Generate a live list of suppliers ONLY from the filtered date range!
                            active_suppliers = ["All Suppliers"] + sorted(df_arch['supplier'].unique().tolist())
                            chosen_supplier = st.selectbox("🧾 Filter by Supplier:", active_suppliers, key="archive_sup_filter")
                            if chosen_supplier != "All Suppliers":
                                df_arch = df_arch[df_arch['supplier'] == chosen_supplier]
                        
                        st.divider()
                        
                        # --- 🚀 4. DISPLAY THE RESULTS ---
                        if df_arch.empty:
                            st.info("No invoices match your selected filters.")
                        else:
                            st.success(f"📚 Found {len(df_arch)} posted invoice(s).")
                            
                            for index, row in df_arch.iterrows():
                                c_name = row['client_name']
                                with st.container(border=True):
                                    col_date, col_sup, col_loc, col_badge = st.columns([1.5, 2.5, 2, 1], vertical_alignment="center")
                                    col_date.write(f"📅 {str(row['created_at'])[:10]}")
                                    col_sup.write(f"🧾 **{row['supplier']}**")
                                    col_loc.write(f"🏢 {c_name} ({row['outlet']})")
                                    col_badge.success("✅ Posted")
                                    
                                    # Read-only expander for the archive
                                    with st.expander("👁️ View Invoice Details"):
                                        col_img, col_det = st.columns([1.2, 1])
                                        with col_img:
                                            st.image(row['image_url'], use_container_width=True, output_format="JPEG")
                                            st.markdown(f"[🔍 Click here to open full size image in a new tab]({row['image_url']})")
                                        with col_det:
                                            st.write(f"**👤 Uploaded By:** {row.get('uploaded_by', 'Unknown')}")
                                            st.write(f"**✅ Posted By:** {row.get('posted_by', 'Head Office')}")
                                            
                                            notes = row.get('data_entry_notes', '')
                                            st.write(f"**📝 Notes:** {notes if notes else '*No notes provided.*'}")
                except Exception as e:
                    st.error(f"❌ Error loading archive: {e}")
            else:
                st.info("Please select both a Start Date and an End Date.")

    # ==========================================
    # VIEW 3: SNAP INVOICE (Everyone sees this)
    # ==========================================
    with tab_upload:
        st.info("💡 **Mobile Users:** Tap 'Browse files' to open your camera.")
        
        # --- 🧠 BULLETPROOF MOBILE SUPPLIER SEARCH ---
        try:
            sup_res = supabase.table("suppliers").select("supplier_name").execute()
            supplier_list = sorted([row['supplier_name'] for row in sup_res.data]) if sup_res.data else []
        except Exception:
            supplier_list = []
            
        search_term = st.text_input("🔍 Search Supplier", placeholder="Type here to filter the list below...")
        
        if search_term:
            filtered_suppliers = [s for s in supplier_list if search_term.lower() in s.lower()]
            if "➕ Other (Type manually)" not in filtered_suppliers:
                filtered_suppliers.append("➕ Other (Type manually)")
        else:
            filtered_suppliers = supplier_list + ["➕ Other (Type manually)"]

        selected_supplier = st.selectbox("🏢 Choose from Results", filtered_suppliers)
        
        if selected_supplier == "➕ Other (Type manually)":
            final_supplier_name = st.text_input("📝 Type the new supplier name:")
        else:
            final_supplier_name = selected_supplier
        
        uploaded_file = st.file_uploader("Take a Photo or Upload PDF", type=['jpg', 'jpeg', 'png', 'pdf'])
        
        if uploaded_file:
            if uploaded_file.type.startswith('image'):
                st.image(uploaded_file, caption="Invoice Preview", use_container_width=True)
            else:
                st.success(f"📄 PDF Selected: {uploaded_file.name}")
        
        if st.button("🚀 Submit Invoice to Accounting", type="primary", use_container_width=True):
            if not final_supplier_name:
                st.error("❌ Please select a Supplier.")
            elif not uploaded_file:
                st.error("❌ Please upload or take a photo.")
            else:
                with st.spinner("Uploading..."):
                    try:
                        file_ext = uploaded_file.name.split('.')[-1].lower()
                        unique_filename = f"{client_name.replace(' ', '')}_{uuid.uuid4().hex[:8]}.{file_ext}"
                        
                        supabase.storage.from_("invoices").upload(path=unique_filename, file=uploaded_file.getvalue(), file_options={"content-type": uploaded_file.type})
                        image_url = supabase.storage.from_("invoices").get_public_url(unique_filename)
                        
                        db_record = {
                            "client_name": client_name, "outlet": outlet, "location": location,
                            "uploaded_by": user, "supplier": final_supplier_name.strip().title(),
                            "image_url": image_url, "status": "Pending", "data_entry_notes": ""
                        }
                        supabase.table("invoices_log").insert([db_record]).execute()
                        
                        st.success("✅ Invoice successfully uploaded!")
                        st.toast("Invoice sent!", icon="🚀")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

        # ── MY UPLOADS TODAY ─────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📋 My Uploads Today")

        try:
            today_str = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d")
            my_res = supabase.table("invoices_log")                .select("supplier, image_url, status, created_at")                .eq("uploaded_by", user)                .gte("created_at", f"{today_str}T00:00:00")                .order("created_at", desc=True)                .limit(20)                .execute()

            if not my_res.data:
                st.caption("No invoices uploaded yet today.")
            else:
                for inv in my_res.data:
                    # Format time
                    raw_time = str(inv.get("created_at", ""))
                    try:
                        from datetime import timezone
                        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                        beirut_dt = dt.astimezone(zoneinfo.ZoneInfo("Asia/Beirut"))
                        time_str = beirut_dt.strftime("%I:%M %p")
                    except Exception:
                        time_str = raw_time[11:16]

                    status = inv.get("status", "Pending")
                    status_color = {
                        "Pending": "#854F0B",
                        "Posted":  "#3B6D11",
                        "On Hold": "#A32D2D"
                    }.get(status, "#888")

                    with st.container(border=True):
                        col_img, col_info = st.columns([1, 2], vertical_alignment="center")
                        with col_img:
                            img_url = inv.get("image_url", "")
                            if img_url and not img_url.endswith(".pdf"):
                                st.image(img_url, use_container_width=True)
                            else:
                                st.markdown("📄 **PDF**")
                        with col_info:
                            st.markdown(f"**{inv.get('supplier', 'Unknown')}**")
                            st.markdown(f"🕐 {time_str}")
                            st.markdown(
                                f"<span style='background:{status_color}20; color:{status_color}; "
                                f"padding:2px 10px; border-radius:20px; font-size:12px; font-weight:500;'>"
                                f"{status}</span>",
                                unsafe_allow_html=True
                            )
        except Exception as e:
            st.caption(f"Could not load today's uploads: {e}")