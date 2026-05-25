# all to all

from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_date
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0, 2, 3, 4, 5, 6, 8])
    data.columns = ['From Location','From Branch','To Location','To Branch','Date','Product','Qty']
    data = data.dropna(how='any')
    data = remove_repeated_headers(data,'From Location')
    data = make_columns_numeric(data,['Qty'])
    data = make_columns_date(data,['Date'])
    cols = ['Product','From Location','From Branch','To Location','To Branch','Qty','Date']
    data = data[cols]
    data.columns = ['product','from location','from branch','to location','to branch','qty','date']
    return data