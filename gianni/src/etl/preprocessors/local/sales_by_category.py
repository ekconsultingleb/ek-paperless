from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = data.dropna(subset=[data.columns[2]])
    total_col = int(data.iloc[1].last_valid_index())
    data = keep_cols_by_index(data,[1,total_col])
    data.columns = ['Category', 'Sales']
    data['Sales'] = data['Sales'].shift(-1)
    data = drop_na_by_name(data,['Category'])
    data = make_columns_numeric(data,['Sales'])
    return data