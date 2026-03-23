import streamlit as st
import pandas as pd
from supabase import create_client, Client

# ── Supabase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

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

def _tag(text: str, color: str = "#E3C5AD") -> str:
    return (
        f'<span style="display:inline-block;background:{color}30;color:#1B252C;'
        f'border-radius:4px;padding:1px 8px;font-size:11px;margin:2px 2px 0 0;">'
        f'{text}</span>'
    )

def _load_clients(supabase) -> list:
    return supabase.table("clients").select("*").order("client_name").execute().data or []

def _load_branches(supabase, client_name: str = None) -> list:
    q = supabase.table("branches").select("*").order("outlet")
    if client_name:
        q = q.eq("client_name", client_name)
    return q.execute().data or []

def _load_areas(supabase, outlet: str = None) -> list:
    q = supabase.table("areas").select("*").order("area_name")
    if outlet:
        q = q.eq("outlet", outlet)
    return q.execute().data or []


# ══════════════════════════════════════════════════════════════════════════════
# FORMS
# ══════════════════════════════════════════════════════════════════════════════

def _client_form(supabase, existing: dict = None):
    is_edit = existing is not None
    prefix  = f"cl_edit_{existing['id']}_" if is_edit else "cl_add_"

    with st.form(key=f"{prefix}form", clear_on_submit=not is_edit):
        c1, c2 = st.columns(2)
        with c1:
            client_name = st.text_input("Client Name *",
                value=existing.get("client_name", "") if is_edit else "",
                placeholder="e.g. Lor")
        with c2:
            company_name = st.text_input("Company Name",
                value=existing.get("company_name") or "" if is_edit else "",
                placeholder="e.g. Lor SAL")

        status = st.selectbox("Status",
            ["prospect", "active", "churned"],
            index=["prospect", "active", "churned"].index(
                existing.get("status", "active") if is_edit else "active"))

        submitted = st.form_submit_button(
            "💾 Update Client" if is_edit else "➕ Add Client",
            use_container_width=True)

        if submitted:
            if not client_name.strip():
                st.error("Client Name is required.")
                return
            payload = {
                "client_name":  client_name.strip().title(),
                "company_name": company_name.strip() or None,
                "status":       status,
            }
            try:
                if is_edit:
                    supabase.table("clients").update(payload).eq("id", existing["id"]).execute()
                    st.success(f"✅ '{payload['client_name']}' updated.")
                else:
                    supabase.table("clients").insert(payload).execute()
                    st.success(f"✅ '{payload['client_name']}' added.")
                st.session_state[f"{prefix}open"] = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")


def _branch_form(supabase, clients: list, existing: dict = None):
    is_edit      = existing is not None
    prefix       = f"br_edit_{existing['id']}_" if is_edit else "br_add_"
    client_names = [c["client_name"] for c in clients]

    with st.form(key=f"{prefix}form", clear_on_submit=not is_edit):
        c1, c2 = st.columns(2)
        with c1:
            default_client = existing.get("client_name", client_names[0] if client_names else "") if is_edit else (client_names[0] if client_names else "")
            sel_client = st.selectbox("Client *", client_names,
                index=client_names.index(default_client) if default_client in client_names else 0)
            outlet = st.text_input("Outlet Code *",
                value=existing.get("outlet", "") if is_edit else "",
                placeholder="e.g. Lor  /  Broumana  /  A",
                help="Must exactly match master_items.outlet and users.outlet")
        with c2:
            address = st.text_input("Address",
                value=existing.get("address") or "" if is_edit else "",
                placeholder="e.g. Badaro Street, Beirut")

        submitted = st.form_submit_button(
            "💾 Update Branch" if is_edit else "➕ Add Branch",
            use_container_width=True)

        if submitted:
            if not outlet.strip():
                st.error("Outlet Code is required.")
                return
            client_row = next((c for c in clients if c["client_name"] == sel_client), None)
            payload = {
                "client_id":   client_row["id"] if client_row else None,
                "client_name": sel_client,
                "outlet":      outlet.strip().title(),
                "address":     address.strip() or None,
            }
            try:
                if is_edit:
                    supabase.table("branches").update(payload).eq("id", existing["id"]).execute()
                    st.success(f"✅ Branch '{payload['outlet']}' updated.")
                else:
                    supabase.table("branches").insert(payload).execute()
                    st.success(f"✅ Branch '{payload['outlet']}' added.")
                st.session_state[f"{prefix}open"] = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")


def _area_form(supabase, branches: list, existing: dict = None):
    is_edit     = existing is not None
    prefix      = f"ar_edit_{existing['id']}_" if is_edit else "ar_add_"
    outlet_list = [b["outlet"] for b in branches]

    with st.form(key=f"{prefix}form", clear_on_submit=not is_edit):
        c1, c2 = st.columns(2)
        with c1:
            default_outlet = existing.get("outlet", outlet_list[0] if outlet_list else "") if is_edit else (outlet_list[0] if outlet_list else "")
            sel_outlet = st.selectbox("Branch (Outlet) *", outlet_list,
                index=outlet_list.index(default_outlet) if default_outlet in outlet_list else 0)
        with c2:
            area_name = st.text_input("Area Name *",
                value=existing.get("area_name", "") if is_edit else "",
                placeholder="e.g. Kitchen  /  Bar  /  Warehouse",
                help="Must exactly match master_items.location and users.location")

        submitted = st.form_submit_button(
            "💾 Update Area" if is_edit else "➕ Add Area",
            use_container_width=True)

        if submitted:
            if not area_name.strip():
                st.error("Area Name is required.")
                return
            branch_row = next((b for b in branches if b["outlet"] == sel_outlet), None)
            payload = {
                "branch_id": branch_row["id"] if branch_row else None,
                "outlet":    sel_outlet,
                "area_name": area_name.strip().title(),
            }
            try:
                if is_edit:
                    supabase.table("areas").update(payload).eq("id", existing["id"]).execute()
                    st.success(f"✅ Area '{payload['area_name']}' updated.")
                else:
                    supabase.table("areas").insert(payload).execute()
                    st.success(f"✅ Area '{payload['area_name']}' added under {sel_outlet}.")
                st.session_state[f"{prefix}open"] = False
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render_clients(supabase=None):
    """
    Call from main.py inside the Clients tab:
        from modules.clients import render_clients
        with t_clients:
            render_clients(supabase)
    """
    if supabase is None:
        supabase = get_supabase()

    # Load all data once
    all_clients  = _load_clients(supabase)
    all_branches = _load_branches(supabase)
    all_areas    = _load_areas(supabase)

    # ── Summary metrics ────────────────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("Active Clients", sum(1 for c in all_clients if c.get("status") == "active"))
    m2.metric("Total Branches", len(all_branches))
    m3.metric("Total Areas",    len(all_areas))

    st.divider()

    # ── 3 sub-tabs ─────────────────────────────────────────────────────────
    t1, t2, t3 = st.tabs(["🏢 Clients", "🏠 Branches", "📍 Areas"])

    # ──────────────────────────────────────────────────────────────────────
    # TAB 1: CLIENTS
    # ──────────────────────────────────────────────────────────────────────
    with t1:
        col_h, col_btn = st.columns([5, 1])
        with col_h:
            st.markdown("##### Client List")
        with col_btn:
            if st.button("＋ Add", key="cl_open_add", use_container_width=True):
                st.session_state["cl_add_open"] = not st.session_state.get("cl_add_open", False)

        if st.session_state.get("cl_add_open", False):
            with st.container(border=True):
                st.markdown("**New Client**")
                _client_form(supabase, existing=None)
            st.divider()

        f1, f2 = st.columns([3, 1])
        with f1:
            cl_search = st.text_input("search", placeholder="Search clients...",
                label_visibility="collapsed", key="cl_search")
        with f2:
            cl_filter = st.selectbox("status", ["All", "prospect", "active", "churned"],
                label_visibility="collapsed", key="cl_status_filter")

        clients = all_clients
        if cl_filter != "All":
            clients = [c for c in clients if c.get("status") == cl_filter]
        if cl_search:
            q = cl_search.lower()
            clients = [c for c in clients
                       if q in (c.get("client_name") or "").lower()
                       or q in (c.get("company_name") or "").lower()]

        if not clients:
            st.info("No clients found.")
        else:
            for client in clients:
                cid      = client["id"]
                cname    = client.get("client_name", "—")
                company  = client.get("company_name") or ""
                status   = client.get("status", "prospect")
                br_count = sum(1 for b in all_branches if b.get("client_name") == cname)
                edit_key = f"cl_edit_{cid}_open"

                st.markdown(f"""
                <div style="background:#fff;border:1px solid #e8e8e8;border-left:4px solid #E3C5AD;
                    border-radius:8px;padding:12px 18px;margin-bottom:4px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span style="font-size:15px;font-weight:700;color:#1B252C;">{cname}</span>
                            {'<span style="font-size:12px;color:#888;"> · ' + company + '</span>' if company else ''}
                        </div>
                        <div style="display:flex;align-items:center;gap:8px;">
                            {_tag(f"{br_count} branch{'es' if br_count != 1 else ''}", "#1B252C")}
                            {_status_badge(status)}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if st.button("✏️ Edit", key=f"cl_edit_btn_{cid}"):
                    st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                if st.session_state.get(edit_key, False):
                    with st.container(border=True):
                        _client_form(supabase, existing=client)
                st.write("")

    # ──────────────────────────────────────────────────────────────────────
    # TAB 2: BRANCHES
    # ──────────────────────────────────────────────────────────────────────
    with t2:
        col_h, col_btn = st.columns([5, 1])
        with col_h:
            st.markdown("##### Branch List")
        with col_btn:
            if st.button("＋ Add", key="br_open_add", use_container_width=True):
                st.session_state["br_add_open"] = not st.session_state.get("br_add_open", False)

        if st.session_state.get("br_add_open", False):
            with st.container(border=True):
                st.markdown("**New Branch**")
                _branch_form(supabase, clients=all_clients, existing=None)
            st.divider()

        client_names_all = ["All"] + sorted(set(b["client_name"] for b in all_branches))
        br_filter = st.selectbox("Filter by Client", client_names_all, key="br_client_filter")

        branches = all_branches if br_filter == "All" else [
            b for b in all_branches if b["client_name"] == br_filter]

        if not branches:
            st.info("No branches found.")
        else:
            for branch in branches:
                bid      = branch["id"]
                outlet   = branch.get("outlet", "—")
                cname    = branch.get("client_name", "—")
                address  = branch.get("address") or ""
                ar_count = sum(1 for a in all_areas if a.get("outlet") == outlet)
                edit_key = f"br_edit_{bid}_open"

                st.markdown(f"""
                <div style="background:#fff;border:1px solid #e8e8e8;border-left:4px solid #1B252C;
                    border-radius:8px;padding:12px 18px;margin-bottom:4px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span style="font-size:15px;font-weight:700;color:#1B252C;">{outlet}</span>
                            <span style="font-size:12px;color:#888;"> · {cname}</span>
                            {'<span style="font-size:12px;color:#aaa;"> · ' + address + '</span>' if address else ''}
                        </div>
                        <div>
                            {_tag(f"{ar_count} area{'s' if ar_count != 1 else ''}", "#E3C5AD")}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if st.button("✏️ Edit", key=f"br_edit_btn_{bid}"):
                    st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                if st.session_state.get(edit_key, False):
                    with st.container(border=True):
                        _branch_form(supabase, clients=all_clients, existing=branch)
                st.write("")

    # ──────────────────────────────────────────────────────────────────────
    # TAB 3: AREAS
    # ──────────────────────────────────────────────────────────────────────
    with t3:
        col_h, col_btn = st.columns([5, 1])
        with col_h:
            st.markdown("##### Area List")
        with col_btn:
            if st.button("＋ Add", key="ar_open_add", use_container_width=True):
                st.session_state["ar_add_open"] = not st.session_state.get("ar_add_open", False)

        if st.session_state.get("ar_add_open", False):
            with st.container(border=True):
                st.markdown("**New Area**")
                _area_form(supabase, branches=all_branches, existing=None)
            st.divider()

        outlet_list_all = ["All"] + sorted(set(a["outlet"] for a in all_areas))
        ar_filter = st.selectbox("Filter by Branch (Outlet)", outlet_list_all, key="ar_outlet_filter")

        areas = all_areas if ar_filter == "All" else [
            a for a in all_areas if a["outlet"] == ar_filter]

        if not areas:
            st.info("No areas found.")
        else:
            # Group by outlet
            for outlet in sorted(set(a["outlet"] for a in areas)):
                outlet_areas  = [a for a in areas if a["outlet"] == outlet]
                parent_branch = next((b for b in all_branches if b["outlet"] == outlet), None)
                parent_client = parent_branch["client_name"] if parent_branch else ""

                st.markdown(f"""
                <div style="font-size:13px;font-weight:600;color:#1B252C;
                    margin:12px 0 4px 0;padding-left:6px;border-left:3px solid #E3C5AD;">
                    {outlet}
                    <span style="font-weight:400;color:#888;font-size:12px;"> · {parent_client}</span>
                </div>
                """, unsafe_allow_html=True)

                for area in outlet_areas:
                    aid      = area["id"]
                    aname    = area.get("area_name", "—")
                    edit_key = f"ar_edit_{aid}_open"

                    col_card, col_ebtn = st.columns([6, 1])
                    with col_card:
                        st.markdown(f"""
                        <div style="background:#fff;border:1px solid #e8e8e8;border-radius:6px;
                            padding:8px 14px;margin-bottom:3px;">
                            <span style="font-size:13px;color:#1B252C;">📍 {aname}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_ebtn:
                        if st.button("✏️", key=f"ar_edit_btn_{aid}", use_container_width=True):
                            st.session_state[edit_key] = not st.session_state.get(edit_key, False)

                    if st.session_state.get(edit_key, False):
                        with st.container(border=True):
                            _area_form(supabase, branches=all_branches, existing=area)