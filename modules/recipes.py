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

def _delete_recipe(supabase: Client, recipe_id: str) -> bool:
    try:
        supabase.table("recipe_lines").delete().eq("recipe_id", recipe_id).execute()
        supabase.table("recipes").delete().eq("id", recipe_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting recipe: {e}")
        return False

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
            file_options={"content-type": mime, "upsert": "true"}
        )
        return supabase.storage.from_("recipe-photos").get_public_url(path)
    except Exception as e:
        st.warning(f"Photo upload error: {e}")
        return None

def _generate_recipe_pdf(recipe: dict, lines: list) -> "bytes | None":
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable
        )
        from reportlab.lib.enums import TA_CENTER
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )

        EK_DARK  = colors.HexColor("#1B252C")
        EK_SAND  = colors.HexColor("#E3C5AD")
        EK_LIGHT = colors.HexColor("#F5F0EB")

        style_title = ParagraphStyle(
            "title", fontSize=22, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceAfter=4
        )
        style_sub = ParagraphStyle(
            "sub", fontSize=11,
            textColor=colors.HexColor("#5F5E5A"),
            fontName="Helvetica", spaceAfter=2
        )
        style_section = ParagraphStyle(
            "section", fontSize=10, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6
        )
        style_body = ParagraphStyle(
            "body", fontSize=10, textColor=EK_DARK,
            fontName="Helvetica", leading=16
        )
        style_footer = ParagraphStyle(
            "footer", fontSize=8,
            textColor=colors.HexColor("#888780"),
            fontName="Helvetica", alignment=TA_CENTER
        )

        story = []

        story.append(Paragraph(recipe.get("name", "Recipe"), style_title))
        story.append(Paragraph(
            f"{recipe.get('category', '')}  ·  "
            f"{recipe.get('portions', 1)} {recipe.get('yield_unit', 'plate')}",
            style_sub
        ))
        story.append(HRFlowable(
            width="100%", thickness=1,
            color=EK_SAND, spaceAfter=10
        ))

        story.append(Paragraph("Ingredients", style_section))
        if lines:
            table_data = [["Item", "Qty", "Unit", "Type"]]
            for line in lines:
                t = "Production" if line.get("is_production") else "Raw material"
                table_data.append([
                    line.get("item_name", ""),
                    str(line.get("qty", "")),
                    line.get("unit", ""),
                    t,
                ])
            tbl = Table(
                table_data,
                colWidths=[8*cm, 2.5*cm, 2.5*cm, 4*cm]
            )
            tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), EK_DARK),
                ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, EK_LIGHT]),
                ("GRID",          (0, 0), (-1, -1), 0.3,
                                  colors.HexColor("#D3D1C7")),
                ("LEFTPADDING",   (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(tbl)

        method = recipe.get("method", "")
        if method:
            story.append(Spacer(1, 0.3*cm))
            story.append(HRFlowable(
                width="100%", thickness=0.5, color=EK_SAND
            ))
            story.append(Paragraph("Method of preparation", style_section))
            for line in method.split("\n"):
                if line.strip():
                    story.append(Paragraph(line.strip(), style_body))

        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(
            width="100%", thickness=1, color=EK_SAND
        ))
        story.append(Paragraph(
            f"EK Consulting  ·  ek-consulting.co  ·  "
            f"Generated {datetime.now().strftime('%d %b %Y')}",
            style_footer
        ))

        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    except ImportError:
        st.error("reportlab not installed. Add it to requirements.txt.")
        return None
    except Exception as e:
        st.error(f"PDF generation error: {e}")
        return None


# ─────────────────────────────────────────────
# SUB-RECIPE DIALOG
# ─────────────────────────────────────────────

@st.dialog("Build sub-recipe", width="large")
def _sub_recipe_dialog(item: dict, supabase: Client, client_name: str):
    st.markdown(f"**{item['item_name']}** — production")
    st.caption("Add raw ingredients and set the batch size this production yields.")

    col1, col2 = st.columns(2)
    with col1:
        _pre_qty = st.session_state.get(
            f"prod_qty_{item['product_code']}", 1.0
        )
        batch_qty = st.number_input(
            "Batch qty", min_value=0.01,
            value=float(_pre_qty) if float(_pre_qty) > 0 else 1.0,
            step=0.1, key="sub_batch_qty"
        )
    with col2:
        _pre_unit = st.session_state.get(
            f"prod_unit_{item['product_code']}", "kg"
        )
        _unit_opts = ["kg", "l", "portion", "batch", "pcs"]
        _unit_idx = (
            _unit_opts.index(_pre_unit)
            if _pre_unit in _unit_opts else 0
        )
        batch_unit = st.selectbox(
            "Unit", _unit_opts, index=_unit_idx,
            key="sub_batch_unit"
        )

    st.markdown("---")

    sub_key = f"sub_ings_{item['product_code']}"
    if sub_key not in st.session_state:
        st.session_state[sub_key] = []

    client_region = st.session_state.get("client_region", "Global")

    sub_search = st.text_input(
        "Search ingredient",
        placeholder="salt · garlic · olive oil...",
        key=f"sub_srch_{item['product_code']}"
    )

    if sub_search:
        already_codes = [
            s["product_code"] for s in st.session_state[sub_key]
        ]
        suggestions = search_global_items(
            query=sub_search,
            supabase=supabase,
            region=client_region,
            limit=5,
            exclude_codes=already_codes,
        )
        suggestions = [
            s for s in suggestions
            if not s.get("is_production", False)
        ]
        if suggestions:
            for sug in suggestions:
                c1, c2 = st.columns([4, 1])
                with c1:
                    ar = (
                        f" · {sug['item_name_ar']}"
                        if sug.get("item_name_ar") else ""
                    )
                    st.write(f"{sug['item_name']}{ar}")
                with c2:
                    if st.button(
                        "Add",
                        key=f"subadd_{item['product_code']}_{sug['product_code']}",
                        use_container_width=True
                    ):
                        st.session_state[sub_key].append({
                            "product_code": sug["product_code"],
                            "item_name":    sug["item_name"],
                            "unit":         sug.get("unit", "kg"),
                            "cost_per_unit":sug.get("cost_per_unit", 0),
                            "qty":          0.0,
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
                if st.button(
                    "×", key=f"subdel_{item['product_code']}_{idx}"
                ):
                    st.session_state[sub_key].pop(idx)
                    st.rerun()
        st.caption(f"Yields: {batch_qty} {batch_unit}")
    else:
        st.caption("No ingredients yet.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop(sub_key, None)
            st.rerun()
    with c2:
        if st.button(
            "Add to recipe", type="primary", use_container_width=True
        ):
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
    st.markdown(f"**{recipe_name}** saved!")
    st.caption(
        "Photo appears as thumbnail in the library "
        "and prints on the PDF card."
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
            st.session_state["saved_recipe_id"]   = None
            st.session_state["show_photo_dialog"] = False
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
                        st.warning(f"Photo update failed: {e}")
            st.session_state["saved_recipe_id"]   = None
            st.session_state["show_photo_dialog"] = False
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
            "Search", placeholder="Search recipes...",
            label_visibility="collapsed", key="lib_search"
        )
    with col_cat:
        cat_filter = st.selectbox(
            "Category",
            ["All", "Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
            label_visibility="collapsed", key="lib_cat"
        )

    filtered = recipes
    if search:
        filtered = [
            r for r in filtered
            if search.lower() in r.get("name", "").lower()
        ]
    if cat_filter != "All":
        filtered = [
            r for r in filtered
            if r.get("category") == cat_filter
        ]

    if not filtered:
        st.warning("No recipes match your filter.")
        return

    if "confirm_delete" not in st.session_state:
        st.session_state["confirm_delete"] = None

    cols = st.columns(3)
    for i, recipe in enumerate(filtered):
        with cols[i % 3]:
            with st.container(border=True):
                photo_url = recipe.get("photo_url", "")
                if photo_url:
                    st.image(photo_url, use_container_width=True)
                else:
                    st.markdown(
                        "<div style='height:60px;display:flex;"
                        "align-items:center;justify-content:center;"
                        "border-radius:8px;font-size:22px;"
                        "background:var(--secondary-background-color)'>"
                        "🍽</div>",
                        unsafe_allow_html=True
                    )

                st.markdown(f"**{recipe['name']}**")
                st.caption(
                    f"{recipe.get('category','—')} · "
                    f"{recipe.get('portions',1)} "
                    f"{recipe.get('yield_unit','plate')}"
                )
                if show_cost and recipe.get("cost_per_portion") is not None:
                    st.caption(f"${recipe['cost_per_portion']:.2f} / portion")

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button(
                        "View", key=f"view_{recipe['id']}",
                        use_container_width=True
                    ):
                        st.session_state["viewing_recipe"] = recipe["id"]
                        st.session_state["confirm_delete"] = None
                        st.rerun()
                with c2:
                    lines     = _get_recipe_lines(supabase, recipe["id"])
                    pdf_bytes = _generate_recipe_pdf(recipe, lines)
                    if pdf_bytes:
                        st.download_button(
                            "PDF",
                            data=pdf_bytes,
                            file_name=(
                                f"{recipe['name'].replace(' ','_')}.pdf"
                            ),
                            mime="application/pdf",
                            key=f"pdf_{recipe['id']}",
                            use_container_width=True
                        )
                    else:
                        st.button(
                            "PDF", key=f"pdf_na_{recipe['id']}",
                            use_container_width=True, disabled=True
                        )
                with c3:
                    if st.session_state["confirm_delete"] == recipe["id"]:
                        if st.button(
                            "Confirm", key=f"conf_{recipe['id']}",
                            use_container_width=True, type="primary"
                        ):
                            if _delete_recipe(supabase, recipe["id"]):
                                st.session_state["confirm_delete"] = None
                                st.success("Deleted.")
                                st.rerun()
                    else:
                        if st.button(
                            "Delete", key=f"del_{recipe['id']}",
                            use_container_width=True
                        ):
                            st.session_state["confirm_delete"] = recipe["id"]
                            st.rerun()

    if st.session_state.get("viewing_recipe"):
        rid    = st.session_state["viewing_recipe"]
        recipe = next(
            (r for r in recipes if r["id"] == rid), None
        )
        if recipe:
            st.divider()
            photo_url = recipe.get("photo_url", "")
            if photo_url:
                st.image(photo_url, width=300)
            st.markdown(f"### {recipe['name']}")
            caption = (
                f"{recipe.get('category')} · "
                f"{recipe.get('portions')} {recipe.get('yield_unit')}"
            )
            if show_cost and recipe.get("cost_per_portion") is not None:
                caption += f" · ${recipe['cost_per_portion']:.2f}/portion"
            st.caption(caption)

            lines = _get_recipe_lines(supabase, rid)
            if lines:
                st.markdown("**Ingredients**")
                for line in lines:
                    badge    = "🏭" if line.get("is_production") else "🛒"
                    cost_str = ""
                    if show_cost and line.get("cost_per_unit"):
                        cost_str = (
                            f" · ${line['cost_per_unit']:.2f}"
                            f"/{line['unit']}"
                        )
                    st.write(
                        f"{badge} {line['item_name']} — "
                        f"{line['qty']} {line['unit']}{cost_str}"
                    )
            if recipe.get("method"):
                st.markdown("**Method of preparation**")
                st.write(recipe["method"])

            if st.button("← Close", key="close_view"):
                del st.session_state["viewing_recipe"]
                st.rerun()


# ─────────────────────────────────────────────
# NEW RECIPE — SINGLE PAGE FORM
# ─────────────────────────────────────────────

def _init_form():
    defaults = {
        "recipe_ingredients": [],
        "bp_memory":          {},
        "pending_subs":       {},
        "show_photo_dialog":  False,
        "saved_recipe_id":    None,
        "saved_recipe_name":  "",
        "recipe_photo_done":  False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset_form():
    for k in [
        "recipe_ingredients", "bp_memory", "pending_subs",
        "show_photo_dialog", "saved_recipe_id", "saved_recipe_name",
        "open_sub_dialog", "recipe_photo_done",
        "new_recipe_name", "new_recipe_category",
        "new_recipe_portions", "new_recipe_yield_unit",
        "new_recipe_method", "ing_search_q",
    ]:
        st.session_state.pop(k, None)
    _init_form()


def _render_new_recipe(
    supabase: Client,
    client_name: str,
    outlet: str,
    user: str,
    show_cost: bool,
):
    _init_form()

    # Photo dialog
    if st.session_state.get("show_photo_dialog"):
        _photo_dialog(
            supabase,
            st.session_state["saved_recipe_id"],
            st.session_state["saved_recipe_name"],
        )

    # Success screen after photo dialog closes
    if st.session_state.get("recipe_photo_done"):
        st.success(
            f"**{st.session_state.get('saved_recipe_name','')}** saved!"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Create another recipe", use_container_width=True):
                _reset_form()
                st.rerun()
        with c2:
            if st.button(
                "Go to library", type="primary",
                use_container_width=True, key="goto_lib_btn"
            ):
                _reset_form()
                st.session_state["recipe_tab"] = "library"
                st.rerun()
        return

    # ── SINGLE PAGE FORM ─────────────────────────────────────────────────
    master_items  = _get_master_items(supabase, client_name)
    client_region = st.session_state.get("client_region", "Global")
    added_codes   = [
        i["product_code"]
        for i in st.session_state["recipe_ingredients"]
    ]

    # Recipe name
    st.text_input(
        "Recipe name",
        placeholder="e.g. Hamburger",
        key="new_recipe_name",
        label_visibility="collapsed",
    )
    st.markdown(
        "<p style='font-size:11px;color:var(--text-color);"
        "opacity:0.5;margin-top:-12px;margin-bottom:8px;'>"
        "Recipe name</p>",
        unsafe_allow_html=True
    )

    # Category
    st.radio(
        "Category",
        ["Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
        horizontal=True,
        key="new_recipe_category",
        label_visibility="collapsed",
    )

    # Yield — tight left-aligned columns, no dividers around
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        st.number_input(
            "Portions", min_value=1, value=1,
            key="new_recipe_portions"
        )
    with c2:
        st.selectbox(
            "Unit",
            ["Plate", "Portion", "Kg", "Litre", "Batch"],
            key="new_recipe_yield_unit"
        )

    st.markdown("---")

    # Ingredient search
    search_query = st.text_input(
        "Add ingredient",
        placeholder="Type here e.g. Chicken breast",
        key="ing_search_q",
        label_visibility="collapsed",
    )
    st.markdown(
        "<p style='font-size:11px;color:var(--text-color);"
        "opacity:0.5;margin-top:-12px;margin-bottom:8px;'>"
        "Search ingredient</p>",
        unsafe_allow_html=True
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
                [
                    i for i in master_items
                    if i["product_code"] not in added_codes
                ],
                limit=5,
            )

        if results:
            for item in results:
                mem      = st.session_state["bp_memory"].get(
                    item["product_code"]
                )
                pre_prod = item.get("is_production", False)

                with st.container(border=True):
                    # Row 1: name + buy/produce toggle
                    r1c1, r1c2 = st.columns([3, 2])
                    with r1c1:
                        known = " ✓" if mem is not None else ""
                        st.markdown(f"**{item['item_name']}**{known}")
                        if item.get("item_name_ar"):
                            st.caption(item["item_name_ar"])
                    with r1c2:
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

                    # Row 2: qty + unit + Add
                    r2c1, r2c2, r2c3 = st.columns([2, 2, 1])
                    with r2c1:
                        qty_val = st.number_input(
                            "Qty",
                            min_value=0.0, step=0.1, value=0.0,
                            key=f"srch_qty_{item['product_code']}",
                            label_visibility="collapsed",
                        )
                    with r2c2:
                        unit_options = [
                            "kg", "g", "l", "ml", "pcs", "portion"
                        ]
                        default_unit = item.get("unit", "kg")
                        if default_unit not in unit_options:
                            unit_options.insert(0, default_unit)
                        unit_val = st.selectbox(
                            "Unit",
                            unit_options,
                            index=unit_options.index(default_unit),
                            key=f"srch_unit_{item['product_code']}",
                            label_visibility="collapsed",
                        )
                    with r2c3:
                        if st.button(
                            "Add",
                            key=f"add_{item['product_code']}",
                            use_container_width=True,
                            type="primary"
                        ):
                            if choice == "produce":
                                st.session_state[
                                    f"prod_qty_{item['product_code']}"
                                ] = qty_val
                                st.session_state[
                                    f"prod_unit_{item['product_code']}"
                                ] = unit_val
                                st.session_state["open_sub_dialog"] = item
                                st.rerun()
                            else:
                                st.session_state[
                                    "recipe_ingredients"
                                ].append({
                                    "product_code": item["product_code"],
                                    "item_name":    item["item_name"],
                                    "unit":         unit_val,
                                    "cost_per_unit":item.get(
                                        "cost_per_unit", 0
                                    ),
                                    "qty":          qty_val,
                                    "is_production":False,
                                    "sub_data":     None,
                                })
                                if not master_items:
                                    _upsert_master_item(supabase, {
                                        "client_name":  client_name,
                                        "product_code": item["product_code"],
                                        "item_name":    item["item_name"],
                                        "item_name_ar": item.get(
                                            "item_name_ar", ""
                                        ),
                                        "unit":         unit_val,
                                        "is_production":False,
                                        "cost_per_unit":item.get(
                                            "cost_per_unit", 0
                                        ),
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
                (i for i in master_items if i["product_code"] == code),
                {}
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
                    "item_name_ar": item_info.get("item_name_ar", ""),
                    "unit":         sub_data["batch_unit"],
                    "is_production":True,
                    "cost_per_unit":0,
                    "region":       client_region,
                    "source":       "worldwide",
                })
            del st.session_state["pending_subs"][code]
            st.rerun()

    # Added ingredients list
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
                if (
                    show_cost
                    and ing.get("cost_per_unit")
                    and not ing["is_production"]
                ):
                    st.caption(
                        f"${ing['cost_per_unit'] * ing['qty']:.2f}"
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

    # Method
    st.markdown("---")
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
            key="new_recipe_method",
            label_visibility="collapsed",
        )
        char_count = len(st.session_state.get("new_recipe_method", ""))
        st.caption(f"{char_count} / 500")

    # Save button
    st.markdown("")
    name      = st.session_state.get("new_recipe_name", "").strip()
    can_save  = bool(name) and len(
        st.session_state["recipe_ingredients"]
    ) > 0

    if not name:
        st.caption("Enter a recipe name to save.")
    elif not st.session_state["recipe_ingredients"]:
        st.caption("Add at least one ingredient to save.")

    if st.button(
        "Save recipe",
        type="primary",
        use_container_width=True,
        disabled=not can_save,
    ):
        portions   = st.session_state.get("new_recipe_portions", 1)
        yield_unit = st.session_state.get("new_recipe_yield_unit", "Plate")
        category   = st.session_state.get("new_recipe_category", "Main")
        method     = st.session_state.get("new_recipe_method", "") or None
        ings       = st.session_state["recipe_ingredients"]

        total_cost = sum(
            i["cost_per_unit"] * i["qty"]
            for i in ings if not i["is_production"]
        )
        cpp = round(total_cost / portions, 2) if portions > 0 else 0.0

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
            "yield_unit":       yield_unit,
            "method":           method,
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
            st.session_state["saved_recipe_id"]   = saved_id
            st.session_state["saved_recipe_name"] = name
            st.session_state["show_photo_dialog"] = True
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

    if st.session_state.get("recipe_tab") == "library":
        st.session_state.pop("recipe_tab", None)

    tab_lib, tab_new = st.tabs(["Recipe library", "New recipe"])

    with tab_lib:
        _render_library(supabase, client_name, show_cost)

    with tab_new:
        _render_new_recipe(supabase, client_name, outlet, user, show_cost)