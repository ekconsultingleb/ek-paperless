import xlwings as xw

def clear_all(
    master_path: str,
    jobs: list[dict],
    cleaned: dict | None = None,
) -> None:
    if cleaned is None:
        cleaned = {}

    app = xw.App(visible=False, add_book=False)
    try:
        wb = app.books.open(master_path)

        for job in jobs:

            sheet_name = job["sheet"]

            if sheet_name == "Recipes" and "sales items ingredients" not in cleaned:
                continue

            if sheet_name == "sub recipes" and "inventory items ingredients" not in cleaned:
                continue

            sht = wb.sheets[sheet_name]
            start_row = job["start_row"]

            for col in job["excel_cols"]:
                last_used = sht.range(
                    f"{col}{sht.cells.last_cell.row}"
                ).end("up").row

                if last_used >= start_row:
                    sht.range(
                        f"{col}{start_row}:{col}{last_used}"
                    ).value = None



        wb.save()
        wb.close()

    finally:
        app.quit()
