"""
dpos_simulation.py
──────────────────
Simulation engine for D-POS Pricing Studio.

Key points:
- dpos_unit_costs.usage_cost_usd is already the final USD per g/ml/unit
  (pulled directly from ac_unit_cost.usage_cost — no recalculation needed)
- Overrides store predicted_avg_cost_lbp → recalculate usage_cost on the fly
- Sub recipe cost_for_1 is already USD (pulled from ac_sub_recipes.cost_for_1)
- Selling prices from ac_selling_prices are ex-VAT
- Final display shows both ex-VAT and inc-VAT prices
- Psychological price = round to nearest session.rounding (default $0.50)
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
#  FORMULA FUNCTIONS
# ─────────────────────────────────────────────

def compute_unit_cost_usd(avg_cost_lbp: float, rate: float) -> float:
    """LBP → USD conversion."""
    return avg_cost_lbp / rate if rate and rate > 0 else 0.0


def compute_usage_cost(unit_cost_usd: float, qty_inv: float, qty_buy: float) -> float:
    """
    Excel Usage Cost formula:
      qty_buy = 1  → unit_cost / qty_inv
      qty_buy < 1  → (unit_cost / qty_buy) / 1000
      else         → unit_cost / qty_buy
    """
    qty_buy = qty_buy or 1
    qty_inv = qty_inv or 1
    if qty_buy == 1:
        return unit_cost_usd / qty_inv
    elif qty_buy < 1:
        return (unit_cost_usd / qty_buy) / 1000
    else:
        return unit_cost_usd / qty_buy


def psychological_price(price: float, rounding: float = 0.50) -> float:
    """Round to nearest rounding increment (default $0.50)."""
    if not price or price <= 0 or not rounding:
        return 0.0
    return round(price / rounding) * rounding


# ─────────────────────────────────────────────
#  SIMULATION ENGINE
# ─────────────────────────────────────────────

def compute_simulation(
    recipes_df: pd.DataFrame,
    unit_costs_df: pd.DataFrame,
    sub_recipes_df: pd.DataFrame,
    overrides: dict,
    session: dict,
) -> tuple[pd.DataFrame, dict, dict]:
    """
    Full bottom-up pricing simulation.

    overrides: {product_description_lower: predicted_avg_cost_lbp}

    Returns:
      sim_df       — one row per menu item
      usage_lookup — {ingredient_lower: usage_cost_usd}  for drill-down
      sr_lookup    — {product_name_lower: cost_for_1_usd} for drill-down
    """
    vat_rate   = float(session.get("vat_rate", 0))
    target_pct = float(session.get("target_cost_pct", 0.30))
    rounding   = float(session.get("rounding", 0.50))

    if recipes_df.empty:
        return pd.DataFrame(), {}, {}

    # ── Step 1: Build usage cost lookup ──
    # Use usage_cost_usd directly — already the final number from ac_unit_cost
    # Only recalculate when an override exists (override is LBP)
    usage_lookup = {}

    if not unit_costs_df.empty:
        for _, uc in unit_costs_df.iterrows():
            key          = str(uc.get("product_description","")).lower().strip()
            usage_direct = float(uc.get("usage_cost_usd") or 0)

            if key in overrides:
                # Recalculate from override LBP value
                rate         = float(uc.get("rate") or 90000)
                qty_inv      = float(uc.get("qty_inv") or 1)
                qty_buy      = float(uc.get("qty_buy") or 1)
                unit_cost    = compute_unit_cost_usd(float(overrides[key]), rate)
                usage_lookup[key] = compute_usage_cost(unit_cost, qty_inv, qty_buy)
            else:
                usage_lookup[key] = usage_direct

    # ── Step 2: Build sub recipe cost lookup ──
    # Use cost_for_1 directly from dpos_sub_recipes (already USD)
    # If override affects a sub recipe ingredient, recompute
    sr_lookup = {}

    if not sub_recipes_df.empty:
        for prod_name, grp in sub_recipes_df.groupby("product_name"):
            key = prod_name.lower().strip()

            # Check if any ingredient in this sub recipe is overridden
            has_override = any(
                str(ln.get("ingredient_description","")).lower().strip() in overrides
                for _, ln in grp.iterrows()
            )

            if has_override:
                # Recompute SUMIF: each line = (gross_w × avg_cost_usd) / prepared_qty
                total = 0.0
                for _, ln in grp.iterrows():
                    ing_key  = str(ln.get("ingredient_description","")).lower().strip()
                    gw       = float(ln.get("gross_w") or ln.get("net_w") or 0)
                    prep_qty = float(ln.get("prepared_qty") or 1)
                    # avg_cost in sub recipes = usage_cost USD — use lookup (has override applied)
                    avg_usd  = usage_lookup.get(ing_key, float(ln.get("avg_cost") or 0))
                    total   += (gw * avg_usd) / prep_qty if prep_qty > 0 else 0.0
                sr_lookup[key] = total
            else:
                # Use pre-calculated cost_for_1 directly
                cost_for_1 = float(grp.iloc[0].get("cost_for_1") or 0)
                sr_lookup[key] = cost_for_1

    # ── Step 3: Resolve ingredient cost ──
    # IF ingredient found in sub recipe product names → sr_lookup
    # ELSE → usage_lookup
    def get_cost(ingredient_desc: str) -> float:
        k = ingredient_desc.lower().strip()
        return sr_lookup.get(k, usage_lookup.get(k, 0.0))

    # ── Step 4: Sum recipe costs per menu item ──
    results = {}
    for _, line in recipes_df.iterrows():
        item  = str(line.get("menu_item","")).strip()
        if not item:
            continue
        gw        = float(line.get("gross_w") or line.get("net_w") or 0)
        line_cost = gw * get_cost(str(line.get("ingredient_description","")))

        if item not in results:
            results[item] = {
                "menu_item":              item,
                "category":               line.get("category") or "",
                "group_name":             line.get("group_name") or "",
                "new_cost":               0.0,
                "current_selling_price_ex": float(line.get("current_selling_price") or 0) or None,
            }
        results[item]["new_cost"] += line_cost

    # ── Step 5: Build output rows ──
    rows = []
    for item, data in results.items():
        new_cost = data["new_cost"]
        sp_ex    = data.get("current_selling_price_ex")  # ex-VAT from ac_selling_prices

        # Suggestive price
        if target_pct > 0:
            suggestive_ex  = new_cost / target_pct
            suggestive_inc = suggestive_ex * (1 + vat_rate)
        else:
            suggestive_ex = suggestive_inc = 0.0

        # Current SP inc-VAT for display
        sp_inc = sp_ex * (1 + vat_rate) if sp_ex else None

        rows.append({
            "menu_item":                  item,
            "category":                   data.get("category",""),
            "group_name":                 data.get("group_name",""),
            "new_cost":                   round(new_cost, 6),
            "current_selling_price_ex":   sp_ex,
            "current_sp_inc_vat":         round(sp_inc, 4) if sp_inc else None,
            "suggestive_ex_vat":          round(suggestive_ex, 4),
            "suggestive_price":           round(suggestive_inc, 4),
            "psychological_price":        psychological_price(suggestive_inc, rounding),
            "target_cost_pct":            target_pct,
            "vat_rate":                   vat_rate,
            "rounding":                   rounding,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, usage_lookup, sr_lookup

    return df.sort_values(["category","group_name","menu_item"]).reset_index(drop=True), usage_lookup, sr_lookup


def enrich_with_prices(
    sim_df: pd.DataFrame,
    old_costs: dict,
    session: dict,
) -> pd.DataFrame:
    """
    Add cost % metrics using current selling prices already in sim_df.

    old_costs: {menu_item: previous_new_cost_usd} from last approved session
    """
    if sim_df.empty:
        return sim_df

    vat    = float(session.get("vat_rate", 0))
    target = float(session.get("target_cost_pct", 0.30)) * 100

    df = sim_df.copy()
    df["old_cost"] = df["menu_item"].map(lambda x: old_costs.get(x))

    def ex_vat(p):
        return p / (1 + vat) if vat > 0 and p else p

    # Cost variance vs previous session
    df["cost_variance"] = df.apply(
        lambda r: round(r["new_cost"] - float(r["old_cost"]), 6)
        if r["old_cost"] is not None else None, axis=1
    )
    df["cost_variance_pct"] = df.apply(
        lambda r: round((r["cost_variance"] / float(r["old_cost"])) * 100, 2)
        if r["old_cost"] and r["cost_variance"] is not None else None, axis=1
    )
    df["affected"] = df["cost_variance"].notna() & (pd.to_numeric(df["cost_variance"], errors="coerce").abs() > 0.000001)

    # Current cost % — new_cost vs current SP ex-VAT
    df["current_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / r["current_selling_price_ex"]) * 100, 2)
        if r.get("current_selling_price_ex") and r["current_selling_price_ex"] > 0 else None, axis=1
    )

    # Current profit margin
    df["current_profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / r["current_selling_price_ex"]) * 100, 2)
        if r.get("current_selling_price_ex") and r["current_selling_price_ex"] > 0 else None, axis=1
    )

    # New cost % — new_cost vs suggestive ex-VAT
    df["new_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / r["suggestive_ex_vat"]) * 100, 2)
        if r.get("suggestive_ex_vat") and r["suggestive_ex_vat"] > 0 else None, axis=1
    )

    # New profit margin
    df["profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / r["suggestive_ex_vat"]) * 100, 2)
        if r.get("suggestive_ex_vat") and r["suggestive_ex_vat"] > 0 else None, axis=1
    )

    # Cost position flag
    df["cost_position"] = df["current_cost_pct"].apply(
        lambda v: f"Higher > {target:.0f}%" if v and v > target
        else (f"Lower ≤ {target:.0f}%" if v else "—")
    )

    return df


# ─────────────────────────────────────────────
#  FORMAT HELPERS
# ─────────────────────────────────────────────

def fmt_usd(val, decimals=4):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"${val:,.{decimals}f}"


def fmt_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{val:.2f}%"


def fmt_variance(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{'+' if val > 0 else ''}${val:,.4f}"


def fmt_variance_pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "—"
    return f"{'+' if val > 0 else ''}{val:.2f}%"
