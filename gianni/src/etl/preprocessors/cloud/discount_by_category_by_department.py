import pandas as pd
from etl.utils import read 
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric

def preprocess(path):
    data = read(path)
    data = data.iloc[:,[1,-3]].copy()
    data.columns = ['category', 'total']
    data = drop_na_by_name(data,['category'])
    data = make_columns_numeric(data,['total'])
    return data