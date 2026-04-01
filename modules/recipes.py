# modules/recipes.py
import streamlit as st
import uuid
from datetime import datetime
import zoneinfo
from supabase import Client
from modules.worldwide_master_items import search_global_items

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

def fuzzy_search_items(query: str, items: list, limit: int = 5) -> list:
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
        if hay == corrected: score = 100
        elif corrected in hay or hay.startswith(corrected): score = 90
        else:
            for word in hay.split():
                if word == corrected: score = max(score, 80)
                elif len(word) > 2 and _levenshtein(word, corrected) <= 2:
                    score = max(score, 65)
                elif corrected != q and len(word) > 2 and _levenshtein(word, q) <= 2:
                    score = max(score, 55)
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
        res = supabase.table("recipe_lines").select("*").eq(
            "recipe_id", recipe_id
        ).execute()
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

def _upload_recipe_photo(
    supabase: Client, recipe_id: str, file_bytes: bytes, mime: str
) -> "str | None":
    try:
        ext = mime.split("/")[-1].replace("jpeg", "jpg")
        path = f"recipes/{recipe_id}.{ext}"
        supabase.storage.from_("recipe-photos").upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": mime}
        )
        return supabase.storage.from_("recipe-photos").get_public_url(path)
    except Exception:
        return None


# ─────────────────────────────────────────────
# SUB-RECIPE DIALOG
# ─────────────────────────────────────────────

@st.dialog("Build sub-recipe", width="large")
def _sub_recipe_dialog(item: dict, supabase: Client, client_name: str):
    st.markdown(f"**{item['item_name']}** is a production.")
    st.caption("Add its raw ingredients and set the batch size it produces.")

    col1, col2 = st.columns(2)
    with col1:
        batch_qty = st.number_input(
            "Batch qty", min_value=0.01, value=1.0, step=0.1,
            key="sub_batch_qty"
        )
    with col2:
        batch_unit = st.selectbox(
            "Unit", ["kg", "l", "portion", "batch", "pcs"],
            key="sub_batch_unit"
        )

    st.markdown("---")

    sub_key = f"sub_ings_{item['product_code']}"
    if sub_key not in st.session_state:
        st.session_state[sub_key] = []

    client_region = st.session_state.get("client_region", "Global")

    sub_search = st.text_input(
        "Search ingredient",
        placeholder="salt · olive oil · garlic · ثوم...",
        key=f"sub_srch_{item['product_code']}"
    )

    if sub_search:
        already_codes = [s["product_code"] for s in st.session_state[sub_key]]
        suggestions = search_global_items(
            query=sub_search,
            supabase=supabase,
            region=client_region,
            limit=5,
            exclude_codes=already_codes,
        )
        # Only raw materials inside a sub-recipe
        suggestions = [s for s in suggestions if not s.get("is_production", False)]

        if suggestions:
            for sug in suggestions:
                c1, c2 = st.columns([4, 1])
                with c1:
                    ar = f" · {sug['item_name_ar']}" if sug.get("item_name_ar") else ""
                    st.write(f"{sug['item_name']}{ar}")
                with c2:
                    if st.button(
                        "Add",
                        key=f"subadd_{item['product_code']}_{sug['product_code']}",
                        use_container_width=True
                    ):
                        st.session_state[sub_key].append({
                            "product_code": sug["product_code"],
                            "item_name": sug["item_name"],
                            "unit": sug.get("unit", "kg"),
                            "cost_per_unit": sug.get("cost_per_unit", 0),
                            "qty": 0.0,
                        })
                        st.rerun()
        else:
            st.caption("No results.")

    if st.session_state[sub_key]:
        st.markdown("---")
        for idx, line in enumerate(st.session_state[sub_key]):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 0.4])
            with c1:
                st.write(line["item_name"])
            with c2:
                qty = st.number_input(
                    "qty", min_value=0.0, step=0.1,
                    value=float(line["qty"]),
                    key=f"subqty_{item['product_code']}_{idx}",
                    label_visibility="collapsed"
                )
                st.session_state[sub_key][idx]["qty"] = qty
            with c3:
                st.caption(line["unit"])
            with c4:
                if st.button("×", key=f"subdel_{item['product_code']}_{idx}"):
                    st.session_state[sub_key].pop(idx)
                    st.rerun()
        st.caption(f"This production yields: {batch_qty} {batch_unit}")
    else:
        st.caption("No ingredients added yet.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop(sub_key, None)
            st.rerun()
    with c2:
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
            st.session_state.pop(sub_key, None)
            st.rerun()


# ─────────────────────────────────────────────
# PHOTO DIALOG
# ─────────────────────────────────────────────

@st.dialog("Add a photo of this dish", width="small")
def _photo_dialog(supabase: Client, recipe_id: str, recipe_name: str):
    st.markdown(f"**{recipe_name}** has been saved!")
    st.caption(
        "Photo appears as the recipe thumbnail "
        "and prints on the PDF recipe card."
    )
    uploaded = st.file_uploader(
        "Take a photo or upload",
        type=["jpg", "jpeg", "png", "webp", "heic"],
        key="recipe_photo_upload"
    )
    if uploaded:
        st.image(uploaded, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Skip for now", use_container_width=True):
            st.session_state["recipe_photo_done"] = True
            st.rerun()
    with c2:
        if st.button(
            "Save with photo", type="primary",
            use_container_width=True, disabled=not uploaded
        ):
            if uploaded:
                url = _upload_recipe_photo(
                    supabase, recipe_id,
                    uploaded.getvalue(), uploaded.type
                )
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
        st.info("No recipes yet. Go to New Recipe to create your first one.")
        return

    col_search, col_cat = st.columns([2, 1])
    with col_search:
        search = st.text_input(
            "Search", placeholder="chicken, shrimp...",
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
                        "<div style='height:60px;display:flex;align-items:center;"
                        "justify-content:center;border-radius:8px;font-size:22px;"
                        "background:var(--secondary-background-color)'>🍽</div>",
                        unsafe_allow_html=True
                    )
                st.markdown(f"**{recipe['name']}**")
                st.caption(
                    f"{recipe.get('category','—')} · "
                    f"{recipe.get('portions',1)} {recipe.get('yield_unit','plate')}"
                )
                if show_cost and recipe.get("cost_per_portion") is not None:
                    st.caption(f"${recipe['cost_per_portion']:.2f} / portion")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button(
                        "View", key=f"view_{recipe['id']}",
                        use_container_width=True
                    ):
                        st.session_state["viewing_recipe"] = recipe["id"]
                        st.rerun()
                with c2:
                    if st.button(
                        "PDF", key=f"pdf_{recipe['id']}",
                        use_container_width=True
                    ):
                        st.info("PDF export coming soon.")

    if st.session_state.get("viewing_recipe"):
        rid = st.session_state["viewing_recipe"]
        recipe = next((r for r in recipes if r["id"] == rid), None)
        if recipe:
            st.divider()
            st.markdown(f"### {recipe['name']}")
            caption = (
                f"{recipe.get('category')} · "
                f"{recipe.get('portions')} {recipe.get('yield_unit')}"
            )
            if show_cost and recipe.get("cost_per_portion") is not None:
                caption += f" · ${recipe['cost_per_portion']:.2f}/portion"
            st.caption(caption)
            if recipe.get("photo_url"):
                st.image(recipe["photo_url"], width=280)
            lines = _get_recipe_lines(supabase, rid)
            if lines:
                st.markdown("**Ingredients**")
                for line in lines:
                    badge = "🏭" if line.get("is_production") else "🛒"
                    cost_str = ""
                    if show_cost and line.get("cost_per_unit"):
                        cost_str = f" · ${line['cost_per_unit']:.2f}/{line['unit']}"
                    st.write(
                        f"{badge} {line['item_name']} — "
                        f"{line['qty']} {line['unit']}{cost_str}"
                    )
            if recipe.get("method"):
                st.markdown("**Method of preparation**")
                st.write(recipe["method"])
            if st.button("← Close"):
                del st.session_state["viewing_recipe"]
                st.rerun()


# ─────────────────────────────────────────────
# WIZARD STATE
# ─────────────────────────────────────────────

def _init_wizard():
    defaults = {
        "recipe_step":       1,
        "recipe_category":   "Main",
        "recipe_portions":   1,
        "recipe_yield_unit": "Plate",
        "recipe_ingredients":[],
        "recipe_method":     "",
        "bp_memory":         {},
        "pending_subs":      {},
        "recipe_saved_id":   None,
        "recipe_photo_done": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset_wizard():
    for k in [
        "recipe_step", "recipe_name", "recipe_category",
        "recipe_portions", "recipe_yield_unit", "recipe_ingredients",
        "recipe_method", "pending_subs", "recipe_saved_id",
        "recipe_photo_done", "open_sub_dialog",
    ]:
        st.session_state.pop(k, None)
    _init_wizard()


# ─────────────────────────────────────────────
# STEP INDICATOR
# ─────────────────────────────────────────────

def _step_indicator(step: int):
    labels = ["1 · Name", "2 · Ingredients", "3 · Review"]
    c1, c2, c3 = st.columns(3)
    for col, i, label in zip([c1, c2, c3], [1, 2, 3], labels):
        with col:
            if i < step:
                st.success(label)
            elif i == step:
                st.info(label)
            else:
                st.caption(label)


# ─────────────────────────────────────────────
# NEW RECIPE WIZARD
# ─────────────────────────────────────────────

def _render_new_recipe(
    supabase: Client,
    client_name: str,
    outlet: str,
    user: str,
    show_cost: bool,
):
    _init_wizard()

    # Photo dialog after save
    if (
        st.session_state.get("recipe_saved_id")
        and not st.session_state.get("recipe_photo_done")
    ):
        _photo_dialog(
            supabase,
            st.session_state["recipe_saved_id"],
            st.session_state.get("recipe_name", "Recipe"),
        )
        return

    # Success screen
    if (
        st.session_state.get("recipe_saved_id")
        and st.session_state.get("recipe_photo_done")
    ):
        st.success(f"**{st.session_state.get('recipe_name','')}** saved!")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Create another", use_container_width=True):
                _reset_wizard()
                st.rerun()
        with c2:
            if st.button("Go to library", type="primary", use_container_width=True):
                _reset_wizard()
                st.rerun()
        return

    step = st.session_state["recipe_step"]
    _step_indicator(step)
    st.markdown("---")

    # ── STEP 1 ───────────────────────────────────────────────────────────
    if step == 1:
        # Use key= only — NO st.session_state write on every keystroke
        # Value is read only when Next is clicked
        st.text_input(
            "Recipe name",
            placeholder="e.g. Grilled chicken taouk",
            key="recipe_name",
        )

        st.radio(
            "Category",
            ["Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
            horizontal=True,
            key="recipe_category",
        )

        st.markdown("")
        if st.button(
            "Next →", type="primary", use_container_width=True,
            disabled=not st.session_state.get("recipe_name", "").strip()
        ):
            st.session_state["recipe_step"] = 2
            st.rerun()

    # ── STEP 2 ───────────────────────────────────────────────────────────
    elif step == 2:

        # Yield — compact, 2 columns, no heading
        c1, c2 = st.columns(2)
        with c1:
            st.number_input(
                "Portions", min_value=1,
                key="recipe_portions"
            )
        with c2:
            st.selectbox(
                "Unit",
                ["Plate", "Portion", "Kg", "Litre", "Batch"],
                key="recipe_yield_unit"
            )

        st.markdown("---")

        # Search — full width, dominant, no section heading
        master_items = _get_master_items(supabase, client_name)
        client_region = st.session_state.get("client_region", "Global")
        added_codes = [
            i["product_code"]
            for i in st.session_state["recipe_ingredients"]
        ]

        search_query = st.text_input(
            "Search ingredient",
            placeholder="shrimp · taouk · chicken tender · جمبري · chrimp...",
            key="ing_search_q",
            label_visibility="collapsed",
        )

        if search_query:
            results = search_global_items(
                query=search_query,
                supabase=supabase,
                region=client_region,
                limit=5,
                exclude_codes=added_codes,
            )
            if not results and master_items:
                results = fuzzy_search_items(
                    search_query,
                    [i for i in master_items if i["product_code"] not in added_codes],
                    limit=5,
                )

            if results:
                for item in results:
                    mem = st.session_state["bp_memory"].get(item["product_code"])
                    pre_prod = item.get("is_production", False)

                    with st.container(border=True):
                        c_name, c_toggle, c_add = st.columns([3, 2, 1])
                        with c_name:
                            known = " ✓" if mem is not None else ""
                            st.markdown(f"**{item['item_name']}**{known}")
                            if item.get("item_name_ar"):
                                st.caption(item["item_name_ar"])
                            if show_cost and item.get("cost_per_unit"):
                                st.caption(
                                    f"${item['cost_per_unit']:.2f}"
                                    f" / {item.get('unit','kg')}"
                                )
                        with c_toggle:
                            if pre_prod and master_items:
                                st.caption("🏭 Production")
                                choice = "produce"
                            else:
                                default_idx = 1 if (
                                    mem == "produce" or pre_prod
                                ) else 0
                                choice = st.radio(
                                    "type",
                                    ["Buy", "Produce"],
                                    index=default_idx,
                                    horizontal=True,
                                    key=f"tog_{item['product_code']}",
                                    label_visibility="collapsed",
                                ).lower()
                                st.session_state["bp_memory"][
                                    item["product_code"]
                                ] = choice
                        with c_add:
                            if st.button(
                                "Add",
                                key=f"add_{item['product_code']}",
                                use_container_width=True
                            ):
                                if choice == "produce":
                                    st.session_state["open_sub_dialog"] = item
                                    st.rerun()
                                else:
                                    st.session_state["recipe_ingredients"].append({
                                        "product_code": item["product_code"],
                                        "item_name":    item["item_name"],
                                        "unit":         item.get("unit", "kg"),
                                        "cost_per_unit":item.get("cost_per_unit", 0),
                                        "qty":          0.0,
                                        "is_production":False,
                                        "sub_data":     None,
                                    })
                                    if not master_items:
                                        _upsert_master_item(supabase, {
                                            "client_name":  client_name,
                                            "product_code": item["product_code"],
                                            "item_name":    item["item_name"],
                                            "item_name_ar": item.get("item_name_ar",""),
                                            "unit":         item.get("unit","kg"),
                                            "is_production":False,
                                            "cost_per_unit":item.get("cost_per_unit",0),
                                            "region":       client_region,
                                            "source":       "worldwide",
                                        })
                                    st.rerun()
            else:
                st.caption("No match — will be flagged for EK to add.")

        # Sub-recipe dialog trigger
        if st.session_state.get("open_sub_dialog"):
            item = st.session_state.pop("open_sub_dialog")
            _sub_recipe_dialog(item, supabase, client_name)

        # Absorb confirmed sub-recipes
        for code, sub_data in list(
            st.session_state.get("pending_subs", {}).items()
        ):
            already = any(
                i["product_code"] == code
                for i in st.session_state["recipe_ingredients"]
            )
            if not already:
                item_info = next(
                    (i for i in master_items if i["product_code"] == code), {}
                )
                st.session_state["recipe_ingredients"].append({
                    "product_code": code,
                    "item_name":    item_info.get("item_name", code),
                    "unit":         sub_data["batch_unit"],
                    "cost_per_unit":0,
                    "qty":          float(sub_data["batch_qty"]),
                    "is_production":True,
                    "sub_data":     sub_data,
                })
                if not master_items and item_info:
                    _upsert_master_item(supabase, {
                        "client_name":  client_name,
                        "product_code": code,
                        "item_name":    item_info.get("item_name", code),
                        "item_name_ar": item_info.get("item_name_ar",""),
                        "unit":         sub_data["batch_unit"],
                        "is_production":True,
                        "cost_per_unit":0,
                        "region":       client_region,
                        "source":       "worldwide",
                    })
                del st.session_state["pending_subs"][code]
                st.rerun()

        # Added ingredients — compact list
        if st.session_state["recipe_ingredients"]:
            st.markdown("---")
            for idx, ing in enumerate(st.session_state["recipe_ingredients"]):
                c1, c2, c3, c4 = st.columns([3, 1, 1, 0.4])
                with c1:
                    badge = "🏭" if ing["is_production"] else "🛒"
                    st.write(f"{badge} {ing['item_name']}")
                    if ing["is_production"] and ing.get("sub_data"):
                        sub = ing["sub_data"]
                        st.caption(
                            f"{sub['batch_qty']} {sub['batch_unit']} · "
                            f"{len(sub['lines'])} ingredient(s)"
                        )
                with c2:
                    qty = st.number_input(
                        "qty", min_value=0.0, step=0.1,
                        value=float(ing["qty"]),
                        key=f"qty_{idx}",
                        label_visibility="collapsed",
                    )
                    st.session_state["recipe_ingredients"][idx]["qty"] = qty
                with c3:
                    st.caption(ing["unit"])
                with c4:
                    if st.button("×", key=f"del_{idx}"):
                        st.session_state["recipe_ingredients"].pop(idx)
                        st.rerun()

        # Method — collapsed by default, totally out of the way
        with st.expander("Method of preparation (optional)"):
            st.text_area(
                "Method",
                placeholder=(
                    "1. Marinate chicken for 2hrs\n"
                    "2. Grill 4 mins each side\n"
                    "3. Rest 2 mins before plating"
                ),
                max_chars=500,
                height=130,
                key="recipe_method",
                label_visibility="collapsed",
            )
            st.caption(
                f"{len(st.session_state.get('recipe_method',''))} / 500"
            )

        # Back / Next — always side by side
        st.markdown("")
        c_back, c_next = st.columns(2)
        with c_back:
            if st.button("← Back", use_container_width=True):
                st.session_state["recipe_step"] = 1
                st.rerun()
        with c_next:
            if st.button(
                "Next →", type="primary", use_container_width=True,
                disabled=len(st.session_state["recipe_ingredients"]) == 0,
            ):
                st.session_state["recipe_step"] = 3
                st.rerun()

    # ── STEP 3 ───────────────────────────────────────────────────────────
    elif step == 3:
        ings     = st.session_state["recipe_ingredients"]
        portions = st.session_state.get("recipe_portions", 1)
        name     = st.session_state.get("recipe_name", "")
        category = st.session_state.get("recipe_category", "")
        method   = st.session_state.get("recipe_method", "")

        total_cost = sum(
            i["cost_per_unit"] * i["qty"]
            for i in ings if not i["is_production"]
        )
        cpp = round(total_cost / portions, 2) if portions > 0 else 0.0

        # Summary row
        c1, c2, c3 = st.columns(3)
        c1.metric("Recipe", name)
        c2.metric("Yield", f"{portions} {st.session_state.get('recipe_yield_unit','plate')}")
        if show_cost:
            c3.metric("Cost / portion", f"${cpp:.2f}")
        else:
            c3.metric("Ingredients", len(ings))

        st.markdown("---")
        st.caption(category)

        for ing in ings:
            badge = "🏭" if ing["is_production"] else "🛒"
            line  = f"{badge} {ing['item_name']} · {ing['qty']} {ing['unit']}"
            if show_cost and ing.get("cost_per_unit") and not ing["is_production"]:
                line += f"  —  ${ing['cost_per_unit'] * ing['qty']:.2f}"
            st.write(line)

        if method:
            st.markdown("---")
            st.markdown("**Method of preparation**")
            st.write(method)

        # Back / Save — side by side
        st.markdown("")
        c_back, c_save = st.columns(2)
        with c_back:
            if st.button("← Back", use_container_width=True):
                st.session_state["recipe_step"] = 2
                st.rerun()
        with c_save:
            if st.button(
                "Save recipe", type="primary", use_container_width=True
            ):
                recipe_id = str(uuid.uuid4())
                now = datetime.now(
                    zoneinfo.ZoneInfo("Asia/Beirut")
                ).isoformat()

                recipe_record = {
                    "id":               recipe_id,
                    "client_name":      client_name,
                    "outlet":           outlet,
                    "name":             name,
                    "category":         category,
                    "portions":         portions,
                    "yield_unit":       st.session_state.get("recipe_yield_unit","Plate"),
                    "method":           method or None,
                    "cost_per_portion": cpp,
                    "created_by":       user,
                    "created_at":       now,
                    "photo_url":        None,
                }

                lines = [
                    {
                        "id":              str(uuid.uuid4()),
                        "recipe_id":       recipe_id,
                        "product_code":    ing["product_code"],
                        "item_name":       ing["item_name"],
                        "qty":             ing["qty"],
                        "unit":            ing["unit"],
                        "cost_per_unit":   ing["cost_per_unit"],
                        "is_production":   ing["is_production"],
                        "sub_recipe_data": (
                            str(ing["sub_data"])
                            if ing.get("sub_data") else None
                        ),
                    }
                    for ing in ings
                ]

                saved_id = _save_recipe(supabase, recipe_record, lines)
                if saved_id:
                    st.session_state["recipe_saved_id"] = saved_id
                    st.rerun()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

def render_recipes(supabase: Client, user: str, role: str):
    client_name = st.session_state.get("client_name", "Unknown")
    outlet      = st.session_state.get("assigned_outlet", "Unknown")
    show_cost   = str(role).lower() in [
        "admin", "admin_all", "manager", "viewer"
    ]

    st.markdown("### Recipes")
    tab_lib, tab_new = st.tabs(["Recipe library", "New recipe"])

    with tab_lib:
        _render_library(supabase, client_name, show_cost)

    with tab_new:
        _render_new_recipe(supabase, client_name, outlet, user, show_cost)