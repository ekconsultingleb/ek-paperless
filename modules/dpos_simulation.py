"""
dpos_simulation.py
──────────────────
Simulation engine for D-POS Pricing Studio.

Tranche modes:
  target_pct  — suggestive price = cost / target_pct
  fixed_price — suggestive price = fixed_price directly (ignores cost %)

Tranche priority: per-Type tranche > global tranche > category_target > global_target
BTL→GLS derivation: optional per-client toggle. When ON, GLS price = BTL price ÷ glasses_count.
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
#  FORMULA FUNCTIONS
# ─────────────────────────────────────────────

def compute_unit_cost_usd(avg_cost_lbp: float, rate: float) -> float:
    return avg_cost_lbp / rate if rate and rate > 0 else 0.0


def compute_usage_cost(unit_cost_usd: float, qty_inv: float, qty_buy: float) -> float:
    qty_buy = qty_buy or 1
    qty_inv = qty_inv or 1
    if qty_buy == 1:
        return unit_cost_usd / qty_inv
    elif qty_buy < 1:
        return (unit_cost_usd / qty_buy) / 1000
    else:
        return unit_cost_usd / qty_buy


def psychological_price(price: float, rounding: float = 0.50) -> float:
    if not price or price <= 0 or not rounding:
        return 0.0
    return round(price / rounding) * rounding


def resolve_tranche(new_cost: float, tranches: list) -> dict | None:
    """
    Find the matching tranche for a given cost.
    Returns the tranche dict or None if no match.
    Tranche dict keys: min_cost, max_cost, mode, target_pct, fixed_price, item_type (optional)
    """
    for t in sorted(tranches, key=lambda x: float(x.get("min_cost", 0))):
        min_c = float(t.get("min_cost", 0))
        max_c = float(t.get("max_cost", 9999))
        if min_c <= new_cost < max_c:
            return t
    return None


def get_target_for_item(
    new_cost: float,
    category: str,
    item_type: str,
    category_targets: dict,
    tranches: list,
    global_target: float,
) -> tuple[float, float | None, str]:
    """
    Resolve pricing for an item.

    Priority:
      1. Type-specific tranche (item_type column matches)
      2. Global tranche (no item_type on tranche, or item_type is None/'')
      3. Category target
      4. Global target

    Returns:
      effective_target  — target cost % (0 if fixed price mode)
      fixed_price       — fixed selling price inc-VAT or None
      pricing_mode      — 'target_pct' or 'fixed_price'
    """
    item_type_clean = (item_type or "").lower().strip()

    # 1. Type-specific tranches first
    type_tranches = [
        t for t in tranches
        if (t.get("item_type") or "").lower().strip() == item_type_clean
        and item_type_clean != ""
    ]
    tranche = resolve_tranche(new_cost, type_tranches)

    # 2. Fall back to global tranches (no item_type set)
    if not tranche:
        global_tranches = [
            t for t in tranches
            if not (t.get("item_type") or "").strip()
        ]
        tranche = resolve_tranche(new_cost, global_tranches)

    if tranche:
        mode = str(tranche.get("mode", "target_pct"))
        if mode == "fixed_price":
            fp = tranche.get("fixed_price")
            return 0.0, float(fp) if fp is not None else None, "fixed_price"
        else:
            tp = tranche.get("target_pct")
            return float(tp) if tp else global_target, None, "target_pct"

    # 3. Category target
    if category:
        cat_key = category.lower().strip()
        if cat_key in category_targets:
            return category_targets[cat_key], None, "target_pct"

    # 4. Global target
    return global_target, None, "target_pct"


def detect_btl_gls(menu_item: str) -> str:
    name = str(menu_item).lower()
    if name.startswith("btl ") or " btl " in name or name.endswith(" btl") or \
       name.startswith("bottle ") or " bottle " in name:
        return "btl"
    if name.startswith("gls ") or " gls " in name or name.endswith(" gls") or \
       name.startswith("glass ") or " glass " in name:
        return "gls"
    return "other"


def get_base_name(menu_item: str) -> str:
    name = str(menu_item).strip()
    prefixes = ["Btl ", "Gls ", "Bottle ", "Glass "]
    suffixes = [" Btl", " Gls", " Bottle", " Glass"]
    for p in prefixes:
        if name.lower().startswith(p.lower()):
            name = name[len(p):]
            break
    for s in suffixes:
        if name.lower().endswith(s.lower()):
            name = name[:-len(s)]
            break
    return name.strip().lower()


# ─────────────────────────────────────────────
#  SIMULATION ENGINE
# ─────────────────────────────────────────────

def compute_simulation(
    recipes_df: pd.DataFrame,
    unit_costs_df: pd.DataFrame,
    sub_recipes_df: pd.DataFrame,
    overrides: dict,
    session: dict,
    category_targets: dict = None,
    tranches: list = None,
    item_config: pd.DataFrame = None,
    btl_gls_derive: bool = True,
) -> tuple[pd.DataFrame, dict, dict]:
    """
    Full bottom-up pricing simulation.

    btl_gls_derive: when True, GLS price is derived from BTL price ÷ glasses_count
                    (client-level toggle). When False, GLS uses its own tranche rules.
    """
    vat_rate   = float(session.get("vat_rate", 0))
    target_pct = float(session.get("target_cost_pct", 0.30))
    rounding   = float(session.get("rounding", 0.50))

    if category_targets is None: category_targets = {}
    if tranches is None:         tranches = []

    if recipes_df.empty:
        return pd.DataFrame(), {}, {}

    # ── Build usage cost lookup ──
    usage_lookup = {}
    if not unit_costs_df.empty:
        for _, uc in unit_costs_df.iterrows():
            key          = str(uc.get("product_description", "")).lower().strip()
            usage_direct = float(uc.get("usage_cost_usd") or 0)
            if key in overrides:
                rate          = float(uc.get("rate") or 90000)
                qty_inv       = float(uc.get("qty_inv") or 1)
                qty_buy       = float(uc.get("qty_buy") or 1)
                unit_cost_usd = compute_unit_cost_usd(float(overrides[key]), rate)
                usage_lookup[key] = compute_usage_cost(unit_cost_usd, qty_inv, qty_buy)
            else:
                usage_lookup[key] = usage_direct

    # ── Build item config lookup ──
    glasses_map = {}
    tier_map    = {}
    if item_config is not None and not item_config.empty:
        for _, row in item_config.drop_duplicates("menu_item").iterrows():
            item = row["menu_item"]
            gc = row.get("glasses_count")
            if gc is not None and not (isinstance(gc, float) and np.isnan(gc)):
                glasses_map[item] = float(gc)
            if row.get("tier"):
                tier_map[item] = str(row["tier"])

    # ── Sum recipe costs per menu item ──
    results = {}
    for _, line in recipes_df.iterrows():
        item = str(line.get("menu_item", "")).strip()
        if not item:
            continue
        gw        = float(line.get("gross_w") or line.get("net_w") or 0)
        ing_key   = str(line.get("ingredient_description", "")).lower().strip()
        line_cost = gw * usage_lookup.get(ing_key, 0.0)

        if item not in results:
            results[item] = {
                "menu_item":                item,
                "category":                 line.get("category") or "",
                "group_name":               line.get("group_name") or "",
                "new_cost":                 0.0,
                "current_selling_price_ex": float(line.get("current_selling_price") or 0) or None,
                "on_menu":                  bool(line.get("on_menu", True)),
            }
        results[item]["new_cost"] += line_cost

    # ── Build output rows ──
    rows = []
    for item, data in results.items():
        new_cost  = data["new_cost"]
        category  = data.get("category", "")
        sp_ex     = data.get("current_selling_price_ex")
        item_type = detect_btl_gls(item)
        glasses_count = glasses_map.get(item)

        # Resolve pricing using type-aware tranche lookup
        effective_target, fixed_price, pricing_mode = get_target_for_item(
            new_cost, category, item_type, category_targets, tranches, target_pct
        )

        # Calculate suggestive price
        if pricing_mode == "fixed_price" and fixed_price is not None:
            suggestive_inc = float(fixed_price)
            suggestive_ex  = suggestive_inc / (1 + vat_rate) if vat_rate > 0 else suggestive_inc
        elif effective_target > 0:
            suggestive_ex  = new_cost / effective_target
            suggestive_inc = suggestive_ex * (1 + vat_rate)
        else:
            suggestive_ex = suggestive_inc = 0.0

        psych  = psychological_price(suggestive_inc, rounding)
        sp_inc = sp_ex * (1 + vat_rate) if sp_ex else None

        rows.append({
            "menu_item":                  item,
            "category":                   category,
            "group_name":                 data.get("group_name", ""),
            "on_menu":                    data.get("on_menu", True),
            "new_cost":                   round(new_cost, 6),
            "current_selling_price_ex":   sp_ex,
            "current_sp_inc_vat":         round(sp_inc, 4) if sp_inc else None,
            "effective_target_pct":       effective_target,
            "pricing_mode":               pricing_mode,
            "fixed_price":                fixed_price,
            "suggestive_ex_vat":          round(suggestive_ex, 4),
            "suggestive_price":           round(suggestive_inc, 4),
            "psychological_price":        psych,
            "item_type":                  item_type,
            "glasses_count":              glasses_count,
            "tier":                       tier_map.get(item),
            "vat_rate":                   vat_rate,
            "rounding":                   rounding,
            "gls_derived_from_btl":       False,
            "tier_violation":             False,
            "tier_violation_msg":         "",
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, usage_lookup, {}

    df = df.sort_values(["category", "group_name", "menu_item"]).reset_index(drop=True)

    if btl_gls_derive:
        df = _apply_bottle_glass_pricing(df, rounding, vat_rate)

    df = _validate_tier_hierarchy(df)

    return df, usage_lookup, {}


def _apply_bottle_glass_pricing(df: pd.DataFrame, rounding: float, vat_rate: float) -> pd.DataFrame:
    """Derive GLS price from BTL price ÷ glasses_count where a matching BTL exists."""
    df = df.copy()

    btl_price_map = {}
    for _, row in df[df["item_type"] == "btl"].iterrows():
        base = get_base_name(row["menu_item"])
        btl_price_map[base] = float(row["psychological_price"] or 0)

    for idx, row in df[df["item_type"] == "gls"].iterrows():
        base          = get_base_name(row["menu_item"])
        glasses_count = float(row.get("glasses_count") or 0)
        btl_price     = btl_price_map.get(base, 0)

        if btl_price > 0 and glasses_count > 0:
            gls_price_inc   = btl_price / glasses_count
            gls_price_psych = psychological_price(gls_price_inc, rounding)
            gls_price_ex    = gls_price_psych / (1 + vat_rate) if vat_rate > 0 else gls_price_psych
            df.at[idx, "suggestive_price"]     = round(gls_price_inc, 4)
            df.at[idx, "suggestive_ex_vat"]    = round(gls_price_ex, 4)
            df.at[idx, "psychological_price"]  = gls_price_psych
            df.at[idx, "gls_derived_from_btl"] = True

    return df


def _validate_tier_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    tier_order = {"regular": 1, "premium": 2, "ultra premium": 3}

    has_tier = df["tier"].notna() & (df["tier"] != "")
    tagged   = df[has_tier].copy()

    if tagged.empty:
        return df

    for (cat, grp), grp_df in tagged.groupby(["category", "group_name"]):
        btl_grp = grp_df[grp_df["item_type"] == "btl"].copy()
        if btl_grp.empty:
            btl_grp = grp_df.copy()

        btl_grp["tier_order"] = btl_grp["tier"].str.lower().str.strip().map(tier_order)
        btl_grp = btl_grp.dropna(subset=["tier_order"])

        # Get the max price per tier level
        tier_max_price = btl_grp.groupby("tier_order")["psychological_price"].max().to_dict()

        # Only flag when a higher tier's MAX price <= a lower tier's MAX price
        tier_levels = sorted(tier_max_price.keys())
        for i in range(1, len(tier_levels)):
            lower_tier_order  = tier_levels[i - 1]
            higher_tier_order = tier_levels[i]
            lower_price  = float(tier_max_price[lower_tier_order])
            higher_price = float(tier_max_price[higher_tier_order])

            if higher_price <= lower_price:
                lower_tier_name  = [k for k, v in tier_order.items() if v == lower_tier_order][0].title()
                higher_tier_name = [k for k, v in tier_order.items() if v == higher_tier_order][0].title()
                msg = f"{higher_tier_name} (${higher_price:.2f}) ≤ {lower_tier_name} (${lower_price:.2f})"
                # Flag all items in the higher tier within this group
                mask = (
                    (df["category"]   == cat) &
                    (df["group_name"] == grp) &
                    (df["tier"].str.lower().str.strip() == higher_tier_name.lower())
                )
                df.loc[mask, "tier_violation"]     = True
                df.loc[mask, "tier_violation_msg"] = msg

    return df


# ─────────────────────────────────────────────
#  ENRICH WITH PRICES
# ─────────────────────────────────────────────

def enrich_with_prices(
    sim_df: pd.DataFrame,
    old_costs: dict,
    session: dict,
) -> pd.DataFrame:
    if sim_df.empty:
        return sim_df

    vat    = float(session.get("vat_rate", 0))
    target = float(session.get("target_cost_pct", 0.30)) * 100

    df = sim_df.copy()
    df["old_cost"] = df["menu_item"].map(lambda x: old_costs.get(x))

    cv_raw = df.apply(
        lambda r: round(float(r["new_cost"]) - float(r["old_cost"]), 6)
        if r["old_cost"] is not None else None, axis=1
    )
    df["cost_variance"] = cv_raw
    df["cost_variance_pct"] = df.apply(
        lambda r: round((float(r["cost_variance"]) / float(r["old_cost"])) * 100, 2)
        if r["old_cost"] and r["cost_variance"] is not None else None, axis=1
    )

    cv = pd.to_numeric(df["cost_variance"], errors="coerce")
    df["affected"] = cv.notna() & (cv.abs() > 0.000001)

    df["current_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / float(r["current_selling_price_ex"])) * 100, 2)
        if r.get("current_selling_price_ex") and float(r["current_selling_price_ex"]) > 0 else None, axis=1
    )
    df["current_profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / float(r["current_selling_price_ex"])) * 100, 2)
        if r.get("current_selling_price_ex") and float(r["current_selling_price_ex"]) > 0 else None, axis=1
    )
    df["new_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / float(r["suggestive_ex_vat"])) * 100, 2)
        if r.get("suggestive_ex_vat") and float(r["suggestive_ex_vat"]) > 0 else None, axis=1
    )
    df["profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / float(r["suggestive_ex_vat"])) * 100, 2)
        if r.get("suggestive_ex_vat") and float(r["suggestive_ex_vat"]) > 0 else None, axis=1
    )
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
