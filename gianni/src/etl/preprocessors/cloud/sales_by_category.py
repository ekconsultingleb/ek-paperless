from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import drop_rows
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    total_col = int(data.iloc[3].last_valid_index())
    data = keep_cols_by_index(data,[0,total_col])
    data.columns = ['Category', 'Sales']
    data = drop_na_by_name(data,['Category','Sales'])
    data = drop_rows(data,'Category',value = 'Total ')
    data = make_columns_numeric(data,['Sales'])
    return data