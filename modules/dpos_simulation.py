"""
dpos_simulation.py
──────────────────
Simulation engine for D-POS Pricing Studio.

Pricing intelligence:
  1. Per-category target cost % (overrides global target)
  2. Cost tranches (override category target based on item cost)
  3. Bottle/Glass logic (Gls price = Btl price / glasses_count)
  4. Sub-category tier hierarchy validation (Regular < Premium < Ultra Premium)

Source of truth: dpos_unit_costs (mirrors ac_unit_cost)
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


def get_target_for_item(
    new_cost: float,
    category: str,
    category_targets: dict,
    tranches: list,
    global_target: float,
) -> float:
    """
    Resolve the correct target cost % for an item.
    Priority: tranche > category > global

    tranches: list of dicts sorted by min_cost ascending
      [{"min_cost": 0, "max_cost": 10, "target_pct": 0.25}, ...]
    category_targets: {category_lower: target_pct}
    """
    # 1. Check tranches first (highest priority)
    for tranche in sorted(tranches, key=lambda t: float(t.get("min_cost", 0))):
        min_c = float(tranche.get("min_cost", 0))
        max_c = float(tranche.get("max_cost", 9999))
        if min_c <= new_cost < max_c:
            return float(tranche.get("target_pct", global_target))

    # 2. Category target
    if category:
        cat_key = category.lower().strip()
        if cat_key in category_targets:
            return category_targets[cat_key]

    # 3. Global target
    return global_target


def detect_btl_gls(menu_item: str) -> str:
    """
    Detect if item is a bottle or glass.
    Returns: 'btl', 'gls', or 'other'
    """
    name = menu_item.lower()
    # Check for Btl patterns
    if name.startswith("btl ") or " btl " in name or name.endswith(" btl") or \
       name.startswith("bottle ") or " bottle " in name:
        return "btl"
    # Check for Gls patterns
    if name.startswith("gls ") or " gls " in name or name.endswith(" gls") or \
       name.startswith("glass ") or " glass " in name:
        return "gls"
    return "other"


def get_base_name(menu_item: str) -> str:
    """
    Strip Btl/Gls prefix/suffix to get the base product name.
    e.g. "Btl Laphroaig 10y" → "laphroaig 10y"
         "Laphroaig 10y Btl" → "laphroaig 10y"
         "Gls Laphroaig 10y" → "laphroaig 10y"
    """
    name = menu_item.strip()
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
) -> tuple[pd.DataFrame, dict, dict]:
    """
    Full bottom-up pricing simulation with pricing intelligence.

    category_targets: {category_lower: target_pct}
    tranches: [{"min_cost", "max_cost", "target_pct"}, ...]
    item_config: DataFrame with menu_item, glasses_count, sub_category, tier
    """
    vat_rate   = float(session.get("vat_rate", 0))
    target_pct = float(session.get("target_cost_pct", 0.30))
    rounding   = float(session.get("rounding", 0.50))

    if category_targets is None:
        category_targets = {}
    if tranches is None:
        tranches = []

    if recipes_df.empty:
        return pd.DataFrame(), {}, {}

    # ── Build usage cost lookup ──
    usage_lookup = {}
    if not unit_costs_df.empty:
        for _, uc in unit_costs_df.iterrows():
            key          = str(uc.get("product_description", "")).lower().strip()
            usage_direct = float(uc.get("usage_cost_usd") or 0)

            if key in overrides:
                rate    = float(uc.get("rate") or 90000)
                qty_inv = float(uc.get("qty_inv") or 1)
                qty_buy = float(uc.get("qty_buy") or 1)
                unit_cost_usd = compute_unit_cost_usd(float(overrides[key]), rate)
                usage_lookup[key] = compute_usage_cost(unit_cost_usd, qty_inv, qty_buy)
            else:
                usage_lookup[key] = usage_direct

    # ── Build item config lookup ──
    glasses_map    = {}
    sub_cat_map    = {}
    tier_map       = {}
    if item_config is not None and not item_config.empty:
        for _, row in item_config.drop_duplicates("menu_item").iterrows():
            item = row["menu_item"]
            if row.get("glasses_count"):
                glasses_map[item] = float(row["glasses_count"])
            if row.get("sub_category"):
                sub_cat_map[item] = str(row["sub_category"])
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
        new_cost = data["new_cost"]
        category = data.get("category", "")
        sp_ex    = data.get("current_selling_price_ex")

        # Detect bottle/glass type
        item_type    = detect_btl_gls(item)
        glasses_count = glasses_map.get(item)

        # Resolve target for this item
        effective_target = get_target_for_item(
            new_cost, category, category_targets, tranches, target_pct
        )

        # Suggestive price
        if effective_target > 0:
            suggestive_ex  = new_cost / effective_target
            suggestive_inc = suggestive_ex * (1 + vat_rate)
        else:
            suggestive_ex = suggestive_inc = 0.0

        psych = psychological_price(suggestive_inc, rounding)
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
            "suggestive_ex_vat":          round(suggestive_ex, 4),
            "suggestive_price":           round(suggestive_inc, 4),
            "psychological_price":        psych,
            "item_type":                  item_type,
            "glasses_count":              glasses_count,
            "sub_category":               sub_cat_map.get(item),
            "tier":                       tier_map.get(item),
            "vat_rate":                   vat_rate,
            "rounding":                   rounding,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, usage_lookup, {}

    df = df.sort_values(["category", "group_name", "menu_item"]).reset_index(drop=True)

    # ── Phase 3: Derive Gls price from Btl price ──
    df = _apply_bottle_glass_pricing(df, rounding, vat_rate)

    # ── Phase 4: Tier hierarchy validation ──
    df = _validate_tier_hierarchy(df)

    return df, usage_lookup, {}


def _apply_bottle_glass_pricing(df: pd.DataFrame, rounding: float, vat_rate: float) -> pd.DataFrame:
    """
    For glass items: derive price from the matching bottle item.
    Gls price (inc VAT) = Btl psychological_price / glasses_count
    Then round to nearest rounding increment.
    """
    df = df.copy()

    # Build bottle price map: base_name → psychological_price
    btl_price_map = {}
    btl_cost_map  = {}
    for _, row in df[df["item_type"] == "btl"].iterrows():
        base = get_base_name(row["menu_item"])
        btl_price_map[base] = float(row["psychological_price"] or 0)
        btl_cost_map[base]  = float(row["new_cost"] or 0)

    # Apply to glass items
    for idx, row in df[df["item_type"] == "gls"].iterrows():
        base          = get_base_name(row["menu_item"])
        glasses_count = float(row.get("glasses_count") or 0)
        btl_price     = btl_price_map.get(base, 0)

        if btl_price > 0 and glasses_count > 0:
            gls_price_inc  = btl_price / glasses_count
            gls_price_psych = psychological_price(gls_price_inc, rounding)
            gls_price_ex   = gls_price_psych / (1 + vat_rate) if vat_rate > 0 else gls_price_psych

            df.at[idx, "suggestive_price"]    = round(gls_price_inc, 4)
            df.at[idx, "suggestive_ex_vat"]   = round(gls_price_ex, 4)
            df.at[idx, "psychological_price"]  = gls_price_psych
            df.at[idx, "gls_derived_from_btl"] = True
        else:
            df.at[idx, "gls_derived_from_btl"] = False

    if "gls_derived_from_btl" not in df.columns:
        df["gls_derived_from_btl"] = False

    return df


def _validate_tier_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag tier hierarchy violations within same sub_category.
    Regular price must be < Premium price < Ultra Premium price.
    """
    df = df.copy()
    df["tier_violation"] = False
    df["tier_violation_msg"] = ""

    tier_order = {"regular": 1, "premium": 2, "ultra premium": 3}

    # Group by sub_category
    has_sub_cat = df["sub_category"].notna() & (df["sub_category"] != "")
    has_tier    = df["tier"].notna() & (df["tier"] != "")
    tagged      = df[has_sub_cat & has_tier].copy()

    if tagged.empty:
        return df

    for sub_cat, grp in tagged.groupby("sub_category"):
        # Get btl items only for hierarchy comparison
        btl_grp = grp[grp["item_type"] == "btl"].copy()
        if btl_grp.empty:
            btl_grp = grp.copy()

        btl_grp["tier_order"] = btl_grp["tier"].str.lower().str.strip().map(tier_order)
        btl_grp = btl_grp.dropna(subset=["tier_order"]).sort_values("tier_order")

        # Check ascending price order
        prev_price = 0.0
        prev_tier  = ""
        for _, row in btl_grp.iterrows():
            price = float(row.get("psychological_price") or 0)
            tier  = str(row.get("tier", "")).strip()
            if prev_price > 0 and price <= prev_price:
                msg = f"{tier} (${price:.2f}) ≤ {prev_tier} (${prev_price:.2f})"
                df.loc[df["menu_item"] == row["menu_item"], "tier_violation"]     = True
                df.loc[df["menu_item"] == row["menu_item"], "tier_violation_msg"] = msg
            prev_price = price
            prev_tier  = tier

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

    # Cost variance
    df["cost_variance"] = df.apply(
        lambda r: round(float(r["new_cost"]) - float(r["old_cost"]), 6)
        if r["old_cost"] is not None else None, axis=1
    )
    df["cost_variance_pct"] = df.apply(
        lambda r: round((float(r["cost_variance"]) / float(r["old_cost"])) * 100, 2)
        if r["old_cost"] and r["cost_variance"] is not None else None, axis=1
    )

    cv = pd.to_numeric(df["cost_variance"], errors="coerce")
    df["affected"] = cv.notna() & (cv.abs() > 0.000001)

    # Current cost % vs current SP ex-VAT
    df["current_cost_pct"] = df.apply(
        lambda r: round((r["new_cost"] / float(r["current_selling_price_ex"])) * 100, 2)
        if r.get("current_selling_price_ex") and float(r["current_selling_price_ex"]) > 0 else None, axis=1
    )

    df["current_profit_margin"] = df.apply(
        lambda r: round((1 - r["new_cost"] / float(r["current_selling_price_ex"])) * 100, 2)
        if r.get("current_selling_price_ex") and float(r["current_selling_price_ex"]) > 0 else None, axis=1
    )

    # New cost % vs suggestive ex-VAT
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
