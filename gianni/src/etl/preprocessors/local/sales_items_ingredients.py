from etl.utils import read
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data.columns = ['a','b','c','d','e','f','g','h','i','j','k','l']
    x = data[data.drop(columns=['f']).isna().all(axis=1)]
    item_ids = x[x['f'].notna()].index
    data.loc[item_ids,'item'] = data.loc[item_ids,'f']
    data['item'] = data['item'].ffill()
    data = drop_na_by_name(data,['c'])
    cols = ['item','c','f']
    data = data[cols].copy()
    data.columns = ['Item','Ingredient','Qty']
    data = make_columns_numeric(data,['Qty'], er='coerce')
    data = drop_na_by_name(data,['Qty'])
    data.columns = ['menu items','product description','qty']
    return data