# modules/recipes.py
import streamlit as st
import uuid
from datetime import datetime
import zoneinfo
from supabase import Client

# ─────────────────────────────────────────────
# FUZZY SEARCH
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

def _levenshtein(a: str, b: str) -> int:
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

def fuzzy_search_items(query: str, items: list, limit: int = 8) -> list:
    if not query.strip():
        return []
    q = query.strip().lower()
    corrected = TYPO_MAP.get(q, q)
    arabic = _is_arabic(query)
    scored = []
    for item in items:
        hay = item.get("item_name_ar", "").lower() if arabic else item.get("item_name", "").lower()
        score = 0
        if hay == corrected: score = 100
        elif corrected in hay or hay.startswith(corrected): score = 90
        else:
            for word in hay.split():
                if word == corrected: score = max(score, 80)
                elif len(word) > 2 and _levenshtein(word, corrected) <= 2: score = max(score, 65)
                elif corrected != q and len(word) > 2 and _levenshtein(word, q) <= 2: score = max(score, 55)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:limit]]


# ─────────────────────────────────────────────
# SUPABASE HELPERS
# ─────────────────────────────────────────────

def _get_master_items(supabase: Client, client_name: str) -> list:
    try:
        res = supabase.table("master_items").select(
            "product_code,item_name,item_name_ar,unit,is_production,cost_per_unit"
        ).eq("client_name", client_name).execute()
        return res.data or []
    except Exception:
        return []

def _get_recipes(supabase: Client, client_name: str) -> list:
    try:
        res = supabase.table("recipes").select("*").eq(
            "client_name", client_name
        ).order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []

def _get_recipe_lines(supabase: Client, recipe_id: str) -> list:
    try:
        res = supabase.table("recipe_lines").select("*").eq("recipe_id", recipe_id).execute()
        return res.data or []
    except Exception:
        return []

def _save_recipe(supabase: Client, recipe: dict, lines: list) -> "str | None":
    try:
        res = supabase.table("recipes").insert(recipe).execute()
        recipe_id = res.data[0]["id"]
        if lines:
            for line in lines:
                line["recipe_id"] = recipe_id
            supabase.table("recipe_lines").insert(lines).execute()
        return recipe_id
    except Exception as e:
        st.error(f"Error saving recipe: {e}")
        return None

def _upsert_master_item(supabase: Client, item: dict):
    try:
        supabase.table("master_items").upsert(
            item, on_conflict="client_name,product_code"
        ).execute()
    except Exception:
        pass

def _upload_recipe_photo(supabase: Client, recipe_id: str, file_bytes: bytes, mime: str) -> "str | None":
    try:
        ext = mime.split("/")[-1].replace("jpeg", "jpg")
        path = f"recipes/{recipe_id}.{ext}"
        supabase.storage.from_("recipe-photos").upload(
            path=path, file=file_bytes, file_options={"content-type": mime}
        )
        return supabase.storage.from_("recipe-photos").get_public_url(path)
    except Exception:
        return None


# ─────────────────────────────────────────────
# SUB-RECIPE DIALOG
# ─────────────────────────────────────────────

@st.dialog("Build sub-recipe", width="large")
def _sub_recipe_dialog(item: dict, master_items: list, client_name: str):
    st.markdown(f"**{item['item_name']}** is a production. Define its ingredients and batch size.")

    col1, col2 = st.columns(2)
    with col1:
        batch_qty = st.number_input("Batch qty", min_value=0.01, value=1.0, step=0.1, key="sub_batch_qty")
    with col2:
        batch_unit = st.selectbox("Unit", ["kg", "l", "portion", "batch", "pcs"], key="sub_batch_unit")

    st.markdown("**Ingredients of this production**")

    sub_key = f"sub_ings_{item['product_code']}"
    if sub_key not in st.session_state:
        st.session_state[sub_key] = []

    # Only raw materials inside a sub-recipe (no nested productions)
    raw_items = [i for i in master_items if not i.get("is_production", False)]

    sub_search = st.text_input(
        "Search ingredient",
        placeholder="Type to search...",
        key=f"sub_srch_{item['product_code']}"
    )
    if sub_search:
        suggestions = fuzzy_search_items(sub_search, raw_items, limit=5)
        for sug in suggestions:
            already = any(s["product_code"] == sug["product_code"] for s in st.session_state[sub_key])
            if not already:
                if st.button(f"+ {sug['item_name']}", key=f"subadd_{item['product_code']}_{sug['product_code']}"):
                    st.session_state[sub_key].append({
                        "product_code": sug["product_code"],
                        "item_name": sug["item_name"],
                        "unit": sug.get("unit", "kg"),
                        "cost_per_unit": sug.get("cost_per_unit", 0),
                        "qty": 0.0,
                    })
                    st.rerun()

    if st.session_state[sub_key]:
        st.divider()
        for idx, line in enumerate(st.session_state[sub_key]):
            c1, c2, c3 = st.columns([3, 1, 0.5])
            with c1:
                st.write(line["item_name"])
            with c2:
                qty = st.number_input(
                    line["unit"], min_value=0.0, step=0.1,
                    value=float(line["qty"]),
                    key=f"subqty_{item['product_code']}_{idx}",
                    label_visibility="collapsed"
                )
                st.session_state[sub_key][idx]["qty"] = qty
            with c3:
                if st.button("×", key=f"subdel_{item['product_code']}_{idx}"):
                    st.session_state[sub_key].pop(idx)
                    st.rerun()
        st.caption(f"Batch unit: {batch_unit}")
    else:
        st.caption("No ingredients added yet.")

    st.divider()
    col_cancel, col_confirm = st.columns(2)
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            if sub_key in st.session_state:
                del st.session_state[sub_key]
            st.rerun()
    with col_confirm:
        if st.button("Add to recipe", type="primary", use_container_width=True):
            if "pending_subs" not in st.session_state:
                st.session_state["pending_subs"] = {}
            st.session_state["pending_subs"][item["product_code"]] = {
                "batch_qty": batch_qty,
                "batch_unit": batch_unit,
                "lines": list(st.session_state[sub_key]),
            }
            if "bp_memory" not in st.session_state:
                st.session_state["bp_memory"] = {}
            st.session_state["bp_memory"][item["product_code"]] = "produce"
            if sub_key in st.session_state:
                del st.session_state[sub_key]
            st.rerun()


# ─────────────────────────────────────────────
# PHOTO DIALOG
# ─────────────────────────────────────────────

@st.dialog("Add a photo of this dish", width="small")
def _photo_dialog(supabase: Client, recipe_id: str, recipe_name: str):
    st.markdown(f"**{recipe_name}** has been saved!")
    st.caption("Photo appears as thumbnail in the library and prints on the PDF recipe card.")

    uploaded = st.file_uploader(
        "Take a photo or upload",
        type=["jpg", "jpeg", "png", "webp", "heic"],
        key="recipe_photo_upload"
    )
    if uploaded:
        st.image(uploaded, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Skip for now", use_container_width=True):
            st.session_state["recipe_photo_done"] = True
            st.rerun()
    with col2:
        if st.button("Save with photo", type="primary", use_container_width=True, disabled=not uploaded):
            if uploaded:
                url = _upload_recipe_photo(supabase, recipe_id, uploaded.getvalue(), uploaded.type)
                if url:
                    try:
                        supabase.table("recipes").update(
                            {"photo_url": url}
                        ).eq("id", recipe_id).execute()
                    except Exception as e:
                        st.warning(f"Photo upload failed: {e}")
            st.session_state["recipe_photo_done"] = True
            st.rerun()


# ─────────────────────────────────────────────
# RECIPE LIBRARY
# ─────────────────────────────────────────────

def _render_library(supabase: Client, client_name: str, show_cost: bool):
    recipes = _get_recipes(supabase, client_name)
    if not recipes:
        st.info("No recipes yet. Create your first recipe in the New Recipe tab.")
        return

    col_search, col_cat = st.columns([2, 1])
    with col_search:
        search = st.text_input(
            "Search recipes", placeholder="chicken, shrimp...",
            label_visibility="collapsed"
        )
    with col_cat:
        cat_filter = st.selectbox(
            "Category",
            ["All", "Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
            label_visibility="collapsed"
        )

    filtered = recipes
    if search:
        filtered = [r for r in filtered if search.lower() in r.get("name", "").lower()]
    if cat_filter != "All":
        filtered = [r for r in filtered if r.get("category") == cat_filter]

    if not filtered:
        st.warning("No recipes match your filter.")
        return

    cols = st.columns(3)
    for i, recipe in enumerate(filtered):
        with cols[i % 3]:
            with st.container(border=True):
                if recipe.get("photo_url"):
                    st.image(recipe["photo_url"], use_container_width=True)
                else:
                    st.markdown(
                        "<div style='height:70px;display:flex;align-items:center;"
                        "justify-content:center;border-radius:8px;font-size:24px;"
                        "background:var(--secondary-background-color)'>🍽</div>",
                        unsafe_allow_html=True
                    )
                st.markdown(f"**{recipe['name']}**")
                st.caption(
                    f"{recipe.get('category','—')} · "
                    f"{recipe.get('portions',1)} {recipe.get('yield_unit','plate')}"
                )
                # Cost visible only to admin/manager
                if show_cost and recipe.get("cost_per_portion") is not None:
                    st.caption(f"${recipe['cost_per_portion']:.2f}/portion")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("View", key=f"view_{recipe['id']}", use_container_width=True):
                        st.session_state["viewing_recipe"] = recipe["id"]
                        st.rerun()
                with c2:
                    if st.button("PDF", key=f"pdf_{recipe['id']}", use_container_width=True):
                        st.info("PDF export coming soon.")

    if st.session_state.get("viewing_recipe"):
        rid = st.session_state["viewing_recipe"]
        recipe = next((r for r in recipes if r["id"] == rid), None)
        if recipe:
            st.divider()
            st.markdown(f"### {recipe['name']}")
            caption = f"{recipe.get('category')} · {recipe.get('portions')} {recipe.get('yield_unit')}"
            if show_cost and recipe.get("cost_per_portion") is not None:
                caption += f" · ${recipe['cost_per_portion']:.2f}/portion"
            st.caption(caption)
            if recipe.get("photo_url"):
                st.image(recipe["photo_url"], width=300)
            lines = _get_recipe_lines(supabase, rid)
            if lines:
                st.markdown("**Ingredients**")
                for line in lines:
                    badge = "🏭" if line.get("is_production") else "🛒"
                    cost_str = ""
                    if show_cost and line.get("cost_per_unit"):
                        cost_str = f" · ${line['cost_per_unit']:.2f}/{line['unit']}"
                    st.write(f"{badge} {line['item_name']} — {line['qty']} {line['unit']}{cost_str}")
            if recipe.get("method"):
                st.markdown("**Method of preparation**")
                st.write(recipe["method"])
            if st.button("Close"):
                del st.session_state["viewing_recipe"]
                st.rerun()


# ─────────────────────────────────────────────
# WIZARD STATE
# ─────────────────────────────────────────────

def _init_wizard():
    defaults = {
        "recipe_step": 1,
        "recipe_name": "",
        "recipe_category": "Main",
        "recipe_portions": 1,
        "recipe_yield_unit": "Plate",
        "recipe_ingredients": [],
        "recipe_method": "",
        "bp_memory": {},
        "pending_subs": {},
        "recipe_saved_id": None,
        "recipe_photo_done": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset_wizard():
    for k in [
        "recipe_step", "recipe_name", "recipe_category", "recipe_portions",
        "recipe_yield_unit", "recipe_ingredients", "recipe_method",
        "pending_subs", "recipe_saved_id", "recipe_photo_done", "open_sub_dialog",
    ]:
        st.session_state.pop(k, None)
    _init_wizard()


# ─────────────────────────────────────────────
# NEW RECIPE WIZARD
# ─────────────────────────────────────────────

def _render_new_recipe(
    supabase: Client,
    client_name: str,
    outlet: str,
    user: str,
    show_cost: bool
):
    _init_wizard()

    # Photo dialog pending after save
    if st.session_state.get("recipe_saved_id") and not st.session_state.get("recipe_photo_done"):
        _photo_dialog(
            supabase,
            st.session_state["recipe_saved_id"],
            st.session_state.get("recipe_name", "Recipe")
        )
        return

    # Fully done
    if st.session_state.get("recipe_saved_id") and st.session_state.get("recipe_photo_done"):
        st.success(f"**{st.session_state['recipe_name']}** saved successfully!")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Create another recipe", use_container_width=True):
                _reset_wizard()
                st.rerun()
        with c2:
            if st.button("Go to library", type="primary", use_container_width=True):
                _reset_wizard()
                st.rerun()
        return

    step = st.session_state["recipe_step"]
    labels = ["Name & category", "Yield & ingredients", "Review & save"]
    st.progress(step / 3, text=f"Step {step} of 3 — {labels[step-1]}")
    st.markdown("---")

    # ── STEP 1: Name + Category ──────────────
    if step == 1:
        st.markdown("#### Recipe name & category")
        name = st.text_input(
            "Recipe name",
            value=st.session_state["recipe_name"],
            placeholder="e.g. Grilled chicken taouk",
        )
        st.session_state["recipe_name"] = name

        cat = st.radio(
            "Category",
            ["Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
            horizontal=True,
            index=["Starter", "Main", "Dessert", "Beverage", "Sub-recipe"].index(
                st.session_state["recipe_category"]
            ),
        )
        st.session_state["recipe_category"] = cat

        st.markdown("")
        if st.button("Next →", type="primary", disabled=not name.strip()):
            st.session_state["recipe_step"] = 2
            st.rerun()

    # ── STEP 2: Yield + Ingredients + Method ─
    elif step == 2:
        st.markdown("#### Yield & ingredients")

        col1, col2 = st.columns(2)
        with col1:
            portions = st.number_input(
                "Portions", min_value=1,
                value=st.session_state["recipe_portions"]
            )
            st.session_state["recipe_portions"] = portions
        with col2:
            yield_unit = st.selectbox(
                "Unit",
                ["Plate", "Portion", "Kg", "Litre", "Batch"],
                index=["Plate", "Portion", "Kg", "Litre", "Batch"].index(
                    st.session_state["recipe_yield_unit"]
                )
            )
            st.session_state["recipe_yield_unit"] = yield_unit

        st.divider()
        st.markdown("**Search & add ingredients**")

        # ── SINGLE UNIFIED SEARCH ─────────────────────────────────────────
        # Always uses worldwide_master_items via search_global_items().
        # Falls back to client's master_items if worldwide returns nothing.
        from modules.worldwide_master_items import search_global_items

        master_items = _get_master_items(supabase, client_name)
        is_bootstrap = len(master_items) == 0
        client_region = st.session_state.get("client_region", "Global")

        if is_bootstrap:
            st.info(
                "Bootstrap mode — no items in database yet for this client. "
                "Searching EK global ingredient registry."
            )
        else:
            st.caption(f"{len(master_items)} items in this client's ingredient database.")

        added_codes = [i["product_code"] for i in st.session_state["recipe_ingredients"]]

        search_query = st.text_input(
            "Search",
            placeholder="shrimp · taouk · chicken tender · جمبري · chrimp...",
            key="ing_search_q"
        )

        if search_query:
            # Unified search — worldwide first, fallback to local master_items
            results = search_global_items(
                query=search_query,
                supabase=supabase,
                region=client_region,
                limit=6,
                exclude_codes=added_codes,
            )

            # If worldwide returns nothing at all, fall back to local
            if not results and master_items:
                results = fuzzy_search_items(
                    search_query,
                    [i for i in master_items if i["product_code"] not in added_codes],
                    limit=6
                )

            if results:
                for item in results:
                    mem = st.session_state["bp_memory"].get(item["product_code"])
                    pre_prod = item.get("is_production", False)

                    c_name, c_toggle, c_add = st.columns([3, 2, 1])
                    with c_name:
                        is_known = mem is not None
                        label = f"**{item['item_name']}**" + (" ✓" if is_known else "")
                        st.markdown(label)
                        if item.get("item_name_ar"):
                            st.caption(item["item_name_ar"])
                        # Show cost only to authorised roles
                        if show_cost and item.get("cost_per_unit"):
                            st.caption(f"${item['cost_per_unit']:.2f}/{item.get('unit','kg')}")

                    with c_toggle:
                        # Existing client with flag set — no toggle needed
                        if pre_prod and not is_bootstrap:
                            st.caption("🏭 Production")
                            choice = "produce"
                        else:
                            default_idx = 1 if (mem == "produce" or pre_prod) else 0
                            choice = st.radio(
                                "type",
                                ["Buy", "Produce"],
                                index=default_idx,
                                horizontal=True,
                                key=f"tog_{item['product_code']}",
                                label_visibility="collapsed"
                            ).lower()
                            # Remember this choice forever for this client session
                            st.session_state["bp_memory"][item["product_code"]] = choice

                    with c_add:
                        if st.button("Add", key=f"add_{item['product_code']}"):
                            if choice == "produce":
                                # Fire sub-recipe dialog
                                st.session_state["open_sub_dialog"] = item
                                st.rerun()
                            else:
                                st.session_state["recipe_ingredients"].append({
                                    "product_code": item["product_code"],
                                    "item_name": item["item_name"],
                                    "unit": item.get("unit", "kg"),
                                    "cost_per_unit": item.get("cost_per_unit", 0),
                                    "qty": 0.0,
                                    "is_production": False,
                                    "sub_data": None,
                                })
                                # Bootstrap: upsert to client master_items
                                if is_bootstrap:
                                    _upsert_master_item(supabase, {
                                        "client_name": client_name,
                                        "product_code": item["product_code"],
                                        "item_name": item["item_name"],
                                        "item_name_ar": item.get("item_name_ar", ""),
                                        "unit": item.get("unit", "kg"),
                                        "is_production": False,
                                        "cost_per_unit": item.get("cost_per_unit", 0),
                                        "region": client_region,
                                        "source": "worldwide",
                                    })
                                st.rerun()
            else:
                st.caption("No match found — item will be flagged for EK to add to the global registry.")

        # Open sub-recipe dialog if triggered
        if st.session_state.get("open_sub_dialog"):
            item = st.session_state.pop("open_sub_dialog")
            # Pass local master_items for sub-ingredient search
            # If bootstrap, pass worldwide results as fallback pool
            sub_pool = master_items if master_items else []
            _sub_recipe_dialog(item, sub_pool, client_name)

        # Absorb confirmed sub-recipes from dialog
        for code, sub_data in list(st.session_state.get("pending_subs", {}).items()):
            if not any(i["product_code"] == code for i in st.session_state["recipe_ingredients"]):
                item_info = next(
                    (i for i in master_items if i["product_code"] == code), {}
                )
                st.session_state["recipe_ingredients"].append({
                    "product_code": code,
                    "item_name": item_info.get("item_name", code),
                    "unit": sub_data["batch_unit"],
                    "cost_per_unit": 0,
                    "qty": float(sub_data["batch_qty"]),
                    "is_production": True,
                    "sub_data": sub_data,
                })
                if is_bootstrap and item_info:
                    _upsert_master_item(supabase, {
                        "client_name": client_name,
                        "product_code": code,
                        "item_name": item_info.get("item_name", code),
                        "item_name_ar": item_info.get("item_name_ar", ""),
                        "unit": sub_data["batch_unit"],
                        "is_production": True,
                        "cost_per_unit": 0,
                        "region": client_region,
                        "source": "worldwide",
                    })
                del st.session_state["pending_subs"][code]
                st.rerun()

        # Ingredient list
        if st.session_state["recipe_ingredients"]:
            st.divider()
            st.markdown("**Added ingredients**")
            for idx, ing in enumerate(st.session_state["recipe_ingredients"]):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 0.5])
                with c1:
                    badge = "🏭" if ing["is_production"] else "🛒"
                    st.write(f"{badge} {ing['item_name']}")
                    if ing["is_production"] and ing.get("sub_data"):
                        sub = ing["sub_data"]
                        st.caption(
                            f"Batch: {sub['batch_qty']} {sub['batch_unit']} "
                            f"· {len(sub['lines'])} ingredient(s)"
                        )
                with c2:
                    qty = st.number_input(
                        "qty", min_value=0.0, step=0.1,
                        value=float(ing["qty"]),
                        key=f"qty_{idx}",
                        label_visibility="collapsed"
                    )
                    st.session_state["recipe_ingredients"][idx]["qty"] = qty
                with c3:
                    st.caption(ing["unit"])
                with c4:
                    if st.button("×", key=f"del_{idx}"):
                        st.session_state["recipe_ingredients"].pop(idx)
                        st.rerun()

        st.divider()
        with st.expander("Method of preparation (optional)"):
            method = st.text_area(
                "Method",
                value=st.session_state["recipe_method"],
                placeholder=(
                    "1. Marinate chicken for 2hrs\n"
                    "2. Grill 4 mins each side\n"
                    "3. Rest before plating"
                ),
                max_chars=500,
                height=150,
                label_visibility="collapsed",
            )
            st.session_state["recipe_method"] = method
            st.caption(f"{len(method)} / 500")

        st.markdown("")
        c_back, c_next = st.columns(2)
        with c_back:
            if st.button("← Back"):
                st.session_state["recipe_step"] = 1
                st.rerun()
        with c_next:
            if st.button(
                "Next →", type="primary",
                disabled=len(st.session_state["recipe_ingredients"]) == 0
            ):
                st.session_state["recipe_step"] = 3
                st.rerun()

    # ── STEP 3: Review ───────────────────────
    elif step == 3:
        st.markdown("#### Review & save")

        ings = st.session_state["recipe_ingredients"]
        portions = st.session_state["recipe_portions"]
        total_cost = sum(
            i["cost_per_unit"] * i["qty"]
            for i in ings if not i["is_production"]
        )
        cpp = round(total_cost / portions, 2) if portions > 0 else 0.0

        c1, c2, c3 = st.columns(3)
        c1.metric("Portions", f"{portions} {st.session_state['recipe_yield_unit']}")
        c2.metric("Ingredients", len(ings))
        # Cost metric only for authorised roles
        if show_cost:
            c3.metric("Cost / portion", f"${cpp:.2f}")

        st.divider()
        st.markdown(f"**{st.session_state['recipe_name']}** — {st.session_state['recipe_category']}")
        for ing in ings:
            badge = "🏭" if ing["is_production"] else "🛒"
            st.write(f"{badge} {ing['item_name']} · {ing['qty']} {ing['unit']}")

        method = st.session_state["recipe_method"]
        if method:
            st.divider()
            st.markdown("**Method of preparation**")
            st.write(method)

        st.markdown("")
        c_back, c_save = st.columns(2)
        with c_back:
            if st.button("← Back"):
                st.session_state["recipe_step"] = 2
                st.rerun()
        with c_save:
            if st.button("Save recipe", type="primary", use_container_width=True):
                recipe_id = str(uuid.uuid4())
                now = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).isoformat()
                recipe_record = {
                    "id": recipe_id,
                    "client_name": client_name,
                    "outlet": outlet,
                    "name": st.session_state["recipe_name"],
                    "category": st.session_state["recipe_category"],
                    "portions": portions,
                    "yield_unit": st.session_state["recipe_yield_unit"],
                    "method": method or None,
                    "cost_per_portion": cpp,
                    "created_by": user,
                    "created_at": now,
                    "photo_url": None,
                }
                lines = [{
                    "id": str(uuid.uuid4()),
                    "recipe_id": recipe_id,
                    "product_code": ing["product_code"],
                    "item_name": ing["item_name"],
                    "qty": ing["qty"],
                    "unit": ing["unit"],
                    "cost_per_unit": ing["cost_per_unit"],
                    "is_production": ing["is_production"],
                    "sub_recipe_data": str(ing["sub_data"]) if ing.get("sub_data") else None,
                } for ing in ings]

                saved_id = _save_recipe(supabase, recipe_record, lines)
                if saved_id:
                    st.session_state["recipe_saved_id"] = saved_id
                    st.rerun()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def render_recipes(supabase: Client, user: str, role: str):
    client_name = st.session_state.get("client_name", "Unknown")
    outlet = st.session_state.get("assigned_outlet", "Unknown")

    # Role-based cost visibility
    show_cost = str(role).lower() in ["admin", "admin_all", "manager", "viewer"]

    st.markdown("### Recipes")
    tab_lib, tab_new = st.tabs(["Recipe library", "New recipe"])

    with tab_lib:
        _render_library(supabase, client_name, show_cost)

    with tab_new:
        _render_new_recipe(supabase, client_name, outlet, user, show_cost)