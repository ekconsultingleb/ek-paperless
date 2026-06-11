from bootstrap import bootstrap_src, ensure_supa_env_from_secrets
import pandas as pd
import streamlit as st


def push_sales_purchase(user: str):
    st.markdown("#### Push Sales-Purchase")
    st.caption("Upload Sales and Purchase files.")

    if not bootstrap_src():
        st.error("Backend package path not found. Ensure `gianni/src` is deployed with the app.")
        return

    ensure_supa_env_from_secrets()

    try:
        from supa_import.db import get_pg_connection, init_supabase, get_branch_id
        from supa_import.config import SHEET_CONFIG

        from etl.preprocessors.local.sales_by_menu_by_items import preprocess as local_sales
        from etl.preprocessors.local.purchase_with_all_details import preprocess as local_purchase
        from etl.preprocessors.cloud.sales_by_items import preprocess as cloud_sales
        from etl.preprocessors.cloud.purchase_master_report_for_all_branches import preprocess as cloud_purchase
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
        from supa_import.saver import save_cleaned_data
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

    if "psp_supabase_client" not in st.session_state:
        st.session_state.psp_supabase_client = init_supabase()
    supabase = st.session_state.psp_supabase_client

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        sales = st.file_uploader("Upload Sales file", type=["xlsx", "xls"], key="psp_upload_sales")
    with col2:
        purchase = st.file_uploader("Upload Purchase file", type=["xlsx", "xls"], key="psp_upload_purchase")
    with col3:
        client_options = get_client_list(supabase)
        selected_client = st.selectbox("Select Branch", options=client_options, key="psp_client")
    with col4:
        period_options = get_period_options()
        selected_period = st.selectbox("Select Reporting Period", options=period_options, key="psp_period")
    with col5:
        mode = st.selectbox("Select Mode", options=["cloud", "local"], index=0, key="psp_mode")

    if not st.button("Run", type="primary", use_container_width=True, key="psp_run"):
        return

    if not sales or not purchase or not mode:
        st.error("Please provide mode, sales and purchase files.")
        return

    report_date = pd.to_datetime(selected_period)


    with st.status("Processing files...", expanded=True) as process_st:
        if mode == 'cloud':
            sales = cloud_sales(sales)
            purchase = cloud_purchase(purchase)
        else:
            sales = local_sales(sales)
            purchase = local_purchase(purchase)

        sheets_dict = {
            'Sales': sales,
            'Purchase': purchase,
        }

        save_cleaned_data(sheets_dict, 'C:/Users/eliek/Desktop/test sales pur')
        st.write('Done heheeee')