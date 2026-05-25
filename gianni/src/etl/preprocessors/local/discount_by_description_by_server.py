# In orchestrator: discount by description by employee

from etl.utils import read
from etl.utils import keep_cols_by_index
from etl.utils import remove_repeated_headers
from etl.utils import drop_rows
from etl.utils import make_columns_numeric
from etl.utils import drop_na_by_name
from etl.utils import clean_check


def preprocess(path):
    data = read(path)
    data = keep_cols_by_index(data,[0,7,8])
    data.columns = ['Check', 'Discount', 'Amount']
    data = remove_repeated_headers(data,'Discount')
    data = drop_rows(data,'Discount')
    data = drop_na_by_name(data,['Check','Discount','Amount'])
    data = make_columns_numeric(data,['Discount','Amount'])
    data['Discount_Percentage'] = data['Discount'] / data['Amount']
    data = clean_check(data,['Check'])
    data.columns = ['check', 'discount', 'amount', 'discount_percentage']
    return data