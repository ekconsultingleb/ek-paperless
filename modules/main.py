import streamlit as st
import pandas as pd
from supabase import create_client, Client
from modules.clients import render_clients
from modules.nav_helper import hash_password
from modules.sales_purchase import push_sales_purchase
from modules.branch_config import render_branch_config

# — SAFELY INITIALIZE SUPABASE —

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def render_main(conn, sheet_link, user, role):
    # 🚨 ENTERPRISE TIER SECURITY LOCK
    user_role = role.lower()
    user_client = st.session_state.get('client_name', '').lower()

    is_super_admin = (user_role == "admin_all")
    is_normal_admin = (user_role == "admin")
    is_hq_manager = (user_role == "manager" and user_client == "all")

    if not (is_super_admin or is_normal_admin or is_hq_manager):
        st.error("🚫 Access Denied. This area is restricted to Head Office and Administrators.")
        return

    st.markdown("### ⚙️ Control Panel")
    supabase = get_supabase()

    if is_super_admin or is_normal_admin:
        if st.button("💲 Pricing Studio", type="primary"):
            st.session_state['current_page'] = "pricing studio"
            st.rerun()
        st.divider()

    # --- 🏗️ STRUCTURED ROUTING FROM clients / branches / areas ---
    def get_clients_list():
        try:
            res = supabase.table("clients").select("client_name").order("client_name").execute()
            return [r["client_name"] for r in (res.data or []) if r.get("client_name")]
        except:
            return []

    def get_outlets_for_client(client_name: str):
        try:
            q = supabase.table("branches").select("outlet").order("outlet")
            if client_name and client_name != "All":
                q = q.eq("client_name", client_name)
            res = q.execute()
            return [r["outlet"] for r in (res.data or []) if r.get("outlet")]
        except:
            return []

    def get_areas_for_outlet(outlet: str):
        try:
            q = supabase.table("areas").select("area_name").order("area_name")
            if outlet and outlet != "All":
                q = q.eq("outlet", outlet)
            res = q.execute()
            return [r["area_name"] for r in (res.data or []) if r.get("area_name")]
        except:
            return []

    clients_list = get_clients_list()

    # ==========================================
    # 📑 DYNAMIC TAB DEFINITION
    # ==========================================
    if is_super_admin:
        st.info("👑 Super Admin Mode: Full access to all database and user controls.")
        tabs = st.tabs(["📤 Master Sync", "📋 Push Sub Recipes", "📊 Sales & Purchase", "➕ Create User", "👥 Manage Users", "🚚 Manage Suppliers", "📝 Edit Data", "🏢 Clients", "⚙️ Branch Config"])
        t_sync, t_push_db, t_sales_purchase, t_create, t_view, t_supp, t_edit, t_clients, t_branch_config = tabs
        t_ac = None
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: Access to sync and onboard users/suppliers.")
        tabs = st.tabs(["📤 Master Sync", "📋 Push Sub Recipes", "📊 Sales & Purchase", "➕ Create User", "🚚 Manage Suppliers", "📝 Edit Data", "🏢 Clients", "⚙️ Branch Config"])
        t_sync, t_push_db, t_sales_purchase, t_create, t_supp, t_edit, t_clients, t_branch_config = tabs[0], tabs[1], tabs[2], tabs[3], tabs[4], tabs[5], tabs[6], tabs[7]
        t_view = t_ac = None
    else:
        st.info("🏢 HQ Manager Mode: Access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Sync"])
        t_sync = tabs[0]
        t_push_db = t_sales_purchase = t_create = t_view = t_supp = t_edit = t_clients = t_ac = t_branch_config = None

    # ==========================================
    # TAB: MASTER ITEMS SYNC
    # ==========================================
    with t_sync:

        sync_mode = st.radio("Select Sync Mode", 
                             ["🔄 Omega Sync (Auto Clean)", "📤 Smart Database Importer (Manual)"],
                             horizontal=True, key="sync_mode")

        # ── Helper: PROPER() equivalent ───────────────────────────────────────
        def proper(val):
            if pd.isna(val) or str(val).strip() == "": return ""
            return str(val).strip().title()

        def is_page_break_row(row):
            vals = [v for v in row if str(v) not in ["nan","NaT","None",""]]
            if not vals: return True
            if len(vals) <= 2 and any("page" in str(v).lower() for v in vals): return True
            return False

        # ══════════════════════════════════════════════════════════════════════
        # MODE 1: OMEGA SYNC
        # ══════════════════════════════════════════════════════════════════════
        if sync_mode == "🔄 Omega Sync (Auto Clean)":
            st.markdown("#### 🔄 Omega Sync — Auto Clean & Push")
            st.info("Upload the 2 Programming Summary files exported from Omega. Paperless will clean, apply PROPER(), and push to master_items automatically.")

            # ── Client setup ───────────────────────────────────────────────
            st.markdown("##### 1. Select or Create Client")

            client_mode = st.radio("Client", ["Select existing", "Create new"], 
                                    horizontal=True, key="omega_client_mode")
            
            col_c1, col_c2, col_c3 = st.columns(3)
            
            if client_mode == "Select existing":
                with col_c1:
                    sel_client = st.selectbox("Client", clients_list, key="omega_client")
                with col_c2:
                    outlets = get_outlets_for_client(sel_client)
                    sel_outlet = st.selectbox("Outlet", outlets if outlets else ["Main"], key="omega_outlet")
                with col_c3:
                    areas = get_areas_for_outlet(sel_outlet)
                    loc_list = areas if areas else ["Main Store"]
                    sel_location = st.selectbox("Location", loc_list, key="omega_location")
                final_client   = sel_client
                final_outlet   = sel_outlet
                final_location = sel_location
            else:
                with col_c1: final_client   = st.text_input("New Client Name", key="omega_new_client").strip().title()
                with col_c2: final_outlet   = st.text_input("Outlet Name",     key="omega_new_outlet").strip().title()
                with col_c3: final_location = st.text_input("Location Name",   key="omega_new_location").strip().title()

            if not final_client or not final_outlet or not final_location:
                st.warning("Please fill in Client, Outlet and Location before uploading files.")
                st.stop()

            st.markdown("##### 2. Upload Omega Files")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                inv_file  = st.file_uploader("📦 Programming Summary — Inventory — Rep_I_0044",
                                              type=["xlsx", "xls"], key="omega_inv")
            with col_f2:
                menu_file = st.file_uploader("🍽️ Programming Summary — Menu Items — Rep_S_00178",
                                              type=["xlsx", "xls"], key="omega_menu")

            # ── Shared helpers ────────────────────────────────────────────
            from datetime import datetime as _dt
            import numpy as np

            def _is_empty(val):
                if val is None: return True
                if isinstance(val, (pd.Timestamp, _dt)): return True
                return str(val).strip() in ["", "nan", "NaT", "None"]

            NOISE_LABELS = {
                "item id", "description", "menu description", "kitchen",
                "programming summary", "copyright", "omega"
            }

            def _clean_file(raw_df):
                """
                Step 1: Remove row index 8 (row 9 in Excel) — shift up.
                Step 2: Drop timestamps, all-blank rows, and noise header rows.
                Returns a list of row value lists (col A, B, C, D).
                """
                rows = []
                for i, row in raw_df.iterrows():
                    # Step 1: skip the orphan row at index 8
                    if i == 8:
                        continue
                    a = row[0]
                    # Step 2a: drop timestamps
                    if isinstance(a, (pd.Timestamp, _dt)):
                        continue
                    # Step 2b: drop all-blank rows
                    vals = [v for v in row if not _is_empty(v)]
                    if not vals:
                        continue
                    # Step 2c: drop noise rows (copyright, column headers, etc.)
                    if not _is_empty(a) and any(n in str(a).lower() for n in NOISE_LABELS):
                        continue
                    b = row[1]
                    if not _is_empty(b) and str(b).strip().lower() in ["description", "item id"]:
                        continue
                    rows.append([row[j] if j < len(row) else None for j in range(4)])
                return rows

            def _is_label(row):
                """A header/label row: col A has text, col B is empty."""
                return (not _is_empty(row[0]) and
                        not isinstance(row[0], (int, float)) and
                        _is_empty(row[1]))

            def _next_label_count(data, idx):
                count = 0
                j = idx + 1
                while j < len(data) and _is_label(data[j]):
                    count += 1
                    j += 1
                return count

            # ════════════════════════════════════════════════════════════════════════
            # Omega Programming Summary parsers — v3 (run-based, category/division/group)
            # Drop-in replacements for parse_inventory() and parse_menu_items() in the
            # Omega Sync tab of main.py. Requires `proper()` in scope (already there).
            #
            # Hierarchy mapping (Omega → master_items columns):
            #   Omega Category  (Food / Beverages / Tobacco)  →  category
            #   Omega Division  (Gin, Burgers, Alcohol...)    →  division   (NEW, nullable)
            #   Omega Group     (Les Gins, Bars & Bites...)   →  sub_category
            #
            # sub_category keeps its DB name so nothing breaks in Next.js — it now
            # holds Omega's "Group" level. `division` must exist in master_items
            # (text, nullable) before pushing. Inventory files have no division → NULL.
            # ════════════════════════════════════════════════════════════════════════
            import re
            import datetime as _dt
            import pandas as pd


            # ── Parse Menu Items file (REP_S_00178) ─────────────────────────────────
            def parse_menu_items(f, client, outlet, location):
                """
                Alternating rows: name row (col A empty, col B = name) then ID row
                (col A numeric, col B empty).
                Section headers = runs of consecutive text rows in col A:
                run of 3 = (category, division, group)   e.g. FOOD / BURGERS / LES BURGERS
                run of 2 = (division, group)             e.g. GIN / LES GINS
                run of 1 = orphan group (pair split by page break) — division
                            mirrored by stripping leading "LES ".
                Division and group names usually DIFFER — never rely on
                duplicate-consecutive-rows detection.
                Page-break blocks (timestamp / "Description" / "Item ID") are transparent
                so pairs split across pages re-join.
                Excluded: DELETE * sections, REMARKS * / Doneness (modifier buttons),
                xxx-prefixed, company-name header, REP_S_xxxxx copyright footer.
                """
                def _e(v):
                    if v is None: return True
                    if isinstance(v, float) and pd.isna(v): return True
                    return str(v).strip() in ("", "nan", "None", "NaN")

                def _n(v):
                    if _e(v): return False
                    try: float(str(v)); return True
                    except (ValueError, TypeError): return False

                _engine = "xlrd" if getattr(f, "name", "").lower().endswith(".xls") else None
                raw = pd.read_excel(f, header=None, engine=_engine)
                df  = raw.astype(object)
                n   = len(df)

                # Pass 1 — classify rows
                RT = []
                for i in range(n):
                    a  = df.iloc[i, 0]
                    b  = df.iloc[i, 1] if df.shape[1] > 1 else None
                    c  = df.iloc[i, 2] if df.shape[1] > 2 else None
                    sa = str(a).strip()
                    if (isinstance(a, (_dt.datetime, pd.Timestamp))
                            or sa in ("Item ID", "Programming Summary")
                            or str(b).strip() == "Description"
                            or (_e(a) and _e(b))
                            or "Copyright" in str(c)
                            or re.match(r"^REP_[A-Z]_\d+$", sa)):
                        RT.append("noise")
                    elif not _e(a) and not _n(a):
                        RT.append("text")
                    elif _e(a) and not _e(b):
                        RT.append("name")
                    elif _n(a) and _e(b):
                        RT.append("id")
                    else:
                        RT.append("noise")

                # Company-name row: first text row before any item data → noise
                for i in range(n):
                    if RT[i] == "text":
                        RT[i] = "noise"
                        break
                    if RT[i] in ("name", "id"):
                        break

                # Pass 2 — group text rows into runs (noise transparent → re-joins
                # pairs split by page breaks, e.g. TEQUILA / LES TEQUILAS)
                runs, cur = [], []
                for i in range(n):
                    if RT[i] == "text":
                        cur.append(str(df.iloc[i, 0]).strip())
                    elif RT[i] == "noise":
                        continue
                    else:
                        if cur: runs.append((i, cur)); cur = []
                if cur:
                    runs.append((n, cur))

                resolved = {}
                for pos, r in runs:
                    if len(r) >= 3:
                        resolved[pos] = (r[-3], r[-2], r[-1])
                    elif len(r) == 2:
                        resolved[pos] = (None, r[0], r[1])
                    else:
                        resolved[pos] = (None, re.sub(r"^les\s+", "", r[0], flags=re.I), r[0])

                # Pass 3 — emit records
                records = []
                cat = div = grp = ""
                pending = None
                bounds = sorted(resolved)
                bi = 0
                for i in range(n):
                    while bi < len(bounds) and i >= bounds[bi]:
                        c, d, g = resolved[bounds[bi]]
                        if c is not None:
                            cat = proper(c)
                        div, grp = proper(d), proper(g)
                        pending = None
                        bi += 1
                    t = RT[i]
                    if t in ("noise", "text"):
                        continue
                    if t == "name":
                        pending = proper(str(df.iloc[i, 1]).strip())
                        continue
                    if t == "id" and pending:
                        low = f"{cat}|{div}|{grp}|{pending}".lower()
                        excluded = (
                            low.startswith("xxx") or "|xxx" in low
                            or div.lower().startswith("delete") or grp.lower().startswith("delete")
                            or div.lower().startswith("remarks") or grp.lower().startswith("remarks")
                            or grp.lower() == "doneness"
                        )
                        if not excluded:
                            records.append({
                                "client_name":  client,
                                "outlet":       outlet,
                                "location":     location,
                                "item_type":    "Menu Item",
                                "category":     cat,
                                "division":     div,
                                "sub_category": grp,
                                "product_code": str(int(float(str(df.iloc[i, 0])))),
                                "item_name":    pending,
                                "count_unit":   "Unit",
                            })
                        pending = None

                return pd.DataFrame(records)


            # ── Parse Inventory file (REP_I_0044) — v4 ──────────────────────────────
            # REPLACES parse_inventory v3 ONLY. parse_menu_items stays unchanged.
            #
            # Fix: inventory uses the SAME 3-level run structure as the menu file —
            # NOT "duplicated pair = category". Verified on two clients:
            #   Doupont: [BEVERAGES, AMAROS, AMAROS]  → cat, div, grp (div often = grp)
            #   Fit Hub: [Beverages, Beverages, Bars & Bites] → cat, div, grp (div = cat)
            # Run of 3+ = (category, division, group); run of 2 = (division, group);
            # run of 1 = group only, division unchanged (e.g. WHISKY JAPANESE stays
            # under division WHISKY). DELETE * sections now excluded here too.
            def parse_inventory(f, client, outlet, location):
                import re
                import datetime as _dt
                import pandas as pd

                def _e(v):
                    if v is None: return True
                    if isinstance(v, float) and pd.isna(v): return True
                    return str(v).strip() in ("", "nan", "None", "NaN")

                def _n(v):
                    if _e(v): return False
                    try: float(str(v)); return True
                    except (ValueError, TypeError): return False

                _engine = "xlrd" if getattr(f, "name", "").lower().endswith(".xls") else None
                raw = pd.read_excel(f, header=None, engine=_engine)
                df  = raw.astype(object)
                n   = len(df)

                RT = []
                for i in range(n):
                    a  = df.iloc[i, 0]
                    b  = df.iloc[i, 1] if df.shape[1] > 1 else None
                    d  = df.iloc[i, 3] if df.shape[1] > 3 else None
                    sa = str(a).strip()
                    if (isinstance(a, (_dt.datetime, pd.Timestamp))
                            or sa.lower() in ("item id", "programming summary (inventory items)")
                            or "Copyright" in str(d)
                            or re.match(r"^REP_[A-Z]_\d+$", sa)
                            or (_e(a) and _e(b))):
                        RT.append("noise")
                    elif not _e(a) and not _n(a) and _e(b):
                        RT.append("text")
                    elif _n(a) and not _e(b):
                        RT.append("item")
                    else:
                        RT.append("noise")

                # Company-name row → noise (automatic, works for any client)
                for i in range(n):
                    if RT[i] == "text":
                        RT[i] = "noise"
                        break
                    if RT[i] == "item":
                        break

                # Group text rows into runs; page-break noise is transparent so
                # label runs split across pages re-join.
                runs, cur = [], []
                for i in range(n):
                    if RT[i] == "text":
                        cur.append(str(df.iloc[i, 0]).strip())
                    elif RT[i] == "noise":
                        continue
                    else:
                        if cur: runs.append((i, cur)); cur = []
                if cur:
                    runs.append((n, cur))

                resolved = {}
                for pos, r in runs:
                    if len(r) >= 3:
                        resolved[pos] = (r[-3], r[-2], r[-1])   # cat, div, grp
                    elif len(r) == 2:
                        resolved[pos] = (None, r[0], r[1])      # div, grp (cat unchanged)
                    else:
                        resolved[pos] = (None, None, r[0])      # grp only (cat+div unchanged)

                records = []
                cat = div = grp = ""
                bounds = sorted(resolved)
                bi = 0
                for i in range(n):
                    while bi < len(bounds) and i >= bounds[bi]:
                        c, d, g = resolved[bounds[bi]]
                        if c is not None: cat = proper(c)
                        if d is not None: div = proper(d)
                        grp = proper(g)
                        bi += 1
                    if RT[i] != "item":
                        continue
                    b     = df.iloc[i, 1]
                    cdesc = df.iloc[i, 2] if df.shape[1] > 2 else None
                    dunit = df.iloc[i, 3] if df.shape[1] > 3 else None
                    product_code = proper(str(b))
                    item_name    = proper(str(cdesc)) if not _e(cdesc) else ""
                    count_unit   = proper(str(dunit)) if not _e(dunit) else ""
                    if not item_name:
                        continue
                    low = f"{product_code}|{item_name}|{cat}|{div}|{grp}".lower()
                    if low.startswith("xxx") or "|xxx" in low:
                        continue
                    if div.lower().startswith("delete") or grp.lower().startswith("delete"):
                        continue
                    records.append({
                        "client_name":  client,
                        "outlet":       outlet,
                        "location":     location,
                        "item_type":    "Inventory",
                        "category":     cat,
                        "division":     div,
                        "sub_category": grp,
                        "product_code": product_code,
                        "item_name":    item_name,
                        "count_unit":   count_unit,
                    })

                return pd.DataFrame(records)

            # ── Modifier detection helpers ──────────────────────────────
            _MODIFIER_PREFIXES = (
                "no ", "add ", "add-", "extra ", "without ", "w/o ", "w/ ",
                "remove ", "less ", "more ", "sub ", "substitute ", "light ",
                "heavy ", "side of ", "on the side", "well done", "medium ",
                "upgrade ", "change ", "swap ",
            )
            _MODIFIER_SUBCATS = (
                "modifier", "modifiers", "add-on", "add on", "addon",
                "option", "options", "extra", "extras", "instruction",
                "instructions", "special request",
            )

            def _is_modifier_row(row):
                name   = str(row.get("item_name", "")).lower().strip()
                subcat = str(row.get("sub_category", "")).lower().strip()
                return (
                    any(name.startswith(p) for p in _MODIFIER_PREFIXES) or
                    any(m in subcat for m in _MODIFIER_SUBCATS)
                )

            # ── Preview & Push ─────────────────────────────────────────────
            if inv_file or menu_file:
                st.markdown("##### 3. Review & Select Items")

                df_inv  = pd.DataFrame()
                df_menu = pd.DataFrame()

                if inv_file:
                    try:
                        df_inv_raw = parse_inventory(inv_file, final_client, final_outlet, final_location)

                        # All items included by default
                        df_inv_raw.insert(0, "include", True)

                        st.markdown(f"**Inventory Items:** {len(df_inv_raw)} rows parsed")

                        # ── Group exclude by category / subcategory ────────────────────
                        inv_all_cats = sorted(df_inv_raw["category"].unique().tolist())
                        inv_all_subs = sorted(df_inv_raw["sub_category"].unique().tolist())

                        with st.expander("🗂️ Bulk exclude by Category / Subcategory", expanded=False):
                            st.caption("Uncheck a category or subcategory to exclude all its items. Row-level checkboxes below can still override.")
                            ic1, ic2 = st.columns(2)
                            with ic1:
                                st.markdown("**By Category**")
                                inv_excl_cats = set()
                                for _cat in inv_all_cats:
                                    n_cat = int((df_inv_raw["category"] == _cat).sum())
                                    if not st.checkbox(f"{_cat}  ({n_cat})", value=True, key=f"inv_cat_{_cat}"):
                                        inv_excl_cats.add(_cat)
                            with ic2:
                                st.markdown("**By Subcategory**")
                                inv_excl_subs = set()
                                for _sub in inv_all_subs:
                                    n_sub = int((df_inv_raw["sub_category"] == _sub).sum())
                                    if not st.checkbox(f"{_sub}  ({n_sub})", value=True, key=f"inv_sub_{_sub}"):
                                        inv_excl_subs.add(_sub)

                        # Apply group exclusions
                        if inv_excl_cats or inv_excl_subs:
                            inv_mask = (
                                df_inv_raw["category"].isin(inv_excl_cats) |
                                df_inv_raw["sub_category"].isin(inv_excl_subs)
                            )
                            df_inv_raw.loc[inv_mask, "include"] = False

                        edited_inv = st.data_editor(
                            df_inv_raw[["include", "category", "division", "sub_category", "product_code", "item_name", "count_unit"]],
                            column_config={
                                "include": st.column_config.CheckboxColumn("✅ Include", default=True, width="small"),
                            },
                            hide_index=True,
                            use_container_width=True,
                            key="inv_editor",
                        )

                        df_inv = df_inv_raw[edited_inv["include"].values].drop(columns=["include"]).reset_index(drop=True)
                        st.caption(f"**{len(df_inv)}** items selected for push · **{len(df_inv_raw) - len(df_inv)}** excluded")

                    except Exception as e:
                        st.error(f"❌ Inventory parse error: {e}")

                if menu_file:
                    try:
                        df_menu_raw = parse_menu_items(menu_file, final_client, final_outlet, final_location)

                        # Auto-flag modifiers as unchecked
                        df_menu_raw.insert(0, "include", ~df_menu_raw.apply(_is_modifier_row, axis=1))

                        auto_excluded = int((~df_menu_raw["include"]).sum())
                        st.markdown(
                            f"**Menu Items:** {len(df_menu_raw)} rows parsed — "
                            f"{auto_excluded} auto-flagged as modifiers (unchecked). "
                            f"Review below and adjust before pushing."
                        )

                        # ── Group exclude by category / subcategory ────────────────────
                        all_cats = sorted(df_menu_raw["category"].unique().tolist())
                        all_subs = sorted(df_menu_raw["sub_category"].unique().tolist())

                        with st.expander("🗂️ Bulk exclude by Category / Subcategory", expanded=False):
                            st.caption("Uncheck a category or subcategory to exclude all its items. Row-level checkboxes below can still override.")
                            gc1, gc2 = st.columns(2)
                            with gc1:
                                st.markdown("**By Category**")
                                excl_cats = set()
                                for _cat in all_cats:
                                    n_cat = int((df_menu_raw["category"] == _cat).sum())
                                    if not st.checkbox(f"{_cat}  ({n_cat})", value=True, key=f"grp_cat_{_cat}"):
                                        excl_cats.add(_cat)
                            with gc2:
                                st.markdown("**By Subcategory**")
                                excl_subs = set()
                                for _sub in all_subs:
                                    n_sub = int((df_menu_raw["sub_category"] == _sub).sum())
                                    if not st.checkbox(f"{_sub}  ({n_sub})", value=True, key=f"grp_sub_{_sub}"):
                                        excl_subs.add(_sub)

                        if excl_cats or excl_subs:
                            mask = (
                                df_menu_raw["category"].isin(excl_cats) |
                                df_menu_raw["sub_category"].isin(excl_subs)
                            )
                            df_menu_raw.loc[mask, "include"] = False

                        edited_menu = st.data_editor(
                            df_menu_raw[["include", "category", "division", "sub_category", "product_code", "item_name"]],
                            column_config={
                                "include": st.column_config.CheckboxColumn("✅ Include", default=True, width="small"),
                            },
                            hide_index=True,
                            use_container_width=True,
                            key="menu_editor",
                        )

                        df_menu = df_menu_raw[edited_menu["include"].values].drop(columns=["include"]).reset_index(drop=True)
                        st.caption(f"**{len(df_menu)}** items selected for push · **{len(df_menu_raw) - len(df_menu)}** excluded")

                    except Exception as e:
                        st.error(f"❌ Menu Items parse error: {e}")
                combined = pd.concat([df_inv, df_menu], ignore_index=True)
                
                if len(combined) > 0:
                    st.markdown(f"##### 4. Push to Supabase")
                    st.markdown(f"**Total records to upsert: {len(combined)}** "
                                f"({len(df_inv)} inventory + {len(df_menu)} menu items)")
                    
                    if st.button("🚀 Push to Supabase", type="primary", 
                                  width="stretch", key="omega_push"):
                        with st.spinner("Pushing to Supabase..."):
                            try:
                                cols = [c for c in combined.columns if c != "division"]
                                combined[cols] = combined[cols].fillna("")
                                records  = combined.to_dict(orient="records")
                                pushed   = 0
                                for i in range(0, len(records), 500):
                                    supabase.table("master_items").upsert(
                                        records[i:i+500],
                                        on_conflict="client_name,outlet,location,item_type,product_code"
                                    ).execute()
                                    pushed += len(records[i:i+500])
                                st.success(f"✅ Done! {pushed} items pushed to Supabase for {final_client}.")
                                st.balloons()
                            except Exception as e:
                                st.error(f"❌ Push failed: {e}")

        # ══════════════════════════════════════════════════════════════════════
        # MODE 2: SMART DATABASE IMPORTER (existing, unchanged)
        # ══════════════════════════════════════════════════════════════════════
        else:
            st.markdown("#### 📤 Smart Database Importer")
            uploaded_file = st.file_uploader("Upload Master Items List", type=["xls", "xlsx"])
            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.xls') else pd.read_excel(uploaded_file)
                    df.columns = [str(c).strip().lower() for c in df.columns]
                    st.dataframe(df.head(5), use_container_width=True)
                    required_cols = ['client_name', 'outlet', 'location', 'item_type', 'product_code', 'item_name']
                    if all(c in df.columns for c in required_cols):
                        if st.button("🚀 Run Smart Sync", type="primary", width="stretch"):
                            with st.spinner("Syncing..."):
                                df = df.fillna('')
                                records = df.to_dict(orient='records')
                                for i in range(0, len(records), 500):
                                    supabase.table("master_items").upsert(records[i:i + 500], on_conflict="client_name,outlet,location,item_type,product_code").execute()
                                st.success(f"✅ Synced {len(records)} items!")
                    else:
                        st.error("❌ Missing required columns.")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

    # ==========================================
    # TAB: CREATE USER
    # ==========================================
    if t_push_db:
        with t_push_db:
            st.markdown("#### 📋 Push Sub Recipes")

            data_source = st.radio(
                "Select Data Source", ["☁️ Cloud", "💾 Local"],
                horizontal=True, key="sr_data_source"
            )

            st.markdown("##### 1. Select Client & Location")
            col_sc1, col_sc2, col_sc3 = st.columns(3)
            with col_sc1:
                sr_client = st.selectbox("🏢 Client", clients_list, key="sr_client")
            with col_sc2:
                sr_outlets = get_outlets_for_client(sr_client)
                sr_outlet = st.selectbox("🏠 Outlet", sr_outlets if sr_outlets else ["Main"], key="sr_outlet")
            with col_sc3:
                sr_areas = get_areas_for_outlet(sr_outlet)
                sr_location = st.selectbox("📍 Location", sr_areas if sr_areas else ["Main Store"], key="sr_location")

            st.markdown("##### 2. Upload Sub Recipes File")
            sr_file = st.file_uploader("📄 Ingredients QTP Report (.xlsx / .xls)", type=["xlsx", "xls"], key="sr_file")

            if sr_file:
                try:
                    import numpy as _np
                    import math as _math

                    def _sr_empty(v):
                        if v is None: return True
                        if isinstance(v, float) and _math.isnan(v): return True
                        return str(v).strip() in ("", "nan", "NaT", "None", "NaN")

                    def _sr_numeric(v):
                        if _sr_empty(v): return False
                        try: float(str(v)); return True
                        except: return False

                    def _json_safe(v):
                        if v is None: return None
                        try:
                            if isinstance(v, float) and _math.isnan(v): return None
                        except: pass
                        return v

                    raw = pd.read_excel(sr_file, header=None)

                    if data_source == "☁️ Cloud":
                        # Cloud: cols B,C,E,F  → index [1,2,4,5]
                        df_sr = raw.iloc[:, [1, 2, 4, 5]].copy()
                        df_sr.columns = ["Name", "Product Description", "Qty", "unit"]

                        # Header rows: Name col is not empty
                        ids = df_sr[df_sr["Name"].apply(lambda x: not _sr_empty(x))].index
                        df_sr.loc[ids, "Qty"] = df_sr.loc[ids, "Qty"].astype(str).str.replace(
                            "Ingredients to prepare ", "", regex=False)
                        df_sr.loc[ids, "Production Name"] = df_sr.loc[ids, "Qty"].str.split().apply(
                            lambda x: " ".join(x[3:]) if len(x) > 3 else "")
                        df_sr["Production Name"] = df_sr["Production Name"].ffill()
                        df_sr.loc[ids, "_tp"] = df_sr.loc[ids, "Qty"].str.split().apply(lambda x: x[:2])
                        df_sr.loc[ids, "Qty to be Prepared"] = df_sr.loc[ids, "_tp"].apply(
                            lambda x: x[0] if isinstance(x, list) and len(x) > 0 else "")
                        df_sr.loc[ids, "Prepared Unit"] = df_sr.loc[ids, "_tp"].apply(
                            lambda x: x[1] if isinstance(x, list) and len(x) > 1 else "")
                        df_sr[["Qty to be Prepared", "Prepared Unit"]] = df_sr[["Qty to be Prepared", "Prepared Unit"]].ffill()

                        # Remove repeated header rows and blank rows
                        df_sr = df_sr[df_sr["Qty"].astype(str).str.strip() != "Qty"]
                        df_sr = df_sr[df_sr["Product Description"].apply(lambda x: not _sr_empty(x))]
                        df_sr = df_sr[df_sr["Qty"].apply(lambda x: not _sr_empty(x))]

                        # Make numeric
                        df_sr["Qty"] = pd.to_numeric(df_sr["Qty"], errors="coerce")
                        df_sr["Qty to be Prepared"] = pd.to_numeric(df_sr["Qty to be Prepared"], errors="coerce")

                        df_sr = df_sr[["Production Name", "Product Description", "Qty", "unit",
                                       "Qty to be Prepared", "Prepared Unit"]].copy()

                    else:  # Local
                        # Local: cols C,F,G  → index [2,5,6]
                        df_sr = raw.iloc[:, [2, 5, 6]].copy()
                        df_sr.columns = ["Product Description", "Qty", "unit"]

                        # Remove repeated header rows and blank rows
                        df_sr = df_sr[df_sr["Qty"].astype(str).str.strip() != "Qty"]
                        df_sr = df_sr[df_sr["Product Description"].apply(lambda x: not _sr_empty(x))]
                        df_sr = df_sr[df_sr["Qty"].apply(lambda x: not _sr_empty(x))]

                        # Non-numeric Qty rows are the recipe header rows
                        df_sr["_num"] = pd.to_numeric(df_sr["Qty"], errors="coerce")
                        ids = df_sr[df_sr["_num"].isna()].index
                        df_sr.loc[ids, "Qty"] = df_sr.loc[ids, "Qty"].astype(str).str.replace(
                            "Ingredients to prepare ", "", regex=False)
                        df_sr.loc[ids, "Production Name"] = df_sr.loc[ids, "Qty"].str.split().apply(
                            lambda x: " ".join(x[3:]) if len(x) > 3 else "")
                        df_sr["Production Name"] = df_sr["Production Name"].ffill()
                        df_sr.loc[ids, "_tp"] = df_sr.loc[ids, "Qty"].str.split().apply(lambda x: x[:2])
                        df_sr.loc[ids, "Qty to be Prepared"] = df_sr.loc[ids, "_tp"].apply(
                            lambda x: x[0] if isinstance(x, list) and len(x) > 0 else "")
                        df_sr.loc[ids, "Prepared Unit"] = df_sr.loc[ids, "_tp"].apply(
                            lambda x: x[1] if isinstance(x, list) and len(x) > 1 else "")
                        df_sr[["Qty to be Prepared", "Prepared Unit"]] = df_sr[["Qty to be Prepared", "Prepared Unit"]].ffill()

                        # Drop the header rows — keep only ingredient rows
                        df_sr = df_sr.drop(index=ids)

                        df_sr = df_sr[["Production Name", "Product Description", "Qty", "unit",
                                       "Qty to be Prepared", "Prepared Unit"]].copy()
                        df_sr["Qty"] = pd.to_numeric(df_sr["Qty"], errors="coerce")
                        df_sr["Qty to be Prepared"] = pd.to_numeric(df_sr["Qty to be Prepared"], errors="coerce")

                    df_sr = df_sr.reset_index(drop=True)
                    df_sr.columns = ["production_name", "product_description", "qty", "unit",
                                     "qty_to_prepared", "prepared_unit"]
                    df_sr["client_name"] = sr_client
                    df_sr["location"] = sr_location

                    st.markdown(f"##### 3. Preview — {len(df_sr)} records")
                    st.dataframe(df_sr, use_container_width=True, hide_index=True)

                    if len(df_sr) > 0:
                        st.markdown("##### 4. Push to Supabase")
                        if st.button("🚀 Push Sub Recipes", type="primary", width="stretch", key="sr_push"):
                            with st.spinner("Looking up branch and pushing..."):
                                try:
                                    b_res = supabase.table("branches").select("id").eq(
                                        "client_name", sr_client).eq("outlet", sr_outlet).limit(1).execute()
                                    if not b_res.data:
                                        st.error(f"❌ No branch found for {sr_client} / {sr_outlet}. Verify in Branch Config.")
                                    else:
                                        branch_id = b_res.data[0]["id"]
                                        push_df = df_sr.copy()
                                        push_df["branch_id"] = branch_id
                                        push_df["last_modified_by"] = user
                                        rec_list = [
                                            {k: _json_safe(v) for k, v in row.items()}
                                            for row in push_df.to_dict(orient="records")
                                        ]
                                        pushed = 0
                                        for i in range(0, len(rec_list), 500):
                                            supabase.table("production_recipes").upsert(
                                                rec_list[i:i + 500],
                                                on_conflict="branch_id,production_name,product_description"
                                            ).execute()
                                            pushed += len(rec_list[i:i + 500])
                                        st.success(f"✅ Done! {pushed} sub-recipe records pushed for {sr_client} / {sr_outlet}.")
                                        st.balloons()
                                except Exception as e:
                                    st.error(f"❌ Push failed: {e}")

                except Exception as e:
                    st.error(f"❌ File processing error: {e}")

    if t_sales_purchase:
        with t_sales_purchase:
            try:
                push_sales_purchase(user)
            except Exception as e:
                st.error(f"Sales & Purchase failed: {e}")

    if t_create:
        with t_create:
            st.subheader("Account Details")
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Username", key="c_usr")
                new_password = st.text_input("Password", key="c_pwd")
                new_fullname = st.text_input("Full Name", key="c_name")
                role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                new_role = st.selectbox("Role", role_options, key="c_role")
            with col2:
                available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger", "recipes", "recipes report", "production", "purchase-orders", "variance", "live"]
                new_modules = st.multiselect("App Access", available_modules, default=["waste"], key="c_mod")

            col_ce1, col_ce2, col_ce3 = st.columns([3, 3, 1])
            with col_ce1:
                new_email = st.text_input("📧 Email", placeholder="user@example.com", key="c_email")
            with col_ce2:
                new_phone = st.text_input("📞 Phone", placeholder="+961 xx xxx xxx", key="c_phone")
            with col_ce3:
                st.write("")
                new_inv_reminder = st.checkbox("📅 Inv. Reminder", value=False, key="c_inv_reminder")
                new_cost_reminder = st.checkbox("💰 Cost Reminder", value=False, key="c_cost_reminder")
                new_transfer_notif = st.checkbox("🔄 Transfer Notif.", value=False, key="c_transfer_notif")

            use_allowed = st.checkbox("🔓 Allowed Clients", key="c_use_allowed")
            if use_allowed:
                new_allowed_clients = st.multiselect("🏢 Allowed Clients", clients_list, key="c_allowed_clients")
                new_client = "All"
                new_outlet = "All"
                new_locations = ["All"]
            else:
                new_allowed_clients = []
                col3, col4, col5 = st.columns(3)
                with col3:
                    new_client = st.selectbox("🏢 Select Client", ["All"] + clients_list, key="c_client")
                with col4:
                    outlets_for_create = get_outlets_for_client(new_client if new_client != "All" else None)
                    new_outlet = st.selectbox("🏠 Select Outlet", ["All"] + outlets_for_create, key="c_outlet")
                with col5:
                    areas_for_create = get_areas_for_outlet(new_outlet if new_outlet != "All" else None)
                    new_locations = st.multiselect("📍 Select Area(s)", ["All"] + areas_for_create, default=["All"], key="c_loc")

            if st.button("CREATE USER", type="primary", width="stretch"):
                if not new_username.strip() or not new_password.strip():
                    st.error("❌ Username and password are required.")
                else:
                    new_user_data = {
                        "username": new_username.strip().lower(),
                        "password": hash_password(new_password.strip()),
                        "full_name": new_fullname.strip(),
                        "role": new_role, "client_name": new_client, "outlet": new_outlet,
                        "location": ", ".join(new_locations), "module": ", ".join(new_modules),
                        "allowed_clients": ", ".join(new_allowed_clients),
                        "email": new_email.strip().lower() or None,
                        "phone": new_phone.strip() or None,
                        "inv_reminder": new_inv_reminder,
                        "cost_reminder": new_cost_reminder,
                        "transfer_notification": new_transfer_notif,
                    }
                    supabase.table("users").insert([new_user_data]).execute()
                    st.success("✅ User created!")

    # ==========================================
    # TAB: MANAGE USERS (Super Admin Only)
    # ==========================================
    if t_view:
        with t_view:
            try:
                res = supabase.table("users").select("*").execute()
                if res.data:
                    df_u = pd.DataFrame(res.data)
                    u_sel = st.selectbox("Select User to Edit", sorted(df_u['username'].tolist()), key="e_user_sel")
                    u_data = df_u[df_u['username'] == u_sel].iloc[0]
                    
                    st.divider()
                    st.subheader(f"⚙️ Editing User: {u_sel}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        e_pass = st.text_input("🔑 New Password (leave blank to keep current)", value="", type="password", key=f"e_pass_{u_sel}")
                        e_fullname = st.text_input("Full Name", value=u_data.get('full_name', ''), key=f"e_fullname_{u_sel}")

                        role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                        e_role_index = role_options.index(u_data['role']) if u_data['role'] in role_options else 0
                        e_role = st.selectbox("Role", role_options, index=e_role_index, key=f"e_role_{u_sel}")

                    with col2:
                        available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger", "recipes", "recipes report", "production", "purchase-orders", "variance","live"]
                        raw_mods = u_data.get('module', '') or ''
                        current_mods = [m.strip().lower() for m in str(raw_mods).split(',') if m.strip()]
                        if not current_mods:
                            current_mods = ["waste"]
                        valid_mods = [m for m in current_mods if m in available_modules]
                        e_modules = st.multiselect("📱 App Access", available_modules, default=valid_mods, key=f"e_modules_{u_sel}")

                    col_ee1, col_ee2, col_ee3 = st.columns([3, 3, 1])
                    with col_ee1:
                        e_email = st.text_input("📧 Email", value=u_data.get('email', '') or '', key=f"e_email_{u_sel}")
                    with col_ee2:
                        e_phone = st.text_input("📞 Phone", value=u_data.get('phone', '') or '', key=f"e_phone_{u_sel}")
                    with col_ee3:
                        st.write("")
                        e_inv_reminder = st.checkbox("📅 Inv. Reminder", value=bool(u_data.get('inv_reminder', False)), key=f"e_inv_reminder_{u_sel}")
                        e_cost_reminder = st.checkbox("💰 Cost Reminder", value=bool(u_data.get('cost_reminder', False)), key=f"e_cost_reminder_{u_sel}")
                        e_transfer_notif = st.checkbox("🔄 Transfer Notif.", value=bool(u_data.get('transfer_notification', False)), key=f"e_transfer_notif_{u_sel}")

                    raw_allowed = u_data.get('allowed_clients', '') or ''
                    current_allowed = [c.strip() for c in str(raw_allowed).split(',') if c.strip()]
                    valid_allowed = [c for c in current_allowed if c in clients_list]

                    e_use_allowed = st.checkbox("🔓 Allowed Clients", value=bool(valid_allowed), key=f"e_use_allowed_{u_sel}")
                    if e_use_allowed:
                        e_allowed_clients = st.multiselect("🏢 Allowed Clients", clients_list, default=valid_allowed, key=f"e_allowed_{u_sel}")
                        e_client = "All"
                        e_outlet = "All"
                        e_locations = ["All"]
                    else:
                        e_allowed_clients = []
                        col3, col4, col5 = st.columns(3)
                        with col3:
                            c_index = (["All"] + clients_list).index(u_data['client_name']) if u_data['client_name'] in (["All"] + clients_list) else 0
                            e_client = st.selectbox("🏢 Select Client", ["All"] + clients_list, index=c_index, key=f"e_client_{u_sel}")

                        outlets_for_edit = get_outlets_for_client(e_client if e_client != "All" else None)
                        with col4:
                            o_list   = ["All"] + outlets_for_edit
                            o_index  = o_list.index(u_data['outlet']) if u_data['outlet'] in o_list else 0
                            e_outlet = st.selectbox("🏠 Select Outlet", o_list, index=o_index, key=f"e_outlet_{u_sel}")

                        areas_for_edit = get_areas_for_outlet(e_outlet if e_outlet != "All" else None)
                        with col5:
                            l_list       = ["All"] + areas_for_edit
                            current_locs = [l.strip() for l in str(u_data.get('location', '')).split(',') if l.strip()]
                            valid_locs   = [l for l in current_locs if l in l_list] or ["All"]
                            e_locations  = st.multiselect("📍 Select Area(s)", l_list, default=valid_locs, key=f"e_loc_{u_sel}")

                    st.write("")
                    if st.button("💾 Save User Changes", type="primary", width="stretch"):
                        update_payload = {
                            "password": hash_password(e_pass.strip()) if e_pass.strip() else u_data.get('password'),
                            "full_name": e_fullname,
                            "role": e_role,
                            "module": ", ".join(e_modules),
                            "client_name": e_client,
                            "outlet": e_outlet,
                            "location": ", ".join(e_locations),
                            "allowed_clients": ", ".join(e_allowed_clients),
                            "email": e_email.strip() or None,
                            "phone": e_phone.strip() or None,
                            "inv_reminder": e_inv_reminder,
                            "cost_reminder": e_cost_reminder,
                            "transfer_notification": e_transfer_notif,
                        }
                        supabase.table("users").update(update_payload).eq("username", u_sel).execute()
                        st.success(f"✅ User '{u_sel}' updated successfully!")
                        st.rerun()
            except Exception as e:
                st.error(f"❌ Error loading user manager: {e}")

    # ==========================================
    # TAB: MANAGE SUPPLIERS
    # ==========================================
    if t_supp:
        with t_supp:
            st.markdown("#### 🚚 Supplier Management")
            try:
                s_res = supabase.table("suppliers").select("*").execute()
                existing_s = pd.DataFrame(s_res.data) if s_res.data else pd.DataFrame(columns=["supplier_name"])
                
                c1, c2 = st.columns(2)
                with c1:
                    with st.form("add_supp", clear_on_submit=True):
                        n_s = st.text_input("New Supplier Name")
                        if st.form_submit_button("➕ Add Supplier"):
                            clean_n = n_s.strip().lower()
                            existing_list = [x.lower() for x in existing_s['supplier_name'].tolist()]
                            if clean_n in existing_list:
                                st.warning("⚠️ Already exists!")
                            else:
                                supabase.table("suppliers").insert({"supplier_name": n_s.title()}).execute()
                                st.success("Added!")
                                st.rerun()
                with c2:
                    st.write("**Current List:**")
                    st.dataframe(existing_s[['supplier_name']].sort_values('supplier_name'), hide_index=True, width="stretch")
                    s_del = st.selectbox("Delete Supplier", existing_s['supplier_name'].tolist(), index=None)
                    if st.button("🗑️ Delete"):
                        supabase.table("suppliers").delete().eq("supplier_name", s_del).execute()
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    # ==========================================
    # TAB: LIVE DATA EDITOR (The God Mode)
    # ==========================================
    if t_edit:
        with t_edit:
            st.markdown("#### 📝 Live Database Editor")
            st.info("💡 Double-click any cell to edit it. When you are finished, click the Save button at the bottom.")
            
            table_to_edit = st.selectbox("🗄️ Select Table to Edit:", ["waste_logs", "invoices_log", "ledger_logs"])
            
            try:
                res = supabase.table(table_to_edit).select("*").order("id", desc=True).limit(150).execute()
                
                if res.data:
                    df_edit = pd.DataFrame(res.data)
                    
                    edited_df = st.data_editor(
                        df_edit,
                        width="stretch",
                        disabled=["id", "created_at"],
                        hide_index=True,
                        key=f"editor_{table_to_edit}"
                    )
                    
                    st.write("")
                    if st.button(f"💾 Save Changes to {table_to_edit}", type="primary", width="stretch"):
                        with st.spinner("Scanning for changes and updating cloud..."):
                            updates_made = 0
                            
                            safe_edited_df = edited_df.fillna('')
                            safe_orig_df = df_edit.fillna('')
                            
                            for index, new_row in safe_edited_df.iterrows():
                                old_row = safe_orig_df.loc[index]
                                
                                if new_row.to_dict() != old_row.to_dict():
                                    row_id = new_row['id']
                                    update_payload = edited_df.loc[index].drop(['id', 'created_at']).to_dict()
                                    supabase.table(table_to_edit).update(update_payload).eq("id", row_id).execute()
                                    updates_made += 1
                            
                            if updates_made > 0:
                                st.success(f"✅ Successfully updated {updates_made} record(s)!")
                                st.rerun()
                            else:
                                st.info("No changes were detected.")
                else:
                    st.warning("No records found in this table.")
            except Exception as e:
                st.error(f"❌ Error loading data: {e}")

    # ==========================================
    # TAB: CLIENTS
    # ==========================================
    if t_clients:
        with t_clients:
            render_clients(supabase)

    # ==========================================
    # TAB: BRANCH CONFIG
    # ==========================================
    if t_branch_config:
        with t_branch_config:
            render_branch_config(user, role)