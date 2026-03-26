import streamlit as st
import pandas as pd
import uuid
import base64
import json
from datetime import datetime, timedelta
import zoneinfo
from supabase import create_client, Client
import google.generativeai as genai

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

@st.cache_resource
def _get_gemini():
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    return genai.GenerativeModel('gemini-2.5-flash')

def _extract_invoice_data(file_bytes: bytes, mime_type: str) -> dict:
    """Use Gemini to extract supplier, total, and currency from invoice image/PDF."""
    try:
        model = _get_gemini()
        prompt = """Analyze this invoice and extract:
1. Supplier / vendor name (the company selling, not the buyer)
2. Total amount to pay (the final total, grand total, or amount due)
3. Currency (USD, LBP, EUR, etc.)

Return ONLY valid JSON in this exact format, no explanation:
{"supplier": "name or null", "total": number or null, "currency": "USD" or "LBP" or null}

If currency is unclear but amounts look like Lebanese Pounds (large numbers like 500000+), use "LBP".
If amounts are small (under 10000), likely USD.
If supplier name is not found, return null for supplier."""
        response = model.generate_content([
            {"mime_type": mime_type, "data": base64.b64encode(file_bytes).decode()},
            prompt
        ])
        clean = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception:
        return {"supplier": None, "total": None, "currency": None}

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
                # ── Date filter ──────────────────────────────────────────────
                _today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
                _default_start = _today - timedelta(days=30)
                col_pd1, col_pd2 = st.columns(2)
                with col_pd1:
                    proc_start = st.date_input("📅 From", value=_default_start, max_value=_today, key="proc_start")
                with col_pd2:
                    proc_end = st.date_input("📅 To", value=_today, max_value=_today, key="proc_end")

                # Fetch invoices that need attention
                query = (supabase.table("invoices_log").select("*")
                         .in_("status", ["Pending", "On Hold"])
                         .gte("created_at", f"{proc_start}T00:00:00")
                         .lte("created_at", f"{proc_end}T23:59:59"))

                if client_name != "All":
                    query = query.eq("client_name", client_name)
                if outlet != "All":
                    query = query.eq("outlet", outlet)

                res = query.execute()

                if not res.data:
                    st.success("🎉 All caught up! No Pending or On Hold invoices for this period.")
                else:
                    df = pd.DataFrame(res.data)
                    df = df.sort_values(by="created_at", ascending=True)

                    # --- 🧠 SMART CLIENT FILTER FOR EK TEAM ---
                    if client_name == "All":
                        active_clients = ["All Clients"] + sorted(df['client_name'].unique().tolist())
                        st.markdown("#### 🎯 Filter Workspace")
                        chosen_client = st.selectbox("Select a Client to focus on:", active_clients, key="process_filter")
                        if chosen_client != "All Clients":
                            df = df[df['client_name'] == chosen_client]

                    if df.empty:
                        st.info("✅ No pending invoices for this specific client.")
                    else:
                        st.markdown(f"#### 📥 Pending Invoices Feed ({len(df)})")
                        
                        # Build the scrolling interactive feed
                        for index, row in df.iterrows():
                            inv_id = row['id']
                            c_name = row['client_name']

                            # --- Format date nicely ---
                            try:
                                import zoneinfo as _zi
                                _dt = datetime.fromisoformat(str(row['created_at']).replace("Z", "+00:00"))
                                _dt_b = _dt.astimezone(_zi.ZoneInfo("Asia/Beirut"))
                                card_date = _dt_b.strftime("%d %b %Y · %I:%M %p")
                            except Exception:
                                card_date = str(row['created_at'])[:10]

                            # --- Status badge styling ---
                            status = row.get('status', 'Pending')
                            if status == 'On Hold':
                                badge_bg = "#FCEBEB"; badge_color = "#A32D2D"
                            elif status == 'Posted':
                                badge_bg = "#EAF3DE"; badge_color = "#3B6D11"
                            else:
                                badge_bg = "#FAEEDA"; badge_color = "#854F0B"

                            img_url = row.get('image_url', '')
                            is_pdf = str(img_url).lower().endswith('.pdf')

                            with st.container(border=True):
                                # --- Card header: thumbnail + info + badge ---
                                col_thumb, col_info = st.columns([1, 4], vertical_alignment="center")

                                with col_thumb:
                                    if img_url and not is_pdf:
                                        st.image(img_url, use_container_width=True)
                                    else:
                                        st.markdown(
                                            "<div style='text-align:center; padding:10px; font-size:28px;'>📄</div>",
                                            unsafe_allow_html=True
                                        )

                                with col_info:
                                    st.markdown(
                                        f"<p style='margin:0 0 2px; font-size:15px; font-weight:500;'>{row['supplier']}</p>"
                                        f"<p style='margin:0 0 6px; font-size:12px; color:var(--color-text-secondary);'>{card_date} · {c_name} ({row['outlet']})</p>"
                                        f"<span style='background:{badge_bg}; color:{badge_color}; font-size:11px; font-weight:500; padding:3px 10px; border-radius:20px;'>{status}</span>",
                                        unsafe_allow_html=True
                                    )

                                # 🔒 THE INLINE EXPANDER
                                with st.expander("⚙️ Process Invoice"):
                                    col_img, col_form = st.columns([1.2, 1])
                                    
                                    with col_img:
                                        if is_pdf:
                                            st.markdown("<div style='text-align:center; padding:20px; font-size:48px;'>📄</div>", unsafe_allow_html=True)
                                        else:
                                            st.image(row['image_url'], use_container_width=True)
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
                                            _arch_is_pdf = str(row.get('image_url', '')).lower().endswith('.pdf')
                                            if _arch_is_pdf:
                                                st.markdown("<div style='text-align:center; padding:20px; font-size:48px;'>📄</div>", unsafe_allow_html=True)
                                            else:
                                                st.image(row['image_url'], use_container_width=True)
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

        # ── EK team: select client + outlet before uploading ─────────────────
        if client_name == "All":
            try:
                _cl_res = supabase.table("clients").select("client_name").order("client_name").execute()
                _cl_list = [r["client_name"] for r in (_cl_res.data or [])]
            except Exception:
                _cl_list = []
            upload_client = st.selectbox("🏢 Select Client", _cl_list, key="upload_client_sel") if _cl_list else st.text_input("🏢 Client Name")
            try:
                _out_res = supabase.table("branches").select("outlet").eq("client_name", upload_client).execute()
                _out_list = [r["outlet"] for r in (_out_res.data or [])]
            except Exception:
                _out_list = []
            upload_outlet = st.selectbox("🏠 Select Outlet", _out_list, key="upload_outlet_sel") if _out_list else outlet
        else:
            upload_client = client_name
            upload_outlet = outlet

        # Load supplier list
        try:
            sup_res = supabase.table("suppliers").select("supplier_name").execute()
            supplier_list = sorted([r['supplier_name'] for r in sup_res.data]) if sup_res.data else []
        except Exception:
            supplier_list = []

        # Hide only the live video feed — keep the capture button visible
        st.markdown("""
            <style>
                [data-testid="stCameraInputButton"] ~ div video {
                    display: none !important;
                }
                [data-testid="stCameraInput"] video {
                    height: 0 !important;
                    min-height: 0 !important;
                    padding: 0 !important;
                    margin: 0 !important;
                    overflow: hidden !important;
                }
            </style>
        """, unsafe_allow_html=True)

        camera_photo = st.camera_input("📷 Take a Photo")
        browse_file  = st.file_uploader("🖼️ Or browse / upload PDF", type=['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif', 'pdf'])

        if camera_photo:
            uploaded_file = camera_photo
            file_bytes    = camera_photo.getvalue()
            file_mime     = "image/jpeg"
        elif browse_file:
            uploaded_file = browse_file
            file_bytes    = browse_file.getvalue()
            file_mime     = browse_file.type if browse_file.type else "image/jpeg"
        else:
            uploaded_file = None
            file_bytes    = None
            file_mime     = None

        # Reset submitted state when a new file is chosen
        current_file_id = id(uploaded_file) if uploaded_file else None
        if st.session_state.get('invoice_submitted_file') != current_file_id:
            st.session_state['invoice_submitted'] = False
            st.session_state['invoice_submitted_file'] = current_file_id
            st.session_state.pop('ai_invoice_data', None)

        if uploaded_file:
            if file_mime and file_mime.startswith('image'):
                st.image(file_bytes, caption="Invoice Preview", use_container_width=True)
            elif file_mime == 'application/pdf':
                st.success(f"📄 PDF Selected: {uploaded_file.name}")

            # ── AI Extraction ──────────────────────────────────────────────
            if 'ai_invoice_data' not in st.session_state:
                with st.spinner("🤖 AI is reading your invoice..."):
                    ai = _extract_invoice_data(file_bytes, file_mime)
                    st.session_state['ai_invoice_data'] = ai

            ai = st.session_state.get('ai_invoice_data', {})
            ai_supplier = ai.get("supplier")
            ai_total    = ai.get("total")
            ai_currency = ai.get("currency")

            st.divider()
            st.markdown("**📋 Confirm Invoice Details**")

            # ── Supplier ──────────────────────────────────────────────────
            # Try to find AI suggestion in supplier list (fuzzy)
            _sup_options = supplier_list + ["➕ Other (Type manually)"]
            _sup_default = 0
            if ai_supplier:
                _ai_lower = ai_supplier.lower()
                for i, s in enumerate(supplier_list):
                    if _ai_lower in s.lower() or s.lower() in _ai_lower:
                        _sup_default = i
                        break
                else:
                    st.caption(f"🤖 AI detected: **{ai_supplier}** — not found in list, select manually below.")

            selected_supplier = st.selectbox("🏢 Supplier", _sup_options, index=_sup_default)
            if selected_supplier == "➕ Other (Type manually)":
                final_supplier_name = st.text_input("📝 Type supplier name:", value=ai_supplier or "")
            else:
                final_supplier_name = selected_supplier

            # ── Total Amount ──────────────────────────────────────────────
            col_amt, col_cur = st.columns([2, 1])
            with col_amt:
                final_total = st.number_input(
                    "💰 Total Amount",
                    min_value=0.0, step=0.01, format="%.2f",
                    value=float(ai_total) if ai_total else 0.0
                )
            with col_cur:
                _cur_options = ["USD", "LBP", "EUR"]
                _cur_default = _cur_options.index(ai_currency) if ai_currency in _cur_options else 0
                final_currency = st.selectbox("Currency", _cur_options, index=_cur_default)

            if ai_total or ai_currency:
                st.caption(f"🤖 AI detected: {f'${ai_total:,.2f}' if ai_total else 'no amount'} · {ai_currency or 'unknown currency'}")

        already_submitted = st.session_state.get('invoice_submitted', False)

        if st.button("🚀 Submit Invoice to Accounting", type="primary", use_container_width=True, disabled=already_submitted):
            if not uploaded_file:
                st.error("❌ Please upload or take a photo.")
            elif not final_supplier_name:
                st.error("❌ Please confirm the supplier name.")
            else:
                with st.spinner("Uploading..."):
                    try:
                        import re as _re
                        _fname = getattr(uploaded_file, 'name', 'photo.jpg')
                        file_ext = _fname.split('.')[-1].lower() if '.' in _fname else 'jpg'
                        _safe_client = _re.sub(r'[^A-Za-z0-9_-]', '', upload_client.replace(' ', '_'))
                        unique_filename = f"{_safe_client}_{uuid.uuid4().hex[:8]}.{file_ext}"

                        supabase.storage.from_("invoices").upload(path=unique_filename, file=file_bytes, file_options={"content-type": file_mime})
                        image_url = supabase.storage.from_("invoices").get_public_url(unique_filename)

                        db_record = {
                            "client_name": upload_client, "outlet": upload_outlet, "location": location,
                            "uploaded_by": user, "supplier": final_supplier_name.strip().title(),
                            "image_url": image_url, "status": "Pending", "data_entry_notes": "",
                            "total_amount": float(final_total) if final_total > 0 else None,
                            "currency": final_currency,
                        }
                        supabase.table("invoices_log").insert([db_record]).execute()

                        st.session_state['invoice_submitted'] = True
                        st.session_state['invoice_submitted_file'] = uploaded_file.name
                        st.session_state.pop('ai_invoice_data', None)
                        st.success("✅ Invoice successfully uploaded!")
                        st.toast("Invoice sent!", icon="🚀")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

        # ── MY UPLOAD HISTORY ────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📋 My Invoice History")

        try:
            today         = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=7)

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                hist_start = st.date_input("From", value=default_start, max_value=today, key="hist_start")
            with col_d2:
                hist_end = st.date_input("To", value=today, max_value=today, key="hist_end")

            my_res = supabase.table("invoices_log")                .select("supplier, image_url, status, created_at")                .eq("uploaded_by", user)                .gte("created_at", f"{hist_start}T00:00:00")                .lte("created_at", f"{hist_end}T23:59:59")                .order("created_at", desc=True)                .limit(100)                .execute()

            if not my_res.data:
                st.info(f"No invoices found between {hist_start} and {hist_end}.")
            else:
                # ── Supplier filter ───────────────────────────────────────
                all_suppliers = sorted(set(i["supplier"] for i in my_res.data if i.get("supplier")))
                sup_search = st.text_input(
                    "🔍 Filter by Supplier",
                    placeholder="Type supplier name to filter...",
                    key="hist_sup_search"
                )

                filtered_data = my_res.data
                if sup_search.strip():
                    filtered_data = [
                        i for i in my_res.data
                        if sup_search.strip().lower() in str(i.get("supplier", "")).lower()
                    ]

                total = len(my_res.data)
                showing = len(filtered_data)
                if sup_search.strip():
                    st.caption(f"Showing {showing} of {total} matching '{sup_search.strip()}'")
                else:
                    st.caption(f"Found {total} invoice(s)")

                STATUS_COLORS = {
                    "Pending": ("#854F0B", "#FAEEDA"),
                    "Posted":  ("#3B6D11", "#EAF3DE"),
                    "On Hold": ("#A32D2D", "#FCEBEB"),
                }

                for inv in filtered_data:
                    # Format date + time in Beirut timezone
                    raw_time = str(inv.get("created_at", ""))
                    try:
                        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                        beirut_dt = dt.astimezone(zoneinfo.ZoneInfo("Asia/Beirut"))
                        date_str = beirut_dt.strftime("%d %b %Y")
                        time_str = beirut_dt.strftime("%I:%M %p")
                    except Exception:
                        date_str = raw_time[:10]
                        time_str = raw_time[11:16]

                    status = inv.get("status", "Pending")
                    txt_col, bg_col = STATUS_COLORS.get(status, ("#888", "#eee"))
                    img_url = inv.get("image_url", "")
                    is_pdf  = img_url.lower().endswith(".pdf")

                    with st.container(border=True):
                        col_img, col_info = st.columns([1, 2], vertical_alignment="center")
                        with col_img:
                            if img_url and not is_pdf:
                                st.image(img_url, use_container_width=True)
                            else:
                                st.markdown(
                                    "<div style='text-align:center; padding:20px; font-size:36px;'>📄</div>",
                                    unsafe_allow_html=True
                                )
                        with col_info:
                            st.markdown(f"**{inv.get('supplier', 'Unknown')}**")
                            st.markdown(f"📅 {date_str} &nbsp; 🕐 {time_str}")
                            st.markdown(
                                f"<span style='background:{bg_col}; color:{txt_col}; "
                                f"padding:3px 12px; border-radius:20px; font-size:12px; font-weight:500;'>"
                                f"{status}</span>",
                                unsafe_allow_html=True
                            )
                            if img_url:
                                st.markdown(
                                    f"<a href='{img_url}' target='_blank' style='font-size:12px; color:#8a9eaa;'>"
                                    f"🔍 View full size</a>",
                                    unsafe_allow_html=True
                                )
        except Exception as e:
            st.caption(f"Could not load invoice history: {e}")