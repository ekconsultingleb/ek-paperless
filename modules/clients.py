import streamlit as st
from supabase import create_client, Client

# ── Supabase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def _load_clients(supabase) -> list:
    return supabase.table("clients").select("*").order("client_name").execute().data or []

def _load_branches(supabase) -> list:
    return supabase.table("branches").select("*").order("outlet").execute().data or []

def _load_areas(supabase) -> list:
    return supabase.table("areas").select("*").order("area_name").execute().data or []


# ══════════════════════════════════════════════════════════════════════════════
# CSS — inject once
# ══════════════════════════════════════════════════════════════════════════════

def _inject_css():
    st.markdown("""
    <style>
    .ek-card {
        background: #1e2c35;
        border: 1px solid rgba(227,197,173,0.15);
        border-left: 4px solid #E3C5AD;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 2px;
    }
    .ek-card-dark {
        background: #1e2c35;
        border: 1px solid rgba(227,197,173,0.15);
        border-left: 4px solid #1B252C;
        border-radius: 8px;
        padding: 12px 18px;
        margin-bottom: 2px;
    }
    .ek-card-name {
        font-size: 15px;
        font-weight: 700;
        color: #E3C5AD;
    }
    .ek-card-meta {
        font-size: 12px;
        color: #8a9eaa;
        margin-top: 2px;
    }
    .ek-area-row {
        background: #1e2c35;
        border: 1px solid rgba(227,197,173,0.1);
        border-radius: 6px;
        padding: 7px 14px;
        margin-bottom: 3px;
        font-size: 13px;
        color: #E3C5AD;
    }
    .ek-outlet-header {
        font-size: 13px;
        font-weight: 600;
        color: #E3C5AD;
        margin: 14px 0 4px 0;
        padding-left: 6px;
        border-left: 3px solid #E3C5AD;
    }
    .ek-outlet-sub {
        font-weight: 400;
        color: #8a9eaa;
        font-size: 12px;
    }
    </style>
    """, unsafe_allow_html=True)


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
            group_company_name = st.text_input("Group / Company Name",
                value=existing.get("group_company_name") or "" if is_edit else "",
                placeholder="e.g. Lor SAL")

        status = st.selectbox("Status", ["prospect", "active", "churned"],
            index=["prospect", "active", "churned"].index(
                existing.get("status", "active") if is_edit else "active"))

        if st.form_submit_button("💾 Update Client" if is_edit else "➕ Add Client",
                                  width="stretch"):
            if not client_name.strip():
                st.error("Client Name is required.")
                return
            payload = {
                "client_name":        client_name.strip().title(),
                "group_company_name": group_company_name.strip() or None,
                "status":             status,
            }
            try:
                if is_edit:
                    supabase.table("clients").update(payload).eq("id", existing["id"]).execute()
                    st.success(f"✅ '{payload['client_name']}' updated.")
                else:
                    supabase.table("clients").insert(payload).execute()
                    st.success(f"✅ '{payload['client_name']}' added.")
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
            company_name = st.text_input("Company Name",
                value=existing.get("company_name") or "" if is_edit else "",
                placeholder="e.g. Lor SAL")
            address = st.text_input("Address",
                value=existing.get("address") or "" if is_edit else "",
                placeholder="e.g. Badaro Street, Beirut")

        if st.form_submit_button("💾 Update Branch" if is_edit else "➕ Add Branch",
                                  width="stretch"):
            if not outlet.strip():
                st.error("Outlet Code is required.")
                return
            client_row = next((c for c in clients if c["client_name"] == sel_client), None)
            payload = {
                "client_id":    client_row["id"] if client_row else None,
                "client_name":  sel_client,
                "company_name": company_name.strip() or None,
                "outlet":       outlet.strip(),
                "address":      address.strip() or None,
            }
            try:
                if is_edit:
                    supabase.table("branches").update(payload).eq("id", existing["id"]).execute()
                    st.success(f"✅ Branch '{payload['outlet']}' updated.")
                else:
                    supabase.table("branches").insert(payload).execute()
                    st.success(f"✅ Branch '{payload['outlet']}' added.")
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

        if st.form_submit_button("💾 Update Area" if is_edit else "➕ Add Area",
                                  width="stretch"):
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
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")


# ══════════════════════════════════════════════════════════════════════════════
# CARD RENDERERS — pure native Streamlit, no inner HTML
# ══════════════════════════════════════════════════════════════════════════════

STATUS_EMOJI = {"active": "🟢", "prospect": "🟡", "churned": "⚫"}

def _render_client_card(client, all_branches, supabase):
    cid      = client["id"]
    cname    = client.get("client_name", "—")
    company  = client.get("group_company_name") or ""
    status   = client.get("status", "prospect")
    br_count = sum(1 for b in all_branches if b.get("client_name") == cname)
    edit_key = f"cl_edit_{cid}_open"

    with st.container(border=True):
        col_info, col_meta, col_btn = st.columns([4, 2, 1])
        with col_info:
            st.markdown(f"**{cname}**" + (f"  \n*{company}*" if company else ""))
        with col_meta:
            st.caption(f"{STATUS_EMOJI.get(status, '⚫')} {status.title()}   ·   {br_count} branch{'es' if br_count != 1 else ''}")
        with col_btn:
            if st.button("✏️", key=f"cl_edit_btn_{cid}", width="stretch"):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key, False):
        with st.container(border=True):
            _client_form(supabase, existing=client)


def _render_branch_card(branch, all_areas, all_clients, supabase):
    bid          = branch["id"]
    outlet       = branch.get("outlet", "—")
    cname        = branch.get("client_name", "—")
    company_name = branch.get("company_name") or ""
    address      = branch.get("address") or ""
    ar_count     = sum(1 for a in all_areas if a.get("outlet") == outlet)
    edit_key     = f"br_edit_{bid}_open"

    with st.container(border=True):
        col_info, col_meta, col_btn = st.columns([4, 2, 1])
        with col_info:
            meta = f"*{cname}*" + (f" · {company_name}" if company_name else "")
            st.markdown(f"**{outlet}**  \n{meta}" + (f"  \n{address}" if address else ""))
        with col_meta:
            st.caption(f"🏠 {ar_count} area{'s' if ar_count != 1 else ''}")
        with col_btn:
            if st.button("✏️", key=f"br_edit_btn_{bid}", width="stretch"):
                st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key, False):
        with st.container(border=True):
            _branch_form(supabase, clients=all_clients, existing=branch)


def _render_area_row(area, all_branches, supabase):
    aid      = area["id"]
    aname    = area.get("area_name", "—")
    edit_key = f"ar_edit_{aid}_open"

    col_name, col_btn = st.columns([6, 1])
    with col_name:
        st.markdown(f"📍 {aname}")
    with col_btn:
        if st.button("✏️", key=f"ar_edit_btn_{aid}", width="stretch"):
            st.session_state[edit_key] = not st.session_state.get(edit_key, False)

    if st.session_state.get(edit_key, False):
        with st.container(border=True):
            _area_form(supabase, branches=all_branches, existing=area)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render_clients(supabase=None):
    if supabase is None:
        supabase = get_supabase()

    _inject_css()

    all_clients  = _load_clients(supabase)
    all_branches = _load_branches(supabase)
    all_areas    = _load_areas(supabase)

    # Summary metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Active Clients", sum(1 for c in all_clients if c.get("status") == "active"))
    m2.metric("Total Branches", len(all_branches))
    m3.metric("Total Areas",    len(all_areas))

    st.divider()

    t1, t2, t3 = st.tabs(["🏢 Clients", "🏠 Branches", "📍 Areas"])

    # ── TAB 1: CLIENTS ────────────────────────────────────────────────────
    with t1:
        col_h, col_btn = st.columns([5, 1])
        with col_h:
            st.markdown("##### Client List")
        with col_btn:
            if st.button("＋ Add", key="cl_open_add", width="stretch"):
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
                       or q in (c.get("group_company_name") or "").lower()]

        if not clients:
            st.info("No clients found.")
        else:
            for client in clients:
                _render_client_card(client, all_branches, supabase)

    # ── TAB 2: BRANCHES ───────────────────────────────────────────────────
    with t2:
        col_h, col_btn = st.columns([5, 1])
        with col_h:
            st.markdown("##### Branch List")
        with col_btn:
            if st.button("＋ Add", key="br_open_add", width="stretch"):
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
                _render_branch_card(branch, all_areas, all_clients, supabase)

    # ── TAB 3: AREAS ──────────────────────────────────────────────────────
    with t3:
        col_h, col_btn = st.columns([5, 1])
        with col_h:
            st.markdown("##### Area List")
        with col_btn:
            if st.button("＋ Add", key="ar_open_add", width="stretch"):
                st.session_state["ar_add_open"] = not st.session_state.get("ar_add_open", False)

        if st.session_state.get("ar_add_open", False):
            with st.container(border=True):
                st.markdown("**New Area**")
                _area_form(supabase, branches=all_branches, existing=None)
            st.divider()

        outlet_list_all = ["All"] + sorted(set(a["outlet"] for a in all_areas))
        ar_filter = st.selectbox("Filter by Branch", outlet_list_all, key="ar_outlet_filter")

        areas = all_areas if ar_filter == "All" else [
            a for a in all_areas if a["outlet"] == ar_filter]

        if not areas:
            st.info("No areas found.")
        else:
            for outlet in sorted(set(a["outlet"] for a in areas)):
                outlet_areas  = [a for a in areas if a["outlet"] == outlet]
                parent_branch = next((b for b in all_branches if b["outlet"] == outlet), None)
                parent_client = parent_branch["client_name"] if parent_branch else ""

                st.markdown(f"**{outlet}** · *{parent_client}*")
                st.divider()

                for area in outlet_areas:
                    _render_area_row(area, all_branches, supabase)

                st.write("")