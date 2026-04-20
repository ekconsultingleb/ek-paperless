import pandas as pd
from supa_import.modeling import normalize_column_name, clean_value
import pandas as pd
from psycopg2.extras import execute_values
from psycopg2 import sql as psql


def load_sheet(file, sheet_name):
    df = pd.read_excel(file, sheet_name=sheet_name)
    df.columns = [normalize_column_name(c) for c in df.columns]
    return df


def extract_sheets_and_client(file_path, sheet_config):

    with pd.ExcelFile(file_path) as xls:

        common_names = [s for s in xls.sheet_names if s in sheet_config]
        sheets_dict = {
            name: pd.read_excel(xls, sheet_name=name)
            for name in common_names
        }

        info_df = pd.read_excel(xls, sheet_name="Info")
        real_client = info_df.iloc[0,1]
        currency = info_df.iloc[0,3].strip().lower()
        rate = info_df.iloc[0,4]

        info = {
            "common_sheet_names": common_names,
            "missing_in_workbook": [s for s in sheet_config if s not in xls.sheet_names],
            "extra_in_workbook": [s for s in xls.sheet_names if s not in sheet_config]
        }

        if info['missing_in_workbook']:
            info['missing_str'] = ", ".join(info['missing_in_workbook'])

    return sheets_dict, real_client, currency, rate, info


def push_sheets(sheets: dict, sheet_config: dict, conn):
    empty_sheets: list[str] = []
    loaded: list[str] = []

    def _fmt_lines(items: list[str]) -> str:
        return "  \n".join(items) if items else "None"

    try:
        with conn.cursor() as cur:
            for sheet_name, config in sheet_config.items():
                df = sheets.get(sheet_name)

                if df is None or not hasattr(df, "empty") or df.empty:
                    empty_sheets.append(sheet_name)
                    continue

                table = config["target_table"]
                expected_columns = config.get("expected_columns")
                unique_key = config.get("unique_key")

                if expected_columns:

                    cols_to_use = list(expected_columns)
                    if unique_key:
                        for c in unique_key:
                            if c not in cols_to_use:
                                cols_to_use.append(c)

                    for meta_col in ("branch_id", "report_date", "currency", "client_rate"):
                        if meta_col in df.columns and meta_col not in cols_to_use:
                            cols_to_use.append(meta_col)

                    missing = [c for c in cols_to_use if c not in df.columns]
                    if missing:
                        raise ValueError(
                            f"Sheet '{sheet_name}' is missing required column(s): {', '.join(missing)}"
                        )
                    df = df[cols_to_use]

                rows = df.to_dict(orient="records")
                if not rows:
                    empty_sheets.append(sheet_name)
                    continue

                if unique_key:
                    missing_uk = [c for c in unique_key if c not in rows[0]]
                    if missing_uk:
                        raise ValueError(
                            f"Sheet '{sheet_name}' missing unique_key column(s): {', '.join(missing_uk)}"
                        )

                    seen = set()
                    for row in rows:
                        key = tuple(row.get(k) for k in unique_key)
                        if key in seen:
                            raise ValueError(f"Duplicate row in sheet '{sheet_name}' for unique key: {key}")
                        seen.add(key)

                cols = list(rows[0].keys())
                values = [[clean_value(row.get(c)) for c in cols] for row in rows]

                query = psql.SQL("INSERT INTO {table} ({cols}) VALUES %s").format(
                    table=psql.Identifier(table),
                    cols=psql.SQL(",").join(psql.Identifier(c) for c in cols),
                )

                try:
                    execute_values(cur, query, values)
                except Exception as e:
                    raise RuntimeError(f"Insert failed for sheet '{sheet_name}' into table '{table}': {e}") from e

                loaded.append(f"{sheet_name} → {len(values)} row(s)")

        conn.commit()
        return {
            "status": "ok",
            "message": (
                "Committed all sheets successfully.  \n  \n"
                f"Loaded:  \n{_fmt_lines(loaded)}  \n  \n"
                f"Skipped empty sheets:  \n{_fmt_lines(empty_sheets)}"
            ),
            "details": {"loaded": loaded, "empty": empty_sheets},
        }

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass

        return {
            "status": "error",
            "message": (
                "Failed; rolled back everything  \n  \n"
                f"Reason:  \n{e}  \n  \n"
                f"Loaded before failure (not committed):  \n{_fmt_lines(loaded)}  \n  \n"
                f"Empty sheets:  \n{_fmt_lines(empty_sheets)}"
            ),
            "details": {"loaded": loaded, "empty": empty_sheets, "error": str(e)},
        }