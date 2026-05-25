import pandas as pd
import numpy as np
from pathlib import Path
from typing import Literal
from importlib import import_module
from etl.utils import keep_cols_by_index
import streamlit as st

FINAL_COLS = ['Case', 'Item', 'Ingredient', 'Qty', 'Qty autocalc', 'Qty omega']

FILE_MAP = {
    "REP_I_0022.xlsx": (
        "cloud",
        "sales_items_ingredients",
    ),
    "REP_I_00201.xlsx": (
        "cloud",
        "inventory_items_ingredients_qtp",
    ),
    "rep_i_0022.xls": (
        "local",
        "sales_items_ingredients",
    ),
    "rep_i_00201.xls": (
        "local",
        "inventory_items_ingredients_qtp",
    ),
}


def sort_df(df):
    return df.sort_values(['Item', 'Ingredient']).reset_index(drop=True)


def align_cols(df):
    return df.reindex(columns=FINAL_COLS)


def compare(
        folder: str | Path,
) -> dict[str, object]:
    
    folder = Path(folder)
    autocalc_path = folder / 'Auto Calc.xlsx'

    matched_file = next(
        f for f in folder.iterdir()
        if f.is_file() and f.name in FILE_MAP
    )
    source, submodule = FILE_MAP[matched_file.name]
    preprocess = import_module(
        f"etl.preprocessors.{source}.{submodule}"
    ).preprocess

    omega = preprocess(matched_file)
    autocalc = pd.read_excel(autocalc_path)

    cols = ['Item', 'Ingredient', 'Qty']

    omega = keep_cols_by_index(omega,[0,1,2])
    omega.columns = cols

    autocalc = keep_cols_by_index(autocalc,[0,1,2])
    autocalc.columns = cols

    items_autocalc = set(autocalc['Item'])
    items_omega = set(omega['Item'])

    only_items_autocalc = items_autocalc - items_omega
    only_items_omega = items_omega - items_autocalc
    common_items = items_autocalc & items_omega

    a_common = autocalc[autocalc['Item'].isin(common_items)]
    o_common = omega[omega['Item'].isin(common_items)]

    merged = a_common.merge(
        o_common,
        on=['Item', 'Ingredient'],
        how='outer',
        suffixes=('_autocalc', '_omega'),
        indicator=True
    )

    merged['Case'] = pd.NA
    merged.loc[merged['_merge'] == 'left_only', 'Case'] = 'ingredient only in autocalc'
    merged.loc[merged['_merge'] == 'right_only', 'Case'] = 'ingredient only in omega'

    both_mask = merged['_merge'] == 'both'

    if both_mask.any():
        merged.loc[both_mask, 'Case'] = np.where(
            np.isclose(
                merged.loc[both_mask, 'Qty_autocalc'],
                merged.loc[both_mask, 'Qty_omega'],
                equal_nan=True
            ),
            pd.NA,
            'qty mismatch'
        )

    merged = merged[merged['Case'].notna()]

    qty_mismatch = merged.loc[merged['Case'] == 'qty mismatch', [
        'Case', 'Item', 'Ingredient', 'Qty_autocalc', 'Qty_omega'
    ]].rename(columns={
        'Qty_autocalc': 'Qty autocalc',
        'Qty_omega': 'Qty omega'
    })

    add_ing_to_omega = merged.loc[merged['Case'] == 'ingredient only in autocalc', [
        'Case', 'Item', 'Ingredient', 'Qty_autocalc'
    ]].rename(columns={'Qty_autocalc': 'Qty'})

    add_ing_to_autocalc = merged.loc[merged['Case'] == 'ingredient only in omega', [
        'Case', 'Item', 'Ingredient', 'Qty_omega'
    ]].rename(columns={'Qty_omega': 'Qty'})

    items_only_in_autocalc_df = autocalc.loc[autocalc['Item'].isin(only_items_autocalc), [
        'Item', 'Ingredient', 'Qty'
    ]].copy()
    items_only_in_autocalc_df.insert(0, 'Case', 'item only in autocalc')

    items_only_in_omega_df = omega.loc[omega['Item'].isin(only_items_omega), [
        'Item', 'Ingredient', 'Qty'
    ]].copy()
    items_only_in_omega_df.insert(0, 'Case', 'item only in omega')

    final_diff = pd.concat([
        align_cols(qty_mismatch),
        align_cols(add_ing_to_omega),
        align_cols(add_ing_to_autocalc),
        align_cols(items_only_in_autocalc_df),
        align_cols(items_only_in_omega_df),
    ], ignore_index=True)

    final_diff = sort_df(final_diff)

    RESULTS = {
        'DIFF': final_diff,
        'add items to Omega': items_only_in_autocalc_df,
        'add items to Auto Calc': items_only_in_omega_df,
        'add ingredients to Omega': add_ing_to_omega,
        'add ingredients to Auto Calc': add_ing_to_autocalc,
        'Qty mismatch': qty_mismatch,
        'omega': omega,
        'autocalc': autocalc
    }

    RESULTS = {
        k: v for k, v in RESULTS.items()
        if not (isinstance(v, pd.DataFrame) and v.empty)
    }

    return RESULTS