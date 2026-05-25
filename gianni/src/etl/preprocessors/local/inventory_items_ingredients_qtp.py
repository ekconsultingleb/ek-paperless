from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[2,5])
    data.columns = ['Product Description','Qty']
    data = remove_repeated_headers(data,'Qty')
    data = drop_na_by_name(data,['Product Description','Qty'])
    data['get_ids'] = data['Qty']
    data = make_columns_numeric(data,['get_ids'], er='coerce')
    ids = data[data['get_ids'].isna()].index
    # data.loc[ids,'Production Name'] = data.loc[ids,'Product Description']
    # data['Production Name'] = data['Production Name'].ffill()
    data.loc[ids,'Qty'] = data.loc[ids,'Qty'].str.replace('Ingredients to prepare ','',regex=False)
    data.loc[ids,'Production Name'] = data.loc[ids,'Qty'].str.split().apply(lambda x: ' '.join(x[3:]))
    data['Production Name'] = data['Production Name'].ffill()
    data.loc[ids,'to prepare'] = data.loc[ids,'Qty'].str.split().apply(lambda x: x[:2])
    data.loc[ids,'Qty to be Prepared'] = data.loc[ids,'to prepare'].apply(lambda x: x[0])
    data.loc[ids,'Prepared Unit'] = data.loc[ids,'to prepare'].apply(lambda x: x[1])
    data[['Qty to be Prepared','Prepared Unit']] = data[['Qty to be Prepared','Prepared Unit']].ffill()
    data = data.drop(index=ids)
    cols = ['Production Name', 'Product Description', 'Qty','Qty to be Prepared', 'Prepared Unit']
    data = data[cols].copy()
    data = make_columns_numeric(data,['Qty','Qty to be Prepared'])
    data.columns = ['production name', 'product description', 'qty','qty to prepared', 'prepared unit']
    return data