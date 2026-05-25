import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import drop_rows
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,2,5])
    data.columns = ['Description','x','Price','y']

    # Category 
    ids = data[data['x'].notna()].index
    data.loc[ids,'Category'] = data.loc[ids,'x']
    data['Category'] = data['Category'].ffill()

    # Group
    ids = pd.to_numeric(data['y'],errors='coerce').isna()
    non_numerics = data.loc[ids]
    new_ids = non_numerics[non_numerics['y'].notna()].index
    data.loc[new_ids,'Group'] = data.loc[new_ids,'y']
    data['Group'] = data['Group'].ffill()

    data = drop_na_by_name(data,['Description'])
    data = drop_rows(data,'Description',value='Description')
    data = drop_na_by_name(data,['Price'])
    cols = ['Category', 'Group', 'Description', 'Price']
    data = data[cols]
    data = make_columns_numeric(data,['Price'])
    data.columns = ['category', 'group', 'menu items', 'sp exc vat']

    return data