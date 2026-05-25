# by Details

import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import remove_repeated_headers
from etl.utils import drop_na_by_name
from etl.utils import make_columns_date, make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,2,3,4,6])
    data.columns = ['From Location', 'To Branch', 'To Location', 'Date', 'Product', 'Qty'] 
    ids = data[data['From Location'].str.startswith('Branch: ', na=False)].index
    data.loc[ids,'From Branch'] = data.loc[ids,'From Location'].str.replace('Branch: ','',regex=False)
    data['From Branch'] = data['From Branch'].ffill()
    data = drop_na_by_name(data,['Product'])
    data = remove_repeated_headers(data,'Product')
    data = make_columns_date(data,['Date'])
    data = make_columns_numeric(data,['Qty'])
    cols = ['Product','From Location','From Branch','To Location','To Branch','Qty','Date']
    data = data[cols]
    data.columns = ['product','from location','from branch','to location','to branch','qty','date']
    return data