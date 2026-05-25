from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[2,4,5])
    data.columns = ['desc','loc','qty']
    loc_ids = data[data['loc']=='Location :'].index
    data.loc[loc_ids,'Location'] = data.loc[loc_ids,'qty']
    data['Location'] = data['Location'].ffill()
    data = data.drop(columns=['loc'])
    data.columns = ['Product Description', 'Qty', 'Location']
    data = data.dropna(how='any').copy()
    data = make_columns_numeric(data,['Qty'])
    data.columns = ['product description', 'qty', 'location']
    return data