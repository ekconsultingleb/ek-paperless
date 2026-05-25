# by branch
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_rows
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import make_columns_date


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,3,6,7,8])
    data.columns = ['Product Description','loc','Date', 'Qty', 'Remark','Unit Cost']
    ids = data[data['loc'].str.contains('Location Name :', na = False)].index
    data.loc[ids,'Location'] = data.loc[ids,'Date']
    data['Location'] = data['Location'].ffill()
    data['Product Description'] = data['Product Description'].ffill()
    data = make_columns_date(data,['Date'],er='coerce')
    data = drop_na_by_name(data,['Date'])
    cols = ['Product Description', 'Qty', 'Remark','Date','Unit Cost','Location']
    data =  data[cols].copy()
    data = make_columns_numeric(data,['Qty','Unit Cost'])
    data.columns = ['product', 'qty', 'original remarks','date','unit cost','location']
    return data