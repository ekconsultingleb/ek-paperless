import streamlit as st
import sys
from pathlib import Path
import warnings

st.set_page_config(
    page_title="Auto Calc Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed"
)

sys.path.append(str(Path(__file__).parent / "src"))

from etl.config import get_jobs
from etl.orchestrator import clean_folder, cleaner_by_code
from etl.merger import merge
from etl.strip_all import strip_all
from etl.special_characters import special_char
from etl.saver import save_cleaned_data
from etl.reset_view import reset_workbook_view
from etl.prev_unit_cost import uc_pre_month
from etl.clearer import clear_all
from etl.clear_sheets import clear_sheets
from etl.writer import write_master
from etl.validators import check_sheets_exist, get_missing_columns
from etl.locate_cols import get_excel_cols
from etl.extract_sheets import extract_sheets

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

warnings.filterwarnings(
    "ignore",
    message="Workbook contains no default style*",
    category=UserWarning,
)

st.title("Auto Calc Pipeline")
st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    folder_input = st.text_input("📁 Target Folder Path", placeholder="C:/Path/To/Folder")
with col2:
    mode = st.selectbox("⚙️ Mode", options=["all", "not-all"], index=0)
with col3:
    source = st.selectbox("🔀 Source", options=["cloud", "local"], index=0)

if st.button("▶ Run Pipeline", type="primary", use_container_width=True):
    
    if folder_input.strip() =='':
        with st.status("Name Patterns", expanded=True) as status_pat_0:
            lines = []
            for i, j in cleaner_by_code[source].items():
                lines.append(f"{j[0]} {'-'*((70-len(j[0]))-2)} {i}")
                
            st.code("\n".join(lines), language=None)
            status_pat_0.update(state="complete",expanded=True)
            st.stop()
    
    base_folder = Path(folder_input).resolve()
    jobs = get_jobs(source)

    if not base_folder.is_dir():
        st.error(f"Error: '{base_folder}' is not a valid directory.")
    else:
        master_path = base_folder / "Auto Calc.xlsx"
        
        # --- BOX 1: INIT ---
        with st.status("Initializing ETL...", expanded=True) as status_init:
            st.write(f"Folder: `{base_folder.name}`")
            status_init.update(label="Initialization", state="complete", expanded=True)

        # --- BOX 2: PATTERNS ---
        with st.status("Name Patterns", expanded=True) as status_pat:
            lines = []
            folder_files = [f.name for f in base_folder.iterdir() if f.is_file()]
            for i, j in cleaner_by_code[source].items():
                emoji = "✅" if any(i in f for f in folder_files) else "❌"
                lines.append(f"{j[0]} {emoji} {'-'*((70-len(j[0]))-2)} {i}")

            st.code("\n".join(lines), language=None)
            status_pat.update(expanded=False)

        # --- BOX 3: CLEANING ---
        with st.status("Cleaning...", expanded=True) as status_clean:
            cleaned = clean_folder(base_folder, source=source, log_func=st.write)

            if not cleaned:
                st.error("Make sure the selected source is correct")
                status_clean.update(label='Empty folder',state="error", expanded=True)
                st.stop()

            cleaned = merge(cleaned)
            cleaned = strip_all(cleaned)
            cleaned = special_char(cleaned)
            save_cleaned_data(cleaned, base_folder)
            st.write("Cleaned data is saved.")
            status_clean.update(label="Cleaning", state="complete", expanded=True)

        if not master_path.is_file():
            with st.status("Opening Workbook...", expanded=True) as status_ow:
                st.error("No 'Auto Calc.xlsx' file found in the folder.")
                status_ow.update(label='Workbook not found',state="error", expanded=False)

            st.success("✅ Successfully cleaned available data")

        else:
            
            with st.status("Opening Workbook...", expanded=True) as status_ow:
                reset_workbook_view(master_path)
                st.write('Completed')
                status_ow.update(label='Opening Workbook',state="complete", expanded=True)


            if mode == "all":
                with st.status("Extracting sheets...", expanded=True) as status_ex:
                    ex_res = extract_sheets(master_path, ['Ending'], jobs, cleaned)
                    jobs = ex_res['jobs']
                    cleaned = ex_res['cleaned_dict']
                    st.write("Completed")
                    status_ex.update(label="Extracting sheets", state="complete", expanded=True)######## honnnn

                # with st.status("test", expanded=True) as status_test:
                #     save_cleaned_data(cleaned, base_folder, 'testtt.xlsx')
                #     st.write(jobs)
                #     status_test.update(label="test", state="complete", expanded=True)
                #     st.stop()



            with st.status("Validating Workbook...", expanded=True) as status_vw:
                missing_sheets = check_sheets_exist(master_path, jobs)
                if missing_sheets['status'] != 'ok':
                    st.write(missing_sheets['msg'])
                    status_vw.update(label='Validating Workbook',state="error", expanded=True)
                    st.stop()
                st.write(missing_sheets['msg'])
                missing_cols = get_missing_columns(master_path, jobs)
                if missing_cols['status'] != 'ok':
                    st.write(missing_cols['msg'])
                    status_vw.update(label='Validating Workbook',state="error", expanded=True)
                    st.stop()
                st.write(missing_cols['msg'])
                loc_res = get_excel_cols(master_path, jobs)
                if loc_res['status'] != 'ok':
                    st.write(loc_res['msg'])
                    status_vw.update(label='Locating columns',state="error", expanded=True)
                    st.stop() 
                jobs = loc_res['result']
                st.write(loc_res['msg'])
                status_vw.update(label="Validating Workbook", state="complete", expanded=True)


            if mode == "all":
                with st.status("UNIT COST -> UC PRE MONTH...", expanded=True) as status_uc:
                    uc_pre_month(str(master_path), log_func=st.write)
                    st.write("Completed")
                    status_uc.update(label="UNIT COST -> UC PRE MONTH", state="complete", expanded=True)

                with st.status("Clearing...", expanded=True) as status_clear:
                    clear_all(str(master_path), jobs, cleaned=cleaned)
                    st.write("Completed")
                    status_clear.update(label="Clearing", state="complete", expanded=True)

                with st.status("Writing...", expanded=True) as status_write:    
                    write_master(str(master_path), cleaned, jobs, suppress_warnings=True, log_func=st.write)
                    status_write.update(label="Writing", state="complete", expanded=True)
                    st.write("Loaded all available data")
            else:
                with st.status("Clearing...", expanded=True) as status_clear:
                    clear_sheets(str(master_path), jobs=jobs, cleaned=cleaned, log_func=st.write)
                    status_clear.update(label="Clearing", state="complete", expanded=True)

                with st.status("Writing...", expanded=True) as status_write:
                    write_master(str(master_path), cleaned, jobs, suppress_warnings=True, log_func=st.write)
                    status_write.update(label="Writing", state="complete", expanded=True)
                    st.write("Loaded all available data")           

            st.success("✅ Successfully updated 'Auto Calc.xlsx'")