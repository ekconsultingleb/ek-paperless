from etl.utils import read
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import make_columns_date

def preprocess(path):
    data = read(path)
    dt = data.iloc[9,7]
    col_idx = 2
    first_row = data.iloc[:, col_idx].first_valid_index()
    last_row = data.iloc[:, col_idx].last_valid_index()
    row_idx = 12
    valid_cols = data.iloc[row_idx].notna()
    first_col = valid_cols.idxmax()
    last_col = valid_cols[::-1].idxmax()
    data = data.iloc[first_row : last_row + 1, first_col : last_col + 1].copy()
    data = data.iloc[:,[0,-1]].copy()
    data.columns = ['category', 'sales']
    data['sales'] = data['sales'].shift(-1)
    data = drop_na_by_name(data, ['category'])
    data = make_columns_numeric(data, ['sales'])
    data.loc[len(data)] = ['calculated_sum', data.sales.sum()]
    data['report_date'] = dt
    data = make_columns_date(data, ['report_date'])
    cols = ['report_date','category','sales']
    data = data[cols]
    return data