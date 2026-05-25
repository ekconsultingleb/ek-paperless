import streamlit as st
import sys
from pathlib import Path
import warnings

st.set_page_config(
    page_title="Recipes",
    layout="wide",
    initial_sidebar_state="collapsed"
)

sys.path.append(str(Path(__file__).parent / "src"))

from etl.compare import compare,FILE_MAP
from etl.saver import save_cleaned_data

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

st.title("Recipes: Omega vs Auto Calc")
st.markdown("---")


folder_input = st.text_input("📁 Target Folder Path", placeholder="C:/Path/To/Folder")

if st.button("▶ Run ", type="primary", use_container_width=True):

    base_folder = Path(folder_input).resolve()

    if folder_input.strip() == '' or not base_folder.is_dir():
        st.error(f"Error: '{base_folder}' is not a valid directory.")
        st.stop()

    if not (base_folder / "Auto Calc.xlsx").is_file():
        st.error("Missing 'Auto Calc.xlsx'")
        st.stop()

    if not any((base_folder / f).is_file() for f in FILE_MAP):
        st.error("Recipes from Omega is missing")
        st.stop()


    matches = [f for f in FILE_MAP if (base_folder / f).is_file()]

    if len(matches) > 1:
        st.error(f"Multiple Omega Recipes files found: {matches}")
        st.stop()

    with st.status("Initializing...", expanded=True) as status_init:
        st.write(f"Folder: `{base_folder.name}`")
        status_init.update(label="Initialization", state="complete", expanded=True)

    with st.status("Comparing...", expanded=True) as status_comp:
        results = compare(base_folder)
        save_cleaned_data(results,base_folder,result_name='RESULTS.xlsx')
        st.write("Completed")
        status_comp.update(label="Comparing", state="complete", expanded=True)

    st.success("✅ Successfully compared Recipes")