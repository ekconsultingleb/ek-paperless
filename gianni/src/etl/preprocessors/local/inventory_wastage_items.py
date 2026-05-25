from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import make_columns_date


def preprocess(path):
    data = read(path)
    data = data.dropna(how='all')
    date_ids = data[data.iloc[:,0].notna() & data.drop(columns=data.columns[0]).isna().all(axis=1)].index
    loc_ids = data[data.iloc[:,0].str.contains('Location Name :',na=False)].index
    data = keep_cols_by_index(data,[0,2,3,5])
    data.columns = ['Qty','Code','Description','Remark']
    data.loc[loc_ids,'Location'] = data.loc[loc_ids,'Code']
    data['Location'] = data['Location'].ffill()
    data.loc[date_ids,'Date'] = data.loc[date_ids,'Qty']
    data['Date'] = data['Date'].ffill()
    data = make_columns_numeric(data,['Qty'],er='coerce')
    data = drop_na_by_name(data,['Qty'])
    data = drop_na_by_name(data,['Description'])
    data.columns = ['Qty','Code','Product Description', 'Remark', 'Location', 'Date']
    cols = ['Location','Qty','Product Description', 'Remark','Date']
    data = data[cols].copy()
    data = make_columns_date(data,['Date'])
    data.columns = ['location','qty','product description','original remarks','date']
    return data