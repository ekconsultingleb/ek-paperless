import io
import json
import re
import calendar as _cal
import streamlit as st
import pandas as pd
from datetime import date as _date, datetime as _datetime
from supabase import create_client, Client
from modules.clients import render_clients
from modules.nav_helper import hash_password
from modules.worldwide_master_items import render_worldwide_admin, bulk_sync_from_autocalc

# ── Auto Calc helpers (ported from auto_calc_reader/reader.py) ─────────────────

_AC_MONTHS = {
"january": 1, "february": 2, "march": 3, "april": 4,
"may": 5, "june": 6, "july": 7, "august": 8,
"september": 9, "october": 10, "november": 11, "december": 12,
}
_AC_ERRORS = {"#div/0!", "#n/a", "#ref!", "#value!", "#name?", "#null!", "#num!"}

def _ac_last_day(year: int, month: int) -> _date:
    return _date(year, month, _cal.monthrange(year, month)[1])

def _ac_detect_month(filename: str) -> str | None:
    name = filename.lower().rsplit(".", 1)[0]
    for mname, mnum in _AC_MONTHS.items():
        if mname[:3] in name or mname in name:
            ym = re.search(r"(20\d{2})", name)
            year = int(ym.group(1)) if ym else _datetime.now().year
            return _ac_last_day(year, mnum).strftime("%Y-%m-%d")
    m = re.search(r"(20\d{2})[-_]?(0[1-9]|1[0-2])", name)
    if m:
        return _ac_last_day(int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d")
    return None

def _ac_clean_value(val):
    if val is None:
        return None
    try:
        if pd.isnull(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, str):
        s = val.strip()
        if s.lower() in _AC_ERRORS:
            return None
        if s.upper() in {m.upper() for m in _AC_MONTHS}:
            return "__MONTH_NAME__"
        return s if s else None
    if isinstance(val, (_datetime, _date)):
        try:
            d = val if isinstance(val, _date) and not isinstance(val, _datetime) else val.date()
            return d.strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None
    if isinstance(val, float) and val != val:
        return None
    return val

def _ac_serial_to_date(serial) -> str | None:
    try:
        from datetime import timedelta
        return (_date(1899, 12, 30) + timedelta(days=int(serial))).strftime("%Y-%m-%d")
    except Exception:
        return None

def _ac_read_sheet(file_bytes: bytes, sheet_name: str, sheet_config: dict,
                   client_name: str, fallback_month: str) -> list[dict]:
    col_map: dict = sheet_config["columns"]
    month_col: str | None = sheet_config.get("month_column")
    month_from_file: bool = sheet_config.get("month_from_file_name", False)
    try:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=0)
    except Exception:
        return []
    available = {str(c).strip(): c for c in df.columns}
    mapped = {ec: dc for ec, dc in col_map.items() if ec in available}
    if not mapped:
        return []
    rows = []
    for _, raw in df.iterrows():
        record = {dc: _ac_clean_value(raw.get(ec)) for ec, dc in mapped.items()}
        meaningful = {k: v for k, v in record.items() if k not in ("month", "client_name")}
        if all(v is None or v == 0 or v == "**MONTH_NAME**" for v in meaningful.values()):
            continue
        record["client_name"] = client_name
        if month_col and month_col in col_map:
            db_col = col_map[month_col]
            val = record.get(db_col)
            if val and val != "**MONTH_NAME**":
                if isinstance(val, (int, float)) and 30000 < val < 60000:
                    record[db_col] = _ac_serial_to_date(int(val))
            else:
                record[db_col] = fallback_month
        elif month_from_file or month_col is None:
            if "month" not in record or record.get("month") in (None, "**MONTH_NAME**"):
                record["month"] = fallback_month
        rows.append(record)
    return rows

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
        tabs = st.tabs(["📤 Master Sync", "➕ Create User", "👥 Manage Users", "🚚 Manage Suppliers", "📝 Edit Data", "🏢 Clients", "📊 Auto Calc", "🌍 Global Registry"])
        t_sync, t_create, t_view, t_supp, t_edit, t_clients, t_ac, t_global = tabs
    elif is_normal_admin:
        st.info("🛡️ Admin Mode: Access to sync and onboard users/suppliers.")
        tabs = st.tabs(["📤 Master Sync", "➕ Create User", "🚚 Manage Suppliers", "📝 Edit Data", "🏢 Clients", "📊 Auto Calc"])
        t_sync, t_create, t_supp, t_edit, t_clients, t_ac = tabs[0], tabs[1], tabs[2], tabs[3], tabs[4], tabs[5]
        t_view = t_global = None
    else:
        st.info("🏢 HQ Manager Mode: Access to sync the Master Items database.")
        tabs = st.tabs(["📤 Master Sync"])
        t_sync = tabs[0]
        t_create = t_view = t_supp = t_edit = t_clients = t_ac = t_global = None

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

            # ── Parse Inventory file ───────────────────────────────────────
            def parse_inventory(f, client, outlet, location):
                raw  = pd.read_excel(f, header=None)
                data_rows = _clean_file(raw)
                records = []
                cat = ""
                sub = ""
                i = 0
                n = len(data_rows)
                while i < n:
                    row = data_rows[i]
                    a, b, c = row[0], row[1], row[2]
                    d = row[3]

                    if _is_label(row):
                        ahead = _next_label_count(data_rows, i)
                        if ahead >= 2:
                            cat = proper(str(a)); sub = ""
                        elif ahead == 1:
                            pass  # Division row — skip
                        else:
                            sub = proper(str(a))
                        i += 1

                    elif not _is_empty(a) and isinstance(a, (int, float)) and not _is_empty(b):
                        try:
                            int(float(str(a)))
                        except:
                            i += 1; continue
                        item_name  = proper(str(c)) if not _is_empty(c) else ""
                        count_unit = (proper(str(row[5])) if len(row) > 5 and not _is_empty(row[5])
                                      else proper(str(d)) if not _is_empty(d) else "")
                        if (str(b).lower().startswith("xxx") or
                            str(c).lower().startswith("xxx") if not _is_empty(c) else False or
                            cat.lower().startswith("xxx") or
                            sub.lower().startswith("xxx")):
                            i += 1; continue
                        if item_name:
                            records.append({
                                "client_name": client, "outlet": outlet, "location": location,
                                "item_type": "Inventory", "category": cat, "sub_category": sub,
                                "product_code": proper(str(b)), "item_name": item_name,
                                "count_unit": count_unit,
                            })
                        i += 1
                    else:
                        i += 1
                return pd.DataFrame(records)

            # ── Parse Menu Items file ──────────────────────────────────────
            def parse_menu_items(f, client, outlet, location):
                """
                Mirrors the VBA macro (ForClaude) exactly:

                1.  Remove timestamp rows (col A is a datetime).
                2.  Remove "Description" column-header rows (col B = "Description").
                3.  Insert a new empty column A (all existing columns shift right).
                4.  Delete cell B8 and shift col B up by one from that row.
                5.  Remove rows where col B (orig col A) = "Item ID".
                6.  Remove rows where col B (orig col A) is empty.
                    → 442 rows remain, mix of item rows and category/sub-cat rows.
                7.  Delete first 2 rows (restaurant name + blank).
                8.  Category formula on new col A:
                        IF(AND(orig_B[i]="", orig_B[i+1]="", orig_B[i+2]=""),
                           orig_A[i], "Null")
                    orig_B = Description column (always empty on non-item rows after
                    step 6 because item rows have Description in orig_B, category/sub
                    rows do not).  Three consecutive empty orig_B rows only occur at
                    major section breaks (BEVERAGES, FOOD, NYE, OTHERS) where Omega
                    inserts a timestamp + blank + Description header that step 1/2
                    removed, leaving a 3-row gap.
                9.  Fill down col A (category).
                10. Copy orig_A into a new col B (sub-category source),
                    clear numeric values (item IDs), fill down.
                11. Remove rows where orig_B (Description / item name) is empty
                    → keeps only actual item rows.
                """
                raw = pd.read_excel(f, header=None)
                df  = raw.copy().astype(object)

                # ── Step 1: remove timestamp rows ──────────────────────────
                df = df[~df.iloc[:, 0].apply(
                    lambda v: isinstance(v, (pd.Timestamp, _dt))
                )].reset_index(drop=True)

                # ── Step 2: remove column-header rows (col B = "Description") ─
                df = df[~df.iloc[:, 1].apply(
                    lambda v: str(v).strip() == "Description"
                )].reset_index(drop=True)

                # ── Step 3: insert new col A (index 0) ─────────────────────
                df.insert(0, "_cat", np.nan)
                # positions: 0=_cat, 1=orig_A(item_id), 2=orig_B(Description),
                #            3=orig_C(Menu Description), 4=orig_D(Kitchen)…

                # ── Step 4: delete B8 (index 7 of col pos-1), shift up ─────
                col1 = df.iloc[:, 1].tolist()
                col1.pop(7)
                col1.append(np.nan)
                df.iloc[:, 1] = col1

                # ── Step 5: remove "Item ID" rows in col pos-1 ─────────────
                df = df[~df.iloc[:, 1].apply(
                    lambda v: str(v).strip() == "Item ID"
                )].reset_index(drop=True)

                # ── Step 6: remove rows where col pos-1 (orig_A) is empty ──
                df = df[~df.iloc[:, 1].apply(_is_empty)].reset_index(drop=True)

                # ── Step 7: drop first 2 rows (title + blank) ──────────────
                df = df.iloc[2:].reset_index(drop=True)

                n = len(df)

                # ── Step 8: category formula ────────────────────────────────
                # col pos-2 = orig_B (Description) — always empty on
                # category/sub-cat rows; item rows have the item name here.
                # Three consecutive empty orig_B values = major section break.
                cat_col = []
                for i in range(n):
                    b0 = df.iloc[i,     2]
                    b1 = df.iloc[i + 1, 2] if i + 1 < n else None
                    b2 = df.iloc[i + 2, 2] if i + 2 < n else None
                    if _is_empty(b0) and _is_empty(b1) and _is_empty(b2):
                        cat_col.append(df.iloc[i, 1])   # orig_A value = category name
                    else:
                        cat_col.append(None)
                df.iloc[:, 0] = cat_col

                # ── Step 9: fill down category ──────────────────────────────
                last_cat = None
                for i in range(n):
                    if not _is_empty(df.iloc[i, 0]):
                        last_cat = df.iloc[i, 0]
                    else:
                        df.iloc[i, 0] = last_cat

                # ── Step 10: sub-category ───────────────────────────────────
                # Copy orig_A (pos-1) into a new col (pos-1 becomes sub),
                # clear rows where the value is numeric (those are item IDs),
                # then fill down.
                sub_source = df.iloc[:, 1].tolist()
                df.insert(1, "_sub", sub_source)
                # positions now: 0=_cat, 1=_sub, 2=orig_A, 3=orig_B(Desc)…

                for i in range(n):
                    v = df.iloc[i, 1]
                    try:
                        if not _is_empty(v) and float(str(v)) > 0:
                            df.iloc[i, 1] = None
                    except (ValueError, TypeError):
                        pass  # text value → keep as sub-category label

                last_sub = None
                for i in range(n):
                    if not _is_empty(df.iloc[i, 1]):
                        last_sub = df.iloc[i, 1]
                    else:
                        df.iloc[i, 1] = last_sub

                # ── Step 11: keep only item rows (orig_B / Description filled) ─
                df = df[~df.iloc[:, 3].apply(_is_empty)].reset_index(drop=True)

                # ── Build output records ────────────────────────────────────
                records = []
                for _, row in df.iterrows():
                    category    = proper(str(row.iloc[0])) if not _is_empty(row.iloc[0]) else ""
                    sub_cat     = proper(str(row.iloc[1])) if not _is_empty(row.iloc[1]) else ""
                    product_code = str(int(float(str(row.iloc[2])))) \
                                   if not _is_empty(row.iloc[2]) \
                                   and isinstance(row.iloc[2], (int, float)) \
                                   else str(row.iloc[2]) if not _is_empty(row.iloc[2]) else ""
                    item_name   = proper(str(row.iloc[3]))

                    # Skip xxx items / categories / sub-categories
                    if (item_name.lower().startswith("xxx") or
                            category.lower().startswith("xxx") or
                            sub_cat.lower().startswith("xxx")):
                        continue

                    if not item_name:
                        continue

                    records.append({
                        "client_name":  client,
                        "outlet":       outlet,
                        "location":     location,
                        "item_type":    "Menu Items",
                        "category":     category,
                        "sub_category": sub_cat,
                        "product_code": product_code,
                        "item_name":    item_name,
                        "count_unit":   "Unit",
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
                        df_inv = parse_inventory(inv_file, final_client, final_outlet, final_location)
                        st.markdown(f"**Inventory Items:** {len(df_inv)} rows cleaned")
                        st.dataframe(df_inv.head(10), use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.error(f"❌ Inventory parse error: {e}")

                if menu_file:
                    try:
                        df_menu_raw = parse_menu_items(menu_file, final_client, final_outlet, final_location)

                        # Auto-flag modifiers as unchecked; real items as checked
                        df_menu_raw.insert(0, "include", ~df_menu_raw.apply(_is_modifier_row, axis=1))

                        auto_excluded = int((~df_menu_raw["include"]).sum())
                        st.markdown(
                            f"**Menu Items:** {len(df_menu_raw)} rows parsed — "
                            f"{auto_excluded} auto-flagged as modifiers (unchecked). "
                            f"Review below and adjust before pushing."
                        )

                        edited_menu = st.data_editor(
                            df_menu_raw[["include", "category", "sub_category", "product_code", "item_name"]],
                            column_config={
                                "include": st.column_config.CheckboxColumn("✅ Include", default=True, width="small"),
                            },
                            hide_index=True,
                            use_container_width=True,
                            key="menu_editor",
                        )

                        # Rebuild df_menu using the admin's selections
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
                                  use_container_width=True, key="omega_push"):
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
                        if st.button("🚀 Run Smart Sync", type="primary", use_container_width=True):
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
                available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger"]
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

            if st.button("🚀 CREATE USER", type="primary", use_container_width=True):
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
                        available_modules = ["waste", "cash", "inventory", "transfers", "dashboard", "invoices", "ledger"]
                        current_mods = [m.strip() for m in str(u_data.get('module', '')).split(',')] if str(u_data.get('module', '')) else ["waste"]
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
                    if st.button("💾 Save User Changes", type="primary", use_container_width=True):
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
                    st.dataframe(existing_s[['supplier_name']].sort_values('supplier_name'), hide_index=True, use_container_width=True)
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
                        use_container_width=True,
                        disabled=["id", "created_at"],
                        hide_index=True,
                        key=f"editor_{table_to_edit}"
                    )
                    
                    st.write("")
                    if st.button(f"💾 Save Changes to {table_to_edit}", type="primary", use_container_width=True):
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
    # TAB: AUTO CALC UPLOAD
    # ==========================================
    if t_ac:
        with t_ac:
            st.markdown("#### 📊 Auto Calc Upload")
            st.info(
                "Upload the client's Auto Calc Excel file and its JSON config to parse "
                "all sheets and push the monthly data to Supabase. "
                "Existing data for the same client + month is replaced automatically."
            )

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                ac_excel = st.file_uploader(
                    "📊 Auto Calc Excel (.xlsx)", type=["xlsx"], key="ac_excel_file")
            with col_f2:
                ac_json = st.file_uploader(
                    "⚙️ Client Config (.json)", type=["json"], key="ac_json_file")

            ac_month_override = st.text_input(
                "📅 Month override (YYYY-MM-DD) — leave blank to auto-detect from filename",
                key="ac_month_override"
            )

            if ac_excel and ac_json:
                try:
                    config = json.load(ac_json)
                except Exception as e:
                    st.error(f"❌ Could not parse JSON config: {e}")
                    config = None

                if config:
                    ac_client   = config.get("client_name", "")
                    ac_sheets   = config.get("active_sheets", {})
                    skip_sheets = set(config.get("skip_sheets", []))

                    fallback_month = ac_month_override.strip() or _ac_detect_month(ac_excel.name)

                    if not fallback_month:
                        st.error(
                            "Could not detect month from the filename. "
                            "Please fill in the month override field above (e.g. 2026-02-28)."
                        )
                    else:
                        st.markdown(f"**Client:** {ac_client} &nbsp;|&nbsp; **Month:** {fallback_month}")

                        file_bytes = ac_excel.read()

                        with st.spinner("Parsing sheets…"):
                            sheet_results: dict[str, list[dict]] = {}
                            skipped = []
                            for sheet_name, sheet_cfg in ac_sheets.items():
                                if sheet_name in skip_sheets:
                                    skipped.append(sheet_name)
                                    continue
                                rows = _ac_read_sheet(
                                    file_bytes, sheet_name, sheet_cfg,
                                    ac_client, fallback_month
                                )
                                table = sheet_cfg["supabase_table"]
                                if rows:
                                    sheet_results[table] = rows
                                else:
                                    skipped.append(sheet_name)

                        total_rows = sum(len(v) for v in sheet_results.values())
                        st.markdown(
                            f"**{total_rows} rows** parsed across "
                            f"**{len(sheet_results)} tables** "
                            f"({len(skipped)} sheets skipped / empty)"
                        )

                        if sheet_results:
                            with st.expander("Preview parsed data"):
                                for table, rows in sheet_results.items():
                                    st.markdown(f"**{table}** — {len(rows)} rows")
                                    st.dataframe(
                                        pd.DataFrame(rows).head(5),
                                        use_container_width=True, hide_index=True
                                    )

                            st.divider()
                            st.warning(
                                f"Pushing will **delete** all existing rows for "
                                f"**{ac_client}** / **{fallback_month}** in each target table, "
                                f"then insert the new data."
                            )

                            if st.button(
                                "🚀 Push to Supabase", type="primary",
                                use_container_width=True, key="ac_push_btn"
                            ):
                                with st.spinner("Pushing to Supabase…"):
                                    pushed_total = 0
                                    errors = []
                                    for table, rows in sheet_results.items():
                                        try:
                                            supabase.table(table).delete()\
                                                .eq("client_name", ac_client)\
                                                .eq("month", fallback_month)\
                                                .execute()
                                        except Exception as e:
                                            pass
                                        try:
                                            for i in range(0, len(rows), 500):
                                                supabase.table(table).insert(rows[i:i+500]).execute()
                                            pushed_total += len(rows)
                                        except Exception as e:
                                            errors.append(f"{table}: {e}")

                                    try:
                                        supabase.table("ac_upload_log").insert({
                                            "client_name": ac_client,
                                            "month": fallback_month,
                                            "uploaded_by": user,
                                            "file_name": ac_excel.name,
                                            "status": "partial" if errors else "success",
                                            "notes": (
                                                "; ".join(errors) if errors
                                                else f"{pushed_total} rows across {len(sheet_results)} tables"
                                            )
                                        }).execute()
                                    except Exception:
                                        pass

                                    if errors:
                                        st.error("Some tables failed:\n" + "\n".join(errors))
                                    else:
                                        st.success(
                                            f"✅ Done! {pushed_total} rows pushed for "
                                            f"{ac_client} / {fallback_month}."
                                        )
                                        st.balloons()
                                        # Sync costs to worldwide_master_items
                                        cost_rows = [
                                            r for rows in sheet_results.values()
                                            for r in rows
                                            if r.get("product_code") and r.get("cost_per_unit") is not None
                                        ]
                                        if cost_rows:
                                            try:
                                                client_region_res = supabase.table("clients").select("region").eq("client_name", ac_client).maybe_single().execute()
                                                client_region = (client_region_res.data or {}).get("region", "Global")
                                            except Exception:
                                                client_region = "Global"
                                            bulk_sync_from_autocalc(
                                                supabase=supabase,
                                                cost_rows=cost_rows,
                                                region=client_region,
                                                source_client=ac_client,
                                            )
                        else:
                            st.warning("No data rows found in any sheet. Check the config column names match the Excel headers.")

    # ==========================================
    # TAB: GLOBAL REGISTRY
    # ==========================================
    if t_global:
        with t_global:
            render_worldwide_admin(supabase, role)