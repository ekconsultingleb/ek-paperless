"""
modules/auto_calc.py
EK Consulting — Auto Calc Reader + Report Generator
Sits inside the Control Panel as a tab (admin_all only).

Tab 1 — Upload & Push:   upload Excel → select client → push to Supabase
Tab 2 — Generate Reports: select client + month → download COGS / Internal PDFs
"""

import io
import json
import re
import calendar
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from supabase import create_client, Client

# ── Supabase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def _sb() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])


# ══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

MONTH_NAMES = {
    "january":1,"february":2,"march":3,"april":4,
    "may":5,"june":6,"july":7,"august":8,
    "september":9,"october":10,"november":11,"december":12
}
ERROR_VALUES = {"#div/0!","#n/a","#ref!","#value!","#name?","#null!","#num!"}

def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])

def detect_month(filename: str):
    name = Path(filename).stem.lower()
    for mn, num in MONTH_NAMES.items():
        if mn[:3] in name or mn in name:
            m = re.search(r"(20\d{2})", name)
            yr = int(m.group(1)) if m else datetime.now().year
            return last_day(yr, num).strftime("%Y-%m-%d")
    m = re.search(r"(20\d{2})[-_]?(0[1-9]|1[0-2])", name)
    if m:
        return last_day(int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d")
    return None

def mlabel(m: str) -> str:
    try: return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%B %Y")
    except: return m

def mshort(m: str) -> str:
    try: return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%b %Y")
    except: return m

def prev_month(m: str) -> str:
    d = datetime.strptime(m[:10], "%Y-%m-%d").date()
    return (d.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")

def excel_serial_to_date(serial):
    try:
        return (date(1899, 12, 30) + timedelta(days=int(serial))).strftime("%Y-%m-%d")
    except: return None

def clean_value(val):
    if val is None: return None
    try:
        if pd.isnull(val): return None
    except (TypeError, ValueError): pass
    if isinstance(val, str):
        s = val.strip()
        if s.lower() in ERROR_VALUES: return None
        if s.upper() in {mn.upper() for mn in MONTH_NAMES}: return "__MONTH_NAME__"
        return s or None
    if isinstance(val, (datetime, date)):
        try:
            v = val if isinstance(val, date) else val.date()
            return v.strftime("%Y-%m-%d")
        except: return None
    if isinstance(val, float) and val != val: return None
    return val

def clean_row(row: dict) -> dict:
    return {k: clean_value(v) for k, v in row.items()}

def is_empty_row(row: dict) -> bool:
    skip = {"month", "client_name"}
    return all(v is None or v == 0 or v == "__MONTH_NAME__"
               for k, v in row.items() if k not in skip)


# ══════════════════════════════════════════════════════════════════════════════
# READER LOGIC  (ported from reader.py)
# ══════════════════════════════════════════════════════════════════════════════

def read_sheet(excel_bytes: bytes, sheet_name: str, sheet_config: dict,
               client_name: str, fallback_month: str):
    """Returns (rows, warnings)."""
    col_map: dict       = sheet_config["columns"]
    month_col = sheet_config.get("month_column")
    month_from_file     = sheet_config.get("month_from_file_name", False)
    warnings            = []

    try:
        df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=sheet_name, header=0)
    except Exception as e:
        return [], [f"Could not read sheet '{sheet_name}': {e}"]

    available = {str(c).strip(): c for c in df.columns}
    mapped, missing = {}, []
    for ec, dc in col_map.items():
        if ec in available: mapped[ec] = dc
        else: missing.append(ec)
    if missing:
        warnings.append(f"Sheet '{sheet_name}': columns not found (skipped): {missing}")
    if not mapped:
        return [], [f"Sheet '{sheet_name}': no mapped columns found."]

    rows = []
    for _, raw in df.iterrows():
        record = {dc: raw.get(ec) for ec, dc in mapped.items()}
        record = clean_row(record)
        if is_empty_row(record): continue
        record["client_name"] = client_name

        # Resolve month
        if month_col and month_col in col_map:
            db_col = col_map[month_col]
            val    = record.get(db_col)
            if val and val != "__MONTH_NAME__":
                if isinstance(val, (int, float)) and 30000 < val < 60000:
                    record[db_col] = excel_serial_to_date(int(val))
            else:
                record[db_col] = fallback_month
        elif month_from_file or month_col is None:
            if record.get("month") in (None, "__MONTH_NAME__"):
                record["month"] = fallback_month

        rows.append(record)
    return rows, warnings


def push_sheet(supabase, table: str, rows: list[dict],
               client_name: str, month: str):
    """Delete existing (client, month) then insert. Returns (count, error)."""
    if not rows: return 0, None
    try:
        supabase.table(table).delete()\
            .eq("client_name", client_name)\
            .eq("month", month).execute()
    except Exception as e:
        pass  # Table may be empty — not fatal

    inserted = 0
    for i in range(0, len(rows), 500):
        batch = rows[i:i+500]
        try:
            supabase.table(table).insert(batch).execute()
            inserted += len(batch)
        except Exception as e:
            return inserted, str(e)
    return inserted, None


def log_upload(supabase, client_name, month, file_name, uploaded_by, status, notes):
    try:
        supabase.table("ac_upload_log").insert({
            "client_name": client_name, "month": month,
            "uploaded_by": uploaded_by, "file_name": file_name,
            "status": status, "notes": notes
        }).execute()
    except: pass


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG LOADER
# ══════════════════════════════════════════════════════════════════════════════

# Configs live in configs/ folder next to this module.
# Falls back to fetching from Supabase ac_configs table if file not found.
CONFIG_DIR = Path(__file__).parent.parent / "configs"

def load_config(client_name: str):
    """Load per-client JSON config by client_name."""
    # Try local file first (snake_case filename)
    slug = client_name.lower().replace(" ", "_")
    for suffix in [slug, slug.split("_")[0]]:
        p = CONFIG_DIR / f"{suffix}.json"
        if p.exists():
            with open(p) as f:
                return json.load(f)
    # Try Supabase ac_configs table as fallback
    try:
        res = _sb().table("ac_configs")\
            .select("config_json")\
            .eq("client_name", client_name)\
            .limit(1).execute()
        if res.data:
            return json.loads(res.data[0]["config_json"])
    except: pass
    return None

def get_available_configs() -> list[str]:
    """Return list of client names that have a config available."""
    clients = []
    if CONFIG_DIR.exists():
        for f in sorted(CONFIG_DIR.glob("*.json")):
            try:
                cfg = json.loads(f.read_text())
                clients.append(cfg.get("client_name", f.stem))
            except: pass
    # Also check Supabase
    try:
        res = _sb().table("ac_configs").select("client_name").execute()
        for r in (res.data or []):
            cn = r["client_name"]
            if cn not in clients:
                clients.append(cn)
    except: pass
    return clients


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR  (ported from report_generator.py — generates PDF in memory)
# ══════════════════════════════════════════════════════════════════════════════

def _fetch(table, client, month):
    r = _sb().table(table).select("*")\
        .eq("client_name", client).eq("month", month).execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

def _fetch_all(table, client):
    r = _sb().table(table).select("*").eq("client_name", client).execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

def get_upload_log(client: str) -> list[dict]:
    try:
        r = _sb().table("ac_upload_log").select("*")\
            .eq("client_name", client).order("created_at", desc=True).execute()
        return r.data or []
    except: return []

def get_pushed_months(client: str) -> list[str]:
    try:
        r = _sb().table("ac_upload_log").select("month")\
            .eq("client_name", client).execute()
        months = sorted({row["month"] for row in (r.data or [])}, reverse=True)
        return months
    except: return []

def generate_cogs_pdf(client: str, month: str) -> bytes:
    """Generate COGS PDF and return as bytes."""
    from modules.report_generator import pdf_cogs, S as make_styles
    cogs_cur  = _fetch("ac_cogs", client, month)
    cogs_prev = _fetch("ac_cogs", client, prev_month(month))
    buf = io.BytesIO()
    # report_generator writes to file — we patch it to write to BytesIO
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        pdf_cogs(tmp_path, client, month, prev_month(month), cogs_cur, cogs_prev, make_styles())
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)

def generate_internal_pdf(client: str, month: str) -> bytes:
    """Generate EK Internal report PDF and return as bytes."""
    from modules.report_generator import pdf_internal, S as make_styles
    cogs_cur  = _fetch("ac_cogs",        client, month)
    cogs_prev = _fetch("ac_cogs",        client, prev_month(month))
    sales_df  = _fetch("ac_sales",       client, month)
    purch_df  = _fetch("ac_purchase",    client, month)
    var_df    = _fetch("ac_variance",    client, month)
    theo_df   = _fetch("ac_theoretical", client, month)
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        pdf_internal(tmp_path, client, month, prev_month(month),
                     cogs_cur, cogs_prev, sales_df, purch_df, var_df, theo_df,
                     make_styles())
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render_auto_calc(supabase=None):
    """
    Call from main.py inside the Auto Calc tab:
        from modules.auto_calc import render_auto_calc
        with t_autocalc:
            render_auto_calc(supabase)
    """
    if supabase is None:
        supabase = _sb()

    st.markdown("#### 📊 Auto Calc")
    st.caption("Upload a finished Auto Calc Excel file to push data to Supabase, then generate client reports.")

    t1, t2, t3, t4 = st.tabs(["📤 Upload & Push", "📄 Generate Reports", "🗂️ Upload History", "⚙️ Config Manager"])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — UPLOAD & PUSH
    # ══════════════════════════════════════════════════════════════════════════
    with t1:
        st.markdown("##### Step 1 — Select Client")

        available_configs = get_available_configs()
        if not available_configs:
            st.warning("No client configs found. Add a JSON config file to the `configs/` folder.")
            return

        col1, col2 = st.columns(2)
        with col1:
            selected_client = st.selectbox(
                "Client", available_configs, key="ac_client")
        with col2:
            month_override = st.text_input(
                "Month override (YYYY-MM-DD)",
                placeholder="Leave blank to detect from filename",
                key="ac_month_override")

        st.markdown("##### Step 2 — Upload Excel File")
        uploaded = st.file_uploader(
            "Auto Calc Excel file", type=["xlsx"], key="ac_file")

        if not uploaded:
            st.info("Upload an Auto Calc Excel file to continue.")
            return

        # Detect month
        fallback_month = month_override.strip() or detect_month(uploaded.name)
        if not fallback_month:
            st.error("Could not detect month from filename. Use the override field (YYYY-MM-DD, last day of month e.g. 2026-02-28).")
            return

        st.success(f"📅 Detected month: **{mlabel(fallback_month)}**")

        # Load config
        config = load_config(selected_client)
        if not config:
            st.error(f"No config found for '{selected_client}'. Add `configs/{selected_client.lower().replace(' ', '_')}.json`.")
            return

        active_sheets: dict = config.get("active_sheets", {})
        skip_sheets: list   = config.get("skip_sheets", [])

        st.markdown("##### Step 3 — Preview")
        excel_bytes = uploaded.read()

        # Parse all sheets
        all_results = {}
        all_warnings = []
        total_rows = 0

        for sheet_name, sheet_config in active_sheets.items():
            if sheet_name in skip_sheets:
                continue
            rows, warns = read_sheet(
                excel_bytes, sheet_name, sheet_config,
                selected_client, fallback_month)
            all_results[sheet_name] = {
                "table": sheet_config["supabase_table"],
                "rows":  rows,
            }
            all_warnings.extend(warns)
            total_rows += len(rows)

        # Show warnings
        if all_warnings:
            with st.expander(f"⚠️ {len(all_warnings)} warnings", expanded=False):
                for w in all_warnings:
                    st.caption(w)

        # Preview table
        preview_data = []
        for sheet_name, res in all_results.items():
            preview_data.append({
                "Sheet": sheet_name,
                "Supabase Table": res["table"],
                "Rows Parsed": len(res["rows"]),
                "Status": "✅ Ready" if res["rows"] else "⚠️ No data"
            })
        st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)
        st.markdown(f"**Total rows to push: {total_rows}**")

        if total_rows == 0:
            st.warning("No data rows found across any sheet. Check the file and config.")
            return

        st.markdown("##### Step 4 — Push to Supabase")
        st.warning(f"This will **delete** existing data for **{selected_client} / {mlabel(fallback_month)}** and replace it.")

        col_push, col_dry = st.columns(2)
        with col_push:
            push_btn = st.button("🚀 Push to Supabase", type="primary",
                                  use_container_width=True, key="ac_push")
        with col_dry:
            dry_btn = st.button("🔍 Dry Run (no push)", use_container_width=True, key="ac_dry")

        if push_btn or dry_btn:
            dry_run = dry_btn
            progress = st.progress(0)
            log_lines = []
            errors = []
            sheets = [s for s, r in all_results.items() if r["rows"]]
            total_pushed = 0

            for i, (sheet_name, res) in enumerate(all_results.items()):
                progress.progress((i + 1) / max(len(all_results), 1))
                if not res["rows"]:
                    log_lines.append(f"↷ {sheet_name}: no data")
                    continue
                if dry_run:
                    log_lines.append(f"[DRY RUN] {sheet_name} → {res['table']}: {len(res['rows'])} rows")
                    total_pushed += len(res["rows"])
                else:
                    count, err = push_sheet(
                        supabase, res["table"], res["rows"],
                        selected_client, fallback_month)
                    if err:
                        log_lines.append(f"✗ {sheet_name} → {res['table']}: ERROR — {err}")
                        errors.append(f"{sheet_name}: {err}")
                    else:
                        log_lines.append(f"✓ {sheet_name} → {res['table']}: {count} rows")
                        total_pushed += count

            progress.progress(1.0)

            with st.expander("📋 Push Log", expanded=True):
                for line in log_lines:
                    st.text(line)

            if not dry_run:
                status = "success" if not errors else "partial"
                notes  = f"{total_pushed} rows pushed" if not errors else "; ".join(errors)
                log_upload(supabase, selected_client, fallback_month,
                           uploaded.name, "EK Team", status, notes)

                if errors:
                    st.error(f"Completed with {len(errors)} error(s). {total_pushed} rows pushed.")
                else:
                    st.success(f"✅ Done! {total_pushed} rows pushed for **{selected_client} / {mlabel(fallback_month)}**.")
                    st.balloons()
            else:
                st.info(f"Dry run complete. {total_pushed} rows would be pushed.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — GENERATE REPORTS
    # ══════════════════════════════════════════════════════════════════════════
    with t2:
        st.markdown("##### Select Client & Month")

        # Get clients that have data
        try:
            r = _sb().table("ac_upload_log").select("client_name").execute()
            pushed_clients = sorted({row["client_name"] for row in (r.data or [])})
        except:
            pushed_clients = available_configs

        if not pushed_clients:
            st.info("No data pushed yet. Use the Upload & Push tab first.")
            return

        col1, col2 = st.columns(2)
        with col1:
            rep_client = st.selectbox("Client", pushed_clients, key="rep_client")
        with col2:
            months = get_pushed_months(rep_client)
            if not months:
                st.warning(f"No data found for {rep_client}.")
                st.stop()
            month_labels = {m: mlabel(m) for m in months}
            sel_label = st.selectbox(
                "Month", list(month_labels.values()), key="rep_month")
            rep_month = [k for k, v in month_labels.items() if v == sel_label][0]

        # Data availability check
        st.markdown("##### Data Available")
        with st.spinner("Checking data..."):
            checks = {
                "COGS":        _fetch("ac_cogs",        rep_client, rep_month),
                "Sales":       _fetch("ac_sales",       rep_client, rep_month),
                "Variance":    _fetch("ac_variance",    rep_client, rep_month),
                "Theoretical": _fetch("ac_theoretical", rep_client, rep_month),
                "Purchase":    _fetch("ac_purchase",    rep_client, rep_month),
            }

        check_data = []
        for name, df in checks.items():
            check_data.append({
                "Dataset": name,
                "Rows": len(df) if not df.empty else 0,
                "Status": "✅" if not df.empty else "⚠️ Missing"
            })
        st.dataframe(pd.DataFrame(check_data), use_container_width=True, hide_index=True)

        if checks["COGS"].empty:
            st.error("COGS data is required to generate reports. Push data first.")
            return

        st.divider()
        st.markdown("##### Download Reports")

        # Financial Overview — uses existing overview module
        st.markdown("**Financial Overview PDF** — uses the Overview module (available in the app)")
        st.caption("Navigate to Overview in the main menu to view and export the Financial Overview.")

        st.divider()

        # COGS Report
        col_cogs, col_int = st.columns(2)

        with col_cogs:
            st.markdown("**COGS Report**")
            if st.button("📄 Generate COGS PDF", use_container_width=True, key="gen_cogs"):
                with st.spinner("Generating COGS report..."):
                    try:
                        cogs_cur  = checks["COGS"]
                        cogs_prev = _fetch("ac_cogs", rep_client, prev_month(rep_month))
                        # Import report_generator functions
                        import sys
                        from pathlib import Path as P
                        sys.path.insert(0, str(P(__file__).parent.parent))
                        from report_generator import pdf_cogs, S as make_styles
                        import tempfile, os
                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                            tmp_path = tmp.name
                        pdf_cogs(tmp_path, rep_client, rep_month,
                                 prev_month(rep_month), cogs_cur, cogs_prev,
                                 make_styles())
                        with open(tmp_path, "rb") as f:
                            pdf_bytes = f.read()
                        os.unlink(tmp_path)

                        slug = rep_client.replace(" ","_").replace("/","-")
                        ml_  = mlabel(rep_month).replace(" ","_")
                        st.download_button(
                            "⬇️ Download COGS PDF",
                            data=pdf_bytes,
                            file_name=f"COGS_{slug}_{ml_}.pdf",
                            mime="application/pdf",
                            key="dl_cogs",
                            use_container_width=True
                        )
                        st.success("Ready to download.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_int:
            st.markdown("**EK Internal Report**")
            if st.button("📄 Generate Internal PDF", use_container_width=True, key="gen_int"):
                with st.spinner("Generating internal report..."):
                    try:
                        import sys
                        from pathlib import Path as P
                        sys.path.insert(0, str(P(__file__).parent.parent))
                        from report_generator import pdf_internal, S as make_styles
                        import tempfile, os

                        cogs_cur  = checks["COGS"]
                        cogs_prev = _fetch("ac_cogs",     rep_client, prev_month(rep_month))
                        sales_df  = checks["Sales"]
                        purch_df  = checks["Purchase"]
                        var_df    = checks["Variance"]
                        theo_df   = checks["Theoretical"]

                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                            tmp_path = tmp.name
                        pdf_internal(tmp_path, rep_client, rep_month,
                                     prev_month(rep_month), cogs_cur, cogs_prev,
                                     sales_df, purch_df, var_df, theo_df,
                                     make_styles())
                        with open(tmp_path, "rb") as f:
                            pdf_bytes = f.read()
                        os.unlink(tmp_path)

                        slug = rep_client.replace(" ","_").replace("/","-")
                        ml_  = mlabel(rep_month).replace(" ","_")
                        st.download_button(
                            "⬇️ Download Internal PDF",
                            data=pdf_bytes,
                            file_name=f"Report_{slug}_{ml_}.pdf",
                            mime="application/pdf",
                            key="dl_int",
                            use_container_width=True
                        )
                        st.success("Ready to download.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.divider()

        # Excel exports
        st.markdown("**Excel Exports**")
        col_var, col_theo = st.columns(2)

        with col_var:
            if st.button("📊 Variance Excel", use_container_width=True, key="gen_var"):
                with st.spinner("Generating..."):
                    try:
                        import sys
                        from pathlib import Path as P
                        sys.path.insert(0, str(P(__file__).parent.parent))
                        from report_generator import excel_variance
                        import tempfile, os
                        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                            tmp_path = tmp.name
                        excel_variance(tmp_path, checks["Variance"], rep_client, rep_month)
                        with open(tmp_path, "rb") as f:
                            xl_bytes = f.read()
                        os.unlink(tmp_path)
                        slug = rep_client.replace(" ","_").replace("/","-")
                        ml_  = mlabel(rep_month).replace(" ","_")
                        st.download_button(
                            "⬇️ Download Variance Excel",
                            data=xl_bytes,
                            file_name=f"Variance_{slug}_{ml_}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_var",
                            use_container_width=True
                        )
                        st.success("Ready to download.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_theo:
            if st.button("📊 Theoretical Excel", use_container_width=True, key="gen_theo"):
                with st.spinner("Generating..."):
                    try:
                        import sys
                        from pathlib import Path as P
                        sys.path.insert(0, str(P(__file__).parent.parent))
                        from report_generator import excel_theoretical
                        import tempfile, os
                        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                            tmp_path = tmp.name
                        excel_theoretical(tmp_path, checks["Theoretical"], rep_client, rep_month)
                        with open(tmp_path, "rb") as f:
                            xl_bytes = f.read()
                        os.unlink(tmp_path)
                        slug = rep_client.replace(" ","_").replace("/","-")
                        ml_  = mlabel(rep_month).replace(" ","_")
                        st.download_button(
                            "⬇️ Download Theoretical Excel",
                            data=xl_bytes,
                            file_name=f"Theoretical_{slug}_{ml_}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dl_theo",
                            use_container_width=True
                        )
                        st.success("Ready to download.")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — UPLOAD HISTORY
    # ══════════════════════════════════════════════════════════════════════════
    with t3:
        st.markdown("##### Upload History")

        try:
            res = _sb().table("ac_upload_log")\
                .select("*").order("created_at", desc=True).limit(100).execute()
            logs = res.data or []
        except Exception as e:
            st.error(f"Could not load upload log: {e}")
            return

        if not logs:
            st.info("No uploads logged yet.")
            return

        df_log = pd.DataFrame(logs)

        # Format columns for display
        display_cols = ["client_name", "month", "file_name",
                        "uploaded_by", "status", "notes", "created_at"]
        display_cols = [c for c in display_cols if c in df_log.columns]

        # Clean up month display
        if "month" in df_log.columns:
            df_log["month"] = df_log["month"].apply(
                lambda m: mlabel(str(m)) if m else "")

        # Color-code status
        if "created_at" in df_log.columns:
            df_log["created_at"] = pd.to_datetime(
                df_log["created_at"], errors="coerce")\
                .dt.strftime("%Y-%m-%d %H:%M")

        st.dataframe(
            df_log[display_cols],
            use_container_width=True,
            hide_index=True
        )

        st.caption(f"Showing last {len(df_log)} uploads.")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — CONFIG MANAGER
    # ══════════════════════════════════════════════════════════════════════════
    with t4:
        st.markdown("##### Config Manager")
        st.caption("Copy an existing client config to onboard a new client. No SQL required.")

        # ── Load all existing configs ─────────────────────────────────────────
        try:
            res = _sb().table("ac_configs").select("client_name, config_json, created_at")\
                .order("client_name").execute()
            existing_configs = res.data or []
        except Exception as e:
            st.error(f"Could not load configs: {e}")
            existing_configs = []

        if not existing_configs:
            st.warning("No configs found in Supabase. Insert the first config manually via SQL.")
            return

        # ── Current configs overview ──────────────────────────────────────────
        st.markdown("**Existing Configs**")
        overview_data = []
        for cfg in existing_configs:
            try:
                cj = cfg["config_json"] if isinstance(cfg["config_json"], dict) \
                     else json.loads(cfg["config_json"])
                sheets = list(cj.get("active_sheets", {}).keys())
                skip   = cj.get("skip_sheets", [])
                overview_data.append({
                    "Client":        cfg["client_name"],
                    "Active Sheets": len(sheets),
                    "Skipped Sheets":len(skip),
                    "Sheet Names":   ", ".join(sheets[:6]) + ("..." if len(sheets) > 6 else ""),
                })
            except:
                overview_data.append({
                    "Client":        cfg["client_name"],
                    "Active Sheets": "—",
                    "Skipped Sheets":"—",
                    "Sheet Names":   "Parse error",
                })

        st.dataframe(pd.DataFrame(overview_data), use_container_width=True, hide_index=True)

        st.divider()

        # ── Copy config to new client ─────────────────────────────────────────
        st.markdown("**Copy Config to New Client**")
        st.caption("Copies the full sheet/column mapping from an existing client. "
                   "Change the name, save — done. You can adjust columns later if needed.")

        existing_names = [c["client_name"] for c in existing_configs]

        col1, col2 = st.columns(2)
        with col1:
            source_client = st.selectbox(
                "Copy from", existing_names, key="cfg_source")
        with col2:
            new_client_name = st.text_input(
                "New client name *",
                placeholder="e.g. Mandaloun",
                key="cfg_new_name")

        # Preview what will be copied
        if source_client:
            source_cfg = next(
                (c for c in existing_configs if c["client_name"] == source_client), None)
            if source_cfg:
                try:
                    cj = source_cfg["config_json"] if isinstance(source_cfg["config_json"], dict) \
                         else json.loads(source_cfg["config_json"])
                    sheets = list(cj.get("active_sheets", {}).keys())
                    st.caption(
                        f"Will copy {len(sheets)} sheets from **{source_client}**: "
                        f"{', '.join(sheets)}")
                except:
                    st.caption("Could not parse source config.")

        col_save, col_blank = st.columns([1, 3])
        with col_save:
            save_btn = st.button(
                "💾 Create Config", type="primary",
                use_container_width=True, key="cfg_save")

        if save_btn:
            if not new_client_name.strip():
                st.error("New client name is required.")
            elif new_client_name.strip() in existing_names:
                st.error(f"'{new_client_name.strip()}' already exists. Choose a different name.")
            else:
                source_cfg = next(
                    (c for c in existing_configs if c["client_name"] == source_client), None)
                if not source_cfg:
                    st.error("Source config not found.")
                else:
                    try:
                        # Deep copy and update client_name
                        cj = source_cfg["config_json"] if isinstance(source_cfg["config_json"], dict) \
                             else json.loads(source_cfg["config_json"])
                        new_cfg = dict(cj)
                        new_cfg["client_name"] = new_client_name.strip()

                        _sb().table("ac_configs").insert({
                            "client_name": new_client_name.strip(),
                            "config_json": new_cfg
                        }).execute()

                        st.success(
                            f"✅ Config created for **{new_client_name.strip()}** "
                            f"(copied from {source_client}).")
                        st.info(
                            "If Mandaloun has different or missing columns, "
                            "the reader will skip them automatically and show warnings "
                            "during the push — no further changes needed.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to create config: {e}")

        st.divider()

        # ── Delete a config ───────────────────────────────────────────────────
        st.markdown("**Delete Config**")
        st.caption("Only removes the config — does not delete any pushed data.")

        col_del1, col_del2 = st.columns([2, 1])
        with col_del1:
            del_target = st.selectbox(
                "Select config to delete", existing_names,
                key="cfg_del_target", index=None,
                placeholder="Select a client...")
        with col_del2:
            st.markdown("<br>", unsafe_allow_html=True)
            del_btn = st.button(
                "🗑️ Delete", use_container_width=True,
                key="cfg_del_btn", type="primary")

        if del_btn:
            if not del_target:
                st.error("Select a client to delete.")
            else:
                try:
                    _sb().table("ac_configs").delete()\
                        .eq("client_name", del_target).execute()
                    st.success(f"✅ Config for '{del_target}' deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")