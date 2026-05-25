import pandas as pd
import xlwings as xw

def write_master(
    master_path: str,
    cleaned: dict[str, pd.DataFrame],
    jobs: list[dict],
    output_path: str | None = None,
    suppress_warnings: bool = False,
    log_func = print
) -> None:
    if output_path is None:
        output_path = master_path

    app = xw.App(visible=False, add_book=False)
    try:
        wb = app.books.open(master_path)

        for job in jobs:
            try:
                df = cleaned[job["key"]].copy()
                sht = wb.sheets[job["sheet"]]
            except KeyError as e:
                if not suppress_warnings:
                    log_func(f"⚠️ {job.get('key','?')} not available")
                continue

            log_func(f"{job.get("key")} -> {job.get("sheet")}")

            df_cols = list(job["df_cols"])
            excel_cols = list(job["excel_cols"])

            if len(df_cols) != len(excel_cols):
                log_func(f"⚠️ {job.get('key','?')} df_cols and excel_cols length mismatch")
                continue

            try:
                df = df.loc[:, df_cols]
            except KeyError as e:
                log_func(f"⚠️ {job.get('key','?')} missing df column: {e}")
                continue

            start_row = int(job["start_row"])

            last_row = start_row - 1
            bottom = sht.cells.last_cell.row

            for col in excel_cols:
                vals = sht.range(f"{col}{start_row}:{col}{bottom}").value
                if not vals:
                    continue
                for i, v in enumerate(vals):
                    if v not in (None, ""):
                        last_row = max(last_row, start_row + i)

            write_row = start_row if last_row < start_row else last_row + 1

            for col_name, excel_col in zip(df_cols, excel_cols):
                rng = f"{excel_col}{write_row}"
                sht.range(rng).options(index=False, header=False).value = df[[col_name]].to_numpy()

        wb.save(output_path)
        wb.close()
    finally:
        app.quit()
