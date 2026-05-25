# In orchestrator: sales items by transaction

from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_numeric
from etl.utils import clean_check


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[2,3,7])
    data.columns = ['Description', 'Check', 'QTY']
    data = clean_check(data,['Check'])
    data['Check'] = data['Check'].ffill()
    data = drop_na_by_name(data,['Description','QTY'])
    data = remove_repeated_headers(data,'QTY')
    cols = ['Check', 'Description', 'QTY']
    data = data[cols]
    data = make_columns_numeric(data,['QTY'])
    data.columns = ['check', 'description', 'qty']
    return data