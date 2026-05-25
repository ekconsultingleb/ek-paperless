import pandas as pd
import xlwings as xw

def clear_sheets(
    master_path: str,
    jobs: list[dict],
    cleaned: dict[str, pd.DataFrame],
    log_func = print ) -> None:

    app = xw.App(visible=False, add_book=False)

    try:
        wb = app.books.open(master_path)

        active_jobs = [job for job in jobs if job["key"] in cleaned]

        sheet_cols = {}
        for job in jobs:
            sheet_cols.setdefault(job["sheet"], set()).update(job["excel_cols"])
        sheet_cols = {k: sorted(list(v)) for k, v in sheet_cols.items()}

        used_sheets = {job["sheet"] for job in active_jobs}

        for sheet_name in used_sheets:
            sht = wb.sheets[sheet_name]

            start_row = 2

            for col in sheet_cols[sheet_name]:
                last_used = sht.range(
                    f"{col}{sht.cells.last_cell.row}"
                ).end("up").row

                if last_used >= start_row:
                    sht.range(f"{col}{start_row}:{col}{last_used}").value = None

            log_func(f"Cleared {sheet_name}")

        wb.save()
        wb.close()

    finally:
        app.quit()