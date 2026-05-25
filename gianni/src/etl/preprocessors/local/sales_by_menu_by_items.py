from etl.utils import read
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = data.iloc[11:].copy()
    x = list(data.iloc[0])
    x[0] = 'Description'
    data.columns = x
    cols = ['Description', 'lblTotal']
    data = data[cols]
    data.columns=['Description', 'Qty']
    data = drop_na_by_name(data,['Qty'])
    ids = data[data['Description'].isna()].index
    data.loc[ids,'Total Amount'] = data.loc[ids,'Qty']
    data['Total Amount'] = data['Total Amount'].shift(-1)
    data = drop_na_by_name(data,['Description'])
    data = make_columns_numeric(data,['Qty','Total Amount'])
    data.columns = ['description', 'qty sold', 'gross sales']
    return data