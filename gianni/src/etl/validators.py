import xlwings as xw
    

def check_sheets_exist(file_path, config_list):
    with xw.Book(file_path) as wb:
        existing_sheets = {sheet.name for sheet in wb.sheets}

        missing = [
            config['sheet']
            for config in config_list
            if config['sheet'] not in existing_sheets
        ]

        if missing:
            return {
                'status': 'error',
                'msg': f"Missing sheets: {', '.join(missing)}"
            }

        return {
            'status': 'ok',
            'msg': 'All sheets exist'
        }
    

def get_missing_columns(wb_path, sheets_config, case_sensitive=False):

    app = xw.App(visible=False)
    app.display_alerts = False
    app.screen_updating = False

    try:
        wb = app.books.open(wb_path)
        result = {}

        for item in sheets_config:
            key = item['key']
            sheet_name = item['sheet']
            expected_cols = item['df_cols']
            header_row = item['start_row'] - 1

            ws = wb.sheets[sheet_name]

            last_col = ws.used_range.last_cell.column
            actual_cols = ws.range((header_row, 1), (header_row, last_col)).value

            if actual_cols is None:
                actual_cols = []
            elif not isinstance(actual_cols, list):
                actual_cols = [actual_cols]

            actual_cols = [str(c).strip() for c in actual_cols if c not in (None, "")]
            expected_cols = [str(c).strip() for c in expected_cols]

            if case_sensitive:
                actual_set = set(actual_cols)
                missing = [col for col in expected_cols if col not in actual_set]
            else:
                actual_map = {col.lower(): col for col in actual_cols}
                missing = [col for col in expected_cols if col.lower() not in actual_map]

            if missing:
                result[sheet_name] = missing

        wb.close()

        if result:
            messages = [
                f"Sheet '{sheet}' is missing columns: {', '.join(cols)}."
                for sheet, cols in result.items()]
            return {
                'status': 'error',
                'msg': '  \n'.join(messages)
            }
        
        return {
            'status': 'ok',
            'msg': 'All columns exist'
        }

    finally:
        app.quit()