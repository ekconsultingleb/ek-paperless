import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,4,7])
    data.columns = ['Check', 'QTY', 'Description']
    cols = ['Check','Description','QTY']
    data = data[cols]  
    data = drop_na_by_name(data,['QTY'])
    data = remove_repeated_headers(data,'QTY')
    data = make_columns_numeric(data,['QTY'])
    data.columns = ['check','description','qty']
    return data