import streamlit as st
import pandas as pd
from supabase import create_client, Client
from modules.clients import render_clients
from modules.nav_helper import hash_password
from modules.worldwide_master_items import render_worldwide_admin
from modules.push_to_database import render_push_to_database

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
        tabs = st.tabs(["📤 Master Sync", "🗄️ Push to Database", "➕ Create User", "👥 Manage Users", "🚚 Manage Suppliers", "📝 Edit Data", "🏢 Clients", "🌍 Global Registry"])
        t_sync, t_push_db, t_create, t_view, t_supp, t_edit, t_clients, t_global = tabs
        t_ac = None
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: Access to sync and onboard users/suppliers.")
        tabs = st.tabs(["📤 Master Sync", "🗄️ Push to Database", "➕ Create User", "🚚 Manage Suppliers", "📝 Edit Data", "🏢 Clients"])
        t_sync, t_push_db, t_create, t_supp, t_edit, t_clients = tabs[0], tabs[1], tabs[2], tabs[3], tabs[4], tabs[5]
        t_view = t_ac = t_global = None
    else:
        st.info("🏢 HQ Manager Mode: Access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Sync"])
        t_sync = tabs[0]
        t_push_db = t_create = t_view = t_supp = t_edit = t_clients = t_ac = t_global = None

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
                    sel_client = st.selectbox("🏢 Client", clients_list, key="omega_client")
                with col_c2:
                    outlets = get_outlets_for_client(sel_client)
                    sel_outlet = st.selectbox("🏠 Outlet", outlets if outlets else ["Main"], key="omega_outlet")
                with col_c3:
                    areas = get_areas_for_outlet(sel_outlet)
                    loc_list = areas if areas else ["Main Store"]
                    sel_location = st.selectbox("📍 Location", loc_list, key="omega_location")
                final_client   = sel_client
                final_outlet   = sel_outlet
                final_location = sel_location
            else:
                with col_c1: final_client   = st.text_input("🏢 New Client Name", key="omega_new_client").strip().title()
                with col_c2: final_outlet   = st.text_input("🏠 Outlet Name",     key="omega_new_outlet").strip().title()
                with col_c3: final_location = st.text_input("📍 Location Name",   key="omega_new_location").strip().title()

            if not final_client or not final_outlet or not final_location:
                st.warning("Please fill in Client, Outlet and Location before uploading files.")
                st.stop()

            st.markdown("##### 2. Upload Omega Files")
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                inv_file  = st.file_uploader("📦 Programming Summary — Inventory", 
                                              type=["xlsx"], key="omega_inv")
            with col_f2:
                menu_file = st.file_uploader("🍽️ Programming Summary — Menu Items", 
                                              type=["xlsx"], key="omega_menu")

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

                        # ── Parse Inventory file ───────────────────────────────────────────────────
            def parse_inventory(f, client, outlet, location):
                """
                Parse Omega Programming Summary (Inventory Items).
                Col 0 = item_id (internal, unused), Col 1 = product_code,
                Col 2 = item_name, Col 3 = buying_unit (count_unit).
                Major categories duplicated on consecutive rows (Title then UPPER).
                Sub-categories are single text rows before items.
                """
                import datetime as _dt3

                def _inv_empty(v):
                    if v is None: return True
                    if isinstance(v, float) and pd.isna(v): return True
                    return str(v).strip() in ("", "nan", "None", "NaN")

                def _inv_numeric(v):
                    if _inv_empty(v): return False
                    try: float(str(v)); return True
                    except: return False

                _SKIP = {"lucy lu", "programming summary (inventory items)", "item id"}

                raw = pd.read_excel(f, header=None)
                df  = raw.copy().astype(object)
                n   = len(df)
                records     = []
                current_cat = ""
                current_sub = ""

                for i in range(n):
                    a = df.iloc[i, 0]
                    b = df.iloc[i, 1]
                    c = df.iloc[i, 2] if df.shape[1] > 2 else None
                    d = df.iloc[i, 3] if df.shape[1] > 3 else None

                    # skip timestamps, titles, headers
                    if isinstance(a, (_dt3.datetime, pd.Timestamp)): continue
                    if str(a).strip().lower() in _SKIP: continue
                    if str(a).strip().startswith("REP_I_"): continue

                    b_empty = _inv_empty(b)

                    # category / sub-category: col A text, col B empty
                    if not _inv_empty(a) and not _inv_numeric(a) and b_empty:
                        text   = str(a).strip()
                        next_a = df.iloc[i+1, 0] if i+1 < n else None
                        next_b = df.iloc[i+1, 1] if i+1 < n else None
                        # major category: next row same text (Omega duplicates title→UPPER)
                        if str(next_a).strip().upper() == text.upper() and _inv_empty(next_b):
                            current_cat = proper(text)
                            current_sub = ""
                        else:
                            # skip if this IS the UPPER duplicate
                            prev_a = df.iloc[i-1, 0] if i > 0 else None
                            prev_b = df.iloc[i-1, 1] if i > 0 else None
                            if (not _inv_empty(prev_a) and
                                    str(prev_a).strip().upper() == text.upper() and
                                    _inv_empty(prev_b)):
                                pass  # already set by title-case row above
                            else:
                                current_sub = proper(text)
                        continue

                    # item row: col A numeric, col B = product code
                    if _inv_numeric(a) and not b_empty:
                        product_code = proper(str(b))
                        item_name    = proper(str(c)) if not _inv_empty(c) else ""
                        count_unit   = proper(str(d)) if not _inv_empty(d) else ""

                        if not item_name: continue
                        if (product_code.lower().startswith("xxx") or
                                item_name.lower().startswith("xxx") or
                                current_cat.lower().startswith("xxx") or
                                current_sub.lower().startswith("xxx")): continue

                        records.append({
                            "client_name":  client,
                            "outlet":       outlet,
                            "location":     location,
                            "item_type":    "Inventory",
                            "category":     current_cat,
                            "sub_category": current_sub,
                            "product_code": product_code,
                            "item_name":    item_name,
                            "count_unit":   count_unit,
                        })

                return pd.DataFrame(records)

            # ── Parse Menu Items file ──────────────────────────────────────────────
            def parse_menu_items(f, client, outlet, location):
                """
                Parse Omega Programming Summary (Menu Items) — alternating-row format.
                Name row: col A=NaN, col B=item name.
                ID row:   col A=numeric, col B=NaN  (always follows its name row).
                Major categories duplicated on consecutive rows.
                """
                import datetime as _dt2
            
                def _mi_is_empty(v):
                    if v is None: return True
                    if isinstance(v, float) and pd.isna(v): return True
                    return str(v).strip() in ("", "nan", "None", "NaN")
            
                def _mi_is_numeric(v):
                    if _mi_is_empty(v): return False
                    try: float(str(v)); return True
                    except (ValueError, TypeError): return False
            
                raw = pd.read_excel(f, header=None)
                df  = raw.copy().astype(object)
                n   = len(df)
                records      = []
                current_cat  = ""
                current_sub  = ""
                pending_name = None
            
                for i in range(n):
                    a = df.iloc[i, 0]
                    b = df.iloc[i, 1] if df.shape[1] > 1 else None
                    if isinstance(a, (_dt2.datetime, pd.Timestamp)):
                        pending_name = None; continue
                    if str(b).strip() == "Description":
                        pending_name = None; continue
                    if str(a).strip() == "Item ID":
                        pending_name = None; continue
                    if str(a).strip() == "Programming Summary" and _mi_is_empty(b):
                        continue
                    if not _mi_is_empty(a) and not _mi_is_numeric(a):
                        text   = str(a).strip()
                        next_a = df.iloc[i + 1, 0] if i + 1 < n else None
                        if str(next_a).strip() == text:
                            current_cat = proper(text); current_sub = ""
                        else:
                            current_sub = proper(text)
                        pending_name = None; continue
                    if _mi_is_empty(a) and not _mi_is_empty(b):
                        name = str(b).strip()
                        if name == "Description": continue
                        pending_name = proper(name); continue
                    if _mi_is_numeric(a) and _mi_is_empty(b):
                        if pending_name:
                            item_id = str(int(float(str(a))))
                            if not (pending_name.lower().startswith("xxx") or
                                    current_cat.lower().startswith("xxx") or
                                    current_sub.lower().startswith("xxx")):
                                records.append({
                                    "client_name":  client,
                                    "outlet":       outlet,
                                    "location":     location,
                                    "item_type":    "Menu Items",
                                    "category":     current_cat,
                                    "sub_category": current_sub,
                                    "product_code": item_id,
                                    "item_name":    pending_name,
                                    "count_unit":   "Unit",
                                })
                        pending_name = None; continue
            
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
                            df_inv_raw[["include", "category", "sub_category", "product_code", "item_name", "count_unit"]],
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
                            df_menu_raw[["include", "category", "sub_category", "product_code", "item_name"]],
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
                                combined = combined.fillna("")
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
            uploaded_file = st.file_uploader("Upload Master Items List", type=["csv", "xlsx"])
            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
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
            render_push_to_database(user)

    if t_create:
        with t_create:
            st.subheader("Account Details")
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("👤 Username", key="c_usr")
                new_password = st.text_input("🔑 Password", key="c_pwd")
                new_fullname = st.text_input("📝 Full Name", key="c_name")
                role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                new_role = st.selectbox("🛡️ Role", role_options, key="c_role")
            with col2:
                available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger", "recipes", "overview", "recipes report"]
                new_modules = st.multiselect("📱 App Access", available_modules, default=["waste"], key="c_mod")

            col_ce1, col_ce2, col_ce3 = st.columns([3, 3, 1])
            with col_ce1:
                new_email = st.text_input("📧 Email", placeholder="user@example.com", key="c_email")
            with col_ce2:
                new_phone = st.text_input("📞 Phone", placeholder="+961 xx xxx xxx", key="c_phone")
            with col_ce3:
                st.write("")
                new_inv_reminder = st.checkbox("📅 Inv. Reminder", value=False, key="c_inv_reminder")
                new_cost_reminder = st.checkbox("💰 Cost Reminder", value=False, key="c_cost_reminder")

            col3, col4, col5 = st.columns(3)
            with col3:
                new_client = st.selectbox("🏢 Select Client", ["All"] + clients_list, key="c_client")
            with col4:
                outlets_for_create = get_outlets_for_client(new_client if new_client != "All" else None)
                new_outlet = st.selectbox("🏠 Select Outlet", ["All"] + outlets_for_create, key="c_outlet")
            with col5:
                areas_for_create = get_areas_for_outlet(new_outlet if new_outlet != "All" else None)
                new_locations = st.multiselect("📍 Select Area(s)", ["All"] + areas_for_create, default=["All"], key="c_loc")

            if st.button("🚀 CREATE USER", type="primary", width="stretch"):
                if not new_username.strip() or not new_password.strip():
                    st.error("❌ Username and password are required.")
                else:
                    new_user_data = {
                        "username": new_username.strip(),
                        "password": hash_password(new_password.strip()),
                        "full_name": new_fullname.strip(),
                        "role": new_role, "client_name": new_client, "outlet": new_outlet,
                        "location": ", ".join(new_locations), "module": ", ".join(new_modules),
                        "email": new_email.strip() or None,
                        "phone": new_phone.strip() or None,
                        "inv_reminder": new_inv_reminder,
                        "cost_reminder": new_cost_reminder,
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
                    u_sel = st.selectbox("👤 Select User to Edit", sorted(df_u['username'].tolist()), key="e_user_sel")
                    u_data = df_u[df_u['username'] == u_sel].iloc[0]
                    
                    st.divider()
                    st.subheader(f"⚙️ Editing User: {u_sel}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        e_pass = st.text_input("🔑 New Password (leave blank to keep current)", value="", type="password")
                        e_fullname = st.text_input("📝 Full Name", value=u_data.get('full_name', ''))
                        
                        role_options = ["staff", "chef", "bar manager", "bartender", "storekeeper", "manager", "viewer", "admin", "admin_all"]
                        e_role_index = role_options.index(u_data['role']) if u_data['role'] in role_options else 0
                        e_role = st.selectbox("🛡️ Role", role_options, index=e_role_index)
                        
                    with col2:
                        available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger", "recipes", "overview", "recipes report"]
                        raw_mods = u_data.get('module', '') or ''
                        current_mods = [m.strip().lower() for m in str(raw_mods).split(',') if m.strip()]
                        if not current_mods:
                            current_mods = ["waste"]
                        valid_mods = [m for m in current_mods if m in available_modules]
                        e_modules = st.multiselect("📱 App Access", available_modules, default=valid_mods)

                    col_ee1, col_ee2, col_ee3 = st.columns([3, 3, 1])
                    with col_ee1:
                        e_email = st.text_input("📧 Email", value=u_data.get('email', '') or '', key="e_email")
                    with col_ee2:
                        e_phone = st.text_input("📞 Phone", value=u_data.get('phone', '') or '', key="e_phone")
                    with col_ee3:
                        st.write("")
                        e_inv_reminder = st.checkbox("📅 Inv. Reminder", value=bool(u_data.get('inv_reminder', False)), key="e_inv_reminder")
                        e_cost_reminder = st.checkbox("💰 Cost Reminder", value=bool(u_data.get('cost_reminder', False)), key="e_cost_reminder")

                    col3, col4, col5 = st.columns(3)
                    with col3:
                        c_index = (["All"] + clients_list).index(u_data['client_name']) if u_data['client_name'] in (["All"] + clients_list) else 0
                        e_client = st.selectbox("🏢 Select Client", ["All"] + clients_list, index=c_index, key="e_client_box")

                    outlets_for_edit = get_outlets_for_client(e_client if e_client != "All" else None)
                    with col4:
                        o_list   = ["All"] + outlets_for_edit
                        o_index  = o_list.index(u_data['outlet']) if u_data['outlet'] in o_list else 0
                        e_outlet = st.selectbox("🏠 Select Outlet", o_list, index=o_index, key="e_outlet_box")

                    areas_for_edit = get_areas_for_outlet(e_outlet if e_outlet != "All" else None)
                    with col5:
                        l_list       = ["All"] + areas_for_edit
                        current_locs = [l.strip() for l in str(u_data.get('location', '')).split(',') if l.strip()]
                        valid_locs   = [l for l in current_locs if l in l_list] or ["All"]
                        e_locations  = st.multiselect("📍 Select Area(s)", l_list, default=valid_locs, key="e_loc_box")

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
                            "email": e_email.strip() or None,
                            "phone": e_phone.strip() or None,
                            "inv_reminder": e_inv_reminder,
                            "cost_reminder": e_cost_reminder,
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
    # TAB: GLOBAL REGISTRY
    # ==========================================
    if t_global:
        with t_global:
            render_worldwide_admin(supabase, role)