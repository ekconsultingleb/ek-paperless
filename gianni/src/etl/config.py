JOBS_CLOUD = [

    { #  -> programming summary sales -> SP ####----------
    "key": "programming summary sales",
    "df_cols": ['menu items', 'sp exc vat','category', 'group'],
    "sheet": "SP",
    "start_row": 2,
    },

    { # sales by items -> Sales #### ----------
    "key": "sales by items",
    "df_cols": ['description', 'qty sold', 'gross sales'],
    "sheet": "Sales",
    "start_row": 2,
    },

    { # discount by category by department -> Disc. Cat. #### ----------
    "key": "discount by category by department",
    "df_cols": ['category', 'total'],
    "sheet": "Disc. Cat.",
    "start_row": 2,
    },

    { # disc_by_desc__sales_by_item -> Discount #### ----------
    "key": "disc_by_desc__disc_by_invoice",
    "df_cols": ['description', 'qty'],
    "sheet": "Discount",
    "start_row": 2,
    },

    { # discount by items -> Discount
    "key": "discount by items",
    "df_cols": ['description', 'qty'],
    "sheet": "Discount",
    "start_row": 2,
    },

    { # purchase master report for all branches -> Purchase #### ----------
    "key": "purchase master report for all branches",
    "df_cols": ['location', 'raw materials','qty','total cost','supplier names','invoice #','purchase date'],
    "sheet": "Purchase",
    "start_row": 2,
    },

    { # inventory production -> PRD #### ----------
    "key": "inventory production",
    "df_cols": ['location','production list','qty'],
    "sheet": "PRD",
    "start_row": 2,
    },

    { # summary of sales by customer by item -> W.Inv #### ----------
    "key": "summary of sales by customer by item",
    "df_cols": ['location','qty','product description','original remarks','date','sales revenue','invoice number','customer'],
    "sheet": "W.Inv",
    "start_row": 2,
    },

    { # wastage report
    "key": "wastage report",
    "df_cols": ['location','qty','product description','original remarks','date'],
    "sheet": "W.Inv",
    "start_row": 2,
    },

    { # sales item wastage -> W.Sal #### ----------
    "key": "sales item wastage",
    "df_cols": ['product', 'qty', 'original remarks','date'],
    "sheet": "W.Sal",
    "start_row": 2,
    },

    { # inventory history -> Ending #### ----------
    "key": "inventory history",
    "df_cols": ['location','product description', 'qty'],
    "sheet": "Ending",
    "start_row": 2,
    },

    { # programming summary inventory -> Unit Cost #### ----------
    "key": "programming summary inventory",
    "df_cols": ['category','group','product description','qty I F','unit','pur unit','qty pur','inv unit','lbp'],
    "sheet": "Unit Cost",
    "start_row": 2,
    },

    { # requisition summary -> IN OUT ####----------
    "key": "requisition summary",
    "df_cols": ['product','from location','from branch','to location','to branch','qty','date'],
    "sheet": "IN OUT",
    "start_row": 2,
    },

    { # requisition summary IB
    "key": "requisition summary IB",
    "df_cols": ['product','from location','from branch','to location','to branch','qty','date'],
    "sheet": "IN OUT",
    "start_row": 2,
    },

    { # sales items ingredients -> Recipes ####----------
    "key": "sales items ingredients",
    "df_cols": ['menu items','product description','qty'],
    "sheet": "Recipes",
    "start_row": 2,
    },

    { # inventory items ingredients -> sub recipes ####----------
    "key": "inventory items ingredients",
    "df_cols": ['production name', 'product description', 'qty','qty to prepared', 'prepared unit'],
    "sheet": "sub recipes",
    "start_row": 2,
    }

]

# ----------------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------------

JOBS_LOCAL = [

    { #  -> list sales items -> SP ####----------
    "key": "list sales items",
    "df_cols": ['menu items', 'sp exc vat','category', 'group'],
    "sheet": "SP",
    "start_row": 2,
    },

    { # sales by menu by items -> Sales #### ----------
    "key": "sales by menu by items",
    "df_cols": ['description', 'qty sold', 'gross sales'],
    "sheet": "Sales",
    "start_row": 2,
    },

    { # discount by category -> Disc. Cat. #### ----------
    "key": "discount by category",
    "df_cols": ['category', 'total'],
    "sheet": "Disc. Cat.",
    "start_row": 2,
    },

    { # disc_by_desc__sales_by_item -> Discount #### ----------
    "key": "disc_by_desc__disc_by_invoice",
    "df_cols": ['description', 'qty'],
    "sheet": "Discount",
    "start_row": 2,
    },

    { # discount by items -> Discount
    "key": "discount by items",
    "df_cols": ['description', 'qty'],
    "sheet": "Discount",
    "start_row": 2,
    },

    { # purchase with all details -> Purchase #### ----------
    "key": "purchase with all details",
    "df_cols": ['location', 'raw materials','qty','total cost','supplier names','invoice #','purchase date'],
    "sheet": "Purchase",
    "start_row": 2,
    },

    { # inventory production -> PRD #### ----------
    "key": "inventory production",
    "df_cols": ['location','production list','qty'],
    "sheet": "PRD",
    "start_row": 2,
    },

    { # inventory / summary of sales by customer by items -> W.Inv #### ----------
    "key": "inventory / summary of sales by customer by items",
    "df_cols": ['location','qty','product description','remarks','date','sales revenue','invoice number','customer'],
    "sheet": "W.Inv",
    "start_row": 2,
    },

    { # inventory wastage items
    "key": "inventory wastage items",
    "df_cols": ['location','qty','product description','original remarks','date'],
    "sheet": "W.Inv",
    "start_row": 2,
    },

    { # sales / summary of sales by customer by items -> W.Sal #### ----------
    "key": "sales / summary of sales by customer by items",
    "df_cols": ['product', 'qty', 'remarks','date','total','invoice number','customer'],
    "sheet": "W.Sal",
    "start_row": 2,
    },

    { # sales wastage items
    "key": "sales wastage items",
    "df_cols": ['product', 'qty', 'original remarks','date'],
    "sheet": "W.Sal",
    "start_row": 2,
    },

    { # inventory history -> Ending #### ----------
    "key": "inventory history",
    "df_cols": ['location','product description', 'qty'],
    "sheet": "Ending",
    "start_row": 2,
    },

    { # programming summary inventory -> Unit Cost #### ----------
    "key": "programming summary inventory",
    "df_cols": ['category','group','product description','qty I F','unit','pur unit','qty pur','inv unit','lbp'],
    "sheet": "Unit Cost",
    "start_row": 2,
    },

    { # requisition summary -> IN OUT ####----------
    "key": "requisition summary",
    "df_cols": ['product','from location','from branch','to location','to branch','qty','date'],
    "sheet": "IN OUT",
    "start_row": 2,
    },

    { # sales items ingredients -> Recipes ####----------
    "key": "sales items ingredients",
    "df_cols": ['menu items','product description','qty'],
    "sheet": "Recipes",
    "start_row": 2,
    },

    { # inventory items ingredients -> sub recipes ####----------
    "key": "inventory items ingredients",
    "df_cols": ['production name', 'product description', 'qty','qty to prepared', 'prepared unit'],
    "sheet": "sub recipes",
    "start_row": 2,
    }


]


def get_jobs(source: str) -> list[dict]:
    if source == "cloud":
        return JOBS_CLOUD
    if source == "local":
        return JOBS_LOCAL
    raise ValueError(f"Unknown source: {source!r}. Use 'cloud' or 'local'.")