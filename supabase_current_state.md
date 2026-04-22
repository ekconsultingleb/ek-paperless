# Supabase Project — Current State Inventory

**Project ref:** `hgvubaohmgvesblfvdps`
**Region:** `ap-southeast-2` (AWS Sydney)
**Generated:** 2026-04-22
**Method:** Read-only queries against `information_schema`, `pg_catalog`, and `pg_policies`. No data was modified.

---

## Table of Contents

1. [Tables, Columns & Foreign Keys](#1-tables-columns--foreign-keys)
2. [RLS Enabled vs Disabled](#2-rls-enabled-vs-disabled)
3. [RLS Policies](#3-rls-policies)
4. [Functions & Triggers](#4-functions--triggers)
5. [Roles & Permissions](#5-roles--permissions)
6. [Views](#6-views)
7. [auth.users — Structure & App Connection](#7-authusers--structure--app-connection)
8. [Flags & Observations](#8-flags--observations)

---

## 1. Tables, Columns & Foreign Keys

### 51 tables in the `public` schema

All tables use `id` as primary key (PK). Column format: `name: type [nullable] [default]`.

---

#### `ac_beginning` — Analytical: beginning inventory snapshot
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| location | text | NULL | — |
| product_description | text | NULL | — |
| qty | numeric | NULL | — |
| unit | text | NULL | — |
| avg_cost | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, product_description, location)`

---

#### `ac_cogs` — Analytical: cost of goods sold summary
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| month | date | NULL | — |
| category | text | NULL | — |
| gross_sales | numeric | NULL | — |
| discount | numeric | NULL | — |
| net_sales | numeric | NULL | — |
| beginning | numeric | NULL | — |
| purchase | numeric | NULL | — |
| transfer_in | numeric | NULL | — |
| transfer_out | numeric | NULL | — |
| ending | numeric | NULL | — |
| gross_cogs | numeric | NULL | — |
| staff_meal | numeric | NULL | — |
| cost_of_discount | numeric | NULL | — |
| waste | numeric | NULL | — |
| consumed_oil | numeric | NULL | — |
| consumed_charcoal | numeric | NULL | — |
| sales_cost | numeric | NULL | — |
| other_waste | numeric | NULL | — |
| net_cogs | numeric | NULL | — |
| theoretical_cost | numeric | NULL | — |
| total_variance | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, category)`

---

#### `ac_discount` — Analytical: discount line items
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| description | text | NULL | — |
| qty | numeric | NULL | — |
| category | text | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, description)`

---

#### `ac_discount_category` — Analytical: discount totals by category
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| category | text | NULL | — |
| total | numeric | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, category)`

---

#### `ac_ending` — Analytical: ending inventory snapshot
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| location | text | NULL | — |
| product_description | text | NULL | — |
| qty | numeric | NULL | — |
| unit | text | NULL | — |
| avg_cost | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, product_description, location)`

---

#### `ac_menu_eng` — Analytical: menu engineering per item
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| month | date | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| menu_items | text | NULL | — |
| qty_sold | numeric | NULL | — |
| popularity | text | NULL | — |
| cost_percentage | numeric | NULL | — |
| cost | numeric | NULL | — |
| selling_price | numeric | NULL | — |
| profit | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| total_revenue | numeric | NULL | — |
| total_profit | numeric | NULL | — |
| profit_category | text | NULL | — |
| popularity_category | text | NULL | — |
| menu_item_class | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, menu_items)`

---

#### `ac_menu_mix` — Analytical: menu mix / revenue contribution
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| month | date | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| menu_items | text | NULL | — |
| qty_sold | numeric | NULL | — |
| gross_revenue | numeric | NULL | — |
| sales_mix_percentage | numeric | NULL | — |
| menu_price | numeric | NULL | — |
| cost | numeric | NULL | — |
| contribution_margin | numeric | NULL | — |
| total_contribution_margin | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, menu_items)`

---

#### `ac_production` — Analytical: production quantities
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| location | text | NULL | — |
| production_list | text | NULL | — |
| qty | numeric | NULL | — |
| category | text | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, production_list)`

---

#### `ac_purchase` — Analytical: purchase detail lines
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| location | text | NULL | — |
| category | text | NULL | — |
| raw_materials | text | NULL | — |
| qty | numeric | NULL | — |
| unit | text | NULL | — |
| purchased_unit | text | NULL | — |
| total_qty | numeric | NULL | — |
| unit_cost | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| supplier_names | text | NULL | — |
| invoice_nbr | text | NULL | — |
| purchase_date | date | NULL | — |
| month | date | NULL | — |
| item_group | text | NULL | — |
| min | numeric | NULL | — |
| max | numeric | NULL | — |
| diff | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |
| previous_unit_cost | numeric | NULL | — |
| new_unit_cost | numeric | NULL | — |
| unit_variance_percentage | numeric | NULL | — |
| procurement_ctrl | numeric | NULL | — |
| usd | numeric | NULL | — |

---

#### `ac_recipes` — Analytical: recipe costing snapshot
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| menu_items | text | NULL | — |
| product_description | text | NULL | — |
| qty | numeric | NULL | — |
| unit | text | NULL | — |
| avg_cost | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| sales | numeric | NULL | — |
| waste_sal | text | NULL | — |
| stock_out | numeric | NULL | — |
| qty_if | numeric | NULL | — |
| unit_stock | text | NULL | — |
| location | text | NULL | — |
| qty_pur | numeric | NULL | — |
| total_pur | numeric | NULL | — |
| avgpurcost | numeric | NULL | — |
| avgpurusacost | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

---

#### `ac_sales` — Analytical: sales by line item
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| description | text | NULL | — |
| qty_sold | numeric | NULL | — |
| gross_sales | numeric | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| cost | numeric | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, description)`

---

#### `ac_selling_prices` — Analytical: selling price snapshots
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| menu_items | text | NULL | — |
| sp_exc_vat | numeric | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, menu_items)`

---

#### `ac_sub_recipes` — Analytical: sub-recipe costing snapshot
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| location | text | NULL | — |
| production_name | text | NULL | — |
| product_description | text | NULL | — |
| qty | numeric | NULL | — |
| unit_name | text | NULL | — |
| cost | numeric | NULL | — |
| average_cost | numeric | NULL | — |
| qty_to_prepared | numeric | NULL | — |
| prepared_unit | text | NULL | — |
| cost_for_1 | numeric | NULL | — |
| beginning_inv | text | NULL | — |
| prd_out | numeric | NULL | — |
| trout | numeric | NULL | — |
| sales | numeric | NULL | — |
| waste | numeric | NULL | — |
| ending_inv | text | NULL | — |
| total_prd | numeric | NULL | — |
| calculation | text | NULL | — |
| stock_prdk_out | numeric | NULL | — |
| qty_format | numeric | NULL | — |
| unit_stock | text | NULL | — |
| item_group | text | NULL | — |
| adjustment | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

---

#### `ac_theoretical` — Analytical: theoretical cost vs actual
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| month | date | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| menu_items | text | NULL | — |
| new_cost | numeric | NULL | — |
| current_sprice | numeric | NULL | — |
| gross_sales | numeric | NULL | — |
| discount | numeric | NULL | — |
| sales | numeric | NULL | — |
| theoretical_cost | numeric | NULL | — |
| cost_of_discount | numeric | NULL | — |
| total_revenue | numeric | NULL | — |
| cost_percentage | numeric | NULL | — |
| sp_exc_vat | numeric | NULL | — |
| total_ek_rev | numeric | NULL | — |
| rev_not_made | numeric | NULL | — |
| mode_4 | numeric | NULL | — |
| mode_1 | numeric | NULL | — |
| cost_of_mode_4 | numeric | NULL | — |
| cost_of_mode_1 | numeric | NULL | — |
| cost_percentage_of_m1 | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, menu_items)`

---

#### `ac_transfers` — Analytical: inter-branch/location transfer snapshot
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| product | text | NULL | — |
| from_location | text | NULL | — |
| from_branch | text | NULL | — |
| to_location | text | NULL | — |
| to_branch | text | NULL | — |
| qty | numeric | NULL | — |
| unit | text | NULL | — |
| avg_cost | numeric | NULL | — |
| totavg_cost | numeric | NULL | — |
| date | date | NULL | — |
| month | date | NULL | — |
| category | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

---

#### `ac_unit_cost` — Analytical: unit cost detail (current period)
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| product_description | text | NULL | — |
| qty_i_f | numeric | NULL | — |
| unit | text | NULL | — |
| pur_unit | text | NULL | — |
| qty_pur | numeric | NULL | — |
| inv_unit | text | NULL | — |
| lbp | numeric | NULL | — |
| rate | numeric | NULL | — |
| uc_pre_month | numeric | NULL | — |
| diff_in_value | numeric | NULL | — |
| uc_diff | numeric | NULL | — |
| average_purchase | numeric | NULL | — |
| unit_cost | numeric | NULL | — |
| used_in_recipes | text | NULL | — |
| used_in_sub_recipes | text | NULL | — |
| usage_cost | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, product_description)`

---

#### `ac_unit_cost_prev` — Analytical: unit cost detail (previous period)
Identical schema to `ac_unit_cost`. Same unique index `(branch_id, report_date, product_description)`.

---

#### `ac_variance` — Analytical: inventory variance per product/location
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| month | date | NULL | — |
| category | text | NULL | — |
| item_group | text | NULL | — |
| location | text | NULL | — |
| products | text | NULL | — |
| qty_pck | numeric | NULL | — |
| unit | text | NULL | — |
| inv_unit | text | NULL | — |
| beginning | numeric | NULL | — |
| purchase | numeric | NULL | — |
| trin | numeric | NULL | — |
| prd_in | numeric | NULL | — |
| trout | numeric | NULL | — |
| prd_out | numeric | NULL | — |
| sales | numeric | NULL | — |
| waste | numeric | NULL | — |
| system | numeric | NULL | — |
| ending | numeric | NULL | — |
| variance | numeric | NULL | — |
| avg_cost | numeric | NULL | — |
| tt_variance | numeric | NULL | — |
| chef_prd | numeric | NULL | — |
| auto_prdk | numeric | NULL | — |
| diff | numeric | NULL | — |
| adjustment | numeric | NULL | — |
| dont_show | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |

**Unique index:** `(branch_id, report_date, location, products)`

---

#### `ac_waste_inventory` — Analytical: inventory waste events
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| location | text | NULL | — |
| category | text | NULL | — |
| qty | numeric | NULL | — |
| unit | text | NULL | — |
| product_description | text | NULL | — |
| remarks | text | NULL | — |
| avg_cost | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| month | date | NULL | — |
| original_remarks | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |
| date | date | NULL | — |
| sales_revenue | numeric | NULL | — |
| invoice_number | text | NULL | — |
| customer | text | NULL | — |

---

#### `ac_waste_sales` — Analytical: waste / comp sales events
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| branch_id | bigint | NOT NULL | — | FK → `branches.id` |
| report_date | date | NOT NULL | — |
| product | text | NULL | — |
| qty | numeric | NULL | — |
| cost | numeric | NULL | — |
| total | numeric | NULL | — |
| category | text | NULL | — |
| remarks | text | NULL | — |
| original_remarks | text | NULL | — |
| month | date | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| client_rate | numeric | NOT NULL | `90000` |
| date | date | NULL | — |
| sales_revenue | numeric | NULL | — |
| invoice_number | text | NULL | — |
| customer | text | NULL | — |

---

#### `app_config` — Application key-value configuration store
| Column | Type | Nullable | Default |
|---|---|---|---|
| key | text | NOT NULL | — | **PK** |
| value | text | NOT NULL | — |

---

#### `areas` — Storage locations within an outlet
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | integer | NOT NULL | — | **PK** |
| branch_id | integer | NULL | — | FK → `branches.id` |
| outlet | text | NOT NULL | — |
| area_name | text | NOT NULL | — |
| created_at | timestamptz | NULL | `now()` |

**Unique index:** `(outlet, area_name)`

---

#### `branches` — Outlets / branches per client
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | integer | NOT NULL | — | **PK** |
| client_id | integer | NULL | — | FK → `clients.id` |
| client_name | text | NOT NULL | — |
| outlet | text | NOT NULL | — |
| address | text | NULL | — |
| created_at | timestamptz | NULL | `now()` |
| company_name | text | NULL | — |

**Unique index:** `(outlet)`

---

#### `clients` — Top-level client entities
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | integer | NOT NULL | — | **PK** |
| client_name | text | NOT NULL | — |
| group_company_name | text | NULL | — |
| status | text | NOT NULL | `'active'` |
| created_at | timestamptz | NULL | `now()` |
| client_region | text | NULL | `'Lebanon'` |
| dpos_btl_gls_derive | boolean | NULL | `true` |

**Unique index:** `(client_name)`

---

#### `daily_cash` — Daily cash reconciliation entries
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| created_at | timestamptz | NOT NULL | `now()` |
| date | date | NULL | — |
| client_name | text | NULL | — |
| outlet | text | NULL | — |
| main_reading | real | NULL | — |
| cash | real | NULL | — |
| visa | real | NULL | — |
| expenses | real | NULL | — |
| on_account | real | NULL | — |
| revenue | real | NULL | — |
| over_short | real | NULL | — |
| reported_by | text | NULL | — |

---

#### `dpos_approved_prices` — DPOS: approved pricing decisions per session
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| session_id | bigint | NOT NULL | — | FK → `dpos_sessions.id` CASCADE DELETE |
| menu_item | text | NOT NULL | — |
| category | text | NULL | — |
| group_name | text | NULL | — |
| old_price | numeric | NULL | — |
| new_price | numeric | NULL | — |
| new_cost | numeric | NULL | — |
| new_cost_pct | numeric | NULL | — |
| new_profit_margin | numeric | NULL | — |
| psychological_price | numeric | NULL | — |
| approved_at | timestamptz | NULL | — |
| approved_by | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |

---

#### `dpos_client_config` — DPOS: per-client configuration overrides
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | integer | NOT NULL | `nextval(sequence)` | **PK** |
| client_id | integer | NOT NULL | — |
| btl_gls_derive | boolean | NULL | `true` |
| created_at | timestamptz | NULL | `now()` |

**Unique index:** `(client_id)`

---

#### `dpos_cost_overrides` — DPOS: manual cost overrides per session
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| session_id | bigint | NOT NULL | — | FK → `dpos_sessions.id` CASCADE DELETE |
| product_description | text | NOT NULL | — |
| original_cost | numeric | NULL | — |
| predicted_cost | numeric | NOT NULL | — |
| notes | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |

---

#### `dpos_recipes` — DPOS: live recipe costing records
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| client_id | bigint | NOT NULL | — | FK → `clients.id` |
| category | text | NULL | — |
| group_name | text | NULL | — |
| menu_item | text | NOT NULL | — |
| ingredient_description | text | NOT NULL | — |
| net_w | numeric | NULL | — |
| gross_w | numeric | NULL | — |
| yield_pct | numeric | NULL | — |
| unit | text | NULL | — |
| avg_cost | numeric | NULL | — |
| total_cost | numeric | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| updated_at | timestamptz | NOT NULL | `now()` |
| current_selling_price | numeric | NULL | — |
| on_menu | boolean | NOT NULL | `true` |
| glasses_count | numeric | NULL | — |
| sub_category | text | NULL | — |
| tier | text | NULL | — |

---

#### `dpos_session_targets` — DPOS: target cost % per category per session
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| session_id | bigint | NOT NULL | — | FK → `dpos_sessions.id` CASCADE DELETE |
| category | text | NOT NULL | — |
| target_cost_pct | numeric | NOT NULL | — |

---

#### `dpos_sessions` — DPOS: pricing studio sessions
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| client_id | bigint | NOT NULL | — | FK → `clients.id` |
| session_name | text | NOT NULL | — |
| created_by | text | NULL | — |
| vat_rate | numeric | NOT NULL | `0` |
| target_cost_pct | numeric | NOT NULL | `0.30` |
| status | text | NOT NULL | `'draft'` |
| notes | text | NULL | — |
| created_at | timestamptz | NOT NULL | `now()` |
| updated_at | timestamptz | NOT NULL | `now()` |
| rounding | numeric | NOT NULL | `0.50` |

---

#### `dpos_sub_recipes` — DPOS: sub-recipe costing (production items)
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| client_id | bigint | NOT NULL | — | FK → `clients.id` |
| product_name | text | NOT NULL | — |
| ingredient_description | text | NOT NULL | — |
| net_w | numeric | NULL | — |
| gross_w | numeric | NULL | — |
| yield_pct | numeric | NULL | — |
| unit_name | text | NULL | — |
| avg_cost | numeric | NULL | — |
| batch_cost | numeric | NULL | — |
| prepared_qty | numeric | NULL | — |
| prepared_unit | text | NULL | — |
| rate | numeric | NOT NULL | `90000` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| created_at | timestamptz | NOT NULL | `now()` |
| updated_at | timestamptz | NOT NULL | `now()` |
| cost_for_1 | numeric | NULL | — |

---

#### `dpos_tranches` — DPOS: pricing tranche rules per session
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| session_id | bigint | NOT NULL | — | FK → `dpos_sessions.id` CASCADE DELETE |
| min_cost | numeric | NOT NULL | — |
| max_cost | numeric | NOT NULL | — |
| mode | text | NOT NULL | `'target_pct'` |
| target_pct | numeric | NULL | — |
| fixed_price | numeric | NULL | — |
| item_type | text | NULL | — |

---

#### `dpos_unit_costs` — DPOS: ingredient unit costs per client
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| client_id | bigint | NOT NULL | — | FK → `clients.id` |
| category | text | NULL | — |
| group_name | text | NULL | — |
| product_code | text | NULL | — |
| product_description | text | NOT NULL | — |
| qty_inv | numeric | NULL | — |
| unit | text | NULL | — |
| qty_buy | numeric | NULL | — |
| avg_cost_lbp | numeric | NULL | — |
| rate | numeric | NOT NULL | `90000` |
| currency | varchar(10) | NOT NULL | `'LBP'` |
| unit_cost_usd | numeric | NULL | — |
| usage_cost_usd | numeric | NULL | — |
| show_in_report | boolean | NOT NULL | `true` |
| created_at | timestamptz | NOT NULL | `now()` |
| updated_at | timestamptz | NOT NULL | `now()` |

---

#### `inventory_drafts` — In-progress inventory count drafts (one per user/outlet)
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| user_name | text | NULL | — |
| client_name | text | NULL | — |
| outlet | text | NULL | — |
| location | text | NULL | — |
| draft_data | jsonb | NULL | — |
| updated_at | timestamptz | NULL | `now()` |

**Unique index:** `(user_name, client_name, outlet)`

---

#### `inventory_logs` — Submitted inventory count records
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| created_at | timestamptz | NOT NULL | `timezone('utc', now())` |
| date | date | NOT NULL | — |
| client_name | text | NULL | — |
| outlet | text | NULL | — |
| location | text | NULL | — |
| counted_by | text | NULL | — |
| item_name | text | NOT NULL | — |
| product_code | text | NULL | — |
| item_type | text | NULL | — |
| category | text | NULL | — |
| sub_category | text | NULL | — |
| quantity | double precision | NOT NULL | — |
| count_unit | text | NULL | — |

---

#### `invoices_log` — Supplier invoice image submissions
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| created_at | timestamptz | NULL | `now()` |
| client_name | text | NOT NULL | — |
| outlet | text | NOT NULL | — |
| location | text | NOT NULL | — |
| uploaded_by | text | NULL | — |
| supplier | text | NOT NULL | — |
| image_url | text | NULL | — |
| status | text | NULL | `'Pending'` |
| data_entry_notes | text | NULL | — |
| posted_by | text | NULL | — |
| total_amount | numeric | NULL | — |
| currency | text | NULL | `'USD'` |

---

#### `ledger_categories` — Debt control: transaction categories
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| category_name | text | NULL | — |
| client_name | text | NULL | — |

---

#### `ledger_entities` — Debt control: creditor/debtor entities
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| entity_name | text | NULL | — |
| client_name | text | NULL | — |

---

#### `ledger_logs` — Debt control: transaction log
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| created_at | timestamptz | NOT NULL | `now()` |
| date | date | NULL | — |
| category | text | NULL | — |
| entity_name | text | NULL | — |
| description | text | NULL | — |
| credit | numeric | NULL | — |
| debit | numeric | NULL | — |
| logged_by | text | NULL | — |
| client_name | text | NULL | — |
| outlet | text | NULL | — |

---

#### `master_items` — Per-outlet product master list
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| created_at | timestamptz | NOT NULL | `now()` |
| client_name | text | NULL | — |
| outlet | text | NULL | — |
| location | text | NULL | — |
| item_type | text | NULL | — |
| category | text | NULL | — |
| sub_category | text | NULL | — |
| product_code | text | NULL | — |
| item_name | text | NULL | — |
| count_unit | text | NULL | `'Unit'` |
| item_name_ar | text | NULL | — |
| is_production | boolean | NULL | `false` |
| cost_per_unit | numeric | NULL | `0` |
| region | text | NULL | `''` |
| source | text | NULL | `'manual'` |

**Unique index:** `(client_name, outlet, location, item_type, product_code)`
**Performance indexes:** `(client_name)`, `(outlet)`, `(location)`

---

#### `outlet_suppliers` — Supplier-to-outlet mapping
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| client_name | text | NOT NULL | — |
| outlet | text | NOT NULL | — |
| supplier_name | text | NOT NULL | — |
| created_at | timestamptz | NULL | `now()` |

**Unique index:** `(client_name, outlet, supplier_name)`

---

#### `recipe_lines` — Ingredient lines within a recipe
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| recipe_id | uuid | NULL | — | FK → `recipes.id` CASCADE DELETE |
| product_code | text | NULL | — |
| item_name | text | NULL | — |
| qty | numeric | NULL | `0` |
| unit | text | NULL | — |
| cost_per_unit | numeric | NULL | `0` |
| is_production | boolean | NULL | `false` |
| sub_recipe_data | text | NULL | — |
| created_at | timestamptz | NULL | `now()` |
| chef_input | text | NULL | — |
| ai_resolved | text | NULL | — |
| ai_product_code | text | NULL | — |
| ai_confidence | text | NULL | — |
| sub_lines | jsonb | NULL | — |
| batch_qty | numeric | NULL | — |
| batch_unit | text | NULL | — |
| sub_recipe_id | uuid | NULL | — | FK → `recipes.id` SET NULL |

---

#### `recipe_sub_lines` — AI-expanded sub-lines for a recipe ingredient
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| parent_line_id | uuid | NOT NULL | — | FK → `recipe_lines.id` CASCADE DELETE |
| chef_input | text | NULL | — |
| qty | numeric | NULL | `0` |
| unit | text | NULL | `'kg'` |
| created_at | timestamptz | NULL | `now()` |

**Performance index:** `(parent_line_id)`

---

#### `recipes` — Recipe header
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| client_name | text | NOT NULL | — |
| outlet | text | NULL | — |
| name | text | NOT NULL | — |
| category | text | NULL | — |
| portions | numeric | NULL | `1` |
| yield_unit | text | NULL | `'Plate'` |
| method | text | NULL | — |
| cost_per_portion | numeric | NULL | `0` |
| photo_url | text | NULL | — |
| created_by | text | NULL | — |
| created_at | timestamptz | NULL | `now()` |

---

#### `suppliers` — Global supplier directory
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| supplier_name | text | NOT NULL | — |

**Unique indexes:** `suppliers_name_unique` AND `suppliers_supplier_name_key` — both on `supplier_name` ⚠️ (see §8)

---

#### `transfers` — Inter-outlet transfer requests
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| created_at | timestamptz | NOT NULL | `timezone('utc', now())` |
| transfer_id | text | NOT NULL | — |
| date | text | NOT NULL | — |
| status | text | NOT NULL | — |
| requester | text | NULL | — |
| from_outlet | text | NULL | — |
| from_location | text | NULL | — |
| to_outlet | text | NULL | — |
| to_location | text | NULL | — |
| request_type | text | NULL | — |
| details | text | NULL | — |
| action_by | text | NULL | — |

---

#### `users` — Application user accounts (custom auth)
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| created_at | timestamptz | NOT NULL | `now()` |
| username | text | NULL | — |
| password | text | NULL | — |
| role | text | NULL | — |
| outlet | text | NULL | — |
| location | text | NULL | — |
| module | text | NULL | — |
| client_name | text | NULL | — |
| full_name | text | NULL | — |
| email | text | NULL | — |
| phone | text | NULL | — |
| inv_reminder | boolean | NULL | `false` |
| cost_reminder | boolean | NULL | `false` |

**Performance index:** `(username)`

---

#### `waste_logs` — Operational waste event log
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| created_at | timestamptz | NOT NULL | `timezone('utc', now())` |
| date | date | NOT NULL | — |
| client_name | text | NULL | — |
| outlet | text | NULL | — |
| location | text | NULL | — |
| reported_by | text | NULL | — |
| category | text | NULL | — |
| sub_category | text | NULL | — |
| product_code | text | NULL | — |
| item_name | text | NULL | — |
| count_unit | text | NOT NULL | — |
| remarks | text | NULL | — |
| item_type | text | NULL | — |
| qty | double precision | NULL | — |

**Performance indexes:** `(client_name)`, `(outlet)`, `(date)`

---

#### `waste_remark_options` — Configurable waste remark dropdown values
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | bigint | NOT NULL | — | **PK** |
| client_name | text | NOT NULL | — |
| remark | text | NOT NULL | — |
| created_by | text | NULL | — |
| created_at | timestamptz | NULL | `now()` |

**Unique index:** `(client_name, remark)`

---

#### `worldwide_master_items` — Global ingredient catalogue (multi-region costs)
| Column | Type | Nullable | Default |
|---|---|---|---|
| id | uuid | NOT NULL | `gen_random_uuid()` | **PK** |
| product_code | text | NOT NULL | — |
| item_name | text | NOT NULL | — |
| item_name_ar | text | NULL | — |
| category | text | NULL | — |
| unit | text | NOT NULL | — |
| region | text | NOT NULL | `'Global'` |
| latest_cost_lebanon | numeric | NULL | — |
| latest_cost_dubai | numeric | NULL | — |
| latest_cost_cameroon | numeric | NULL | — |
| latest_cost_global | numeric | NULL | — |
| ek_locked | boolean | NULL | `false` |
| last_synced_at | timestamptz | NULL | — |
| last_synced_from | text | NULL | — |
| created_at | timestamptz | NULL | `now()` |

**Unique index:** `(product_code, region)`

---

### Foreign Key Summary

| Child Table | Child Column | Parent Table | Parent Column | On Delete |
|---|---|---|---|---|
| ac_beginning | branch_id | branches | id | NO ACTION |
| ac_cogs | branch_id | branches | id | NO ACTION |
| ac_discount | branch_id | branches | id | NO ACTION |
| ac_discount_category | branch_id | branches | id | NO ACTION |
| ac_ending | branch_id | branches | id | NO ACTION |
| ac_menu_eng | branch_id | branches | id | NO ACTION |
| ac_menu_mix | branch_id | branches | id | NO ACTION |
| ac_production | branch_id | branches | id | NO ACTION |
| ac_purchase | branch_id | branches | id | NO ACTION |
| ac_recipes | branch_id | branches | id | NO ACTION |
| ac_sales | branch_id | branches | id | NO ACTION |
| ac_selling_prices | branch_id | branches | id | NO ACTION |
| ac_sub_recipes | branch_id | branches | id | NO ACTION |
| ac_theoretical | branch_id | branches | id | NO ACTION |
| ac_transfers | branch_id | branches | id | NO ACTION |
| ac_unit_cost | branch_id | branches | id | NO ACTION |
| ac_unit_cost_prev | branch_id | branches | id | NO ACTION |
| ac_variance | branch_id | branches | id | NO ACTION |
| ac_waste_inventory | branch_id | branches | id | NO ACTION |
| ac_waste_sales | branch_id | branches | id | NO ACTION |
| areas | branch_id | branches | id | NO ACTION |
| branches | client_id | clients | id | NO ACTION |
| dpos_approved_prices | session_id | dpos_sessions | id | **CASCADE** |
| dpos_cost_overrides | session_id | dpos_sessions | id | **CASCADE** |
| dpos_recipes | client_id | clients | id | NO ACTION |
| dpos_session_targets | session_id | dpos_sessions | id | **CASCADE** |
| dpos_sessions | client_id | clients | id | NO ACTION |
| dpos_sub_recipes | client_id | clients | id | NO ACTION |
| dpos_tranches | session_id | dpos_sessions | id | **CASCADE** |
| dpos_unit_costs | client_id | clients | id | NO ACTION |
| recipe_lines | recipe_id | recipes | id | **CASCADE** |
| recipe_lines | sub_recipe_id | recipes | id | SET NULL |
| recipe_sub_lines | parent_line_id | recipe_lines | id | **CASCADE** |

---

## 2. RLS Enabled vs Disabled

### Public Schema — All 51 tables have RLS **ENABLED**

No table in `public` has RLS disabled.

### Auth Schema — Mixed

| Table | RLS |
|---|---|
| audit_log_entries | ENABLED |
| custom_oauth_providers | DISABLED |
| flow_state | ENABLED |
| identities | ENABLED |
| instances | ENABLED |
| mfa_amr_claims | ENABLED |
| mfa_challenges | ENABLED |
| mfa_factors | ENABLED |
| oauth_authorizations | DISABLED |
| oauth_client_states | DISABLED |
| oauth_clients | DISABLED |
| oauth_consents | DISABLED |
| one_time_tokens | ENABLED |
| refresh_tokens | ENABLED |
| saml_providers | ENABLED |
| saml_relay_states | ENABLED |
| schema_migrations | ENABLED |
| sessions | ENABLED |
| sso_domains | ENABLED |
| sso_providers | ENABLED |
| users | ENABLED |
| webauthn_challenges | DISABLED |
| webauthn_credentials | DISABLED |

Auth tables with RLS disabled are Supabase-managed internal tables (OAuth, WebAuthn) — normal.

---

## 3. RLS Policies

**16 tables have at least one policy. 35 tables have RLS enabled but zero policies.**

### Tables with a policy

All 16 policies share the same template — name `"Service role full access"`, permissive, roles `['public']`, cmd `ALL`, qual `true`.

| Table | Policy Name | Roles | Command | USING | WITH CHECK |
|---|---|---|---|---|---|
| areas | Service role full access | public | ALL | true | true |
| branches | Service role full access | public | ALL | true | true |
| clients | Service role full access | public | ALL | true | true |
| daily_cash | Service role full access | public | ALL | true | — |
| inventory_drafts | Service role full access | public | ALL | true | — |
| inventory_logs | Service role full access | public | ALL | true | — |
| invoices_log | Service role full access | public | ALL | true | — |
| ledger_categories | Service role full access | public | ALL | true | — |
| ledger_entities | Service role full access | public | ALL | true | — |
| ledger_logs | Service role full access | public | ALL | true | — |
| master_items | Service role full access | public | ALL | true | — |
| suppliers | Service role full access | public | ALL | true | — |
| transfers | Service role full access | public | ALL | true | — |
| users | Service role full access | public | ALL | true | — |
| waste_logs | Service role full access | public | ALL | true | — |
| waste_remark_options | Service role full access | public | ALL | true | — |

### Tables with RLS ENABLED but NO policies (35 tables)

```
ac_beginning, ac_cogs, ac_discount, ac_discount_category, ac_ending,
ac_menu_eng, ac_menu_mix, ac_production, ac_purchase, ac_recipes,
ac_sales, ac_selling_prices, ac_sub_recipes, ac_theoretical, ac_transfers,
ac_unit_cost, ac_unit_cost_prev, ac_variance, ac_waste_inventory, ac_waste_sales,
app_config, dpos_approved_prices, dpos_client_config, dpos_cost_overrides,
dpos_recipes, dpos_session_targets, dpos_sessions, dpos_sub_recipes,
dpos_tranches, dpos_unit_costs, outlet_suppliers, recipe_lines,
recipe_sub_lines, recipes, worldwide_master_items
```

In PostgreSQL, RLS enabled + zero policies = **implicit DENY ALL** for roles that do not bypass RLS (`anon`, `authenticated`). Since the app uses the `service_role` key (which bypasses RLS), these tables are inaccessible via the PostgREST API to any non-service-role caller. ⚠️ See §8.

---

## 4. Functions & Triggers

### Public Schema Functions

#### `update_updated_at_column()` → trigger
- **Language:** PL/pgSQL
- **Security:** INVOKER (runs as calling user)
- **Purpose:** Sets `updated_at = now()` before UPDATE
- **Called by:** 4 triggers (see below)

#### `rls_auto_enable()` → event_trigger
- **Language:** PL/pgSQL
- **Security:** DEFINER (runs as function owner — elevated privileges)
- **Purpose:** Automatically enables RLS on every newly created table
- **Trigger event:** DDL event trigger (fires on `CREATE TABLE`)
- ⚠️ This is a `SECURITY DEFINER` event trigger — see §8.

### Auth Schema Functions (Supabase-managed)

| Function | Returns | Purpose |
|---|---|---|
| `auth.email()` | text | Returns JWT email claim (deprecated) |
| `auth.jwt()` | jsonb | Returns full JWT claims object |
| `auth.role()` | text | Returns JWT role claim (deprecated) |
| `auth.uid()` | uuid | Returns authenticated user UUID from JWT |

### Triggers

All 4 triggers are `BEFORE UPDATE` row-level triggers in the `public` schema, calling `update_updated_at_column()`:

| Trigger Name | Table | Event | Timing |
|---|---|---|---|
| dpos_recipes_updated_at | dpos_recipes | UPDATE | BEFORE |
| dpos_sessions_updated_at | dpos_sessions | UPDATE | BEFORE |
| dpos_sub_recipes_updated_at | dpos_sub_recipes | UPDATE | BEFORE |
| dpos_unit_costs_updated_at | dpos_unit_costs | UPDATE | BEFORE |

No triggers exist on auth-schema tables (those are Supabase-managed internally).

---

## 5. Roles & Permissions

### Roles Inventory

| Role | Superuser | CreateDB | CreateRole | CanLogin | Replication | BypassRLS |
|---|---|---|---|---|---|---|
| `anon` | No | No | No | No | No | **No** |
| `authenticated` | No | No | No | No | No | **No** |
| `authenticator` | No | No | No | **Yes** | No | **No** |
| `dashboard_user` | No | Yes | Yes | No | Yes | **No** |
| `postgres` | No | Yes | Yes | **Yes** | Yes | **Yes** |
| `service_role` | No | No | No | No | No | **Yes** |
| `supabase_admin` | **Yes** | Yes | Yes | **Yes** | Yes | **Yes** |
| `supabase_auth_admin` | No | No | Yes | **Yes** | No | **No** |
| `supabase_etl_admin` | No | No | No | **Yes** | Yes | **Yes** |
| `supabase_privileged_role` | No | No | No | No | No | **No** |
| `supabase_read_only_user` | No | No | No | **Yes** | No | **Yes** |
| `supabase_realtime_admin` | No | No | No | No | No | **No** |
| `supabase_replication_admin` | No | No | No | **Yes** | Yes | **No** |
| `supabase_storage_admin` | No | No | Yes | **Yes** | No | **No** |

All roles prefixed `supabase_*` and `dashboard_user` are Supabase-managed platform roles — do not modify them.

**Custom application roles:** None defined. The application uses its own role system encoded as text in `public.users.role` (values like `admin`, `admin_all`, `manager`, `staff`).

### Table Grants

The application's `service_role` key bypasses RLS entirely and has full access to all tables. The `anon` and `authenticated` PostgREST roles are granted access per the policies described in §3.

---

## 6. Views

**No views exist** in the `public` or `auth` schemas.

---

## 7. auth.users — Structure & App Connection

### auth.users Columns

| Column | Type | Nullable |
|---|---|---|
| instance_id | uuid | YES |
| **id** | uuid | NO — PK |
| aud | varchar | YES |
| role | varchar | YES |
| email | varchar | YES |
| encrypted_password | varchar | YES |
| email_confirmed_at | timestamptz | YES |
| invited_at | timestamptz | YES |
| confirmation_token | varchar | YES |
| confirmation_sent_at | timestamptz | YES |
| recovery_token | varchar | YES |
| recovery_sent_at | timestamptz | YES |
| email_change_token_new | varchar | YES |
| email_change | varchar | YES |
| email_change_sent_at | timestamptz | YES |
| last_sign_in_at | timestamptz | YES |
| raw_app_meta_data | jsonb | YES |
| raw_user_meta_data | jsonb | YES |
| is_super_admin | boolean | YES |
| created_at | timestamptz | YES |
| updated_at | timestamptz | YES |
| phone | text | YES |
| phone_confirmed_at | timestamptz | YES |
| phone_change | text | YES |
| phone_change_token | varchar | YES |
| phone_change_sent_at | timestamptz | YES |
| confirmed_at | timestamptz | YES |
| email_change_token_current | varchar | YES |
| email_change_confirm_status | smallint | YES |
| banned_until | timestamptz | YES |
| reauthentication_token | varchar | YES |
| reauthentication_sent_at | timestamptz | YES |
| is_sso_user | boolean | NO |
| deleted_at | timestamptz | YES |
| is_anonymous | boolean | NO |

### Connection to public.users

**There is no foreign key between `public.users` and `auth.users`.** They are completely independent tables.

**The application does not use Supabase Auth at all.** Authentication is implemented entirely in the Streamlit application layer using `public.users`, which stores:
- `username` — used as the login identifier
- `password` — stored as either plaintext or a `pbkdf2:sha256:...` hash (werkzeug format)

The app upgrades plaintext passwords to pbkdf2 on first successful login. `auth.users` is empty or unused for this application's login flow. JWT claims (`auth.uid()`, `auth.role()`) are irrelevant to this app's authorization model.

---

## 8. Flags & Observations

### ⚠️ FLAG 1 — RLS policies use `roles: ['public']`, not `['service_role']`

The 16 existing RLS policies apply to the PostgreSQL `public` role, which **all roles inherit from**. This means the policy `qual: true` (allow all rows) applies to `anon` and `authenticated` PostgREST callers as well, not just `service_role`. Any request with the `anon` key (publicly accessible) can read and write `users`, `daily_cash`, `transfers`, `inventory_logs`, `waste_logs`, `invoices_log`, and 10 other sensitive tables — as long as they hit the PostgREST endpoint.

**Risk:** The anon key is embedded in many client-side applications by default. If it was ever exposed (e.g., pasted into a browser JS bundle, or a PostgREST endpoint was probed), all these tables are fully readable and writable with no authentication.

**Mitigation context:** The application uses `service_role` server-side (Streamlit is a Python backend) so the app itself works correctly. But the database is unprotected against direct API calls using the anon key.

---

### ⚠️ FLAG 2 — 35 tables have RLS enabled with zero policies

Tables like `app_config`, `recipes`, `master_items` (DPOS), and all `ac_*` analytical tables have RLS on but no policies. This is an implicit deny for `anon`/`authenticated` roles — which is actually protective — but it means these tables cannot be accessed via the PostgREST API by any non-service-role caller, even intentionally. If you ever want to add a client-facing API endpoint or a dashboard with `anon` access for any of these tables, you would need to add policies first.

---

### ⚠️ FLAG 3 — `public.users.password` stores credentials in a text column

The `password` column in `public.users` holds the credential used for application login. Older records may be plaintext; newer ones are pbkdf2-hashed. This column is accessible to anyone with the anon key (see Flag 1 — the `users` table has a permissive `public` role policy). An attacker with the anon API key could read all usernames and password hashes.

---

### ⚠️ FLAG 4 — `public.users` is disconnected from `auth.users`

The app implements its own authentication entirely, bypassing Supabase Auth. This means:
- No MFA, magic links, or SSO available without refactoring
- No session management at the database level (sessions live in Streamlit's `st.session_state`, which is in-memory and lost on restart)
- The existing `auth.users` table is unused overhead

This is an architectural decision, not a defect — but worth documenting.

---

### ⚠️ FLAG 5 — `suppliers` has a duplicate unique constraint

Two separate unique indexes exist on `suppliers.supplier_name`:
- `suppliers_name_unique`
- `suppliers_supplier_name_key`

They enforce the same constraint. The redundant index wastes storage and write overhead for no benefit.

---

### ℹ️ FLAG 6 — `transfers.date` is stored as `text`, not `date`

The `date` column in `transfers` is `text NOT NULL`. All other operational tables use native `date` or `timestamptz` types. This prevents date-range filtering via SQL operators and may cause sorting inconsistencies if the format is ever inconsistent.

---

### ℹ️ FLAG 7 — `rls_auto_enable` is a SECURITY DEFINER event trigger

The function `rls_auto_enable()` is a `SECURITY DEFINER` event trigger that fires on every `CREATE TABLE` DDL event and automatically enables RLS on the new table. This is a purposeful design pattern (explains why all 51 public tables have RLS enabled). The security definer elevation is appropriate here since enabling RLS requires superuser or table-owner privileges. No concern — just documenting it.

---

### ℹ️ FLAG 8 — All `ac_*` foreign keys use `ON DELETE NO ACTION`

All 20 analytical (`ac_*`) tables reference `branches.id` with `ON DELETE NO ACTION`. This means deleting a branch would fail if analytical data exists for it, which is the safe/conservative choice. Intentional but worth noting when decommissioning a branch.

---

### ℹ️ FLAG 9 — `dpos_client_config` uses an explicit sequence for its PK

`id: integer DEFAULT nextval('dpos_client_config_id_seq')` — this table was likely created before the `GENERATED ALWAYS AS IDENTITY` or `bigserial` conventions were adopted for other tables. Minor inconsistency.

---

### ℹ️ FLAG 10 — No views, no materialized views

All reporting and aggregation logic lives in the Python application layer. Supabase has no server-side computed views. This is fine for the current workload but worth noting if performance becomes a concern as data volume grows.

---

*End of document. No changes were made to the database during this audit.*
