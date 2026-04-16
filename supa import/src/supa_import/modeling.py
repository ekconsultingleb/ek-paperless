import pandas as pd
import re
import streamlit as st

def normalize_column_name(col: str) -> str:
    col = str(col).strip().lower()
    col = re.sub(r"\s+", "_", col)
    col = re.sub("-", "_", col)
    col = re.sub(r"%", "percentage", col)
    col = re.sub(r"[’.]",'',col)
    col = re.sub(r"#",'nbr',col)
    if col == "group":
        col = "item_group"

    return col
def normalize_all_dataframes(sheets_dict):

    for name, df in sheets_dict.items():
        df.columns = [normalize_column_name(c) for c in df.columns]

    return sheets_dict


def add_metadata(
    sheets_dict,
    branch_id,
    report_date,
    currency,
    rate
):

    report_period = pd.to_datetime(report_date, errors="coerce").to_period("M")

    if pd.isna(report_period):
        msg = f"⚠️ Invalid report date: '{report_date}'"
        return {
            "status": "error",
            "message": msg,
            "data": None
        }
    
    if pd.isna(currency):
        msg = f"⚠️ Currency is missing"
        return {
            "status": "error",
            "message": msg,
            "data": None
        }
    
    if pd.isna(rate):
        msg = f"⚠️ rate is missing"
        return {
            "status": "error",
            "message": msg,
            "data": None
        }

    updated_sheets = {}

    for sheet_name, df in sheets_dict.items():
        df = df.copy()

        df["branch_id"] = branch_id
        df["report_date"] = report_period
        df['currency'] = currency
        df['client_rate'] = rate

        cols = ["report_date", "branch_id", "currency", "client_rate"] + [
            c for c in df.columns if c not in ["report_date", "branch_id", "currency", "client_rate"]
        ]
        df = df[cols]

        updated_sheets[sheet_name] = df

    msg = f"Metadata added successfully"

    return {
        "status": "ok",
        "message": msg,
        "data": updated_sheets
    }


def convert_date_columns(sheets_dict, sheet_config):
    errors = []

    for sheet_name, df in sheets_dict.items():
        date_col = sheet_config[sheet_name].get("date_column")

        if not date_col:
            continue

        if date_col not in df.columns:
            errors.append(f"⚠️ {sheet_name} missing date column '{date_col}'")
            continue

        try:
            converted = pd.to_datetime(df[date_col], errors="coerce")

            # detect invalid dates (NaT)
            invalid_mask = converted.isna()
            if invalid_mask.any():
                errors.append(f"⚠️ {sheet_name}[{date_col}] contains invalid date values")

            df[date_col] = converted.dt.to_period("M")

        except Exception as e:
            errors.append(f"⚠️ {sheet_name}[{date_col}]: {e}")

    if errors:
        return {
            "status": "error",
            "message": "  \n".join(errors),
            "data": None
        }

    return {
        "status": "ok",
        "message": "All date columns processed successfully.",
        "data": sheets_dict
    }


def apply_grouping(sheets_dict, sheet_config):
    errors = []
    updated_sheets = {}

    for sheet_name, df in sheets_dict.items():
        config = sheet_config[sheet_name]
        group_by = config.get("group_by")
        agg = config.get("agg")

        if not group_by:
            updated_sheets[sheet_name] = df
            continue

        try:
            grouped_df = df.groupby(group_by, as_index=False).agg(agg)

            updated_sheets[sheet_name] = grouped_df

        except Exception as e:
            errors.append(f"⚠️ {sheet_name}: grouping failed ({e})")

    if errors:
        return {
            "status": "error",
            "message": "  \n".join(errors),
            "data": None
        }

    return {
        "status": "ok",
        "message": "Grouping applied successfully.",
        "data": updated_sheets
    }


def normalize_string_columns(sheets_dict):
    updated_sheets = {}
    errors = []

    for sheet_name, df in sheets_dict.items():
        df = df.copy()
        str_cols = df.select_dtypes(include="object").columns

        for col in str_cols:
            try:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.strip()
                    .str.replace(r"\s+", " ", regex=True)
                    .str.replace(r"[’']", "", regex=True)
                    .str.title()
                )
            except Exception as e:
                errors.append(f"⚠️ {sheet_name}[{col}]: {e}")

        updated_sheets[sheet_name] = df

    if errors:
        return {
            "status": "error",
            "message": "  \n".join(errors),
            "data": None
        }

    return {
        "status": "ok",
        "message": "Data is transformed to Proper State",
        "data": updated_sheets
    }


def clean_value(x):
    if pd.isna(x):
        return None
    if isinstance(x, pd.Period):
        return x.to_timestamp().date()
    if hasattr(x, "to_pydatetime"):
        return x.to_pydatetime()
    return x