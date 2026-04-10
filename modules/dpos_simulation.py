"""
dpos_simulation.py
──────────────────
Simulation engine for D-POS Pricing Studio.

Source of truth: ac_unit_cost (mirrored into dpos_unit_costs)
  - Contains ALL ingredients including sub recipes
  - usage_cost_usd is already the final USD per g/ml/unit
  - No separate sub recipe calculation needed
  - dpos_sub_recipes kept for display/breakdown only

Override logic:
  - Overrides store predicted_avg_cost_lbp
  - When override exists → recalculate usage_cost from lbp/rate/qty
  - ac_unit_cost never touched

Pricing flow:
  new_cost         = SUM(gross_w × usage_cost) per menu item
  suggestive_ex    = new_cost / target_cost_pct
  suggestive_inc   = suggestive_ex × (1 + vat_rate)
  psychological    = round(suggestive_inc / rounding) × rounding
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
    sub_recipes_df: pd.DataFrame,   # kept for signature compatibility, not used in calc
    overrides: dict,
    session: dict,
) -> tuple[pd.DataFrame, dict, dict]:
    """
    Full bottom-up pricing simulation.

    Single source of truth: dpos_unit_costs (mirrors ac_unit_cost).
    Contains ALL ingredients including sub recipes with correct usage_cost_usd.

    overrides: {product_description_lower: predicted_avg_cost_lbp}

    Returns:
      sim_df       — one row per menu item
      usage_lookup — {ingredient_lower: usage_cost_usd} for drill-down
      sr_lookup    — always empty dict (kept for compatibility)
    """
    vat_rate   = float(session.get("vat_rate", 0))
    target_pct = float(session.get("target_cost_pct", 0.30))
    rounding   = float(session.get("rounding", 0.50))

    if recipes_df.empty:
        return pd.DataFrame(), {}, {}

    # ── Build usage cost lookup from dpos_unit_costs ──
    # Use usage_cost_usd directly — already the final number
    # Only recalculate when an override exists
    usage_lookup = {}

    if not unit_costs_df.empty:
        for _, uc in unit_costs_df.iterrows():
            key          = str(uc.get("product_description", "")).lower().strip()
            usage_direct = float(uc.get("usage_cost_usd") or 0)

            if key in overrides:
                # Recalculate from override predicted LBP value
                rate    = float(uc.get("rate") or 90000)
                qty_inv = float(uc.get("qty_inv") or 1)
                qty_buy = float(uc.get("qty_buy") or 1)
                unit_cost_usd = compute_unit_cost_usd(float(overrides[key]), rate)
                usage_lookup[key] = compute_usage_cost(unit_cost_usd, qty_inv, qty_buy)
            else:
                usage_lookup[key] = usage_direct

    # ── Resolve ingredient cost ──
    # Everything comes from usage_lookup — raw materials and sub recipes alike
    def get_cost(ingredient_desc: str) -> float:
        return usage_lookup.get(ingredient_desc.lower().strip(), 0.0)

    # ── Sum recipe costs per menu item ──
    results = {}
    for _, line in recipes_df.iterrows():
        item = str(line.get("menu_item", "")).strip()
        if not item:
            continue

        gw        = float(line.get("gross_w") or line.get("net_w") or 0)
        line_cost = gw * get_cost(str(line.get("ingredient_description", "")))

        if item not in results:
            results[item] = {
                "menu_item":                item,
                "category":                 line.get("category") or "",
                "group_name":               line.get("group_name") or "",
                "new_cost":                 0.0,
                "current_selling_price_ex": float(line.get("current_selling_price") or 0) or None,
            }
        results[item]["new_cost"] += line_cost

    # ── Build output rows ──
    rows = []
    for item, data in results.items():
        new_cost = data["new_cost"]
        sp_ex    = data.get("current_selling_price_ex")

        # Suggestive price
        if target_pct > 0:
            suggestive_ex  = new_cost / target_pct
            suggestive_inc = suggestive_ex * (1 + vat_rate)
        else:
            suggestive_ex = suggestive_inc = 0.0

        sp_inc = sp_ex * (1 + vat_rate) if sp_ex else None

        rows.append({
            "menu_item":                  item,
            "category":                   data.get("category", ""),
            "group_name":                 data.get("group_name", ""),
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
        return df, usage_lookup, {}

    return df.sort_values(["category", "group_name", "menu_item"]).reset_index(drop=True), usage_lookup, {}


# ─────────────────────────────────────────────
#  ENRICH WITH PRICES
# ─────────────────────────────────────────────

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

    # Cost variance vs previous session
    df["cost_variance"] = df.apply(
        lambda r: round(float(r["new_cost"]) - float(r["old_cost"]), 6)
        if r["old_cost"] is not None else None, axis=1
    )
    df["cost_variance_pct"] = df.apply(
        lambda r: round((float(r["cost_variance"]) / float(r["old_cost"])) * 100, 2)
        if r["old_cost"] and r["cost_variance"] is not None else None, axis=1
    )

    # Force numeric before abs() to avoid type errors
    cv = pd.to_numeric(df["cost_variance"], errors="coerce")
    df["affected"] = cv.notna() & (cv.abs() > 0.000001)

    # Current cost % — new_cost vs current SP ex-VAT
    df["current_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / float(r["current_selling_price_ex"])) * 100, 2)
        if r.get("current_selling_price_ex") and float(r["current_selling_price_ex"]) > 0 else None, axis=1
    )

    # Current profit margin
    df["current_profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / float(r["current_selling_price_ex"])) * 100, 2)
        if r.get("current_selling_price_ex") and float(r["current_selling_price_ex"]) > 0 else None, axis=1
    )

    # New cost % — new_cost vs suggestive ex-VAT
    df["new_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / float(r["suggestive_ex_vat"])) * 100, 2)
        if r.get("suggestive_ex_vat") and float(r["suggestive_ex_vat"]) > 0 else None, axis=1
    )

    # New profit margin
    df["profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / float(r["suggestive_ex_vat"])) * 100, 2)
        if r.get("suggestive_ex_vat") and float(r["suggestive_ex_vat"]) > 0 else None, axis=1
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
