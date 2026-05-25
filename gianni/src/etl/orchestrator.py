from pathlib import Path
import re
from typing import Literal

import pandas as pd
import etl.preprocessors.cloud as cloud
import etl.preprocessors.local as local


cleaner_by_code = {
    'cloud' : {
        "REP_I_0022.xlsx": ("sales items ingredients", cloud.sales_items_ingredients.preprocess),
        "REP_I_00201.xlsx": ("inventory items ingredients", cloud.inventory_items_ingredients_qtp.preprocess),
        "REP_I_00023D_rows.xlsx": ("wastage report", cloud.wastage_report.preprocess),
        "REP_I_0024.xlsx": ("inventory production", cloud.inventory_production.preprocess),
        "REP_I_0033_rows.xlsx": ("inventory history", cloud.inventory_history.preprocess),
        "REP_I_0044.xlsx": ("programming summary inventory", cloud.programming_summary_inventory.preprocess),
        "REP_I_00074.xlsx": ("sales item wastage", cloud.sales_item_wastage.preprocess),
        "REP_I_0087.xlsx": ("requisition summary", cloud.requisition_summary.preprocess),
        "REP_I_0087_IB.xlsx": ("requisition summary IB", cloud.requisition_summary_IB.preprocess),
        "REP_I_00268.xlsx": ("summary of sales by customer by item", cloud.summary_of_sales_by_customer_by_item.preprocess),
        "REP_I_00462.xlsx": ("purchase master report for all branches", cloud.purchase_master_report_for_all_branches.preprocess),
        "rep_s_00016.xlsx": ("discount by items", cloud.discount_by_items.preprocess),
        "rep_s_00161.xlsx": ("discount by category by department", cloud.discount_by_category_by_department.preprocess),
        # "REP_S_00175.xlsx": ("sales item by transaction", cloud.sales_item_by_transaction.preprocess),
        'REP_S_00513.xlsx': ('discount by invoice with details', cloud.discount_by_invoice_with_details.preprocess),
        "REP_S_00178.xlsx": ("programming summary sales", cloud.programming_summary_sales.preprocess),
        "rep_s_00191_rows.xlsx": ("sales by items", cloud.sales_by_items.preprocess),
        "rep_s_00438.xlsx": ("discount by description by employee", cloud.discount_by_description_by_employee.preprocess),
        "rep_hs_0006.xlsx": ("sales by category", cloud.sales_by_category.preprocess)

    },

    'local' : {
        "rep_i_0022.xls": ("sales items ingredients", local.sales_items_ingredients.preprocess),
        "rep_i_00201.xls": ("inventory items ingredients", local.inventory_items_ingredients_qtp.preprocess),
        'rep_s_00161.xls': ('discount by category', local.discount_by_category.preprocess),
        'rep_s_00438.xls': ('discount by description by employee', local.discount_by_description_by_server.preprocess),
        'rep_s_00513.xls': ('discount by invoice with details', local.discount_by_invoive_by_details.preprocess),
        'rep_s_00016.xls': ('discount by items', local.discount_by_items.preprocess ),
        'rep_i_0033.xls': ('inventory history', local.inventory_history.preprocess),
        'rep_i_0024.xls': ('inventory production', local.inventory_production.preprocess),
        'rep_i_00268.xls': ('inventory / summary of sales by customer by items',local.inventory_summary_of_sales_by_customer_by_items.preprocess),
        'rep_i_0023.xls': ('inventory wastage items', local.inventory_wastage_items.preprocess),
        'rep_s_00188.xls': ('list sales items', local.list_sales_items.preprocess),
        'rep_i_0044.xls': ('programming summary inventory', local.programming_summary_inventory.preprocess),
        'rep_i_0051.xls': ('purchase with all details', local.purchase_with_all_details.preprocess),
        'rep_i_0087.xls': ('requisition summary', local.requisition_summary.preprocess),
        'rep_s_00138.xls': ('sales by menu by items', local.sales_by_menu_by_items.preprocess),
        'rep_i_00268_s.xls': ('sales / summary of sales by customer by items', local.sales_summary_of_sales_by_customer_by_items.preprocess),
        'rep_i_0074.xls': ('sales wastage items', local.sales_wastage_items.preprocess),
        "rep_s_00135.xls": ("sales by category", local.sales_by_category.preprocess)
    }
}


def _is_requisition_summary_ib_filename(filename: str) -> bool:
    """Match REP_I_0087_IB.xlsx and variants like REP_I_0087_IB (1).xlsx."""
    return re.fullmatch(r"REP_I_0087_IB(?: \(\d+\))?\.xlsx", filename) is not None


def clean_folder(folder: str | Path, source: Literal["cloud", "local"] = "cloud", log_func=print) -> dict[str, object]:
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise NotADirectoryError(f"Folder not found or not a directory: {folder}")
    if source not in cleaner_by_code:
        raise ValueError(f"source must be 'cloud' or 'local', got {source!r}")

    cleaners = cleaner_by_code[source]
    cleaned: dict[str, object] = {}
    ib_files = [
        p
        for p in folder.iterdir()
        if p.is_file() and _is_requisition_summary_ib_filename(p.name)
    ]
    multi_ib = len(ib_files) > 1

    for p in folder.iterdir():
        if not p.is_file():
            continue

        if multi_ib and _is_requisition_summary_ib_filename(p.name):
            ib_index = (
                sum(1 for k in cleaned.keys() if k.startswith("requisition summary IB "))
                + 1
            )
            output_name = f"requisition summary IB {ib_index}"
            cleaner = cloud.requisition_summary_IB.preprocess

            try:
                result = cleaner(str(p))
                cleaned[output_name] = result

                if isinstance(result, pd.DataFrame):
                    nan_cols = result.columns[result.isna().any()].tolist()
                    if nan_cols:
                        log_func(f"⚠️ NaNs in {output_name}: {nan_cols}")

                log_func(f"Cleaned {p.name} -> {output_name}")

            except Exception as e:
                log_func(f"Failed cleaning {p.name} -> {output_name}\n{e}")

            continue

        entry = cleaners.get(p.name)
        if entry is None:
            continue

        output_name, cleaner = entry

        try:
            result = cleaner(str(p))
            cleaned[output_name] = result

            if isinstance(result, pd.DataFrame):
                nan_cols = result.columns[result.isna().any()].tolist()
                if nan_cols:
                    log_func(f"⚠️ NaNs in {output_name}: {nan_cols}")

            log_func(f"Cleaned {p.name} -> {output_name}")

        except Exception as e:
            log_func(f"Failed cleaning {p.name} -> {output_name}\n{e}")

    return cleaned
