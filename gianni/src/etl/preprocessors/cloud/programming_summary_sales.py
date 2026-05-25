# All Branches

import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import remove_repeated_headers
from etl.utils import drop_rows
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,4])
    data.columns = ['ID','Description','Price']
    data = drop_rows(data,'ID','Item ID')
    data = drop_rows(data,'ID',date=True)
    data = remove_repeated_headers(data,'Description')
    data = data.reset_index(drop=True)
    data.loc[6:,'ID'] = data.loc[6:,'ID'].shift(-1)
    data = drop_na_by_name(data,['ID'])

    mask = (
        data['Description'].isna() &
        data['Description'].shift(-1).isna() &
        data['Description'].shift(-2).isna()
        )
    data.loc[mask,'Category'] = data.loc[mask,'ID']
    data['Category'] = data['Category'].ffill()

    is_nan = data['Description'].isna()
    end = is_nan & ~is_nan.shift(-1, fill_value=False)
    ids = data.loc[end].index
    data.loc[ids,'Group'] = data.loc[ids,'ID']
    data['Group'] = data['Group'].ffill()
    data = drop_na_by_name(data,['Description'])
    data = make_columns_numeric(data,['Price'])

    cols = ['Category', 'Group', 'Description', 'Price']
    data = data[cols]
    data.columns = ['category', 'group', 'menu items', 'sp exc vat']

    return data