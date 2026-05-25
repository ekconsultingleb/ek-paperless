from pathlib import Path

import pandas as pd


_SHEET_NAME_MAP: dict[str, str] = {}


def save_cleaned_data(cleaned: dict[str, object], raw_folder: str | Path, result_name: str = 'Cleaned Data.xlsx') -> None:
    
    folder_path = Path(raw_folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise NotADirectoryError(f"Folder not found or not a directory: {folder_path}")

    workbook_path = folder_path / result_name

    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        for name, value in cleaned.items():
            if not isinstance(value, pd.DataFrame):
                continue

            sheet_name = _SHEET_NAME_MAP.get(name, name)[:31]

            value.to_excel(writer, sheet_name=sheet_name, index=False)

    return workbook_path