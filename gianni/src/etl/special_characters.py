import pandas as pd

def excel_safe_cell(v):
    if hasattr(v, "item"):
        try:
            v = v.item()
        except Exception:
            pass

    if v is None:
        return ""

    if isinstance(v, float) and v != v:
        return ""

    if isinstance(v, float) and (v == float("inf") or v == float("-inf")):
        return ""
    
    if isinstance(v, str):
        v = v.lstrip("*")
        s = v.lstrip()
        if s.startswith(("=", "+", "-", "@")) and not s.startswith("'"):
            return "'" + v

    return v


def special_char(data_dict: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    safe_dict = {}
    for key, df in data_dict.items():
        df_safe = df.copy()
        for col in df_safe.columns:
            df_safe[col] = df_safe[col].map(excel_safe_cell)
        safe_dict[key] = df_safe
    return safe_dict
