# modules/worldwide_master_items.py

import streamlit as st
import pandas as pd
from datetime import datetime
import zoneinfo
from supabase import Client

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

REGIONS = ["Lebanon", "Cameroon", "Dubai", "Global"]

UNITS = ["kg", "g", "l", "ml", "pcs", "box", "pack", "portion", "batch"]

CATEGORIES = [
    "Meat & Poultry", "Seafood", "Vegetables", "Fruits",
    "Dairy & Eggs", "Dry Goods", "Oils & Condiments",
    "Bakery", "Beverages", "Spices & Herbs", "Other"
]

# ─────────────────────────────────────────────
# FUZZY SEARCH (same engine as recipes.py)
# ─────────────────────────────────────────────

TYPO_MAP = {
    "chrimp": "shrimp", "shrip": "shrimp",
    "salmen": "salmon", "samon": "salmon",
    "chiken": "chicken", "chicen": "chicken",
    "tomatoe": "tomato", "tamato": "tomato",
    "garlick": "garlic",
    "mustered": "mustard", "mstard": "mustard",
    "limon": "lemon", "lemmon": "lemon",
    "tawouk": "taouk",
}

def _lev(a: str, b: str) -> int:
    m, n = len(a), len(b)
    d = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1): d[i][0] = i
    for j in range(n + 1): d[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            d[i][j] = min(d[i-1][j]+1, d[i][j-1]+1, d[i-1][j-1]+cost)
    return d[m][n]

def _is_arabic(text: str) -> bool:
    return any('\u0600' <= c <= '\u06FF' for c in text)

def search_global_items(
    query: str,
    supabase: Client,
    region: str = "Global",
    limit: int = 8,
    exclude_codes: list = None
) -> list:
    """
    Search worldwide_master_items with fuzzy + Arabic support.
    Filters by region first, falls back to Global if < 3 results.
    """
    exclude_codes = exclude_codes or []
    items = _fetch_global_items(supabase, region)
    items = [i for i in items if i["product_code"] not in exclude_codes]

    if not query.strip():
        return []

    q = query.strip().lower()
    corrected = TYPO_MAP.get(q, q)
    arabic = _is_arabic(query)
    scored = []

    for item in items:
        hay = (
            item.get("item_name_ar", "").lower() if arabic
            else item.get("item_name", "").lower()
        )
        score = 0
        if hay == corrected:                              score = 100
        elif corrected in hay or hay.startswith(corrected): score = 90
        else:
            for word in hay.split():
                if word == corrected:                     score = max(score, 80)
                elif len(word) > 2 and _lev(word, corrected) <= 2:
                                                          score = max(score, 65)
                elif corrected != q and len(word) > 2 and _lev(word, q) <= 2:
                                                          score = max(score, 55)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    results = [item for _, item in scored[:limit]]

    # Fallback to global if regional results are thin
    if len(results) < 3 and region != "Global":
        global_items = _fetch_global_items(supabase, "Global")
        global_items = [
            i for i in global_items
            if i["product_code"] not in exclude_codes
            and i["product_code"] not in [r["product_code"] for r in results]
        ]
        fallback_scored = []
        for item in global_items:
            hay = (
                item.get("item_name_ar", "").lower() if arabic
                else item.get("item_name", "").lower()
            )
            score = 0
            if hay == corrected:                               score = 100
            elif corrected in hay or hay.startswith(corrected): score = 90
            else:
                for word in hay.split():
                    if word == corrected:                      score = max(score, 80)
                    elif len(word) > 2 and _lev(word, corrected) <= 2:
                                                               score = max(score, 65)
            if score > 0:
                fallback_scored.append((score, item))
        fallback_scored.sort(key=lambda x: -x[0])
        results += [item for _, item in fallback_scored[: limit - len(results)]]

    return results


# ─────────────────────────────────────────────
# SUPABASE HELPERS
# ─────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_global_items(_supabase_url: str, region: str) -> list:
    """
    Cached fetch — keyed by supabase URL + region.
    TTL 5 min so costs stay fresh without hammering DB.
    We pass _supabase_url as a cache key (Client is not hashable).
    """
    from supabase import create_client
    import streamlit as _st
    supabase = create_client(_st.secrets["SUPABASE_URL"], _st.secrets["SUPABASE_KEY"])
    try:
        if region == "Global":
            res = supabase.table("worldwide_master_items").select("*").execute()
        else:
            res = supabase.table("worldwide_master_items").select("*").in_(
                "region", [region, "Global"]
            ).execute()
        return res.data or []
    except Exception:
        return []


def _fetch_global_items(supabase: Client, region: str) -> list:
    """Non-cached version for admin panel edits."""
    try:
        if region == "Global":
            res = supabase.table("worldwide_master_items").select("*").execute()
        else:
            res = supabase.table("worldwide_master_items").select("*").in_(
                "region", [region, "Global"]
            ).execute()
        return res.data or []
    except Exception:
        return []


def copy_to_client(supabase: Client, client_name: str, region: str) -> int:
    """
    Seeds a new client's master_items from worldwide_master_items.
    Called once during client onboarding.
    Returns number of items copied.
    """
    global_items = _fetch_global_items(supabase, region)
    if not global_items:
        return 0
    records = []
    for item in global_items:
        records.append({
            "client_name":   client_name,
            "product_code":  item["product_code"],
            "item_name":     item["item_name"],
            "item_name_ar":  item.get("item_name_ar", ""),
            "unit":          item["unit"],
            "category":      item.get("category", "Other"),
            "is_production": False,          # client decides later
            "cost_per_unit": item.get(f"latest_cost_{region.lower()}")
                             or item.get("latest_cost_global") or 0,
            "region":        region,
            "source":        "worldwide",
        })
    try:
        supabase.table("master_items").upsert(
            records, on_conflict="client_name,product_code"
        ).execute()
        return len(records)
    except Exception as e:
        st.error(f"Copy to client failed: {e}")
        return 0


def sync_cost_from_autocalc(
    supabase: Client,
    product_code: str,
    region: str,
    new_cost: float,
    source_client: str,
    ek_override: bool = False
) -> bool:
    """
    Called by Auto Calc reader after each upload.
    Updates latest cost for this product + region in worldwide_master_items.
    If ek_override=True, always writes.
    If auto, only writes if new cost differs by > 2% (avoids noise).
    """
    try:
        res = supabase.table("worldwide_master_items").select(
            "id, latest_cost_lebanon, latest_cost_dubai, latest_cost_cameroon, latest_cost_global, ek_locked"
        ).eq("product_code", product_code).execute()

        if not res.data:
            return False

        item = res.data[0]

        # Respect EK manual lock
        if item.get("ek_locked") and not ek_override:
            return False

        cost_col = f"latest_cost_{region.lower()}"
        current = item.get(cost_col) or 0

        # Only update if change > 2% or EK override
        if not ek_override and current > 0:
            change_pct = abs(new_cost - current) / current
            if change_pct < 0.02:
                return False

        update_data = {
            cost_col: new_cost,
            "last_synced_at": datetime.now(
                zoneinfo.ZoneInfo("Asia/Beirut")
            ).isoformat(),
            "last_synced_from": source_client,
        }

        supabase.table("worldwide_master_items").update(
            update_data
        ).eq("product_code", product_code).execute()
        return True

    except Exception:
        return False


def bulk_sync_from_autocalc(
    supabase: Client,
    cost_rows: list,
    region: str,
    source_client: str
):
    """
    cost_rows: list of {"product_code": str, "cost_per_unit": float}
    Called after full Auto Calc upload — syncs all items at once.
    """
    updated = 0
    skipped = 0
    for row in cost_rows:
        ok = sync_cost_from_autocalc(
            supabase,
            product_code=row["product_code"],
            region=region,
            new_cost=row["cost_per_unit"],
            source_client=source_client,
        )
        if ok:
            updated += 1
        else:
            skipped += 1
    return {"updated": updated, "skipped": skipped}


# ─────────────────────────────────────────────
# ROLE-BASED COST VISIBILITY
# ─────────────────────────────────────────────

def can_see_costs(role: str) -> bool:
    """
    Only admin, admin_all, and manager roles see costs.
    Chef and staff see ingredients and quantities only.
    """
    return str(role).lower() in ["admin", "admin_all", "manager", "viewer"]


# ─────────────────────────────────────────────
# EK ADMIN PANEL
# ─────────────────────────────────────────────

def render_worldwide_admin(supabase: Client, role: str):
    """
    EK-team-only admin panel for managing worldwide_master_items.
    Add items, edit names/costs, merge duplicates, lock costs.
    """
    if str(role).lower() not in ["admin_all"]:
        st.warning("Access restricted to EK team only.")
        return

    st.markdown("### Worldwide master items")
    st.caption("Global ingredient registry shared across all clients. EK team only.")

    tab_browse, tab_add, tab_sync, tab_onboard = st.tabs([
        "Browse & edit", "Add new item", "Cost sync log", "Client onboarding"
    ])

    # ── BROWSE & EDIT ────────────────────────
    with tab_browse:
        col_r, col_c, col_s = st.columns([1, 1, 2])
        with col_r:
            region_filter = st.selectbox("Region", ["All"] + REGIONS, key="wmi_region")
        with col_c:
            cat_filter = st.selectbox("Category", ["All"] + CATEGORIES, key="wmi_cat")
        with col_s:
            search = st.text_input("Search", placeholder="chicken · جمبري...", key="wmi_search")

        try:
            query = supabase.table("worldwide_master_items").select("*").order("item_name")
            if region_filter != "All":
                query = query.eq("region", region_filter)
            if cat_filter != "All":
                query = query.eq("category", cat_filter)
            res = query.execute()
            items = res.data or []
        except Exception as e:
            st.error(f"Failed to load: {e}")
            return

        if search:
            sl = search.lower()
            items = [
                i for i in items
                if sl in i.get("item_name", "").lower()
                or sl in i.get("item_name_ar", "").lower()
                or sl in i.get("product_code", "").lower()
            ]

        st.caption(f"{len(items)} items")

        if not items:
            st.info("No items found.")
            return

        for item in items:
            with st.expander(
                f"{item['item_name']}  ·  {item.get('product_code','')}  ·  {item.get('region','')}",
                expanded=False
            ):
                c1, c2, c3 = st.columns(3)
                with c1:
                    new_name = st.text_input(
                        "Name (EN)", value=item.get("item_name", ""),
                        key=f"wmi_name_{item['id']}"
                    )
                    new_name_ar = st.text_input(
                        "Name (AR)", value=item.get("item_name_ar", ""),
                        key=f"wmi_name_ar_{item['id']}"
                    )
                    new_cat = st.selectbox(
                        "Category",
                        CATEGORIES,
                        index=CATEGORIES.index(item["category"])
                              if item.get("category") in CATEGORIES else 0,
                        key=f"wmi_cat_{item['id']}"
                    )
                with c2:
                    new_unit = st.selectbox(
                        "Unit", UNITS,
                        index=UNITS.index(item["unit"])
                              if item.get("unit") in UNITS else 0,
                        key=f"wmi_unit_{item['id']}"
                    )
                    new_region = st.selectbox(
                        "Region", REGIONS,
                        index=REGIONS.index(item["region"])
                              if item.get("region") in REGIONS else 3,
                        key=f"wmi_region_{item['id']}"
                    )
                    locked = st.checkbox(
                        "Lock cost (EK override — auto-sync will not change)",
                        value=item.get("ek_locked", False),
                        key=f"wmi_lock_{item['id']}"
                    )
                with c3:
                    cost_lb  = st.number_input("Cost Lebanon ($)",  min_value=0.0, step=0.01, value=float(item.get("latest_cost_lebanon")  or 0), key=f"wmi_lb_{item['id']}")
                    cost_du  = st.number_input("Cost Dubai ($)",    min_value=0.0, step=0.01, value=float(item.get("latest_cost_dubai")    or 0), key=f"wmi_du_{item['id']}")
                    cost_cm  = st.number_input("Cost Cameroon ($)", min_value=0.0, step=0.01, value=float(item.get("latest_cost_cameroon") or 0), key=f"wmi_cm_{item['id']}")
                    cost_gl  = st.number_input("Cost Global ($)",   min_value=0.0, step=0.01, value=float(item.get("latest_cost_global")   or 0), key=f"wmi_gl_{item['id']}")

                col_save, col_del = st.columns([3, 1])
                with col_save:
                    if st.button("Save changes", key=f"wmi_save_{item['id']}", use_container_width=True):
                        try:
                            supabase.table("worldwide_master_items").update({
                                "item_name":            new_name,
                                "item_name_ar":         new_name_ar,
                                "category":             new_cat,
                                "unit":                 new_unit,
                                "region":               new_region,
                                "ek_locked":            locked,
                                "latest_cost_lebanon":  cost_lb or None,
                                "latest_cost_dubai":    cost_du or None,
                                "latest_cost_cameroon": cost_cm or None,
                                "latest_cost_global":   cost_gl or None,
                            }).eq("id", item["id"]).execute()
                            st.success("Saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save failed: {e}")
                with col_del:
                    if st.button("Delete", key=f"wmi_del_{item['id']}", use_container_width=True):
                        try:
                            supabase.table("worldwide_master_items").delete().eq(
                                "id", item["id"]
                            ).execute()
                            st.success("Deleted.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Delete failed: {e}")

    # ── ADD NEW ITEM ─────────────────────────
    with tab_add:
        st.markdown("#### Add new ingredient to global registry")

        col1, col2 = st.columns(2)
        with col1:
            n_code    = st.text_input("Product code", placeholder="G-001")
            n_name    = st.text_input("Name (EN)", placeholder="Chicken breast")
            n_name_ar = st.text_input("Name (AR)", placeholder="صدر دجاج")
            n_cat     = st.selectbox("Category", CATEGORIES, key="add_cat")
        with col2:
            n_unit    = st.selectbox("Unit", UNITS, key="add_unit")
            n_region  = st.selectbox("Region", REGIONS, key="add_region")
            n_cost_lb = st.number_input("Cost Lebanon ($)",  min_value=0.0, step=0.01, key="add_lb")
            n_cost_du = st.number_input("Cost Dubai ($)",    min_value=0.0, step=0.01, key="add_du")
            n_cost_cm = st.number_input("Cost Cameroon ($)", min_value=0.0, step=0.01, key="add_cm")
            n_cost_gl = st.number_input("Cost Global ($)",   min_value=0.0, step=0.01, key="add_gl")

        if st.button("Add to global registry", type="primary",
                     disabled=not n_code.strip() or not n_name.strip()):
            try:
                supabase.table("worldwide_master_items").insert({
                    "product_code":         n_code.strip().upper(),
                    "item_name":            n_name.strip().title(),
                    "item_name_ar":         n_name_ar.strip(),
                    "category":             n_cat,
                    "unit":                 n_unit,
                    "region":               n_region,
                    "latest_cost_lebanon":  n_cost_lb or None,
                    "latest_cost_dubai":    n_cost_du or None,
                    "latest_cost_cameroon": n_cost_cm or None,
                    "latest_cost_global":   n_cost_gl or None,
                    "ek_locked":            False,
                    "last_synced_at":       None,
                    "last_synced_from":     None,
                    "created_at":           datetime.now(
                        zoneinfo.ZoneInfo("Asia/Beirut")
                    ).isoformat(),
                }).execute()
                st.success(f"Added: {n_name}")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

    # ── COST SYNC LOG ────────────────────────
    with tab_sync:
        st.markdown("#### Recent cost sync activity")
        st.caption("Items updated automatically from Auto Calc uploads.")
        try:
            res = supabase.table("worldwide_master_items").select(
                "item_name, region, latest_cost_lebanon, latest_cost_dubai, "
                "latest_cost_cameroon, last_synced_at, last_synced_from, ek_locked"
            ).not_.is_("last_synced_at", "null").order(
                "last_synced_at", desc=True
            ).limit(50).execute()
            rows = res.data or []
        except Exception as e:
            st.error(f"Failed: {e}")
            return

        if not rows:
            st.info("No sync activity yet.")
            return

        df = pd.DataFrame(rows)
        df["last_synced_at"] = pd.to_datetime(
            df["last_synced_at"]
        ).dt.tz_convert("Asia/Beirut").dt.strftime("%d %b %Y %H:%M")
        df["locked"] = df["ek_locked"].apply(lambda x: "🔒" if x else "")
        st.dataframe(
            df[["item_name", "region", "latest_cost_lebanon",
                "latest_cost_dubai", "latest_cost_cameroon",
                "last_synced_from", "last_synced_at", "locked"]],
            use_container_width=True,
            hide_index=True
        )

    # ── CLIENT ONBOARDING ────────────────────
    with tab_onboard:
        st.markdown("#### Seed a new client from global registry")
        st.caption("Copies all matching items into the client's master_items table.")

        try:
            clients_res = supabase.table("clients").select("client_name").order("client_name").execute()
            client_list = [r["client_name"] for r in (clients_res.data or [])]
        except Exception:
            client_list = []

        if not client_list:
            st.warning("No clients found in the clients table.")
            return

        col1, col2 = st.columns(2)
        with col1:
            target_client = st.selectbox("Select client", client_list, key="onboard_client")
        with col2:
            target_region = st.selectbox("Client region", REGIONS[:-1], key="onboard_region")

        # Show preview count
        preview = _fetch_global_items(supabase, target_region)
        st.info(f"{len(preview)} items will be copied for region: {target_region}")

        # Check if already seeded
        try:
            existing = supabase.table("master_items").select(
                "product_code", count="exact"
            ).eq("client_name", target_client).execute()
            existing_count = existing.count or 0
        except Exception:
            existing_count = 0

        if existing_count > 0:
            st.warning(
                f"This client already has {existing_count} items in master_items. "
                f"Proceeding will upsert — existing items won't be deleted."
            )

        if st.button(
            "Seed client master items", type="primary",
            disabled=not target_client
        ):
            with st.spinner("Copying..."):
                n = copy_to_client(supabase, target_client, target_region)
            if n > 0:
                st.success(f"Copied {n} items to {target_client}.")
            else:
                st.error("Nothing was copied. Check global registry has items for this region.")