import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import clean_check

def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,2,3])
    data.columns = ['check','description', 'qty']
    data = clean_check(data,['check'])
    data = drop_na_by_name(data,['description','qty'])
    data = make_columns_numeric(data,['qty'], er='coerce')
    data = drop_na_by_name(data,['qty'])
    data = data.reset_index(drop = True)
    return data