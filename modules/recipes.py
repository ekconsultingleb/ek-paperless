# modules/recipes.py
import streamlit as st
import uuid
from datetime import datetime
import zoneinfo
from supabase import Client

# ─────────────────────────────────────────────
# SUPABASE HELPERS
# ─────────────────────────────────────────────

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
        supabase.table("recipe_lines").delete().eq(
            "recipe_id", recipe_id
        ).execute()
        supabase.table("recipes").delete().eq("id", recipe_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting recipe: {e}")
        return False

def _upload_recipe_photo(
    supabase: Client, recipe_id: str, file_bytes: bytes, mime: str
) -> "str | None":
    try:
        ext  = mime.split("/")[-1].replace("jpeg", "jpg")
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
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable
        )
        from reportlab.lib.enums import TA_CENTER
        import io

        buffer  = io.BytesIO()
        doc     = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )
        EK_DARK  = colors.HexColor("#1B252C")
        EK_SAND  = colors.HexColor("#E3C5AD")
        EK_LIGHT = colors.HexColor("#F5F0EB")

        s_title = ParagraphStyle(
            "t", fontSize=22, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceAfter=4
        )
        s_sub = ParagraphStyle(
            "s", fontSize=11,
            textColor=colors.HexColor("#5F5E5A"),
            fontName="Helvetica", spaceAfter=2
        )
        s_sec = ParagraphStyle(
            "sec", fontSize=10, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6
        )
        s_body = ParagraphStyle(
            "b", fontSize=10, textColor=EK_DARK,
            fontName="Helvetica", leading=16
        )
        s_foot = ParagraphStyle(
            "f", fontSize=8,
            textColor=colors.HexColor("#888780"),
            fontName="Helvetica", alignment=TA_CENTER
        )

        story = []
        story.append(Paragraph(recipe.get("name", "Recipe"), s_title))
        story.append(Paragraph(
            f"{recipe.get('category','')}  ·  "
            f"{recipe.get('portions',1)} {recipe.get('yield_unit','plate')}",
            s_sub
        ))
        story.append(HRFlowable(
            width="100%", thickness=1, color=EK_SAND, spaceAfter=10
        ))
        story.append(Paragraph("Ingredients", s_sec))

        if lines:
            table_data = [["#", "Ingredient", "Qty", "Unit", "Type"]]
            for i, line in enumerate(lines, 1):
                # Show AI resolved name if available, else chef input
                display_name = (
                    line.get("ai_resolved") or
                    line.get("chef_input", "")
                )
                t = "Production" if line.get("is_production") else "—"
                table_data.append([
                    str(i),
                    display_name,
                    str(line.get("qty", "")),
                    line.get("unit", ""),
                    t,
                ])
            tbl = Table(
                table_data,
                colWidths=[1*cm, 8*cm, 2*cm, 2*cm, 3*cm]
            )
            tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), EK_DARK),
                ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
                ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",      (0,0), (-1,-1), 9),
                ("ROWBACKGROUNDS",(0,1), (-1,-1),
                 [colors.white, EK_LIGHT]),
                ("GRID",          (0,0), (-1,-1), 0.3,
                 colors.HexColor("#D3D1C7")),
                ("LEFTPADDING",   (0,0), (-1,-1), 8),
                ("RIGHTPADDING",  (0,0), (-1,-1), 8),
                ("TOPPADDING",    (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ]))
            story.append(tbl)

        method = recipe.get("method", "")
        if method:
            story.append(Spacer(1, 0.3*cm))
            story.append(HRFlowable(
                width="100%", thickness=0.5, color=EK_SAND
            ))
            story.append(Paragraph("Method of preparation", s_sec))
            for ln in method.split("\n"):
                if ln.strip():
                    story.append(Paragraph(ln.strip(), s_body))

        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(
            width="100%", thickness=1, color=EK_SAND
        ))
        story.append(Paragraph(
            f"EK Consulting  ·  ek-consulting.co  ·  "
            f"Generated {datetime.now().strftime('%d %b %Y')}",
            s_foot
        ))
        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    except ImportError:
        st.error("reportlab not installed. Add reportlab to requirements.txt.")
        return None
    except Exception as e:
        st.error(f"PDF error: {e}")
        return None


# ─────────────────────────────────────────────
# UNIT OPTIONS — g default first
# ─────────────────────────────────────────────

UNITS = ["g", "kg", "ml", "l", "pcs", "portion", "tbsp", "tsp", "bunch", "slice", "pack"]


# ─────────────────────────────────────────────
# SUB-RECIPE FORM (production overlay)
# ─────────────────────────────────────────────

@st.dialog("Build sub-recipe", width="large")
def _sub_recipe_dialog(parent_ing_index: int):
    """
    Identical ingredient form for building a production sub-recipe.
    Saves result into st.session_state['sub_recipe_result'].
    """
    st.caption(
        "This is a production — build it here. "
        "When done click Save and you'll return to the main recipe."
    )

    sub_key = f"sub_lines_{parent_ing_index}"
    if sub_key not in st.session_state:
        st.session_state[sub_key] = [
            {"chef_input": "", "qty": 0.0, "unit": "kg", "is_production": False}
        ]

    sub_lines = st.session_state[sub_key]

    # Batch size — no labels shown
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        batch_qty = st.number_input(
            "Batch qty", min_value=0.01, value=1.0,
            step=0.1, key=f"sub_bqty_{parent_ing_index}",
            label_visibility="collapsed",
        )
    with c2:
        batch_unit = st.selectbox(
            "Batch unit", UNITS,
            key=f"sub_bunit_{parent_ing_index}",
            label_visibility="collapsed",
        )

    st.markdown("---")
    st.caption("Ingredients of this production:")

    # Ingredient lines
    for idx, line in enumerate(sub_lines):
        c1, c2, c3, c4 = st.columns([4, 1.5, 1.5, 0.5])
        with c1:
            val = st.text_input(
                "Ingredient",
                value=line["chef_input"],
                placeholder="e.g. dijon mustard",
                key=f"sub_name_{parent_ing_index}_{idx}",
                label_visibility="collapsed"
            )
            sub_lines[idx]["chef_input"] = val
        with c2:
            qty = st.number_input(
                "Qty", min_value=0.0, step=1.0,
                value=float(line["qty"]),
                key=f"sub_qty_{parent_ing_index}_{idx}",
                label_visibility="collapsed"
            )
            sub_lines[idx]["qty"] = qty
        with c3:
            unit = st.selectbox(
                "Unit", UNITS,
                index=UNITS.index(line["unit"])
                      if line["unit"] in UNITS else 0,
                key=f"sub_unit_{parent_ing_index}_{idx}",
                label_visibility="collapsed"
            )
            sub_lines[idx]["unit"] = unit
        with c4:
            if len(sub_lines) > 1:
                if st.button("×", key=f"sub_del_{parent_ing_index}_{idx}"):
                    sub_lines.pop(idx)
                    st.session_state[sub_key] = sub_lines
                    st.rerun()

    if st.button("+ Add ingredient line", key=f"sub_add_{parent_ing_index}"):
        sub_lines.append(
            {"chef_input": "", "qty": 0.0, "unit": "g", "is_production": False}
        )
        st.session_state[sub_key] = sub_lines
        st.rerun()

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancel", use_container_width=True,
                     key=f"sub_cancel_{parent_ing_index}"):
            st.session_state.pop(sub_key, None)
            st.session_state.pop("open_sub_idx", None)
            st.rerun()
    with c2:
        if st.button("Save sub-recipe", type="primary",
                     use_container_width=True,
                     key=f"sub_save_{parent_ing_index}"):
            st.session_state["sub_recipe_result"] = {
                "parent_index": parent_ing_index,
                "batch_qty":    batch_qty,
                "batch_unit":   batch_unit,
                "lines":        list(sub_lines),
            }
            st.session_state.pop(sub_key, None)
            st.session_state.pop("open_sub_idx", None)
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
                    st.caption(
                        f"${recipe['cost_per_portion']:.2f} / portion"
                    )

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

    # Recipe detail view
    if st.session_state.get("viewing_recipe"):
        rid    = st.session_state["viewing_recipe"]
        recipe = next(
            (r for r in recipes if r["id"] == rid), None
        )
        if recipe:
            st.divider()
            photo_url = recipe.get("photo_url", "")
            if photo_url:
                st.image(photo_url, width=280)
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
                    badge      = "🏭" if line.get("is_production") else "🛒"
                    raw        = line.get("chef_input", "")
                    resolved   = line.get("ai_resolved", "")
                    qty        = line.get("qty", "")
                    unit       = line.get("unit", "")
                    display    = resolved if resolved else raw
                    ai_tag     = (
                        f" *(AI: {resolved})*" if resolved and resolved != raw
                        else ""
                    )
                    st.write(
                        f"{badge} {raw} — {qty} {unit}{ai_tag}"
                    )
                    if line.get("sub_lines"):
                        with st.expander("Sub-recipe ingredients"):
                            for sl in line["sub_lines"]:
                                st.caption(
                                    f"  {sl.get('chef_input','')} — "
                                    f"{sl.get('qty','')} {sl.get('unit','')}"
                                )

            if recipe.get("method"):
                st.markdown("**Method of preparation**")
                st.write(recipe["method"])

            if st.button("← Close", key="close_view"):
                del st.session_state["viewing_recipe"]
                st.rerun()


# ─────────────────────────────────────────────
# FORM STATE
# ─────────────────────────────────────────────

def _init_form():
    if "form_lines" not in st.session_state:
        st.session_state["form_lines"] = [
            {
                "chef_input":    "",
                "qty":           0.0,
                "unit":          "g",
                "is_production": False,
                "sub_data":      None,
            }
        ]
    for k, v in {
        "form_photo_done":   False,
        "form_saved_id":     None,
        "form_saved_name":   "",
        "form_show_photo":   False,
        "open_sub_idx":      None,
        "sub_recipe_result": None,
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset_form():
    for k in [
        "form_lines", "form_photo_done", "form_saved_id",
        "form_saved_name", "form_show_photo", "open_sub_idx",
        "sub_recipe_result",
        # widget keys
        "form_recipe_name", "form_category",
        "form_portions", "form_yield_unit", "form_method",
    ]:
        st.session_state.pop(k, None)
    _init_form()


# ─────────────────────────────────────────────
# NEW RECIPE — FREE FORM
# ─────────────────────────────────────────────

def _render_new_recipe(
    supabase: Client,
    client_name: str,
    outlet: str,
    user: str,
    show_cost: bool,
):
    _init_form()

    # ── Absorb sub-recipe result from dialog ─────────────────────────────
    result = st.session_state.get("sub_recipe_result")
    if result is not None:
        idx = result["parent_index"]
        if 0 <= idx < len(st.session_state["form_lines"]):
            st.session_state["form_lines"][idx]["sub_data"] = {
                "batch_qty":  result["batch_qty"],
                "batch_unit": result["batch_unit"],
                "lines":      result["lines"],
            }
        st.session_state["sub_recipe_result"] = None

    # ── Photo dialog ──────────────────────────────────────────────────────
    if st.session_state.get("form_show_photo"):
        _photo_dialog(
            supabase,
            st.session_state["form_saved_id"],
            st.session_state["form_saved_name"],
        )

    # ── Success screen ────────────────────────────────────────────────────
    if st.session_state.get("form_photo_done"):
        st.success(
            f"**{st.session_state.get('form_saved_name','')}** saved!"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("New recipe", use_container_width=True):
                _reset_form()
                st.rerun()
        with c2:
            if st.button(
                "Go to library", type="primary",
                use_container_width=True
            ):
                _reset_form()
                st.session_state["recipe_tab"] = "library"
                st.rerun()
        return

    # ── Open sub-recipe dialog if triggered ──────────────────────────────
    if st.session_state.get("open_sub_idx") is not None:
        idx = st.session_state["open_sub_idx"]   # keep key so rerun inside dialog stays open
        _sub_recipe_dialog(idx)

    # ─────────────────────────────────────────────────────────────────────
    # FORM
    # ─────────────────────────────────────────────────────────────────────

    # Category — first
    st.radio(
        "Category",
        ["Starter", "Main", "Dessert", "Beverage", "Sub-recipe"],
        horizontal=True,
        key="form_category",
        label_visibility="collapsed",
    )

    # Yield — tight left columns, no labels shown
    c1, c2, _ = st.columns([1, 1, 2])
    with c1:
        st.number_input(
            "Portions", min_value=1, value=1,
            key="form_portions",
            label_visibility="collapsed",
        )
    with c2:
        st.selectbox(
            "Unit",
            ["Plate", "Portion", "Kg", "Litre", "Batch"],
            key="form_yield_unit",
            label_visibility="collapsed",
        )

    # Recipe name — below category/yield
    st.text_input(
        "Recipe name",
        placeholder="Type here the Recipe Name",
        key="form_recipe_name",
        label_visibility="collapsed",
    )
    st.markdown(
        "<p style='font-size:11px;opacity:0.45;margin-top:-12px;"
        "margin-bottom:10px;'>Recipe name</p>",
        unsafe_allow_html=True
    )

    st.markdown("---")

    # ── Ingredient lines ──────────────────────────────────────────────────
    lines = st.session_state["form_lines"]

    for idx, line in enumerate(lines):
        c1, c2, c3, c4, c5 = st.columns([4, 1.5, 1.5, 1, 0.5])

        with c1:
            val = st.text_input(
                "Ingredient",
                value=line["chef_input"],
                placeholder="Ingredient",
                key=f"ing_name_{idx}",
                label_visibility="collapsed",
            )
            lines[idx]["chef_input"] = val

        with c2:
            qty_str = st.text_input(
                "Qty",
                value="" if line["qty"] == 0.0 else str(line["qty"]),
                placeholder="Qty",
                key=f"ing_qty_{idx}",
                label_visibility="collapsed",
            )
            try:
                lines[idx]["qty"] = float(qty_str) if qty_str else 0.0
            except ValueError:
                lines[idx]["qty"] = line["qty"]

        with c3:
            unit = st.selectbox(
                "Unit",
                UNITS,
                index=UNITS.index(line["unit"])
                      if line["unit"] in UNITS else 0,
                key=f"ing_unit_{idx}",
                label_visibility="collapsed",
            )
            lines[idx]["unit"] = unit

        with c4:
            is_prod = st.checkbox(
                "Production?",
                value=line["is_production"],
                key=f"ing_prod_{idx}",
                label_visibility="visible",
            )
            lines[idx]["is_production"] = is_prod

            # If just ticked production — open sub-recipe dialog
            if is_prod and line["sub_data"] is None:
                if st.button(
                    "Build",
                    key=f"ing_build_{idx}",
                    use_container_width=True
                ):
                    st.session_state["open_sub_idx"] = idx
                    st.rerun()
            elif is_prod and line["sub_data"] is not None:
                sub = line["sub_data"]
                st.caption(
                    f"{sub['batch_qty']} {sub['batch_unit']} · "
                    f"{len(sub['lines'])} ingredient(s)"
                )
                if st.button(
                    "Edit",
                    key=f"ing_edit_{idx}",
                    use_container_width=True
                ):
                    st.session_state["open_sub_idx"] = idx
                    st.rerun()

        with c5:
            if len(lines) > 1:
                if st.button(
                    "×", key=f"ing_del_{idx}"
                ):
                    lines.pop(idx)
                    st.session_state["form_lines"] = lines
                    st.rerun()

    st.session_state["form_lines"] = lines

    # Add line button
    if st.button("+ Add ingredient"):
        st.session_state["form_lines"].append({
            "chef_input":    "",
            "qty":           0.0,
            "unit":          "g",
            "is_production": False,
            "sub_data":      None,
        })
        st.rerun()

    # Method
    st.markdown("---")
    with st.expander("Method of preparation (optional)"):
        st.text_area(
            "Method",
            placeholder=(
                "1. Marinate chicken for 2hrs\n"
                "2. Grill 4 mins each side\n"
                "3. Rest before plating"
            ),
            max_chars=500,
            height=130,
            key="form_method",
            label_visibility="collapsed",
        )
        st.caption(
            f"{len(st.session_state.get('form_method',''))} / 500"
        )

    # ── Save button ───────────────────────────────────────────────────────
    st.markdown("")
    name     = st.session_state.get("form_recipe_name", "").strip()
    has_ings = any(
        l["chef_input"].strip()
        for l in st.session_state["form_lines"]
    )
    can_save = bool(name)

    if not name:
        st.caption("Enter a recipe name to save.")

    if st.button(
        "Save recipe",
        type="primary",
        use_container_width=True,
        disabled=not can_save,
    ):
        portions   = st.session_state.get("form_portions", 1)
        yield_unit = st.session_state.get("form_yield_unit", "Plate")
        category   = st.session_state.get("form_category", "Main")
        method     = st.session_state.get("form_method", "") or None
        ings       = [
            l for l in st.session_state["form_lines"]
            if l["chef_input"].strip()
        ]

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
            "cost_per_portion": 0,
            "created_by":       user,
            "created_at":       now,
            "photo_url":        None,
        }

        lines_to_save = []
        for ing in ings:
            line_record = {
                "id":            str(uuid.uuid4()),
                "recipe_id":     recipe_id,
                "chef_input":    ing["chef_input"].strip(),
                "qty":           ing["qty"],
                "unit":          ing["unit"],
                "is_production": ing["is_production"],
                "ai_resolved":   None,
                "ai_product_code": None,
                "ai_confidence": None,
                "sub_lines":     (
                    ing["sub_data"]["lines"]
                    if ing.get("sub_data") else None
                ),
            }
            lines_to_save.append(line_record)

        saved_id = _save_recipe(supabase, recipe_record, lines_to_save)
        if saved_id:
            st.session_state["form_saved_id"]   = saved_id
            st.session_state["form_saved_name"] = name
            st.session_state["form_show_photo"] = True
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