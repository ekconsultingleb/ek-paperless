import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import remove_repeated_headers
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import drop_rows

def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,2,6])
    data.columns = ['product code', 'product description', 'qty', 'sales revenue']
    id = data[data['product code'] == 'Product Code'].index[0] # Keep only the rows after the first Header
    data = data.iloc[id:].copy()
    data = remove_repeated_headers(data,'product code')

    # Create 'customer' from 'product code'
    cust_ids = data[data['product code'].str.contains('Customer Name: ',na=False)].index
    data.loc[cust_ids,'customer'] = data.loc[cust_ids,'product code'].str.replace('Customer Name: ','',regex = False)
    data['customer'] = data['customer'].ffill()

    # Create 'location' from 'product code'
    loc_ids = data[data['product code'].str.contains('Location: ',na=False)].index
    data.loc[loc_ids,'location'] = data.loc[loc_ids,'product code'].str.replace('Location: ','',regex = False)
    data['location'] = data['location'].ffill()

    # 'date' is 'product code' converted to type date
    date_ids = data[data['product description'].str.contains('From Date:',na=False)].index
    data = data.drop(index=date_ids).copy()
    data['date'] = pd.to_datetime(data['product code'],errors='coerce').dt.date
    data['date'] = data['date'].ffill()

    # Create 'invoice number' from 'product code'
    inv_ids = data[data['product code'].str.contains('Invoice Number: ', na = False)].index
    data.loc[inv_ids,'invoice number'] = data.loc[inv_ids,'product code'].str.replace('Invoice Number: ', '', regex = False)
    data['invoice number'] = data['invoice number'].ffill()

    data = drop_na_by_name(data,['product description'])
    data = data.drop(columns='product code').copy()
    data = drop_na_by_name(data,['qty'])
    data = make_columns_numeric(data,['qty','sales revenue'])
    data['remark'] = 'sales'
    data['original remarks'] = pd.NA
    return data