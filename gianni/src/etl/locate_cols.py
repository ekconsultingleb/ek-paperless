import xlwings as xw
import copy


def get_excel_cols(master_path, config_list):

    def normalize(x):
        return str(x).strip().lower() if x is not None else ""

    app = None
    wb = None

    result = []
    errors = []

    try:
        app = xw.App(visible=False, add_book=False)
        wb = app.books.open(master_path)

        for conf in config_list:
            job_key = conf.get("key", "unknown")

            try:
                new_conf = copy.deepcopy(conf)

                sheet_name = conf["sheet"]
                header_row = conf["start_row"] - 1
                wanted_cols = conf["df_cols"]

                ws = wb.sheets[sheet_name]
                last_col = ws.used_range.last_cell.column

                header_map = {}

                for col_idx in range(1, last_col + 1):
                    val = ws.range((header_row, col_idx)).value
                    norm_val = normalize(val)
                    if norm_val:
                        header_map[norm_val] = col_idx

                excel_cols = [
                    xw.utils.col_name(header_map[normalize(col)])
                    for col in wanted_cols
                ]

                new_conf["excel_cols"] = excel_cols
                result.append(new_conf)

            except Exception as e:
                errors.append({job_key: str(e)})

        if errors:
            return {
                "status": "error",
                "result": None,
                "msg": f'Failed to locate excel columns'
            }

        return {
            "status": "ok",
            "result": result,
            "msg": f'All columns are located successfully'
        }

    except Exception as e:
        return {
            "status": "error",
            "result": None,
            "msg": f'Failed to locate excel columns'
        }

    finally:
        if wb is not None:
            wb.close()
        if app is not None:
            app.quit()


