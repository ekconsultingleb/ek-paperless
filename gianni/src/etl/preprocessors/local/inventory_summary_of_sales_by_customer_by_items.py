from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_date
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,2,5,10])
    data.columns = ['Code','Description','Qty','Total Price']

    # Customer
    cust_ids = data[data['Code'].str.contains('Customer Name :',na=False)].index
    data.loc[cust_ids,'Customer'] = data.loc[cust_ids,'Description']
    data['Customer'] = data['Customer'].ffill()

    # Location
    loc_ids = data[data['Code'].str.contains('LOCATION NAME:',na=False)].index
    data.loc[loc_ids,'Location'] = data.loc[loc_ids,'Description']
    data['Location'] = data['Location'].ffill()

    # Date
    date_ids = data[data['Code'].str.contains('Sales Date  :',na=False)].index
    data.loc[date_ids,'Date'] = data.loc[date_ids,'Description']
    data['Date'] = data['Date'].ffill()

    # Invoice
    inv_ids = data[data['Code'].str.contains('Invoice Number :',na=False)].index
    data.loc[inv_ids,'Invoice'] = data.loc[inv_ids,'Description']
    data['Invoice'] = data['Invoice'].ffill()

    data = remove_repeated_headers(data,'Qty')
    data = drop_na_by_name(data,['Total Price'])
    data = drop_na_by_name(data,['Description'])
    data = make_columns_date(data,['Date'])
    data = make_columns_numeric(data,['Qty','Total Price'])
    cols = ['Description','Qty','Total Price','Customer','Location','Date','Invoice']
    data = data[cols].copy()
    data['Remark'] = 'sales'
    data.columns = ['product description','qty','sales revenue','customer','location','date','invoice number','remarks']
    return data



