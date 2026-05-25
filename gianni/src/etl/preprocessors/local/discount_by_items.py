from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import make_columns_numeric
from etl.utils import clean_check


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[3,5,7])
    data.columns = ['Check','Description','QTY']
    data = drop_na_by_name(data,['Check'])
    data = clean_check(data,['Check'])
    data = make_columns_numeric(data,['QTY'])
    data.columns = ['check', 'description', 'qty']
    return data