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


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

STATUS_COLORS = {
    "Pending":    ("#854F0B", "#FAEEDA"),
    "Posted":     ("#3B6D11", "#EAF3DE"),
    "On Hold":    ("#A32D2D", "#FCEBEB"),
    "Accounting": ("#1B5E8A", "#E3F0FA"),
}

ALL_STATUSES = ["Pending", "On Hold", "Posted", "Accounting"]

def _status_badge_html(status: str) -> str:
    txt, bg = STATUS_COLORS.get(status, ("#888", "#eee"))
    return (
        f"<span style='background:{bg}; color:{txt}; font-size:11px; "
        f"font-weight:500; padding:3px 10px; border-radius:20px;'>{status}</span>"
    )

def _format_beirut_dt(raw: str) -> tuple:
    """Returns (date_str, time_str) in Asia/Beirut timezone."""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        bdt = dt.astimezone(zoneinfo.ZoneInfo("Asia/Beirut"))
        return bdt.strftime("%d %b %Y"), bdt.strftime("%I:%M %p")
    except Exception:
        return str(raw)[:10], str(raw)[11:16]

def _render_invoice_card(supabase, row: dict, user: str, user_role: str, key_prefix: str):
    """Reusable invoice card with thumbnail, info, and process expander."""
    inv_id  = row['id']
    c_name  = row['client_name']
    img_url = row.get('image_url', '')
    is_pdf  = str(img_url).lower().endswith('.pdf')

    date_str, time_str = _format_beirut_dt(row.get('created_at', ''))
    status = row.get('status', 'Pending')

    with st.container(border=True):
        col_thumb, col_info = st.columns([1, 4], vertical_alignment="center")

        with col_thumb:
            if img_url and not is_pdf:
                st.image(img_url, use_container_width=True)
            else:
                st.markdown("<div style='text-align:center;padding:10px;font-size:28px;'>📄</div>", unsafe_allow_html=True)

        with col_info:
            amount_str = ""
            if row.get('total_amount'):
                amt = row['total_amount']
                cur = row.get('currency', '')
                amount_str = f" · **{cur} {amt:,.2f}**"
            st.markdown(
                f"<p style='margin:0 0 2px;font-size:15px;font-weight:500;'>{row['supplier']}{amount_str}</p>"
                f"<p style='margin:0 0 6px;font-size:12px;color:var(--color-text-secondary);'>"
                f"{date_str} · {time_str} · {c_name} ({row['outlet']})</p>"
                + _status_badge_html(status),
                unsafe_allow_html=True
            )

        with st.expander("⚙️ Process Invoice"):
            col_img, col_form = st.columns([1.2, 1])

            with col_img:
                if is_pdf:
                    st.markdown("<div style='text-align:center;padding:20px;font-size:48px;'>📄</div>", unsafe_allow_html=True)
                else:
                    st.image(img_url, use_container_width=True)
                st.markdown(f"[🔍 Open full size]({img_url})")

            with col_form:
                st.write(f"**👤 Uploaded By:** {row['uploaded_by']}")

                with st.form(f"{key_prefix}_form_{inv_id}"):
                    new_status = st.radio(
                        "Status", ALL_STATUSES,
                        index=ALL_STATUSES.index(status) if status in ALL_STATUSES else 0,
                        horizontal=True
                    )
                    new_notes = st.text_area("Data Entry Notes", value=row.get('data_entry_notes', '') or "")

                    if st.form_submit_button("💾 Save & Update", type="primary", use_container_width=True):
                        if user_role == "viewer":
                            st.error("🚫 Viewers cannot modify records.")
                        else:
                            update_data = {
                                "status": new_status,
                                "data_entry_notes": new_notes,
                                "posted_by": user if new_status in ("Posted", "Accounting") else row.get('posted_by')
                            }
                            supabase.table("invoices_log").update(update_data).eq("id", inv_id).eq("client_name", c_name).execute()
                            st.success("✅ Updated!")
                            st.rerun()

                if user_role in ("admin", "admin_all"):
                    st.divider()
                    confirm_key = f"confirm_del_{key_prefix}_{inv_id}"
                    if st.session_state.get(confirm_key):
                        st.warning("Are you sure? This cannot be undone.")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("🗑️ Yes, delete", key=f"yes_{key_prefix}_{inv_id}", use_container_width=True, type="primary"):
                                supabase.table("invoices_log").delete().eq("id", inv_id).execute()
                                st.session_state.pop(confirm_key, None)
                                st.success("Deleted.")
                                st.rerun()
                        with col_no:
                            if st.button("Cancel", key=f"no_{key_prefix}_{inv_id}", use_container_width=True):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()
                    else:
                        if st.button("🗑️ Delete Invoice", key=f"del_{key_prefix}_{inv_id}", use_container_width=True):
                            st.session_state[confirm_key] = True
                            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────────────────────────────────────────

def render_invoices(conn, sheet_link, user, role):
    import re as _re
    supabase = get_supabase()

    client_name = st.session_state.get('client_name', 'Unknown')
    outlet      = st.session_state.get('assigned_outlet', 'Unknown')
    location    = st.session_state.get('assigned_location', 'Unknown')
    user_role   = str(role).lower()

    can_process = user_role in ["manager", "admin", "admin_all", "viewer"]

    if can_process:
        st.markdown("### 🏢 Accounts Payable Dashboard")
        tab_dash, tab_process, tab_archive, tab_upload = st.tabs([
            "📊 Dashboard", "📋 Process Invoices", "🗄️ Archived", "📸 Upload Invoice"
        ])
    else:
        st.markdown("### 📸 Snap & Upload Invoice")
        tab_upload  = st.container()
        tab_dash    = None
        tab_process = None
        tab_archive = None

    # =========================================================================
    # TAB 1 — BASSEL DASHBOARD
    # =========================================================================
    if tab_dash:
        with tab_dash:
            st.markdown("#### 📊 Invoice Queue by Client")

            _today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            _first = _today.replace(day=1)

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                dash_start = st.date_input("📅 From", value=_first, max_value=_today, key="dash_start")
            with col_d2:
                dash_end = st.date_input("📅 To", value=_today, max_value=_today, key="dash_end")

            try:
                q = (supabase.table("invoices_log").select("id,client_name,status")
                     .gte("created_at", f"{dash_start}T00:00:00")
                     .lte("created_at", f"{dash_end}T23:59:59"))
                if client_name != "All":
                    q = q.eq("client_name", client_name)
                res = q.execute()

                if not res.data:
                    st.info("No invoices found for this period.")
                else:
                    df_d = pd.DataFrame(res.data)

                    # Aggregate per client
                    summary = []
                    for cname, grp in df_d.groupby("client_name"):
                        total       = len(grp)
                        pending     = (grp['status'] == 'Pending').sum()
                        on_hold     = (grp['status'] == 'On Hold').sum()
                        posted      = (grp['status'] == 'Posted').sum()
                        accounting  = (grp['status'] == 'Accounting').sum()
                        done        = posted + accounting
                        pct         = int(done / total * 100) if total else 0
                        summary.append({
                            "client_name": cname,
                            "total": total,
                            "pending": pending,
                            "on_hold": on_hold,
                            "posted": posted,
                            "accounting": accounting,
                            "pct_done": pct,
                        })

                    summary = sorted(summary, key=lambda x: x['pending'], reverse=True)

                    # Header row
                    hc = st.columns([3, 1, 1, 1, 1, 1, 1, 1])
                    for col, label in zip(hc, ["Client", "Total", "Pending", "On Hold", "Posted", "Acctg", "% Done", ""]):
                        col.markdown(f"<span style='font-size:12px;font-weight:600;color:#8a9eaa;text-transform:uppercase;letter-spacing:0.05em;'>{label}</span>", unsafe_allow_html=True)
                    st.divider()

                    for row in summary:
                        cname = row['client_name']
                        open_key = f"dash_open_{cname}"

                        rc = st.columns([3, 1, 1, 1, 1, 1, 1, 1])
                        rc[0].markdown(f"**{cname}**")
                        rc[1].markdown(str(row['total']))

                        # Pending in orange if > 0
                        pend_color = "#854F0B" if row['pending'] > 0 else "#3B6D11"
                        rc[2].markdown(f"<span style='color:{pend_color};font-weight:600;'>{row['pending']}</span>", unsafe_allow_html=True)

                        rc[3].markdown(f"<span style='color:{'#A32D2D' if row['on_hold'] > 0 else 'inherit'};'>{row['on_hold']}</span>", unsafe_allow_html=True)
                        rc[4].markdown(str(row['posted']))
                        rc[5].markdown(str(row['accounting']))

                        # Progress bar
                        pct = row['pct_done']
                        bar_color = "#3B6D11" if pct == 100 else "#854F0B" if pct < 50 else "#E3C5AD"
                        rc[6].markdown(
                            f"<div style='background:#2E3D47;border-radius:6px;height:18px;margin-top:4px;'>"
                            f"<div style='width:{pct}%;background:{bar_color};border-radius:6px;height:18px;"
                            f"display:flex;align-items:center;justify-content:center;"
                            f"font-size:10px;color:#fff;font-weight:600;'>"
                            f"{'100%' if pct == 100 else f'{pct}%' if pct > 15 else ''}</div></div>",
                            unsafe_allow_html=True
                        )

                        # Open / Close toggle
                        is_open = st.session_state.get(open_key, False)
                        btn_label = "📂 Close" if is_open else "📂 Open"
                        if rc[7].button(btn_label, key=f"btn_open_{cname}", use_container_width=True):
                            st.session_state[open_key] = not is_open
                            st.rerun()

                        # Inline invoice feed for this client
                        if st.session_state.get(open_key, False):
                            with st.container(border=True):
                                st.markdown(f"##### 📥 {cname} — Pending & On Hold")
                                try:
                                    inv_res = (supabase.table("invoices_log").select("*")
                                               .eq("client_name", cname)
                                               .in_("status", ["Pending", "On Hold"])
                                               .gte("created_at", f"{dash_start}T00:00:00")
                                               .lte("created_at", f"{dash_end}T23:59:59")
                                               .order("created_at", desc=False)
                                               .execute())
                                    if not inv_res.data:
                                        st.success("🎉 All invoices for this client are cleared!")
                                    else:
                                        st.caption(f"{len(inv_res.data)} invoice(s) need attention")
                                        for inv_row in inv_res.data:
                                            _render_invoice_card(supabase, inv_row, user, user_role, f"dash_{cname}")
                                except Exception as e:
                                    st.error(f"Could not load invoices: {e}")

                        st.divider()

            except Exception as e:
                st.error(f"❌ Dashboard error: {e}")

    # =========================================================================
    # TAB 2 — PROCESS INVOICES
    # =========================================================================
    if tab_process:
        with tab_process:
            st.info("💡 **Scroll & Process Mode:** Click '⚙️ Process Invoice' below any record to expand it.")

            try:
                _today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
                _default_start = _today - timedelta(days=30)
                col_pd1, col_pd2 = st.columns(2)
                with col_pd1:
                    proc_start = st.date_input("📅 From", value=_default_start, max_value=_today, key="proc_start")
                with col_pd2:
                    proc_end = st.date_input("📅 To", value=_today, max_value=_today, key="proc_end")

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
                    df = pd.DataFrame(res.data).sort_values(by="created_at", ascending=True)

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
                        for _, row in df.iterrows():
                            _render_invoice_card(supabase, row.to_dict(), user, user_role, "proc")

            except Exception as e:
                st.error(f"❌ Error loading dashboard: {e}")

    # =========================================================================
    # TAB 3 — ARCHIVED (Posted + Accounting)
    # =========================================================================
    if tab_archive:
        with tab_archive:
            st.info("🗄️ **Archived Ledger:** View posted and accounting invoices.")

            today         = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=30)

            date_range = st.date_input("📅 Select Date Range", value=(default_start, today), max_value=today, key="arch_dates")

            if len(date_range) == 2:
                start_date, end_date = date_range

                try:
                    query = (supabase.table("invoices_log").select("*")
                             .in_("status", ["Posted", "Accounting"])
                             .gte("created_at", f"{start_date}T00:00:00")
                             .lte("created_at", f"{end_date}T23:59:59"))

                    if client_name != "All":
                        query = query.eq("client_name", client_name)
                    if outlet != "All":
                        query = query.eq("outlet", outlet)

                    res = query.execute()

                    if not res.data:
                        st.warning(f"No archived invoices found between {start_date} and {end_date}.")
                    else:
                        df_arch = pd.DataFrame(res.data).sort_values(by="created_at", ascending=False)

                        col_f1, col_f2, col_f3 = st.columns(3)

                        with col_f1:
                            if client_name == "All":
                                active_clients = ["All Clients"] + sorted(df_arch['client_name'].unique().tolist())
                                chosen_client = st.selectbox("🎯 Filter by Client:", active_clients, key="archive_client_filter")
                                if chosen_client != "All Clients":
                                    df_arch = df_arch[df_arch['client_name'] == chosen_client]
                            else:
                                st.markdown(f"**🏢 Client:** {client_name}")

                        with col_f2:
                            active_suppliers = ["All Suppliers"] + sorted(df_arch['supplier'].unique().tolist())
                            chosen_supplier = st.selectbox("🧾 Filter by Supplier:", active_suppliers, key="archive_sup_filter")
                            if chosen_supplier != "All Suppliers":
                                df_arch = df_arch[df_arch['supplier'] == chosen_supplier]

                        with col_f3:
                            status_filter = st.selectbox(
                                "📌 Filter by Status:",
                                ["All", "Posted", "Accounting"],
                                key="archive_status_filter"
                            )
                            if status_filter != "All":
                                df_arch = df_arch[df_arch['status'] == status_filter]

                        st.divider()

                        if df_arch.empty:
                            st.info("No invoices match your selected filters.")
                        else:
                            st.success(f"📚 Found {len(df_arch)} invoice(s).")

                            for _, row in df_arch.iterrows():
                                row = row.to_dict()
                                arch_inv_id = row['id']
                                c_name      = row['client_name']
                                img_url     = row.get('image_url', '')
                                is_pdf      = str(img_url).lower().endswith('.pdf')
                                date_str, _ = _format_beirut_dt(row.get('created_at', ''))
                                status      = row.get('status', 'Posted')

                                with st.container(border=True):
                                    col_date, col_sup, col_loc, col_badge = st.columns([1.5, 2.5, 2, 1], vertical_alignment="center")
                                    col_date.write(f"📅 {date_str}")
                                    col_sup.write(f"🧾 **{row['supplier']}**")
                                    col_loc.write(f"🏢 {c_name} ({row['outlet']})")
                                    col_badge.markdown(_status_badge_html(status), unsafe_allow_html=True)

                                    with st.expander("👁️ View Invoice Details"):
                                        col_img, col_det = st.columns([1.2, 1])
                                        with col_img:
                                            if is_pdf:
                                                st.markdown("<div style='text-align:center;padding:20px;font-size:48px;'>📄</div>", unsafe_allow_html=True)
                                            else:
                                                st.image(img_url, use_container_width=True)
                                            st.markdown(f"[🔍 Open full size]({img_url})")
                                        with col_det:
                                            st.write(f"**👤 Uploaded By:** {row.get('uploaded_by', 'Unknown')}")
                                            st.write(f"**✅ Handled By:** {row.get('posted_by', 'Head Office')}")
                                            notes = row.get('data_entry_notes', '')
                                            st.write(f"**📝 Notes:** {notes if notes else '*No notes.*'}")

                                            if user_role in ("admin", "admin_all"):
                                                st.divider()
                                                confirm_key = f"confirm_del_arch_{arch_inv_id}"
                                                if st.session_state.get(confirm_key):
                                                    st.warning("Are you sure? This cannot be undone.")
                                                    col_yes, col_no = st.columns(2)
                                                    with col_yes:
                                                        if st.button("🗑️ Yes, delete", key=f"yes_arch_{arch_inv_id}", use_container_width=True, type="primary"):
                                                            supabase.table("invoices_log").delete().eq("id", arch_inv_id).execute()
                                                            st.session_state.pop(confirm_key, None)
                                                            st.success("Deleted.")
                                                            st.rerun()
                                                    with col_no:
                                                        if st.button("Cancel", key=f"no_arch_{arch_inv_id}", use_container_width=True):
                                                            st.session_state.pop(confirm_key, None)
                                                            st.rerun()
                                                else:
                                                    if st.button("🗑️ Delete Invoice", key=f"del_arch_{arch_inv_id}", use_container_width=True):
                                                        st.session_state[confirm_key] = True
                                                        st.rerun()

                except Exception as e:
                    st.error(f"❌ Error loading archive: {e}")
            else:
                st.info("Please select both a Start Date and an End Date.")

    # =========================================================================
    # TAB 4 — UPLOAD INVOICE
    # =========================================================================
    with tab_upload:
        # ── My Month Summary (metric cards) ───────────────────────────────────
        try:
            _tz    = zoneinfo.ZoneInfo("Asia/Beirut")
            _now   = datetime.now(_tz)
            _m_start = _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            _m_end   = _now

            _my_res = (supabase.table("invoices_log")
                       .select("status")
                       .eq("uploaded_by", user)
                       .gte("created_at", _m_start.isoformat())
                       .lte("created_at", _m_end.isoformat())
                       .execute())

            if _my_res.data:
                _statuses = [r['status'] for r in _my_res.data]
                _total    = len(_statuses)
                _posted   = _statuses.count("Posted")
                _pending  = _statuses.count("Pending")
                _on_hold  = _statuses.count("On Hold")
                _acctg    = _statuses.count("Accounting")

                st.markdown("##### 📅 My Uploads This Month")
                mc1, mc2, mc3, mc4, mc5 = st.columns(5)
                mc1.metric("📸 Uploaded", _total)
                mc2.metric("✅ Posted", _posted)
                mc3.metric("⏳ Pending", _pending)
                mc4.metric("🔴 On Hold", _on_hold)
                mc5.metric("🏦 Accounting", _acctg)
                st.divider()
        except Exception:
            pass

        st.info("💡 **Mobile Users:** Tap 'Browse files' to open your camera.")

        # ── Client / outlet selection for EK team ─────────────────────────────
        if client_name == "All":
            try:
                _cl_res  = supabase.table("clients").select("client_name").order("client_name").execute()
                _cl_list = [r["client_name"] for r in (_cl_res.data or [])]
            except Exception:
                _cl_list = []
            upload_client = st.selectbox("🏢 Select Client", _cl_list, key="upload_client_sel") if _cl_list else st.text_input("🏢 Client Name")
            try:
                _out_res  = supabase.table("branches").select("outlet").eq("client_name", upload_client).execute()
                _out_list = [r["outlet"] for r in (_out_res.data or [])]
            except Exception:
                _out_list = []
            upload_outlet = st.selectbox("🏠 Select Outlet", _out_list, key="upload_outlet_sel") if _out_list else outlet
        else:
            upload_client = client_name
            upload_outlet = outlet

        # ── Supplier list ──────────────────────────────────────────────────────
        try:
            sup_res       = supabase.table("suppliers").select("supplier_name").execute()
            supplier_list = sorted([r['supplier_name'] for r in sup_res.data]) if sup_res.data else []
        except Exception:
            supplier_list = []

        browse_file = st.file_uploader("📸 Take a Photo or Upload PDF", type=['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif', 'pdf'])

        if browse_file:
            uploaded_file = browse_file
            file_bytes    = browse_file.getvalue()
            file_mime     = browse_file.type if browse_file.type else "image/jpeg"
        else:
            uploaded_file = None
            file_bytes    = None
            file_mime     = None

        current_file_id = uploaded_file.name if uploaded_file else None
        if st.session_state.get('invoice_submitted_file') != current_file_id:
            st.session_state['invoice_submitted']      = False
            st.session_state['invoice_submitted_file'] = current_file_id
            st.session_state.pop('ai_invoice_data', None)

        if uploaded_file:
            if file_mime and file_mime.startswith('image'):
                st.image(file_bytes, caption="Invoice Preview", use_container_width=True)
            elif file_mime == 'application/pdf':
                st.success(f"📄 PDF Selected: {uploaded_file.name}")

            if 'ai_invoice_data' not in st.session_state:
                with st.spinner("🤖 AI is reading your invoice..."):
                    ai = _extract_invoice_data(file_bytes, file_mime)
                    st.session_state['ai_invoice_data'] = ai

            ai          = st.session_state.get('ai_invoice_data', {})
            ai_supplier = ai.get("supplier")
            ai_total    = ai.get("total")
            ai_currency = ai.get("currency")

            st.divider()
            st.markdown("**📋 Confirm Invoice Details**")

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

            col_amt, col_cur = st.columns([2, 1])
            with col_amt:
                final_total = st.number_input(
                    "💰 Total Amount", min_value=0.0, step=0.01, format="%.2f",
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
                        _fname    = getattr(uploaded_file, 'name', 'photo.jpg')
                        file_ext  = _fname.split('.')[-1].lower() if '.' in _fname else 'jpg'
                        _safe_client    = _re.sub(r'[^A-Za-z0-9_-]', '', upload_client.replace(' ', '_'))
                        unique_filename = f"{_safe_client}_{uuid.uuid4().hex[:8]}.{file_ext}"

                        if file_mime and file_mime.startswith("image"):
                            try:
                                from PIL import Image as _PImage
                                import io as _io2
                                _img = _PImage.open(_io2.BytesIO(file_bytes))
                                _img = _img.convert("RGB")
                                _img.thumbnail((1200, 1600))
                                _out = _io2.BytesIO()
                                _img.save(_out, format="JPEG", quality=80)
                                file_bytes      = _out.getvalue()
                                file_mime       = "image/jpeg"
                                unique_filename = f"{_safe_client}_{uuid.uuid4().hex[:8]}.jpg"
                            except Exception as _e:
                                st.warning("Compress failed: " + str(_e))

                        supabase.storage.from_("invoices").upload(
                            path=unique_filename, file=file_bytes,
                            file_options={"content-type": file_mime}
                        )
                        image_url = supabase.storage.from_("invoices").get_public_url(unique_filename)

                        db_record = {
                            "client_name": upload_client, "outlet": upload_outlet, "location": location,
                            "uploaded_by": user, "supplier": final_supplier_name.strip().title(),
                            "image_url": image_url, "status": "Pending", "data_entry_notes": "",
                            "total_amount": float(final_total) if final_total > 0 else None,
                            "currency": final_currency,
                        }
                        supabase.table("invoices_log").insert([db_record]).execute()

                        st.session_state['invoice_submitted']      = True
                        st.session_state['invoice_submitted_file'] = uploaded_file.name
                        st.session_state.pop('ai_invoice_data', None)
                        st.success("✅ Invoice successfully uploaded!")
                        st.toast("Invoice sent!", icon="🚀")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

        # ── My Upload History ──────────────────────────────────────────────────
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

            my_res = (supabase.table("invoices_log")
                      .select("supplier, image_url, status, created_at")
                      .eq("uploaded_by", user)
                      .gte("created_at", f"{hist_start}T00:00:00")
                      .lte("created_at", f"{hist_end}T23:59:59")
                      .order("created_at", desc=True)
                      .limit(100)
                      .execute())

            if not my_res.data:
                st.info(f"No invoices found between {hist_start} and {hist_end}.")
            else:
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

                total   = len(my_res.data)
                showing = len(filtered_data)
                st.caption(
                    f"Showing {showing} of {total} matching '{sup_search.strip()}'"
                    if sup_search.strip() else f"Found {total} invoice(s)"
                )

                for inv in filtered_data:
                    date_str, time_str = _format_beirut_dt(inv.get("created_at", ""))
                    status  = inv.get("status", "Pending")
                    txt_col, bg_col = STATUS_COLORS.get(status, ("#888", "#eee"))
                    img_url = inv.get("image_url", "")
                    is_pdf  = img_url.lower().endswith(".pdf")

                    with st.container(border=True):
                        col_img, col_info = st.columns([1, 2], vertical_alignment="center")
                        with col_img:
                            if img_url and not is_pdf:
                                st.image(img_url, use_container_width=True)
                            else:
                                st.markdown("<div style='text-align:center;padding:20px;font-size:36px;'>📄</div>", unsafe_allow_html=True)
                        with col_info:
                            st.markdown(f"**{inv.get('supplier', 'Unknown')}**")
                            st.markdown(f"📅 {date_str} &nbsp; 🕐 {time_str}")
                            st.markdown(
                                f"<span style='background:{bg_col};color:{txt_col};"
                                f"padding:3px 12px;border-radius:20px;font-size:12px;font-weight:500;'>"
                                f"{status}</span>",
                                unsafe_allow_html=True
                            )
                            if img_url:
                                st.markdown(f"<a href='{img_url}' target='_blank' style='font-size:12px;color:#8a9eaa;'>🔍 View full size</a>", unsafe_allow_html=True)

        except Exception as e:
            st.caption(f"Could not load invoice history: {e}")