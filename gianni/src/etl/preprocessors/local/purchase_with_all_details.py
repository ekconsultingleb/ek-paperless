# by branch

from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_rows
from etl.utils import drop_na_by_name
from etl.utils import make_columns_date
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,2,6,7,10])
    data.columns = ['A','B','C','D','E']

    # Location from B
    loc_ids = data[data['A'].str.contains('Location:',na=False)].index
    data.loc[loc_ids,'Location'] = data.loc[loc_ids,'B']
    data['Location'] = data['Location'].ffill()

    # Supplier 
    sup_ids = data[data['A'].str.contains('Supplier Name:',na=False)].index
    data.loc[sup_ids,'Supplier'] = data.loc[sup_ids,'B']
    data['Supplier'] = data['Supplier'].ffill()

    # Invoice
    inv_ids = data[data['A'].str.contains('Invoice Number:',na=False)].index
    data.loc[inv_ids,'Invoice'] = data.loc[inv_ids,'B']
    data['Invoice'] = data['Invoice'].ffill()

    # Date
    date_ids = data[data['C'].str.contains('Purchase Date:',na=False)].index
    data.loc[date_ids,'Date'] = data.loc[date_ids,'D']
    data['Date'] = data['Date'].ffill()

    data = drop_rows(data,'A',value='Invoice Number:')
    data = drop_na_by_name(data,['D'])
    data = drop_na_by_name(data,['Location'])
    data.columns = ['Product Description', 'B', 'Qty', 'D', 'Total', 'Location', 'Supplier', 'Invoice', 'Purchase Date']
    cols = ['Location', 'Product Description', 'Qty', 'Total', 'Supplier', 'Invoice', 'Purchase Date']
    data = data[cols].copy()
    data = make_columns_date(data,['Purchase Date'])
    data = make_columns_numeric(data,['Total','Qty'])
    data.columns = ['location', 'raw materials','qty','total cost','supplier names','invoice #','purchase date']
    return data


