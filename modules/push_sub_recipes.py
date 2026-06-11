from bootstrap import bootstrap_src, ensure_supa_env_from_secrets
import pandas as pd
import streamlit as st


def render_push_to_database(user: str):
    st.markdown("#### Push Sub Recipes")
    st.caption("Upload Sub Recipes file and push data into the database.")

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
        from etl.preprocessors.cloud.inventory_items_ingredients_qtp import preprocess as cloud_sub
        from etl.preprocessors.local.inventory_items_ingredients_qtp import preprocess as local_sub
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
        sub = st.file_uploader("Upload Sub-Recipes", type=["xlsx", "xls"], key="ptdb_upload")
    with col2:
        client_options = get_client_list(supabase)
        selected_client = st.selectbox("Select Branch", options=client_options, key="ptdb_client")
    with col3:
        source = st.selectbox("Select Source", options=["cloud", "local"], index=0, key="ptdb_mode")

    if not st.button("Run", type="primary", use_container_width=True, key="ptdb_run"):
        return

    if not uploaded_file or not selected_client or not source:
        st.error("Please provide a file, a client and a date.")
        return


    with st.status("Processing data...", expanded=True) as process_st:
        if source == 'cloud':
            data = cloud_sub(sub)
        else:
            data = local_sub(sub)

        sheets_dict = {
            'sub recipes': sub,
        }

        st.write(sheets_dict['sub recipes'].head())
        st.write('Done heheeee')