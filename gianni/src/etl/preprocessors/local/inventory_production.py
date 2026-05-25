from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_date
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,1,4,6])
    data.columns = ['Date', 'Location Description', 'Qty', 'Product Description']
    data = drop_na_by_name(data,['Location Description'])
    data = remove_repeated_headers(data,'Qty')
    data = make_columns_date(data,['Date'])
    data= make_columns_numeric(data,['Qty'])
    data.columns = ['date', 'location', 'qty', 'production list']
    return data