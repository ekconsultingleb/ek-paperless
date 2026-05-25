# by branch - with details
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import make_columns_date
from etl.utils import drop_rows


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,2,3])
    data.columns = ['desc','qty','remark','unit cost']
    data = drop_rows(data,'qty',value='Type: All Modules')
    data = drop_rows(data,'desc',value='REP_I_00074')
    data['date'] = data['desc']
    data = make_columns_date(data,['date'], er='coerce')
    drop_ids = data[data['date'].notna()].index
    data['date'] = data['date'].bfill()
    data = data.drop(index=drop_ids).copy()
    ids = data[data['desc'].str.startswith('Location: ', na=False)].index
    data.loc[ids,'loc'] = data.loc[ids,'desc'].str.replace('Location: ','',regex=False)
    data['loc'] = data['loc'].ffill()
    data['qtyy'] = data['qty']
    data = make_columns_numeric(data,['qtyy'],er='coerce')
    data = drop_na_by_name(data,['qtyy'])
    data.columns = ['product','qty', 'original remarks', 'unit cost','date','location','qty_0']
    cols = ['product','date', 'qty', 'original remarks','unit cost','location']
    data = data[cols].copy()
    data = make_columns_numeric(data,['qty','unit cost'])
    data = make_columns_date(data,['date'])
    return data