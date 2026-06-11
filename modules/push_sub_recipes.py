from bootstrap import bootstrap_src, ensure_supa_env_from_secrets
import pandas as pd
import streamlit as st


def render_push_to_database(user: str):
    st.markdown("#### Push to Database")
    st.caption("Upload Auto Calc report files and push validated data into the database.")

    if not bootstrap_src():
        st.error("Backend package path not found. Ensure `gianni/src` is deployed with the app.")
        return

    ensure_supa_env_from_secrets()

    try:
        from supa_import.db import get_pg_connection, init_supabase, get_branch_id
        from supa_import.config import SHEET_CONFIG
        from supa_import.loaders import extract_sheets_and_client, push_sheets
        from supa_import.streamlit_functions import get_client_list, get_period_options
        from supa_import.modeling import (
            normalize_all_dataframes,
            add_metadata,
            convert_date_columns,
            apply_grouping,
            normalize_string_columns,
            clean_numeric_values,
        )
        from supa_import.validators import (
            validate_required_columns,
            validate_client_name,
            validate_report_period,
            find_existing_data,
            delete_existing_data,
            check_duplicates,
            check_rows
        )
    except Exception as e:
        try:
            import supa_import

            loaded_from = getattr(supa_import, "__file__", "unknown")
        except Exception:
            loaded_from = "not importable"
        st.error(
            f"Failed to load supa_import package: {e}\n\n"
            f"Python resolved `supa_import` from: `{loaded_from}`\n\n"
            "Expected code under `gianni/src/supa_import/`. "
            "If the repo also contains a `supa import/` copy, remove it or redeploy after pulling the latest bootstrap fix."
        )
        return

    if "ptdb_supabase_client" not in st.session_state:
        st.session_state.ptdb_supabase_client = init_supabase()
    supabase = st.session_state.ptdb_supabase_client

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        uploaded_file = st.file_uploader("Upload Excel Report", type=["xlsx"], key="ptdb_upload")
    with col2:
        client_options = get_client_list(supabase)
        selected_client = st.selectbox("Select Branch", options=client_options, key="ptdb_client")
    with col3:
        period_options = get_period_options()
        selected_period = st.selectbox("Select Reporting Period", options=period_options, key="ptdb_period")
    with col4:
        mode = st.selectbox("Select Mode", options=["Do not overwrite", "Overwrite"], index=0, key="ptdb_mode")

    if not st.button("Run", type="primary", use_container_width=True, key="ptdb_run"):
        return

    if not uploaded_file or not selected_client or not selected_period:
        st.error("Please provide a file, a client and a date.")
        return
