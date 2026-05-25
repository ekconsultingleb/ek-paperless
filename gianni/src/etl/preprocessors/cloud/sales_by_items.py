import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,2,3])
    data.columns = ['description', 'qty sold', 'gross sales']
    data = drop_na_by_name(data,['qty sold'])
    data = remove_repeated_headers(data,'description')
    data = make_columns_numeric(data,['qty sold','gross sales'])
    return data