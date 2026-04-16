SHEET_CONFIG = {
    
    "Rep.M.Eng.": { ############################################################################################
        "target_table": "ac_menu_eng",

        "expected_columns": [
        "month",
        "category",
        "item_group",
        "menu_items",
        "qty_sold",
        "popularity",
        "cost_percentage",
        "cost",
        "selling_price",
        "profit",
        "total_cost",
        "total_revenue",
        "total_profit",
        "profit_category",
        "popularity_category",
        "menu_item_class"
        ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "menu_items"
        ],

        "load_mode": "insert",
    },

    "Rep.M.Mix": { ############################################################################################
        "target_table": "ac_menu_mix",

        "expected_columns": [
            "month",
            "category",
            "item_group",
            "menu_items",
            "qty_sold",
            "gross_revenue",
            "sales_mix_percentage",
            "menu_price",
            "cost",
            "contribution_margin",
            "total_contribution_margin"
            ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "menu_items"
        ],

        "load_mode": "insert",
    },

    "Rep.Theo": { ############################################################################################
        "target_table": "ac_theoretical",

        "expected_columns": [
            "month",
            "category",
            "item_group",
            "menu_items",
            "new_cost",
            "current_sprice",
            "gross_sales",
            "discount",
            "sales",
            "theoretical_cost",
            "cost_of_discount",
            "total_revenue",
            "cost_percentage",
            "sp_exc_vat",
            "total_ek_rev",
            "rev_not_made",
            "mode_4",
            "mode_1",
            "cost_of_mode_4",
            "cost_of_mode_1",
            "cost_percentage_of_m1"
            ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "menu_items"
        ],

        "load_mode": "insert",
    },

    "SP": { ############################################################################################
        "target_table": "ac_selling_prices",

        "expected_columns": [
            'menu_items', 
            'sp_exc_vat',
            'category', 
            'item_group'
        ],

        "unique_key": [
            "branch_id",
            "report_date",
            "menu_items"
        ],

        "load_mode": "insert",
    },

    "Rep.Variance": { ############################################################################################
        "target_table": "ac_variance",

        "expected_columns": [
            'month',
            'category',
            'item_group',
            'location',
            'products',
            'qty_pck',
            'unit',
            'inv_unit',
            'beginning',
            'purchase',
            'trin',
            'prd_in',
            'trout',
            'prd_out',
            'sales',
            'waste',
            'system',
            'ending',
            'variance',
            'avg_cost',
            'tt_variance',
            'chef_prd',
            'auto_prdk',
            'diff',
            'adjustment',
            'dont_show'
        ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "location",
            "products"
        ],

        "load_mode": "insert",
    },

    "Sales": { ############################################################################################
        "target_table": "ac_sales",

        "expected_columns": [
            'description',
            'qty_sold',
            'gross_sales',
            'category',
            'item_group',
            'cost',
            'month'
        ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "description"
        ],

        "load_mode": "insert",
    },

    "Cogs": { ############################################################################################
        "target_table": "ac_cogs",

        "expected_columns": [
            'month',
            'category',
            'gross_sales',
            'discount',
            'net_sales',
            'beginning',
            'purchase',
            'transfer_in',
            'transfer_out',
            'ending',
            'gross_cogs',
            'staff_meal',
            'cost_of_discount',
            'waste',
            'consumed_oil',
            'consumed_charcoal',
            'sales_cost',
            'other_waste',
            'net_cogs',
            'theoretical_cost',
            'total_variance',
        ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "category"
        ],

        "load_mode": "insert",
    },

    "Disc. Cat.": { ############################################################################################
        "target_table": "ac_discount_category",

        "expected_columns": [
            'category', 
            'total', 
            'month'
        ],

        "date_column": "month",

        "unique_key": [
            "branch_id",
            "report_date",
            "category"
        ],

        "load_mode": "insert",
    },

    "Discount": { ############################################################################################
        "target_table": "ac_discount",

        "expected_columns": [
            'description', 
            'qty', 
            'category', 
            'month'
        ],

        "date_column": "month",

        "group_before_load": True,
        "group_by": ["description"],
        "agg": {
            "qty": "sum",
            "category": "first",
            "month": "first",
        },

        "unique_key": [
            "branch_id",
            "report_date",
            "description"
        ],

        "load_mode": "insert",
    },

    "Beg": { ############################################################################################
        "target_table": "ac_beginning",

        "expected_columns": [
            'location',
            'product_description',
            'qty',
            'unit',
            'avg_cost',
            'total_cost',
            'category',
            'item_group',
            'month'
        ],

        "date_column": "month",

        "group_before_load": True,
        "group_by": ["product_description", "location"],
        "agg": {
            'qty': 'sum',
            'unit': 'first',
            'avg_cost': 'first',
            'total_cost': 'sum',
            'category': 'first',
            'item_group': 'first',
            'month': 'first'
        },

        "unique_key": [
            "branch_id",
            "report_date",
            "product_description",
            "location"
        ],

        "load_mode": "insert",
    },

    "Purchase": { ############################################################################################
        "target_table": "ac_purchase",

        "expected_columns": [
            'location',
            'category',
            'raw_materials',
            'qty',
            'unit',
            'purchased_unit',
            'total_qty',
            'unit_cost',
            'total_cost',
            'supplier_names',
            'invoice_nbr',
            'purchase_date',
            'month',
            'item_group',
            'min',
            'max',
            'diff',
            'previous_unit_cost',
            'new_unit_cost',
            'unit_variance_percentage',
            'procurement_ctrl',
            'usd'
        ],

        "date_column": "month",

        "load_mode": "insert",
    },

    "PRD": { ############################################################################################
        "target_table": "ac_production",

        "expected_columns": [
            'location', 
            'production_list', 
            'qty', 
            'category', 
            'month'
        ],

        "date_column": "month",

        "group_before_load": True,
        "group_by": ["production_list"],
        "agg": {
            "qty": "sum",
            "category": "first",
            "month": "first",
            "location": "first",
        },

        "unique_key": [
            "branch_id",
            "report_date",
            "production_list"
        ],

        "load_mode": "insert",
    },

    "IN OUT": { ############################################################################################
        "target_table": "ac_transfers",

        "expected_columns": [
            'product',
            'from_location',
            'from_branch',
            'to_location',
            'to_branch',
            'qty',
            'unit',
            'avg_cost',
            'totavg_cost',
            'date',
            'month',
            'category'
        ],

        "date_column": "month",

        "load_mode": "insert",
    },

    "W.Inv": { ############################################################################################
        "target_table": "ac_waste_inventory",

        "expected_columns": [
            'location',
            'category',
            'qty',
            'unit',
            'product_description',
            'remark',
            'avg_cost',
            'total_cost',
            'month',
            'original_remarks',
            'date',
            'sales_revenue',
            'invoice_number',
            'customer'
        ],

        "date_column": "month",

        "load_mode": "insert",
    },

    "W.Sal": { ############################################################################################
        "target_table": "ac_waste_sales",

        "expected_columns": [
            'product',
            'qty',
            'cost',
            'total',
            'category',
            'remarks',
            'original_remarks',
            'month',
            'date',
            'sales_revenue',
            'invoice_number',
            'customer'
        ],

        "date_column": "month",

        "load_mode": "insert",
    },

    "Ending": { ############################################################################################
        "target_table": "ac_ending",

        "expected_columns": [
            'location',
            'product_description',
            'qty',
            'unit',
            'avg_cost',
            'total_cost',
            'category',
            'item_group',
            'month'
        ],

        "date_column": "month",

        "group_before_load": True,
        "group_by": ["product_description", "location"],
        "agg": {
            'qty': 'sum',
            'unit': 'first',
            'avg_cost': 'first',
            'total_cost': 'sum',
            'category': 'first',
            'item_group': 'first',
            'month': 'first'
        },

        "unique_key": [
            "branch_id",
            "report_date",
            "product_description",
            "location"
        ],

        "load_mode": "insert",
    },

    "UC PRE MONTH": { ############################################################################################
        "target_table": "ac_unit_cost_prev",

        "expected_columns": [
            'category',
            'item_group',
            'product_description',
            'qty_i_f',
            'unit',
            'pur_unit',
            'qty_pur',
            'inv_unit',
            'lbp',
            'rate',
            'uc_pre_month',
            'diff_in_value',
            'uc_diff',
            'average_purchase',
            'unit_cost',
            'used_in_recipes',
            'used_in_sub_recipes',
            'usage_cost'
        ],

        "unique_key": [
            "branch_id",
            "report_date",
            "product_description"
        ],

        "load_mode": "insert",
    },

    "Unit Cost": { ############################################################################################
        "target_table": "ac_unit_cost",

        "expected_columns": [
            'category',
            'item_group',
            'product_description',
            'qty_i_f',
            'unit',
            'pur_unit',
            'qty_pur',
            'inv_unit',
            'lbp',
            'rate',
            'uc_pre_month',
            'diff_in_value',
            'uc_diff',
            'average_purchase',
            'unit_cost',
            'used_in_recipes',
            'used_in_sub_recipes',
            'usage_cost'
        ],

        "unique_key": [
            "branch_id",
            "report_date",
            "product_description"
        ],

        "load_mode": "insert",
    },

    "Recipes": { ############################################################################################
        "target_table": "ac_recipes",

        "expected_columns": [
            'category',
            'item_group',
            'menu_items',
            'product_description',
            'qty',
            'unit',
            'avg_cost',
            'total_cost',
            'sales',
            'waste_sal',
            'stock_out',
            'qty_if',
            'unit_stock',
            'location',
            'qty_pur',
            'total_pur',
            'avgpurcost',
            'avgpurusacost'
        ],

        "load_mode": "insert",
    },

    "sub recipes": { ############################################################################################
        "target_table": "ac_sub_recipes",

        "expected_columns": [
            'location',
            'production_name',
            'product_description',
            'qty',
            'unit_name',
            'cost',
            'average_cost',
            'qty_to_prepared',
            'prepared_unit',
            'cost_for_1',
            'beginning_inv',
            'prd_out',
            'trout',
            'sales',
            'waste',
            'ending_inv',
            'total_prd',
            'calculation',
            'stock_prdk_out',
            'qty_format',
            'unit_stock',
            'item_group',
            'adjustment'
        ],

        "load_mode": "insert",
    },

}