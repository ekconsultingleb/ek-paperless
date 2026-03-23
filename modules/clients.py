import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- SUPABASE (uses service key — matches app.py pattern) ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _status_badge(status: str) -> str:
    colors = {
        "prospect": ("#F0A500", "#FFF8E7"),
        "active":   ("#4CAF82", "#EAF7F0"),
        "churned":  ("#8E9AA6", "#F2F4F5"),
    }
    color, bg = colors.get(status, ("#8E9AA6", "#F2F4F5"))
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;'
        f'background:{bg};color:{color};border:1px solid {color}40;">{status}</span>'
    )

def _outlet_tags(outlets: list) -> str:
    if not outlets:
        return '<span style="color:#aaa;font-size:11px;">No outlets</span>'
    return " ".join(
        f'<span style="display:inline-block;background:rgba(227,197,173,0.25);'
        f'color:#1B252C;border-radius:4px;padding:1px 8px;font-size:11px;'
        f'margin:2px 2px 0 0;">{o.strip()}</span>'
        for o in outlets if o.strip()
    )

def _load_clients(supabase) -> list:
    res = supabase.table("clients").select("*").order("client_name").execute()
    return res.data or []


# ── Add / Edit form ────────────────────────────────────────────────────────────

def _client_form(supabase, existing: dict = None):
    """
    Renders add or edit form.
    existing=None  → Add mode
    existing=dict  → Edit mode (pre-filled)
    """
    is_edit = existing is not None
    prefix  = f"edit_{existing['id']}_" if is_edit else "add_"

    with st.form(key=f"{prefix}form", clear_on_submit=not is_edit):
        c1, c2 = st.columns(2)
        with c1:
            client_name = st.text_input(
                "Client Name *",
                value=existing.get("client_name", "") if is_edit else "",
                placeholder="e.g. Galilee"
            )
            company_name = st.text_input(
                "Company Name",
                value=existing.get("company_name") or "" if is_edit else "",
                placeholder="e.g. Galilee SAL"
            )
        with c2:
            outlets_raw = st.text_input(
                "Outlets (comma-separated)",
                value=", ".join(existing.get("outlets") or []) if is_edit else "",
                placeholder="e.g. Kaslik, Mar Mikhael"
            )
            address = st.text_input(
                "Address",
                value=existing.get("address") or "" if is_edit else "",
                placeholder="e.g. Kaslik Highway, Jounieh"
            )

        status = st.selectbox(
            "Status",
            options=["prospect", "active", "churned"],
            index=["prospect", "active", "churned"].index(
                existing.get("status", "prospect") if is_edit else "prospect"
            )
        )

        label = "💾 Update Client" if is_edit else "➕ Add Client"
        submitted = st.form_submit_button(label, use_container_width=True)

        if submitted:
            if not client_name.strip():
                st.error("Client Name is required.")
                return

            outlets_list = [o.strip() for o in outlets_raw.split(",") if o.strip()]
            payload = {
                "client_name":  client_name.strip().title(),
                "company_name": company_name.strip() or None,
                "outlets":      outlets_list,
                "address":      address.strip() or None,
                "status":       status,
            }

            try:
                if is_edit:
                    supabase.table("clients").update(payload).eq("id", existing["id"]).execute()
                    st.success(f"✅ '{client_name.strip().title()}' updated.")
                else:
                    supabase.table("clients").insert(payload).execute()
                    st.success(f"✅ '{client_name.strip().title()}' added.")
                # Close the form
                st.session_state[f"{prefix}open"] = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")


# ── Main render ────────────────────────────────────────────────────────────────

def render_clients(supabase=None):
    """
    Call this from main.py inside the Clients tab:
        from modules.clients import render_clients
        with t_clients:
            render_clients()
    """
    if supabase is None:
        supabase = get_supabase()

    st.markdown("#### 🏢 Client Management")
    st.caption("Manage all EK Consulting clients — prospects, active, and churned.")

    # ── Add button ─────────────────────────────────────────────────────────
    col_title, col_btn = st.columns([5, 1])
    with col_btn:
        if st.button("＋ Add Client", use_container_width=True, key="clients_open_add"):
            st.session_state["clients_add_open"] = not st.session_state.get("clients_add_open", False)

    # ── Add form (collapsible) ──────────────────────────────────────────────
    if st.session_state.get("clients_add_open", False):
        with st.container(border=True):
            st.markdown("**New Client**")
            _client_form(supabase, existing=None)
        st.divider()

    # ── Filters ────────────────────────────────────────────────────────────
    f1, f2 = st.columns([3, 1])
    with f1:
        search = st.text_input(
            "search", placeholder="Search by name, company, or outlet...",
            label_visibility="collapsed", key="clients_search"
        )
    with f2:
        filter_status = st.selectbox(
            "status", ["All", "prospect", "active", "churned"],
            label_visibility="collapsed", key="clients_filter_status"
        )

    st.divider()

    # ── Load & filter ───────────────────────────────────────────────────────
    all_clients = _load_clients(supabase)

    # Summary metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Active",    sum(1 for c in all_clients if c.get("status") == "active"))
    m2.metric("Prospects", sum(1 for c in all_clients if c.get("status") == "prospect"))
    m3.metric("Churned",   sum(1 for c in all_clients if c.get("status") == "churned"))

    st.divider()

    # Apply filters
    clients = all_clients
    if filter_status != "All":
        clients = [c for c in clients if c.get("status") == filter_status]
    if search:
        q = search.lower()
        clients = [
            c for c in clients
            if q in (c.get("client_name") or "").lower()
            or q in (c.get("company_name") or "").lower()
            or any(q in o.lower() for o in (c.get("outlets") or []))
        ]

    if not clients:
        st.info("No clients found." if (search or filter_status != "All") else "No clients yet. Click ＋ Add Client to get started.")
        return

    # ── Client list ─────────────────────────────────────────────────────────
    for client in clients:
        cid      = client["id"]
        cname    = client.get("client_name", "—")
        company  = client.get("company_name") or ""
        address  = client.get("address") or ""
        outlets  = client.get("outlets") or []
        status   = client.get("status", "prospect")
        edit_key = f"clients_edit_{cid}_open"

        # Card
        meta_parts = [p for p in [company, address] if p]
        meta_str   = " · ".join(meta_parts)

        st.markdown(f"""
        <div style="
            background:#ffffff; border:1px solid #e8e8e8;
            border-left:4px solid #E3C5AD; border-radius:8px;
            padding:14px 18px; margin-bottom:4px;
        ">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-size:15px;font-weight:700;color:#1B252C;">{cname}</span>
                    {'<span style="font-size:12px;color:#666;"> · ' + meta_str + '</span>' if meta_str else ''}
                </div>
                <div>{_status_badge(status)}</div>
            </div>
            <div style="margin-top:6px;">{_outlet_tags(outlets)}</div>
        </div>
        """, unsafe_allow_html=True)

        # Edit toggle
        if st.button("✏️ Edit", key=f"clients_edit_btn_{cid}"):
            st.session_state[edit_key] = not st.session_state.get(edit_key, False)

        if st.session_state.get(edit_key, False):
            with st.container(border=True):
                _client_form(supabase, existing=client)

        st.write("")  # spacing
