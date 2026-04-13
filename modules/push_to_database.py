import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


def _bootstrap_supa_import() -> bool:
    root = Path(__file__).resolve().parents[1]
    src_dir = root / "supa import" / "src"
    if not src_dir.exists():
        st.error("`supa import/src` was not found in the project root.")
        return False

    src_dir_str = str(src_dir)
    if src_dir_str not in sys.path:
        sys.path.insert(0, src_dir_str)
    return True


def _ensure_supa_env_from_secrets():
    # Bridge app secrets to the legacy env-based supa_import package.
    # secret_key = key name in secrets.toml, env_key = what db.py reads via os.getenv()
    mapping = {
        "SUPABASE_URL": "url",
        "SUPABASE_KEY": "key",
        "host":         "host",
        "name":         "dbname",   # secrets uses "name", psycopg2 expects "dbname"
        "user":         "user",
        "password":     "password",
        "port":         "port",
    }
    for secret_key, env_key in mapping.items():
        if os.getenv(env_key):
            continue
        val = st.secrets.get(secret_key)
        if val:
            os.environ[env_key] = str(val)


def render_push_to_database(user: str):
    st.markdown("#### Push to Database")
    st.caption("Upload Auto Calc report files and push validated data into the database.")

    if not _bootstrap_supa_import():
        return

    _ensure_supa_env_from_secrets()

    try:
        from supa_import.config import SHEET_CONFIG
        from supa_import.db import get_pg_connection, init_supabase, get_client_id
        from supa_import.loaders import extract_sheets_and_client, push_sheets
        from supa_import.streamlit_functions import get_client_list, get_period_options
        from supa_import.modeling import (
            normalize_all_dataframes,
            add_metadata,
            convert_date_columns,
            apply_grouping,
            normalize_string_columns,
        )
        from supa_import.validators import (
            validate_client_name,
            validate_report_period,
            find_existing_data,
            delete_existing_data,
        )
    except Exception as e:
        st.error(f"Failed to load supa_import package: {e}")
        return

    if "ptdb_supabase_client" not in st.session_state:
        st.session_state.ptdb_supabase_client = init_supabase()
    supabase = st.session_state.ptdb_supabase_client

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        uploaded_file = st.file_uploader("Upload Excel Report", type=["xlsx"], key="ptdb_upload")
    with col2:
        client_options = get_client_list(supabase)
        selected_client = st.selectbox("Select Client", options=client_options, key="ptdb_client")
    with col3:
        period_options = get_period_options()
        selected_period = st.selectbox("Select Reporting Period", options=period_options, key="ptdb_period")
    with col4:
        mode = st.selectbox("Select Mode", options=["Do not overwrite", "Overwrite"], index=0, key="ptdb_mode")

    if not st.button("Run Push", type="primary", use_container_width=True, key="ptdb_run"):
        return

    if not uploaded_file or not selected_client or not selected_period:
        st.error("Please provide a file, a client and a date.")
        return

    report_date = pd.to_datetime(selected_period)

    with st.status("Extracting Sheets...", expanded=True) as extract_st:
        sheets_dict, file_client_name, currency, rate, info = extract_sheets_and_client(
            uploaded_file, SHEET_CONFIG
        )
        if info.get("missing_in_workbook"):
            st.error(f"Missing sheets: {info.get('missing_str', '')}")
            extract_st.update(label="Extracting Sheets", state="error", expanded=True)
            return

        qr_res = get_client_id(selected_client, supabase)
        if qr_res["status"] != "ok":
            st.write(qr_res["message"])
            extract_st.update(label="Extracting Sheets", state="error", expanded=True)
            return

        client_id = qr_res["client_id"]
        st.write("All sheets are available.")
        extract_st.update(label="Extracting Sheets", state="complete", expanded=True)

    with st.status("Formatting Data...", expanded=True) as form_st:
        sheets_dict = normalize_all_dataframes(sheets_dict)

        norm_res = normalize_string_columns(sheets_dict)
        if norm_res["status"] != "ok":
            st.write(norm_res["message"])
            form_st.update(label="Formatting Data", state="error", expanded=True)
            return
        sheets_dict = norm_res["data"]
        st.write(norm_res["message"])

        date_conv = convert_date_columns(sheets_dict, SHEET_CONFIG)
        if date_conv["status"] != "ok":
            st.write(date_conv["message"])
            form_st.update(label="Formatting Data", state="error", expanded=True)
            return
        sheets_dict = date_conv["data"]
        st.write(date_conv["message"])
        form_st.update(label="Formatting Data", state="complete", expanded=True)

    with st.status("Validating Client and Date...", expanded=True) as val_st:
        client_res = validate_client_name(file_client_name, selected_client)
        if client_res["status"] != "ok":
            st.write(client_res["message"])
            val_st.update(label="Validating Client and Date", state="error", expanded=True)
            return
        st.write(client_res["message"])

        date_res = validate_report_period(sheets_dict, SHEET_CONFIG, report_date)
        if date_res["status"] != "ok":
            st.write(date_res["message"])
            val_st.update(label="Validating Client and Date", state="error", expanded=True)
            return
        st.write(date_res["message"])

        try:
            conn = get_pg_connection()
        except Exception as e:
            st.error(f"❌ Could not connect to the database. Check that `host`, `name`, `user`, `password`, and `port` are set in Streamlit secrets.\n\n`{e}`")
            val_st.update(label="Validating Client and Date", state="error", expanded=True)
            return
        conn.autocommit = False
        chk_res = find_existing_data(conn, SHEET_CONFIG, client_id, selected_period)

        if chk_res["status"] != "ok":
            st.write(chk_res["msg"])
            if mode != "Overwrite":
                st.write("Process cancelled because data already exists.")
                val_st.update(label="Validating Client and Date", state="error", expanded=True)
                conn.close()
                return

            st.write("Existing data will be replaced.")
            with st.status("Deleting existing data...", expanded=True) as del_st:
                del_res = delete_existing_data(conn, SHEET_CONFIG, client_id, selected_period)
                if del_res["status"] != "ok":
                    st.write(del_res["msg"])
                    del_st.update(label="Deleting existing data", state="error", expanded=True)
                    conn.close()
                    return
                st.write(del_res["msg"])
                del_st.update(label="Deleting existing data", state="complete", expanded=True)
        else:
            st.write(chk_res["msg"])

        val_st.update(label="Validating Client and Date", state="complete", expanded=True)

    with st.status("Processing Data...", expanded=True) as pro_st:
        meta_res = add_metadata(sheets_dict, client_id, selected_period, currency, rate)
        if meta_res["status"] != "ok":
            st.write(meta_res["message"])
            pro_st.update(label="Processing Data", state="error", expanded=True)
            conn.close()
            return
        sheets_dict = meta_res["data"]
        st.write(meta_res["message"])

        grp_res = apply_grouping(sheets_dict, SHEET_CONFIG)
        if grp_res["status"] != "ok":
            st.write(grp_res["message"])
            pro_st.update(label="Processing Data", state="error", expanded=True)
            conn.close()
            return
        sheets_dict = grp_res["data"]
        st.write(grp_res["message"])
        pro_st.update(label="Processing Data", state="complete", expanded=True)

    with st.status("Writing to Database...", expanded=True) as write_st:
        try:
            load_res = push_sheets(sheets_dict, SHEET_CONFIG, conn)
            if load_res["status"] != "ok":
                st.write(load_res["message"])
                write_st.update(label="Writing to Database", state="error", expanded=True)
                return

            st.write(load_res["message"])
            write_st.update(label="Writing to Database", state="complete", expanded=True)
        finally:
            conn.close()

    st.success(f"Successfully loaded data to database. Triggered by `{user}`.")
