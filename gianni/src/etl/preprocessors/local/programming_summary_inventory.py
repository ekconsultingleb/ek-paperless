from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import drop_rows
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0, 2, 3, 5, 7, 9, 10, 11, 12, 14])
    data.columns= ['code','Group','Product Description','Category','Pur Unit','Qty Pur','Inv Unit','Qty I F','Unit','Avg Cost']
    data['Category'] = data['Category'].ffill()
    data['Group'] = data['Group'].ffill()
    data = drop_rows(data,'code',value='Product Code')
    data = drop_na_by_name(data,['Category','Group','code','Product Description','Qty I F','Pur Unit'])
    cols = ['Category','Group','Product Description','Qty I F','Unit','Pur Unit','Qty Pur','Inv Unit','Avg Cost']
    data = data[cols]
    data = make_columns_numeric(data,['Qty I F','Qty Pur','Avg Cost'])
    data.columns = ['category','group','product description','qty I F','unit','pur unit','qty pur','inv unit','lbp']
    return data