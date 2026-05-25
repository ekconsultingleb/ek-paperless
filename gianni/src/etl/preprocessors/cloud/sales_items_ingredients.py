# Price level 1, non separate pages, show cost

import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import remove_repeated_headers
from etl.utils import drop_rows
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,3])
    data.columns = ['code','desc','qty']
    data = drop_rows(data, 'code', value = 'Product Code')
    data = drop_rows(data, 'code', date = True)
    data = data.reset_index(drop=True)
    ids = data[data['code'] == 'Price Level 1'].index - 1
    data.loc[ids]
    data.loc[ids,'item'] = data.loc[ids,'code']
    data['item'] = data['item'].ffill()
    data = drop_na_by_name(data, ['qty'])
    data = make_columns_numeric(data, ['qty'])
    cols = ['item','desc','qty']
    data = data[cols]
    data.columns = ['menu items','product description','qty']
    return data