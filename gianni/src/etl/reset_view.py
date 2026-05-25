import xlwings as xw

def reset_workbook_view(wb_path: str) -> None:
    app = xw.App(visible=False, add_book=False)
    wb = None
    try:
        app.display_alerts = False
        app.screen_updating = False
        app.enable_events = False

        wb = app.books.open(wb_path)

        for sht in wb.sheets:
            api = sht.api

            try:
                if api.FilterMode:
                    api.ShowAllData()
            except Exception:
                pass
            try:
                api.AutoFilterMode = False
            except Exception:
                pass

            try:
                api.Columns.Hidden = False
            except Exception:
                pass
            try:
                api.Rows.Hidden = False
            except Exception:
                pass

        wb.save()
    finally:
        try:
            if wb is not None:
                wb.close()
        except Exception:
            pass
        app.quit()
