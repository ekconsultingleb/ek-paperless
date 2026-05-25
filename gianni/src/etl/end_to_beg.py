import pandas as pd
import xlwings as xw

def end_to_beg(
    master_path: str,
    output_path: str | None = None,
) -> None:

    if output_path is None:
        output_path = master_path

    app = xw.App(visible=False, add_book=False)
    try:
        wb = app.books.open(master_path)

        src = wb.sheets['Ending']
        dst = wb.sheets['Beg']
        dst_start_cell = 'A1'

        data = src.used_range.value
        if data is None:
            wb.save(output_path)
            wb.close()
            return

        dst.used_range.value = None

        dst.range(dst_start_cell).value = data

        wb.save(output_path)
        wb.close()
    finally:
        app.quit()
