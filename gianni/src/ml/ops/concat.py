from pathlib import Path
import pandas as pd


def concat_files(folder_path, preprocessing_func):
    folder = Path(folder_path)

    xlsx_files = list(folder.glob("*.xlsx"))
    xls_files = list(folder.glob("*.xls"))

    if xlsx_files and xls_files:
        return {
            'status': 'error',
            'msg': 'Mixed file types'
        }
    

    excel_files = xlsx_files or xls_files

    if not excel_files:
        return {
            'status': 'error',
            'msg': 'Empty folder'
        }

    all_dfs = []

    for file_path in excel_files:
        df = preprocessing_func(file_path)
        all_dfs.append(df)

    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.sort_values(
        by="report_date",
        ascending=False
    )

    name = preprocessing_func.__module__.split(".")[-1].replace("_", " ")
    output_path = Path(folder_path) / f"{name}.xlsx"
    combined_df.to_excel(output_path, index=False)

    return {
        'status': 'ok',
        'msg': None
    }