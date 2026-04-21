import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import zoneinfo
import uuid
import json
from supabase import create_client, Client
from modules.nav_helper import build_outlet_location_sidebar, get_nav_data, get_all_clients, get_outlets_for_client
from modules.arabizi import arabizi_translate

# --- SAFELY INITIALIZE SUPABASE ---
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# Default units available to every requester
_DEFAULT_UNITS = ["Kg", "G", "L", "ml", "Pcs", "Box", "Bottle", "Can", "Bag", "Tray", "Crate", "Pack", "Dozen", "Jar"]


def _init_transfer_session():
    if 'tr_cart' not in st.session_state:
        st.session_state['tr_cart'] = []
    if 'tr_custom_units' not in st.session_state:
        st.session_state['tr_custom_units'] = []
    if 'tr_staged' not in st.session_state:
        st.session_state['tr_staged'] = None   # item dict waiting for qty/unit input

def _all_units():
    return _DEFAULT_UNITS + [u for u in st.session_state.get('tr_custom_units', []) if u not in _DEFAULT_UNITS]


def _explode_transfers(df: pd.DataFrame) -> pd.DataFrame:
    """One row per item per transfer with requested / fulfilled / received qty columns."""
    rows = []
    for _, t in df.iterrows():
        base = {
            "transfer_id":     t.get("transfer_id", ""),
            "date":            str(t.get("date", ""))[:16],
            "status":          t.get("status", ""),
            "requester":       t.get("requester", ""),
            "from_outlet":     t.get("from_outlet", ""),
            "from_location":   t.get("from_location", ""),
            "to_outlet":       t.get("to_outlet", ""),
            "to_location":     t.get("to_location", ""),
            "action_by":       t.get("action_by", ""),
        }
        try:
            items = json.loads(t.get("details") or "[]")
            if not isinstance(items, list):
                raise ValueError
        except Exception:
            items = []

        if items:
            for item in items:
                rows.append({**base,
                    "item_name":       item.get("item_name", ""),
                    "requested_qty":   item.get("requested_qty", ""),
                    "requested_unit":  item.get("requested_unit", ""),
                    "fulfilled_qty":   item.get("fulfilled_qty", ""),
                    "fulfilled_unit":  item.get("fulfilled_unit", ""),
                    "received_qty":    item.get("received_qty", ""),
                    "issue_note":      item.get("issue_note", ""),
                })
        else:
            rows.append({**base,
                "item_name": t.get("details", ""), "requested_qty": "", "requested_unit": "",
                "fulfilled_qty": "", "fulfilled_unit": "", "received_qty": "", "issue_note": "",
            })
    return pd.DataFrame(rows)

def render_transfers(conn, sheet_link, user, role, assigned_client, assigned_outlet, assigned_location):
    st.markdown("### 🔄 Transfers & Requisitions")
    supabase = get_supabase()
    _init_transfer_session()

    try:
        # ==========================================
        # 1. VIEWER MODE
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
                _outlet = str(assigned_outlet).strip()
                if not df_archive.empty and _outlet.lower() not in ['all', '', 'none', 'nan']:
                    df_archive = df_archive[
                        (df_archive.get('from_outlet', pd.Series(dtype=str)).astype(str) == _outlet) |
                        (df_archive.get('to_outlet',   pd.Series(dtype=str)).astype(str) == _outlet)
                    ]
                if not df_archive.empty:
                    st.dataframe(df_archive, width="stretch", hide_index=True)
                else:
                    st.warning(f"No transfers found between {start_date} and {end_date}.")
            else:
                st.info("Please select both a Start Date and an End Date.")
            return

        # ==========================================
        # 2. SIDEBAR & MASTER ITEMS
        # ==========================================
        final_client, final_outlet, _ = build_outlet_location_sidebar(
            assigned_client, assigned_outlet, assigned_location,
            outlet_key="tr_outlet", location_key="tr_location"
        )

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
            df_inv['outlet']      = df_inv['outlet'].astype(str).str.strip().str.title()
            df_inv['location']    = df_inv['location'].astype(str).str.strip().str.title()
            df_inv = df_inv.drop_duplicates().copy()

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
        # 3. LOAD TRANSFERS
        # ==========================================
        res_transfers = supabase.table("transfers").select("*").execute()
        df_transfers = pd.DataFrame(res_transfers.data)
        if not df_transfers.empty:
            df_transfers.columns = [c.lower() for c in df_transfers.columns]
        else:
            df_transfers = pd.DataFrame(columns=['transfer_id', 'date', 'status', 'requester',
                                                  'from_outlet', 'from_location', 'to_outlet',
                                                  'to_location', 'request_type', 'details', 'action_by'])

        user_locs_lower = [loc.lower() for loc in active_locations]
        user_locs_title = [l.title() for l in active_locations]

        _location_roles = ['chef', 'bar manager', 'manager', 'admin', 'admin_all']
        _is_warehouse    = (raw_loc.lower() == 'all' or any('warehouse' in loc for loc in user_locs_lower))
        _is_location_mgr = role.lower() in _location_roles
        can_dispatch     = _is_warehouse or _is_location_mgr

        if _is_warehouse:
            my_pending = df_transfers[
                (df_transfers['status'] == 'Pending') &
                (df_transfers['from_outlet'].str.title() == final_outlet)
            ]
        elif _is_location_mgr:
            my_pending = df_transfers[
                (df_transfers['status'] == 'Pending') &
                (df_transfers['from_outlet'].str.title() == final_outlet) &
                (df_transfers['from_location'].astype(str).str.title().isin(user_locs_title))
            ]
        else:
            my_pending = pd.DataFrame()

        my_incoming = df_transfers[
            (df_transfers['status'] == 'In Transit') &
            (df_transfers['to_outlet'].str.title() == final_outlet) &
            (df_transfers['to_location'].astype(str).str.title().isin(user_locs_title))
        ]

        if can_dispatch and not my_pending.empty:
            st.warning(f"🔔 **{len(my_pending)} pending request(s)** waiting for you to dispatch!")
        if not my_incoming.empty:
            st.info(f"🚚 **{len(my_incoming)} shipment(s)** arriving — ready to receive.")

        # ==========================================
        # TABS
        # ==========================================
        if can_dispatch:
            tab_req, tab_out, tab_in, tab_report = st.tabs([
                "🛒 Request",
                f"📤 Dispatch ({len(my_pending)})",
                f"✅ Receive ({len(my_incoming)})",
                "📊 Report",
            ])
        else:
            tab_req, tab_in, tab_report = st.tabs([
                "🛒 Request",
                f"✅ Receive ({len(my_incoming)})",
                "📊 Report",
            ])
            tab_out = None

        # ==========================================
        # TAB 1 — REQUEST
        # ==========================================
        with tab_req:
            if final_outlet == "None":
                st.error("No valid outlet assigned. Cannot create requests.")
            else:
                # --- Route selectors ---
                outlets_in_branch = sorted(df_inv['outlet'].unique()) if not df_inv.empty else [final_outlet]
                col_o1, col_o2 = st.columns(2)
                with col_o1:
                    from_outlet = st.selectbox("Request From (Outlet)", outlets_in_branch, key="t_from_out")
                with col_o2:
                    st.selectbox("Request For (Outlet)", [final_outlet], disabled=True, key="t_to_out")
                    to_outlet = final_outlet

                df_source_items = df_inv[(df_inv['client_name'] == final_client) & (df_inv['outlet'] == from_outlet)] if not df_inv.empty else pd.DataFrame()
                from_loc_options = sorted(list(df_source_items['location'].dropna().unique())) if not df_source_items.empty else ["Main Store"]

                col_l1, col_l2 = st.columns(2)
                with col_l1:
                    from_location = st.selectbox("From Location", from_loc_options, key="t_from_loc")
                with col_l2:
                    if raw_loc.lower() == 'all':
                        df_to_items   = df_inv[(df_inv['client_name'] == final_client) & (df_inv['outlet'] == to_outlet)] if not df_inv.empty else pd.DataFrame()
                        to_loc_opts   = sorted(list(df_to_items['location'].dropna().unique())) if not df_to_items.empty else ["Main Store"]
                        to_loc_opts   = [l for l in to_loc_opts if l != from_location] or to_loc_opts
                        to_location   = st.selectbox("To Location", to_loc_opts, key="t_to_loc")
                    else:
                        to_location = st.selectbox("To Location", active_locations, key="t_to_loc")

                st.divider()

                # --- Item search (supports Arabizi: "meleh" → Salt, "batata" → Potato …) ---
                search_q = st.text_input("🔍 Search item to add", placeholder="e.g. mayo, glen, meleh ", key="tr_search")

                df_filtered = pd.DataFrame()
                if search_q.strip() and not df_source_items.empty:
                    translations = arabizi_translate(search_q.strip())
                    # Build a combined regex: original term OR any translation
                    all_terms = [search_q.strip()] + translations
                    pattern = "|".join(all_terms)
                    df_filtered = df_source_items[
                        df_source_items['item_name'].str.contains(pattern, case=False, na=False, regex=True)
                    ].drop_duplicates(subset=['item_name']).head(12)
                    if translations:
                        st.caption(f"🔤 Arabizi detected — also searching: {', '.join(translations)}")

                if not df_filtered.empty:
                    st.caption(f"{len(df_filtered)} result(s) — click an item to select it:")
                    cols = st.columns(3)
                    for i, (_, item_row) in enumerate(df_filtered.iterrows()):
                        with cols[i % 3]:
                            label = f"{item_row['item_name']}\n({item_row.get('count_unit','pcs')})"
                            if st.button(label, key=f"sel_{item_row['item_name']}_{i}", use_container_width=True):
                                st.session_state['tr_staged'] = {
                                    'item_name': item_row['item_name'],
                                    'db_unit':   str(item_row.get('count_unit', 'pcs'))
                                }
                                st.rerun()

                # --- Staged item: enter qty + unit ---
                if st.session_state.get('tr_staged'):
                    staged = st.session_state['tr_staged']
                    st.markdown(f"**Selected:** {staged['item_name']}  ·  DB unit: `{staged['db_unit']}`")

                    all_units = _all_units()
                    col_q, col_u, col_custom, col_add = st.columns([2, 2, 2, 1], vertical_alignment="bottom")

                    with col_q:
                        req_qty = st.number_input("Qty", min_value=0.0, step=1.0, format="%g", key="tr_staged_qty")
                    with col_u:
                        req_unit = st.selectbox("Unit", all_units, key="tr_staged_unit")
                    with col_custom:
                        new_unit = st.text_input("+ New unit", placeholder="e.g. Gallon", key="tr_new_unit")
                    with col_add:
                        if st.button("Add to list", type="primary", key="tr_add_item"):
                            if new_unit.strip() and new_unit.strip() not in all_units:
                                st.session_state['tr_custom_units'].append(new_unit.strip())
                            unit_to_use = new_unit.strip() if new_unit.strip() else req_unit
                            if req_qty > 0:
                                # Avoid duplicates: remove existing entry for same item if present
                                st.session_state['tr_cart'] = [
                                    c for c in st.session_state['tr_cart']
                                    if c['item_name'] != staged['item_name']
                                ]
                                st.session_state['tr_cart'].append({
                                    'item_name':      staged['item_name'],
                                    'db_unit':        staged['db_unit'],
                                    'requested_qty':  req_qty,
                                    'requested_unit': unit_to_use,
                                })
                                st.session_state['tr_staged'] = None
                                st.rerun()
                            else:
                                st.warning("Qty must be greater than 0.")

                    if st.button("✕ Cancel", key="tr_cancel_staged"):
                        st.session_state['tr_staged'] = None
                        st.rerun()

                # --- Cart ---
                cart = st.session_state['tr_cart']
                if cart:
                    st.divider()
                    st.markdown(f"**Cart — {len(cart)} item(s)**")
                    for i, entry in enumerate(cart):
                        c_name, c_qty, c_del = st.columns([5, 2, 1], vertical_alignment="center")
                        c_name.markdown(f"**{entry['item_name']}**  ·  DB unit: `{entry['db_unit']}`")
                        c_qty.markdown(f"`{entry['requested_qty']} {entry['requested_unit']}`")
                        if c_del.button("✕", key=f"tr_rm_{i}"):
                            st.session_state['tr_cart'].pop(i)
                            st.rerun()

                    if st.button("🚀 Submit Request", type="primary", width="stretch", key="tr_submit"):
                        details_json = json.dumps(cart)
                        new_req = {
                            "transfer_id":   str(uuid.uuid4())[:8],
                            "date":          datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).strftime("%Y-%m-%d %H:%M"),
                            "status":        "Pending",
                            "requester":     user,
                            "from_outlet":   from_outlet,
                            "from_location": from_location,
                            "to_outlet":     to_outlet,
                            "to_location":   to_location,
                            "request_type":  "Itemized",
                            "details":       details_json,
                            "action_by":     ""
                        }
                        supabase.table("transfers").insert(new_req).execute()
                        st.session_state['tr_cart'] = []
                        st.session_state['tr_staged'] = None
                        st.success("✅ Request submitted!")
                        st.rerun()

        # ==========================================
        # TAB 2 — DISPATCH
        # ==========================================
        if tab_out:
            with tab_out:
                if my_pending.empty:
                    st.info("No pending requests for your location.")
                else:
                    for _, row in my_pending.iterrows():
                        tid = row['transfer_id']
                        with st.expander(
                            f"📦 {row['to_location']} → {row['from_location']}  ·  {row['requester']}  ·  {str(row.get('date',''))[:16]}"
                        ):
                            st.caption(f"Requested by **{row['requester']}** · from **{row['from_location']}** to **{row['to_location']}**")

                            # Try to parse structured JSON details
                            try:
                                items = json.loads(row['details'])
                                is_structured = isinstance(items, list) and items
                            except (json.JSONDecodeError, TypeError):
                                items = []
                                is_structured = False

                            if is_structured:
                                st.markdown("**Items requested:**")
                                fulfill_qtys = {}
                                for idx, item in enumerate(items):
                                    iname    = item.get('item_name', '?')
                                    req_qty  = item.get('requested_qty', '?')
                                    req_unit = item.get('requested_unit', '')
                                    db_unit  = item.get('db_unit', 'pcs')

                                    col_info, col_input = st.columns([3, 2], vertical_alignment="bottom")
                                    col_info.markdown(
                                        f"**{iname}** — requested `{req_qty} {req_unit}`  ·  dispatch in **{db_unit}**"
                                    )
                                    fulfill_qtys[idx] = col_input.number_input(
                                        f"Qty ({db_unit})",
                                        min_value=0.0, step=0.01, format="%.2f",
                                        key=f"ful_{tid}_{idx}"
                                    )

                                if st.button("✅ Approve & Dispatch", key=f"d_{tid}", type="primary"):
                                    # Embed fulfilled quantities back into the items list
                                    for idx, item in enumerate(items):
                                        item['fulfilled_qty']  = fulfill_qtys[idx]
                                        item['fulfilled_unit'] = item.get('db_unit', 'pcs')
                                    supabase.table("transfers").update({
                                        "details":   json.dumps(items),
                                        "status":    "In Transit",
                                        "action_by": f"Sent by {user}"
                                    }).eq("transfer_id", tid).execute()
                                    st.rerun()
                            else:
                                # Legacy plain-text request
                                edited = st.text_area("Details:", value=row['details'], key=f"e_{tid}", height=120)
                                if st.button("✅ Approve & Dispatch", key=f"d_{tid}", type="primary"):
                                    supabase.table("transfers").update({
                                        "details":   edited,
                                        "status":    "In Transit",
                                        "action_by": f"Sent by {user}"
                                    }).eq("transfer_id", tid).execute()
                                    st.rerun()

        # ==========================================
        # TAB 3 — RECEIVE
        # ==========================================
        with tab_in:
            if my_incoming.empty:
                st.info("No shipments to receive at your location.")
            else:
                for _, row in my_incoming.iterrows():
                    tid = row['transfer_id']
                    with st.container(border=True):
                        st.write(f"**From:** {row['from_location']}  ·  **ID:** {tid}  ·  {str(row.get('date',''))[:16]}")

                        try:
                            items = json.loads(row['details'])
                            is_structured = isinstance(items, list) and items
                        except (json.JSONDecodeError, TypeError):
                            items = []
                            is_structured = False

                        if is_structured:
                            received_qtys = {}
                            for idx, item in enumerate(items):
                                ful       = item.get('fulfilled_qty')
                                funit     = item.get('fulfilled_unit', item.get('db_unit', ''))
                                req_disp  = f"{item.get('requested_qty')} {item.get('requested_unit','')}"

                                col_info, col_rcv = st.columns([3, 2], vertical_alignment="bottom")
                                if ful is not None:
                                    col_info.markdown(
                                        f"**{item['item_name']}**  ·  requested `{req_disp}`  ·  dispatched `{ful} {funit}`"
                                    )
                                    received_qtys[idx] = col_rcv.number_input(
                                        f"Actually received ({funit})",
                                        min_value=0.0, step=0.01, format="%.2f",
                                        value=float(ful),
                                        key=f"rcv_{tid}_{idx}"
                                    )
                                else:
                                    col_info.markdown(f"**{item['item_name']}**  ·  requested `{req_disp}`")
                                    received_qtys[idx] = col_rcv.number_input(
                                        "Actually received",
                                        min_value=0.0, step=0.01, format="%.2f",
                                        value=0.0,
                                        key=f"rcv_{tid}_{idx}"
                                    )

                            issue_note = st.text_input(
                                "⚠️ Issue note (optional — fill only if something is wrong)",
                                placeholder="e.g. 1 bottle missing, box damaged…",
                                key=f"note_{tid}"
                            )

                            col_ok, col_issue = st.columns(2)
                            with col_ok:
                                if st.button("✅ Confirm Receipt", key=f"r_{tid}", type="primary", use_container_width=True):
                                    for idx, item in enumerate(items):
                                        item['received_qty'] = received_qtys.get(idx, item.get('fulfilled_qty'))
                                    supabase.table("transfers").update({
                                        "details":   json.dumps(items),
                                        "status":    "Received",
                                        "action_by": f"Received by {user}"
                                    }).eq("transfer_id", tid).execute()
                                    st.rerun()
                            with col_issue:
                                if st.button("⚠️ Receive with Issue", key=f"ri_{tid}", use_container_width=True):
                                    for idx, item in enumerate(items):
                                        item['received_qty']  = received_qtys.get(idx, item.get('fulfilled_qty'))
                                        item['issue_note']    = issue_note.strip()
                                    supabase.table("transfers").update({
                                        "details":   json.dumps(items),
                                        "status":    "Received with Issue",
                                        "action_by": f"Received by {user} — ISSUE: {issue_note.strip() or 'qty mismatch'}"
                                    }).eq("transfer_id", tid).execute()
                                    st.rerun()

                        else:
                            # Legacy plain-text
                            st.info(row['details'])
                            issue_note = st.text_input(
                                "⚠️ Issue note (optional)",
                                placeholder="e.g. 1 bottle missing…",
                                key=f"note_{tid}"
                            )
                            col_ok, col_issue = st.columns(2)
                            with col_ok:
                                if st.button("✅ Confirm Receipt", key=f"r_{tid}", type="primary", use_container_width=True):
                                    supabase.table("transfers").update({
                                        "status":    "Received",
                                        "action_by": f"Received by {user}"
                                    }).eq("transfer_id", tid).execute()
                                    st.rerun()
                            with col_issue:
                                if st.button("⚠️ Receive with Issue", key=f"ri_{tid}", use_container_width=True):
                                    supabase.table("transfers").update({
                                        "status":    "Received with Issue",
                                        "action_by": f"Received by {user} — ISSUE: {issue_note.strip() or 'reported'}"
                                    }).eq("transfer_id", tid).execute()
                                    st.rerun()

        # ==========================================
        # TAB — REPORT
        # ==========================================
        with tab_report:
            st.markdown("#### 📊 Transfer Report")
            _is_admin_rep = role.lower() in ["admin", "admin_all"]
            if _is_admin_rep:
                _rep_col1, _rep_col2 = st.columns(2)
                with _rep_col1:
                    _all_clients = ["All"] + get_all_clients()
                    rep_client = st.selectbox("🏢 Client", _all_clients, key="tr_rep_client")
                with _rep_col2:
                    _rep_outlets = ["All"] + (get_outlets_for_client(rep_client) if rep_client != "All" else [])
                    rep_outlet = st.selectbox("🏪 Outlet", _rep_outlets, key="tr_rep_outlet")
            else:
                rep_client = final_client
                rep_outlet = final_outlet

            today = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()
            default_start = today - timedelta(days=30)
            date_range = st.date_input("📅 Date Range", value=(default_start, today),
                                       max_value=today, key="rep_date_range")
            if len(date_range) == 2:
                start_date, end_date = date_range
                rep_q = (supabase.table("transfers").select("*")
                         .gte("date", f"{start_date} 00:00")
                         .lte("date", f"{end_date} 23:59")
                         .order("date", desc=True)
                         .limit(5000)
                         .execute())
                df_rep = pd.DataFrame(rep_q.data) if rep_q.data else pd.DataFrame()

                if not df_rep.empty:
                    df_rep.columns = [c.lower() for c in df_rep.columns]
                    if rep_outlet.lower() not in ["all", "", "none", "nan"]:
                        df_rep = df_rep[
                            (df_rep["from_outlet"].str.title() == rep_outlet) |
                            (df_rep["to_outlet"].str.title() == rep_outlet)
                        ]

                if df_rep.empty:
                    st.info("No transfers found for the selected period.")
                else:
                    df_flat = _explode_transfers(df_rep)

                    status_opts = ["All"] + sorted(df_flat["status"].dropna().unique().tolist())
                    sel_status = st.selectbox("Filter by status", status_opts, key="rep_status")
                    if sel_status != "All":
                        df_flat = df_flat[df_flat["status"] == sel_status]

                    df_flat_preview = df_flat.drop(columns=[c for c in ["id", "created_at"] if c in df_flat.columns])
                    st.dataframe(df_flat_preview, use_container_width=True, hide_index=True)
                    st.caption(f"{len(df_flat)} item-rows across {df_flat['transfer_id'].nunique()} transfers")

                    csv_bytes = df_flat.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        label="⬇️ Download CSV",
                        data=csv_bytes,
                        file_name=f"transfers_{start_date}_{end_date}.csv",
                        mime="text/csv",
                        type="primary",
                    )
            else:
                st.info("Select both a start and end date.")

    except Exception as e:
        st.error(f"❌ System Error in Transfers: {e}")
