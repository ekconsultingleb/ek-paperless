import pandas as pd

def read(path, header = None):
    return pd.read_excel(path, header = header)


def keep_cols_by_index(data, indices):
    if not all(isinstance(i, int) for i in indices):
        raise TypeError("All column indices must be integers")
    
    if not all(0 <= i < data.shape[1] for i in indices):
        raise IndexError(f"Column index out of range.")
    
    return data.iloc[:,indices].copy()


def drop_na_by_name(data, col_names, how="any"):
    if not isinstance(col_names, list):
        raise TypeError("col_names must be a list of column names")

    original_norm = data.columns.str.strip().str.lower()
    col_names_norm = [c.strip().lower() for c in col_names]

    missing = [
        col_names[i]
        for i, c in enumerate(col_names_norm)
        if c not in original_norm
    ]
    if missing:
        raise KeyError(f"Missing columns: {missing}")

    ids = [original_norm.get_loc(c) for c in col_names_norm]
    subset = data.columns[ids]

    return data.dropna(subset = subset, how = how).copy()


def make_columns_numeric(data, cols, er = 'raise'):
    if er not in {"raise", "coerce", "ignore"}:
        raise ValueError("er must be one of: 'raise', 'coerce', 'ignore'")

    if not isinstance(cols,list):
        raise TypeError('cols must be a list of column names')
    
    original_norm = data.columns.str.strip().str.lower()
    cols_norm = [c.strip().lower() for c in cols]

    missing = [cols[i] for i,c in enumerate(cols_norm) if c not in original_norm]
    if missing:
        raise KeyError(f'Missing columns: {missing}')
    
    ids = [original_norm.get_loc(c) for c in cols_norm]

    for c in data.columns[ids]:
        data[c] = pd.to_numeric(data[c], errors = er)

    return data
    

def make_columns_date(data, cols, er = 'raise'):
    if er not in {"raise", "coerce", "ignore"}:
        raise ValueError("er must be one of: 'raise', 'coerce', 'ignore'")

    if not isinstance(cols,list):
        raise TypeError('cols must be a list of column names')
    
    original_norm = data.columns.str.strip().str.lower()
    cols_norm = [c.strip().lower() for c in cols]

    missing = [cols[i] for i,c in enumerate(cols_norm) if c not in original_norm]
    if missing:
        raise KeyError(f'Missing columns: {missing}')
    
    ids = [original_norm.get_loc(c) for c in cols_norm]

    for c in data.columns[ids]:
        data[c] = pd.to_datetime(data[c], errors = er).dt.date

    return data


def remove_repeated_headers(data, col):
    if not isinstance(col, str):
        raise TypeError("Column name must be a string")

    if col not in data.columns:
        raise KeyError(f"{col} is not a column in the dataframe")

    col_norm = col.strip().lower()
    values_norm = (data[col].astype(str).str.strip().str.lower())

    return data[values_norm != col_norm].copy()


def drop_rows(data,col,value=r'\d{4}-\d{2}-\d{2}',date=False):
    if not isinstance(col,str):
        raise TypeError('col must be a column name')
    
    if not isinstance(value,str):
        raise TypeError('value must be a string')
    
    cols_norm = data.columns.str.strip().str.lower()
    if col.strip().lower() not in cols_norm:
        raise KeyError(f'{col} is not a column in the dataframe')
    
    real_col = data.columns[cols_norm.get_loc(col.strip().lower())]

    if date:
        return data[~data[real_col].astype(str).str.contains(value,regex=True,na=False)].copy()
    
    return data[data[real_col] != value].copy()


def clean_check(data,cols):
    if not isinstance(cols,list):
        raise TypeError('cols must be a list of column names')
    
    original_norm = data.columns.str.strip().str.lower()
    cols_norm = [c.strip().lower() for c in cols]

    missing = [cols[i] for i,c in enumerate(cols_norm) if c not in original_norm]
    if missing:
        raise KeyError(f'Missing columns: {missing}')

    ids = [original_norm.get_loc(c) for c in cols_norm]

    for c in data.columns[ids]:
        data[c] = pd.to_numeric(data[c].astype(str).str.replace(',', '', regex=False), errors='coerce').astype('Int64')

    return data
