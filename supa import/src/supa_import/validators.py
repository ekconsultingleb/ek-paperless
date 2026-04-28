import pandas as pd
import streamlit as st
import re


def validate_client_name(real_client, entered_client):

    real_client_clean = str(real_client).strip() if real_client is not None else ""
    entered_client_clean = str(entered_client).strip() if entered_client is not None else ""

    if real_client_clean == entered_client_clean:
        msg = "Client name matches the file."

        result = {
            "status": "ok",
            "message": msg
        }
        return result

    msg = (
        f"The client name entered '{entered_client}' "
        f"is different from the one in the file '{real_client}'."
    )

    result = {
        "status": "error",
        "message": msg,
    }
    return result


def validate_required_columns(sheets_dict, sheet_config):

    message = []

    for sheet_name, df in sheets_dict.items():
        expected_columns = sheet_config[sheet_name]["expected_columns"]
        missing_columns = [col for col in expected_columns if col not in df.columns]

        if missing_columns:
            missing_str = ", ".join(missing_columns)
            message.append(f"Sheet {sheet_name} is missing column(s): {missing_str}")


    if message:
        return {
            "status": "error",
            "message": "  \n  \n".join(message)
        }    
        
    return {
        "status": "ok",
        "message": "All required columns exist in all sheets."
    }


def validate_report_period(sheets_dict, sheet_config, report_date):
    errors = []

    report_period = pd.to_datetime(report_date, errors="coerce").to_period("M")

    if pd.isna(report_period):
        return {
            "status": "error",
            "message": "Invalid Report Date",
        }

    total_bad = 0

    for sheet_name, df in sheets_dict.items():
        date_col = sheet_config[sheet_name].get("date_column")

        if not date_col:
            continue

        if date_col not in df.columns:
            errors.append(f"⚠️ {sheet_name}: missing date column '{date_col}'")
            continue

        sheet_dates = df[date_col]
        expected_period = report_period - 1 if sheet_name == "Beg" else report_period

        bad_mask = sheet_dates.isna() | (sheet_dates != expected_period)
        bad_count = int(bad_mask.sum())

        if bad_count > 0:
            total_bad += bad_count
            errors.append(
                f"⚠️ {sheet_name}: {bad_count} row(s) outside reporting period {expected_period}"
            )

    if errors:
        return {
            "status": "error",
            "message": "  \n".join(errors),
        }

    return {
        "status": "ok",
        "message": "All sheet dates match the selected reporting period.",
    }


def handle_status(result, log_func=st.write):

    status = result.get("status")
    message = result.get("message")

    if message:
        log_func(message)

    if status == "error":
        return {
            "action": "stop"
        }

    if status == "warning":
        return {
            "action": "choice",
            "options": ["continue", "stop"],
            "message": message
        }

    return {
        "action": "continue"
    }


def safe_ident(name):
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return name


def find_existing_data(conn, sheet_config, branch_id, report_date):
    conn.rollback()

    results = []
    tables = [sht['target_table'] for sht in sheet_config.values()]

    start_date = f"{report_date}-01"
    
    year, month = map(int, report_date.split("-"))
    if month == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+1:02d}-01"

    with conn.cursor() as cur:
        for table in tables:
            table_name = safe_ident(table)

            cur.execute(
                f"""
                select count(*)
                from {table_name}
                where branch_id = %s
                  and report_date >= %s
                  and report_date < %s
                """,
                (branch_id, start_date, end_date)
            )

            count = cur.fetchone()[0]

            if count > 0:
                results.append(f"{table} → {count} row(s)")

    if results:
        return {
            "status": "warning",
            "msg": "Data already exists in:  \n" + "  \n".join(results)
        }
    else:
        return {
            "status": "ok",
            "msg": "No existing data found."
        }


def delete_existing_data(conn, sheet_config, branch_id, report_date):
    conn.rollback()

    tables = [sht['target_table'] for sht in sheet_config.values()]

    start_date = f"{report_date}-01"
    
    year, month = map(int, report_date.split("-"))
    if month == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+1:02d}-01"

    deleted_tables = []

    try:
        with conn.cursor() as cur:
            for table in tables:
                table_name = safe_ident(table)

                cur.execute(
                    f"""
                    delete from {table_name}
                    where branch_id = %s
                      and report_date >= %s
                      and report_date < %s
                    """,
                    (branch_id, start_date, end_date)
                )

                if cur.rowcount > 0:
                    deleted_tables.append(f"{table} → {cur.rowcount} row(s) deleted")

        conn.commit()

        if deleted_tables:
            return {
                "status": "ok",
                "msg": "Deleted existing data from:  \n" + "  \n".join(deleted_tables)
            }
        else:
            return {
                "status": "warning",
                "msg": "No existing data found to delete."
            }

    except Exception as e:
        conn.rollback()
        return {
            "status": "error",
            "msg": f"Delete failed: {e}"
        }



# def check_duplicates(SHEET_CONFIG, sheets):

#     duplicates_report = {}

#     for sheet_name, config in SHEET_CONFIG.items():

#         if sheet_name not in sheets:
#             continue

#         data = sheets[sheet_name]
#         unique_key = config.get("unique_key", [])

#         if not unique_key:
#             continue

#         missing_cols = [col for col in unique_key if col not in data.columns]

#         if missing_cols:
#             continue

#         duplicate_mask = data.duplicated(subset=unique_key, keep=False)
#         duplicate_rows = data[duplicate_mask].sort_values(by=unique_key)

#         if not duplicate_rows.empty:
#             duplicates_report[sheet_name] = {
#                 "rows": duplicate_rows,
#                 "unique_key": unique_key
#             }

#     if duplicates_report:

#         msgs = []

#         for sheet_name, result in duplicates_report.items():

#             duplicate_rows = result["rows"]
#             unique_key = result.get("unique_key", [])

#             if not unique_key:
#                 continue

#             df_display = (
#                 duplicate_rows[unique_key]
#                 .drop_duplicates()
#                 .astype(str)
#             )

#             col_widths = {
#                 col: max(df_display[col].map(len).max(), len(col))
#                 for col in unique_key
#             }

#             header = " | ".join(
#                 col.ljust(col_widths[col]) for col in unique_key
#             )

#             separator = "-+-".join("-" * col_widths[col] for col in unique_key)

#             rows = [
#                 " | ".join(
#                     row[col].ljust(col_widths[col]) for col in unique_key
#                 )
#                 for _, row in df_display.iterrows()
#             ]

#             rows_text = header + "  \n" + separator + "  \n" + "  \n".join(rows)
            
#             block = (
#                 f"⚠️ {sheet_name}: {len(duplicate_rows)} duplicate rows found  \n"
#                 f"{rows_text}"
#             )

#             msgs.append(block)

#         return {
#             "status": "error",
#             "msg": "  \n  \n".join(msgs)
#         }

#     return {
#         "status": "ok",
#         "msg": "All constraints are satisfied"
#     }


def check_duplicates(SHEET_CONFIG, sheets):

    duplicates_report = {}

    for sheet_name, config in SHEET_CONFIG.items():

        if sheet_name not in sheets:
            continue

        data = sheets[sheet_name]
        unique_key = config.get("unique_key", [])

        if not unique_key:
            continue

        missing_cols = [col for col in unique_key if col not in data.columns]

        if missing_cols:
            continue

        duplicate_mask = data.duplicated(subset=unique_key, keep=False)
        duplicate_rows = data[duplicate_mask].sort_values(by=unique_key)

        if not duplicate_rows.empty:
            duplicates_report[sheet_name] = {
                "rows": duplicate_rows,
                "unique_key": unique_key
            }

    if duplicates_report:

        msgs = []

        for sheet_name, result in duplicates_report.items():

            duplicate_rows = result["rows"]
            unique_key = result.get("unique_key", [])

            if not unique_key:
                continue

            df_display = (
                duplicate_rows[unique_key]
                .drop_duplicates()
                .fillna("")
                .astype(str)
            )

            col_widths = {
                col: max(
                    df_display[col].astype(str).str.len().max(),
                    len(str(col))
                )
                for col in unique_key
            }

            header = " | ".join(
                str(col).ljust(col_widths[col]) for col in unique_key
            )

            separator = "-+-".join(
                "-" * col_widths[col] for col in unique_key
            )

            rows = [
                " | ".join(
                    str(row[col]).ljust(col_widths[col])
                    for col in unique_key
                )
                for _, row in df_display.iterrows()
            ]

            rows_text = header + "  \n" + separator + "  \n" + "  \n".join(rows)

            block = (
                f"⚠️ {sheet_name}: {len(duplicate_rows)} duplicate rows found  \n"
                f"{rows_text}"
            )

            msgs.append(block)

        return {
            "status": "error",
            "msg": "  \n  \n".join(msgs)
        }

    return {
        "status": "ok",
        "msg": "All constraints are satisfied"
    }