import pandas as pd
from etl.utils import make_columns_date

info = {
    'Ending': {
        'sheet': 'Beg',
        'cols': ['location', 'product description', 'qty', 'unit', 'avg cost', 'total cost', 'month']
    }
}


def extract_sheets(file_path, sheet_names, jobs, cleaned_dict):

    with pd.ExcelFile(file_path) as xls:

        sheets_dict = {
            name: pd.read_excel(xls, sheet_name=name)
            for name in sheet_names
        }

    for key, data in sheets_dict.items():

        data.columns = [col_name.strip().lower() for col_name in data.columns]
        if 'month' in data.columns:
            data = make_columns_date(data,['month'])

        jobs.append(
            {
                'key': f'last month ' + str(key),
                'df_cols': info.get(key)['cols'],
                'sheet': info.get(key)['sheet'],
                'start_row' : 2
            }
        )

        cleaned_dict[f'last month ' + str(key)] = data


    return {
        'jobs': jobs,
        'cleaned_dict': cleaned_dict
    }