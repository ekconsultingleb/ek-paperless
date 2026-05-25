# Put Rate Manually

import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_rows
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1, 2, 3, 4, 5, 6, 8, 11])
    data.columns = ['Item Id','Product Code','Product Description','Pur Unit','Qty Pur','Inv Unit','Qty I F','Unit','Avg Cost']
    data = data.iloc[3:-1].copy()
    data = remove_repeated_headers(data,'Product Code')
    data = drop_rows(data,'Item Id',date = True)

    # fill by pattern 
    mask = (
        data['Product Code'].isna() &
        data['Product Code'].shift(-1).isna() &
        data['Product Code'].shift(-2).isna()
        )
    data.loc[mask,'Category'] = data.loc[mask,'Item Id']
    data['Category'] = data['Category'].ffill()

    is_nan = data['Product Code'].isna()
    end = is_nan & ~is_nan.shift(-1, fill_value=False)
    ids = data.loc[end].index
    data.loc[ids, 'Group'] = data.loc[ids,'Item Id']
    data['Group'] = data['Group'].ffill()

    data = drop_na_by_name(data,['Product Description'])
    data = data.drop(['Product Code','Item Id'], axis = 1)    
    cols = ['Category','Group','Product Description','Qty I F','Unit','Pur Unit','Qty Pur','Inv Unit','Avg Cost']
    data = data[cols]
    data = drop_na_by_name(data,['Unit'])
    data = make_columns_numeric(data,['Qty I F','Qty Pur','Avg Cost'])
    data.columns = ['category','group','product description','qty I F','unit','pur unit','qty pur','inv unit','lbp']
    return data