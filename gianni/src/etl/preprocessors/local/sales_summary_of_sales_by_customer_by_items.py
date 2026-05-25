from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import make_columns_numeric
from etl.utils import make_columns_date

def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,2,3,7,10])
    data.columns = ['Code', 'Info', 'Desc', 'Qty', 'Amount']

    cust_ids = data[data['Code'].str.contains('Customer Name :', na = False)].index
    data.loc[cust_ids,'Customer'] = data.loc[cust_ids,'Info']
    data['Customer'] = data['Customer'].ffill()

    loc_ids = data[data['Code'].str.contains('LOCATION NAME:', na = False)].index
    data.loc[loc_ids,'Location'] = data.loc[loc_ids,'Info']
    data['Location'] = data['Location'].ffill()

    date_ids = data[data['Code'].str.contains('Sales Date  :', na = False)].index
    data.loc[date_ids,'Date'] = data.loc[date_ids,'Info']
    data['Date'] = data['Date'].ffill()

    inv_ids = data[data['Code'].str.contains('Invoice Number :', na = False)].index
    data.loc[inv_ids,'Invoice'] = data.loc[inv_ids,'Info']
    data['Invoice'] = data['Invoice'].ffill()
    
    data = data.drop(columns=['Info','Code'])
    data = data.dropna(how='any')
    data.columns = ['Description','Qty','Total Price','Customer','Location','Date','Invoice']
    data = make_columns_numeric(data,['Qty','Total Price'])
    data = make_columns_date(data,['Date'])
    data['Remark'] = 'sales'
    data.columns = ['product', 'qty','total','customer','location','date','invoice number', 'remarks']
    return data