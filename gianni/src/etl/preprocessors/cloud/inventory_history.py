# Remove grouping by details
# nhar l jarde

import pandas as pd
from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import drop_na_by_name
from etl.utils import remove_repeated_headers
from etl.utils import make_columns_numeric


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[1,2,9])
    data.columns = ['product description','qty','location']
    data = drop_na_by_name(data,['qty'])
    data = remove_repeated_headers(data,'qty')
    data = make_columns_numeric(data,['qty'])
    return data