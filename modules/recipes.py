# modules/recipes.py
import streamlit as st
import uuid
from datetime import datetime
import zoneinfo
from supabase import Client

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

UNITS = ["g", "kg", "ml", "l", "cl", "pcs", "portion", "tbsp", "tsp", "bunch", "slice", "pack"]


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

def _get_sub_recipes(supabase: Client, client_name: str) -> list:
    try:
        res = supabase.table("recipes").select("*").eq(
            "client_name", client_name
        ).eq("category", "Sub-recipe").execute()
        return res.data or []
    except Exception:
        return []

def _save_full_recipe(
    supabase: Client,
    recipe_record: dict,
    lines: list,
    pending_sub_recipes: dict,
) -> "str | None":
    try:
        resolved_ids = {}
        for temp_id, sub in pending_sub_recipes.items():
            sub_record = sub["record"]
            sub_lines  = sub["lines"]
            res = supabase.table("recipes").insert(sub_record).execute()
            real_id = res.data[0]["id"]
            resolved_ids[temp_id] = real_id
            if sub_lines:
                for sl in sub_lines:
                    sl["recipe_id"] = real_id
                supabase.table("recipe_lines").insert(sub_lines).execute()

        res = supabase.table("recipes").insert(recipe_record).execute()
        recipe_id = res.data[0]["id"]

        if lines:
            for line in lines:
                line["recipe_id"] = recipe_id
                tid = line.pop("_temp_sub_id", None)
                if tid:
                    if tid in resolved_ids:
                        line["sub_recipe_id"] = resolved_ids[tid]
                    else:
                        line["sub_recipe_id"] = tid
            supabase.table("recipe_lines").insert(lines).execute()

        return recipe_id

    except Exception as e:
        st.error("Error saving recipe: " + str(e))
        return None

def _delete_recipe(supabase: Client, recipe_id: str) -> bool:
    try:
        supabase.table("recipe_lines").delete().eq("recipe_id", recipe_id).execute()
        supabase.table("recipes").delete().eq("id", recipe_id).execute()
        return True
    except Exception as e:
        st.error("Error deleting recipe: " + str(e))
        return False

def _upload_recipe_photo(
    supabase: Client, recipe_id: str, file_bytes: bytes, mime: str
) -> "str | None":
    try:
        try:
            from PIL import Image
            import io as _io
            img = Image.open(_io.BytesIO(file_bytes))
            img.thumbnail((800, 800))
            out = _io.BytesIO()
            img.save(out, format="JPEG", quality=75)
            file_bytes = out.getvalue()
            mime = "image/jpeg"
        except Exception as e:
            st.warning("Compress failed: " + str(e))
        ext  = "jpg"
        path = "recipes/" + recipe_id + "." + ext
        supabase.storage.from_("recipe-photos").upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": mime, "upsert": "true"}
        )
        return supabase.storage.from_("recipe-photos").get_public_url(path)
    except Exception as e:
        st.warning("Photo upload error: " + str(e))
        return None


# ─────────────────────────────────────────────
# FUZZY MATCH
# ─────────────────────────────────────────────

def _fuzzy_match(query: str, candidates: list) -> "dict | None":
    q_words = set(query.lower().split())
    best       = None
    best_score = 0.0
    for c in candidates:
        c_words = set(c["name"].lower().split())
        if not c_words:
            continue
        overlap = len(q_words & c_words) / max(len(q_words), len(c_words))
        if overlap > best_score:
            best_score = overlap
            best       = c
    if best_score >= 0.6:
        return best
    return None


# ─────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────

def _generate_recipe_pdf(recipe: dict, lines: list) -> "bytes | None":
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable, Image
        )
        from reportlab.lib.enums import TA_CENTER
        import io
        import urllib.request

        buffer = io.BytesIO()
        doc    = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )
        EK_DARK  = colors.HexColor("#1B252C")
        EK_SAND  = colors.HexColor("#E3C5AD")
        EK_LIGHT = colors.HexColor("#F5F0EB")

        s_title = ParagraphStyle("t",   fontSize=22, textColor=EK_DARK, fontName="Helvetica-Bold", spaceAfter=4)
        s_sub   = ParagraphStyle("s",   fontSize=11, textColor=colors.HexColor("#5F5E5A"), fontName="Helvetica", spaceAfter=2)
        s_sec   = ParagraphStyle("sec", fontSize=10, textColor=EK_DARK, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6)
        s_body  = ParagraphStyle("b",   fontSize=10, textColor=EK_DARK, fontName="Helvetica", leading=16)
        s_foot  = ParagraphStyle("f",   fontSize=8,  textColor=colors.HexColor("#888780"), fontName="Helvetica", alignment=TA_CENTER)

        story = []

        # ── Hero photo ──
        photo_url = recipe.get("photo_url")
        if photo_url:
            try:
                req = urllib.request.Request(photo_url, headers={"User-Agent": "Mozilla/5.0"})
                img_data = urllib.request.urlopen(req, timeout=5).read()
                try:
                    from PIL import Image as PImage
                    pimg = PImage.open(io.BytesIO(img_data))
                    pimg.thumbnail((900, 600))
                    pout = io.BytesIO()
                    pimg.save(pout, format="JPEG", quality=70)
                    img_data = pout.getvalue()
                except Exception:
                    pass
                img_buffer = io.BytesIO(img_data)
                page_width = A4[0] - 4*cm
                img = Image(img_buffer, width=page_width, height=8*cm)
                img.hAlign = "CENTER"
                story.append(img)
                story.append(Spacer(1, 0.4*cm))
            except Exception:
                pass

        # ── Title ──
        story.append(Paragraph(recipe.get("name", "Recipe"), s_title))
        yield_display = str(recipe.get("yield_unit")) if recipe.get("yield_unit") else ""
        subtitle = str(recipe.get("category") or "")
        if yield_display:
            subtitle += "   " + str(recipe.get("portions") or 1) + " " + yield_display
        story.append(Paragraph(subtitle, s_sub))
        story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND, spaceAfter=10))

        # ── Ingredients ──
        story.append(Paragraph("Ingredients", s_sec))
        if lines:
            table_data = [["#", "Ingredient", "Qty", "Unit", "Type"]]
            for i, line in enumerate(lines, 1):
                display_name = line.get("ai_resolved") or line.get("chef_input", "")
                t = "Produce" if line.get("is_production") else "Buy"
                table_data.append([
                    str(i),
                    str(display_name),
                    str(line.get("qty", "")),
                    str(line.get("unit", "")),
                    t
                ])
            tbl = Table(table_data, colWidths=[1*cm, 8*cm, 2*cm, 2*cm, 3*cm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND",     (0, 0), (-1, 0), EK_DARK),
                ("TEXTCOLOR",      (0, 0), (-1, 0), colors.white),
                ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",       (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, EK_LIGHT]),
                ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#D3D1C7")),
                ("LEFTPADDING",    (0, 0), (-1, -1), 8),
                ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
                ("TOPPADDING",     (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
            ]))
            story.append(tbl)

        # ── Method ──
        method = recipe.get("method", "")
        if method:
            story.append(Spacer(1, 0.3*cm))
            story.append(HRFlowable(width="100%", thickness=0.5, color=EK_SAND))
            story.append(Paragraph("Method of preparation", s_sec))
            for ln in method.split("\n"):
                if ln.strip():
                    story.append(Paragraph(ln.strip(), s_body))

        # ── Footer ──
        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND))
        story.append(Paragraph(
            "EK Consulting - ek-consulting.co - Generated " +
            datetime.now().strftime("%d %b %Y"),
            s_foot
        ))
        doc.build(story)
        buffer.seek(0)
        return buffer.read()

    except ImportError:
        st.error("reportlab not installed.")
        return None
    except Exception as e:
        st.error("PDF error: " + str(e))
        return None


# ─────────────────────────────────────────────
# PHOTO DIALOG
# ─────────────────────────────────────────────

@st.dialog("Add a photo of this dish", width="small")
def _photo_dialog(supabase: Client, recipe_id: str, recipe_name: str):
    st.markdown("**" + recipe_name + "** saved!")
    st.caption("Photo appears as thumbnail in the library and prints on the PDF card.")
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
            st.session_state["form_photo_done"] = True
            st.session_state["form_show_photo"] = False
            st.rerun()
    with c2:
        if st.button("Save with photo", type="primary", use_container_width=True, disabled=not uploaded):
            if uploaded:
                url = _upload_recipe_photo(supabase, recipe_id, uploaded.getvalue(), uploaded.type)
                if url:
                    try:
                        supabase.table("recipes").update({"photo_url": url}).eq("id", recipe_id).execute()
                    except Exception as e:
                        st.warning("Photo update failed: " + str(e))
            st.session_state["form_photo_done"] = True
            st.session_state["form_show_photo"] = False
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
            "Category", ["All", "Food", "Beverage", "Sub-recipe"],
            label_visibility="collapsed", key="lib_cat"
        )

    filtered = recipes
    if search:
        filtered = [r for r in filtered if search.lower() in r.get("name", "").lower()]
    if cat_filter != "All":
        filtered = [r for r in filtered if r.get("category") == cat_filter]

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
                        "<div style='height:80px;display:flex;"
                        "align-items:center;justify-content:center;"
                        "border-radius:8px;background:var(--secondary-background-color);"
                        "color:var(--text-color);font-size:11px;opacity:0.4'>"
                        "No photo</div>",
                        unsafe_allow_html=True
                    )
                st.markdown("**" + recipe["name"] + "**")
                yield_display = str(recipe.get("yield_unit")) if recipe.get("yield_unit") else ""
                caption = str(recipe.get("category", "?"))
                if yield_display:
                    caption += " - " + str(recipe.get("portions", 1)) + " " + yield_display
                st.caption(caption)
                if show_cost and recipe.get("cost_per_portion") is not None:
                    st.caption("$" + f"{recipe['cost_per_portion']:.2f}" + " / portion")

                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("View", key="view_" + recipe["id"], use_container_width=True):
                        st.session_state["viewing_recipe"] = recipe["id"]
                        st.session_state["confirm_delete"] = None
                        st.rerun()
                with c2:
                    if st.button("PDF", key="pdf_btn_" + recipe["id"], use_container_width=True):
                        st.session_state["gen_pdf_id"] = recipe["id"]
                        st.rerun()
                    if st.session_state.get("gen_pdf_id") == recipe["id"]:
                        with st.spinner("Generating…"):
                            lines     = _get_recipe_lines(supabase, recipe["id"])
                            pdf_bytes = _generate_recipe_pdf(recipe, lines)
                        if pdf_bytes:
                            st.download_button(
                                "⬇️ Download", data=pdf_bytes,
                                file_name=recipe["name"].replace(" ", "_") + ".pdf",
                                mime="application/pdf",
                                key="pdf_dl_" + recipe["id"],
                                use_container_width=True,
                            )
                with c3:
                    if st.session_state["confirm_delete"] == recipe["id"]:
                        if st.button("Confirm", key="conf_" + recipe["id"], use_container_width=True, type="primary"):
                            if _delete_recipe(supabase, recipe["id"]):
                                st.session_state["confirm_delete"] = None
                                st.success("Deleted.")
                                st.rerun()
                    else:
                        if st.button("Delete", key="del_" + recipe["id"], use_container_width=True):
                            st.session_state["confirm_delete"] = recipe["id"]
                            st.rerun()

    if st.session_state.get("viewing_recipe"):
        rid    = st.session_state["viewing_recipe"]
        recipe = next((r for r in recipes if r["id"] == rid), None)
        if recipe:
            st.divider()
            photo_url = recipe.get("photo_url", "")
            if photo_url:
                st.image(photo_url, width=280)
            st.markdown("### " + recipe["name"])
            yield_display = str(recipe.get("yield_unit")) if recipe.get("yield_unit") else ""
            caption = str(recipe.get("category", "?"))
            if yield_display:
                caption += " - " + str(recipe.get("portions")) + " " + yield_display
            if show_cost and recipe.get("cost_per_portion") is not None:
                caption += " - $" + f"{recipe['cost_per_portion']:.2f}" + "/portion"
            st.caption(caption)

            lines = _get_recipe_lines(supabase, rid)
            if lines:
                st.markdown("**Ingredients**")
                for line in lines:
                    raw      = line.get("chef_input", "")
                    resolved = line.get("ai_resolved", "")
                    qty      = line.get("qty", "")
                    unit     = line.get("unit", "")
                    type_tag = "Produce" if line.get("is_production") else "Buy"
                    ai_tag   = " (AI: " + resolved + ")" if resolved and resolved != raw else ""
                    detail   = str(raw) + " - " + str(qty) + " " + str(unit) + " - " + type_tag + ai_tag
                    if line.get("is_production") and line.get("batch_qty"):
                        detail += " - prepare " + str(line["batch_qty"]) + " " + str(line["batch_unit"])
                    st.write(detail)

            if recipe.get("method"):
                st.markdown("**Method of preparation**")
                st.write(recipe["method"])

            if st.button("Close", key="close_view"):
                del st.session_state["viewing_recipe"]
                st.rerun()


# ─────────────────────────────────────────────
# FORM STATE
# ─────────────────────────────────────────────

def _init_form():
    defaults = {
        "form_lines":          [],
        "form_photo_done":     False,
        "form_saved_id":       None,
        "form_saved_name":     "",
        "form_show_photo":     False,
        "pending_sub_recipes": {},
        "ing_counter":         0,
        "sub_building":        False,
        "sub_editing_idx":     None,
        "sub_ing_name":        "",
        "sub_ing_qty":         0.0,
        "sub_ing_unit":        "g",
        "sub_lines":           [],
        "sub_mat_counter":     0,
        "sub_match":           None,
        "sub_match_pending":   False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _reset_form():
    keys = [
        "form_lines", "form_photo_done", "form_saved_id",
        "form_saved_name", "form_show_photo", "pending_sub_recipes",
        "form_recipe_name", "form_category", "form_batch_qty",
        "form_batch_unit", "form_method", "ing_counter",
        "sub_building", "sub_editing_idx", "sub_ing_name",
        "sub_ing_qty", "sub_ing_unit", "sub_lines",
        "sub_mat_counter", "sub_match", "sub_match_pending",
    ]
    for k in keys:
        st.session_state.pop(k, None)
    _init_form()


# ─────────────────────────────────────────────
# INLINE SUB-RECIPE BUILDER
# ─────────────────────────────────────────────

def _render_sub_builder(default_unit: str):
    ing_name    = st.session_state.get("sub_ing_name", "")
    editing_idx = st.session_state.get("sub_editing_idx")
    is_edit     = editing_idx is not None

    with st.container(border=True):
        st.markdown("**" + ("Edit" if is_edit else "Sub-recipe") + ": " + ing_name + "**")
        st.caption("Define how this is prepared and what goes into it.")

        c1, c2 = st.columns(2)
        with c1:
            prep_qty_default = 1.0
            if is_edit:
                existing_line = st.session_state["form_lines"][editing_idx]
                prep_qty_default = float(existing_line.get("batch_qty") or 1.0)
            st.number_input(
                "Prepare qty",
                min_value=0.01,
                value=prep_qty_default,
                step=0.1,
                key="sub_prep_qty"
            )
        with c2:
            prep_unit_default = default_unit
            if is_edit:
                prep_unit_default = existing_line.get("batch_unit") or default_unit
            unit_idx = UNITS.index(prep_unit_default) if prep_unit_default in UNITS else 0
            st.selectbox("Prepare unit", UNITS, index=unit_idx, key="sub_prep_unit")

        st.markdown("---")
        st.caption("Raw materials")

        sub_lines = st.session_state["sub_lines"]
        if sub_lines:
            to_del = None
            for idx, sl in enumerate(sub_lines):
                ci, cd = st.columns([6, 0.5])
                with ci:
                    st.markdown("**" + sl["name"] + "** - " + str(int(sl["qty"])) + " " + sl["unit"])
                with cd:
                    if st.button("x", key="sdel_" + str(idx)):
                        to_del = idx
            if to_del is not None:
                st.session_state["sub_lines"].pop(to_del)
                st.rerun()
            st.markdown("---")

        ctr = st.session_state["sub_mat_counter"]
        col_n, col_q, col_u, col_btn = st.columns([3, 1.2, 1.2, 0.8])
        with col_n:
            mat_name = st.text_input(
                "Material", placeholder="Ingredient name",
                key="mat_name_" + str(ctr), label_visibility="collapsed"
            )
        with col_q:
            mat_qty = st.number_input(
                "Qty", min_value=0.0, step=1.0, value=0.0,
                key="mat_qty_" + str(ctr), label_visibility="collapsed", format="%.0f"
            )
        with col_u:
            mat_unit = st.selectbox(
                "Unit", UNITS,
                index=UNITS.index(default_unit) if default_unit in UNITS else 0,
                key="mat_unit_" + str(ctr), label_visibility="collapsed"
            )
        with col_btn:
            add_mat = st.button("Add", key="mat_add_" + str(ctr), type="primary", use_container_width=True)

        if add_mat:
            if mat_name.strip():
                st.session_state["sub_lines"].append({
                    "name": mat_name.strip(),
                    "qty":  mat_qty,
                    "unit": mat_unit,
                })
                st.session_state["sub_mat_counter"] += 1
                st.rerun()
            else:
                st.caption("Enter a material name first.")

        st.markdown("---")
        c_cancel, c_save = st.columns(2)
        with c_cancel:
            if st.button("Cancel", key="sub_cancel", use_container_width=True):
                st.session_state["sub_building"]    = False
                st.session_state["sub_editing_idx"] = None
                st.session_state["sub_lines"]       = []
                st.session_state["sub_mat_counter"] = 0
                st.session_state["sub_match"]       = None
                st.session_state["sub_match_pending"] = False
                st.rerun()

        with c_save:
            save_label = "Update sub-recipe" if is_edit else "Save sub-recipe"
            if st.button(save_label, key="sub_save", type="primary", use_container_width=True):
                prep_qty  = st.session_state.get("sub_prep_qty", 1.0)
                prep_unit = st.session_state.get("sub_prep_unit", default_unit)
                now       = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).isoformat()

                if is_edit:
                    # Update existing line in form_lines
                    old_line   = st.session_state["form_lines"][editing_idx]
                    old_temp   = old_line.get("_temp_sub_id")

                    # Update the pending sub-recipe record if it exists
                    if old_temp and old_temp in st.session_state["pending_sub_recipes"]:
                        st.session_state["pending_sub_recipes"][old_temp]["record"]["portions"]   = prep_qty
                        st.session_state["pending_sub_recipes"][old_temp]["record"]["yield_unit"] = prep_unit
                        new_sub_lines = []
                        for sl in st.session_state["sub_lines"]:
                            new_sub_lines.append({
                                "id":              str(uuid.uuid4()),
                                "recipe_id":       None,
                                "chef_input":      sl["name"],
                                "qty":             sl["qty"],
                                "unit":            sl["unit"],
                                "is_production":   False,
                                "batch_qty":       None,
                                "batch_unit":      None,
                                "ai_resolved":     None,
                                "ai_product_code": None,
                                "ai_confidence":   None,
                                "sub_recipe_id":   None,
                            })
                        st.session_state["pending_sub_recipes"][old_temp]["lines"] = new_sub_lines
                        temp_id = old_temp
                    else:
                        # Was linked to existing DB sub-recipe — create new pending
                        temp_id    = "pending_" + uuid.uuid4().hex[:8]
                        sub_record = {
                            "id":               str(uuid.uuid4()),
                            "client_name":      st.session_state.get("client_name", ""),
                            "outlet":           st.session_state.get("assigned_outlet", ""),
                            "name":             ing_name,
                            "category":         "Sub-recipe",
                            "portions":         prep_qty,
                            "yield_unit":       prep_unit,
                            "method":           None,
                            "cost_per_portion": 0,
                            "created_by":       st.session_state.get("username", ""),
                            "created_at":       now,
                            "photo_url":        None,
                        }
                        new_sub_lines = []
                        for sl in st.session_state["sub_lines"]:
                            new_sub_lines.append({
                                "id":              str(uuid.uuid4()),
                                "recipe_id":       None,
                                "chef_input":      sl["name"],
                                "qty":             sl["qty"],
                                "unit":            sl["unit"],
                                "is_production":   False,
                                "batch_qty":       None,
                                "batch_unit":      None,
                                "ai_resolved":     None,
                                "ai_product_code": None,
                                "ai_confidence":   None,
                                "sub_recipe_id":   None,
                            })
                        st.session_state["pending_sub_recipes"][temp_id] = {
                            "record": sub_record,
                            "lines":  new_sub_lines,
                        }

                    # Update the line
                    st.session_state["form_lines"][editing_idx]["batch_qty"]    = prep_qty
                    st.session_state["form_lines"][editing_idx]["batch_unit"]   = prep_unit
                    st.session_state["form_lines"][editing_idx]["_temp_sub_id"] = temp_id

                else:
                    # New sub-recipe
                    temp_id    = "pending_" + uuid.uuid4().hex[:8]
                    sub_record = {
                        "id":               str(uuid.uuid4()),
                        "client_name":      st.session_state.get("client_name", ""),
                        "outlet":           st.session_state.get("assigned_outlet", ""),
                        "name":             ing_name,
                        "category":         "Sub-recipe",
                        "portions":         prep_qty,
                        "yield_unit":       prep_unit,
                        "method":           None,
                        "cost_per_portion": 0,
                        "created_by":       st.session_state.get("username", ""),
                        "created_at":       now,
                        "photo_url":        None,
                    }
                    sub_lines_to_save = []
                    for sl in st.session_state["sub_lines"]:
                        sub_lines_to_save.append({
                            "id":              str(uuid.uuid4()),
                            "recipe_id":       None,
                            "chef_input":      sl["name"],
                            "qty":             sl["qty"],
                            "unit":            sl["unit"],
                            "is_production":   False,
                            "batch_qty":       None,
                            "batch_unit":      None,
                            "ai_resolved":     None,
                            "ai_product_code": None,
                            "ai_confidence":   None,
                            "sub_recipe_id":   None,
                        })
                    st.session_state["pending_sub_recipes"][temp_id] = {
                        "record": sub_record,
                        "lines":  sub_lines_to_save,
                    }
                    st.session_state["form_lines"].append({
                        "chef_input":    ing_name,
                        "qty":           st.session_state.get("sub_ing_qty", 0.0),
                        "unit":          st.session_state.get("sub_ing_unit", "g"),
                        "is_production": True,
                        "batch_qty":     prep_qty,
                        "batch_unit":    prep_unit,
                        "_temp_sub_id":  temp_id,
                    })

                st.session_state["sub_building"]    = False
                st.session_state["sub_editing_idx"] = None
                st.session_state["sub_lines"]       = []
                st.session_state["sub_mat_counter"] = 0
                st.session_state["ing_counter"]    += 1
                st.rerun()


# ─────────────────────────────────────────────
# NEW RECIPE FORM
# ─────────────────────────────────────────────

def _render_new_recipe(
    supabase: Client,
    client_name: str,
    outlet: str,
    user: str,
    show_cost: bool,
):
    _init_form()

    if st.session_state.get("form_show_photo"):
        _photo_dialog(
            supabase,
            st.session_state["form_saved_id"],
            st.session_state["form_saved_name"],
        )

    if st.session_state.get("form_photo_done"):
        st.success("**" + st.session_state.get("form_saved_name", "") + "** saved!")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("New recipe", use_container_width=True, key="btn_new_recipe"):
                _reset_form()
                st.rerun()
        with c2:
            if st.button("Go to library", type="primary", use_container_width=True, key="btn_go_library"):
                _reset_form()
                st.session_state["go_to_library"] = True
                st.rerun()
        return

    st.text_input(
        "Recipe name",
        placeholder="Type here the recipe name",
        key="form_recipe_name",
        label_visibility="collapsed",
    )

    category = st.radio(
        "Category",
        ["Food", "Beverage", "Sub-recipe"],
        horizontal=True,
        key="form_category",
        label_visibility="collapsed",
    )
    default_unit = "cl" if category == "Beverage" else "g"

    if category == "Sub-recipe":
        c1, c2 = st.columns(2)
        with c1:
            st.number_input("Batch qty", min_value=0.01, value=1.0, step=0.1, key="form_batch_qty")
        with c2:
            st.selectbox("Batch unit", UNITS, key="form_batch_unit")

    st.markdown("---")

    if st.session_state.get("sub_building"):
        if st.session_state.get("sub_match_pending"):
            match = st.session_state["sub_match"]
            st.info(
                "A sub-recipe similar to **" + st.session_state["sub_ing_name"] +
                "** already exists: **" + match["name"] + "** (" +
                str(match.get("portions", 1)) + " " + str(match.get("yield_unit", "")) + ")"
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Use existing", type="primary", use_container_width=True):
                    st.session_state["form_lines"].append({
                        "chef_input":    st.session_state["sub_ing_name"],
                        "qty":           st.session_state["sub_ing_qty"],
                        "unit":          st.session_state["sub_ing_unit"],
                        "is_production": True,
                        "batch_qty":     match.get("portions"),
                        "batch_unit":    match.get("yield_unit"),
                        "_temp_sub_id":  match["id"],
                    })
                    st.session_state["sub_building"]      = False
                    st.session_state["sub_match"]         = None
                    st.session_state["sub_match_pending"] = False
                    st.session_state["sub_lines"]         = []
                    st.session_state["ing_counter"]      += 1
                    st.rerun()
            with c2:
                if st.button("Create new", use_container_width=True):
                    st.session_state["sub_match_pending"] = False
                    st.rerun()
        else:
            _render_sub_builder(default_unit)
    else:
        ctr = st.session_state["ing_counter"]
        ing_name = st.text_input(
            "Ingredient", placeholder="Ingredient name",
            key="ing_name_" + str(ctr), label_visibility="collapsed"
        )
        col_q, col_u, col_t = st.columns([1.5, 1.5, 2])
        with col_q:
            ing_qty = st.number_input(
                "Qty", min_value=0.0, step=1.0, value=0.0,
                key="ing_qty_" + str(ctr), label_visibility="collapsed", format="%.0f"
            )
        with col_u:
            ing_unit = st.selectbox(
                "Unit", UNITS,
                index=UNITS.index(default_unit) if default_unit in UNITS else 0,
                key="ing_unit_" + str(ctr), label_visibility="collapsed"
            )
        with col_t:
            ing_type = st.radio(
                "Type", ["Buy", "Produce"],
                horizontal=True,
                key="ing_type_" + str(ctr), label_visibility="collapsed"
            )
        add_clicked = st.button(
            "Add", use_container_width=True,
            type="primary", key="ing_add_" + str(ctr)
        )

        if add_clicked:
            if not ing_name.strip():
                st.caption("Enter an ingredient name first.")
            elif ing_type == "Buy":
                st.session_state["form_lines"].append({
                    "chef_input":    ing_name.strip(),
                    "qty":           ing_qty,
                    "unit":          ing_unit,
                    "is_production": False,
                    "batch_qty":     None,
                    "batch_unit":    None,
                    "_temp_sub_id":  None,
                })
                st.session_state["ing_counter"] += 1
                st.rerun()
            else:
                existing_subs = _get_sub_recipes(supabase, client_name)
                for temp_id, sub in st.session_state.get("pending_sub_recipes", {}).items():
                    existing_subs.append({
                        "id":         temp_id,
                        "name":       sub["record"]["name"],
                        "portions":   sub["record"]["portions"],
                        "yield_unit": sub["record"]["yield_unit"],
                    })

                match = _fuzzy_match(ing_name.strip(), existing_subs)

                st.session_state["sub_ing_name"] = str(ing_name).strip()
                st.session_state["sub_ing_qty"]  = float(ing_qty)
                st.session_state["sub_ing_unit"] = str(ing_unit)
                st.session_state["sub_building"] = True
                st.session_state["sub_lines"]    = []

                if match:
                    st.session_state["sub_match"]         = match
                    st.session_state["sub_match_pending"] = True
                else:
                    st.session_state["sub_match"]         = None
                    st.session_state["sub_match_pending"] = False

                st.rerun()

    # ── Ingredient list ──
    lines = st.session_state["form_lines"]
    if lines:
        st.markdown("---")
        st.caption(str(len(lines)) + " ingredient" + ("s" if len(lines) != 1 else "") + " added")
        to_delete  = None
        edit_idx   = None

        for idx, line in enumerate(lines):
            type_tag     = "🟢" if line["is_production"] else "🔵"
            name_display = line["chef_input"] if line["chef_input"] else "(unnamed)"
            qty_str      = str(int(line["qty"])) + " " + line["unit"]
            tag_str      = "Produce" if line["is_production"] else "Buy"
            label = type_tag + " **" + name_display + "** — " + qty_str + " · " + tag_str

            col_info, col_del = st.columns([8, 1])
            with col_info:
                st.markdown(label)
                if line["is_production"] and line.get("batch_qty"):
                    st.caption("prepare " + str(line["batch_qty"]) + " " + str(line.get("batch_unit", "")))
            with col_del:
                if st.button("×", key="del_line_" + str(idx), use_container_width=True):
                    to_delete = idx

            if line["is_production"]:
                if st.button("✏️ Edit sub-recipe", key="edit_line_" + str(idx), use_container_width=True):
                    edit_idx = idx

            if edit_idx == idx:
                temp_id   = line.get("_temp_sub_id")
                pre_lines = []
                if temp_id and temp_id in st.session_state.get("pending_sub_recipes", {}):
                    pre_lines = [
                        {"name": sl["chef_input"], "qty": sl["qty"], "unit": sl["unit"]}
                        for sl in st.session_state["pending_sub_recipes"][temp_id]["lines"]
                    ]
                st.session_state["sub_ing_name"]      = line["chef_input"]
                st.session_state["sub_ing_qty"]       = line["qty"]
                st.session_state["sub_ing_unit"]      = line["unit"]
                st.session_state["sub_building"]      = True
                st.session_state["sub_editing_idx"]   = idx
                st.session_state["sub_lines"]         = pre_lines
                st.session_state["sub_mat_counter"]   = len(pre_lines)
                st.session_state["sub_match_pending"] = False
                st.rerun()

        if to_delete is not None:
            st.session_state["form_lines"].pop(to_delete)
            st.rerun()
    # ── Method ──
    st.markdown("---")
    with st.expander("Method of preparation (optional)"):
        st.text_area(
            "Method",
            placeholder=(
                "1. Marinate chicken for 2hrs\n"
                "2. Grill 4 mins each side\n"
                "3. Rest before plating"
            ),
            max_chars=500, height=130,
            key="form_method", label_visibility="collapsed"
        )
        st.caption(str(len(st.session_state.get("form_method", ""))) + " / 500")

    st.markdown("")
    name = st.session_state.get("form_recipe_name", "").strip()
    if not name:
        st.caption("Enter a recipe name to save.")

    if st.button(
        "Save recipe", type="primary",
        use_container_width=True, disabled=not name
    ):
        cat    = st.session_state.get("form_category", "Food")
        method = st.session_state.get("form_method", "") or None
        ings   = [l for l in st.session_state["form_lines"] if l["chef_input"].strip()]

        if cat == "Sub-recipe":
            portions   = st.session_state.get("form_batch_qty", 1.0)
            yield_unit = st.session_state.get("form_batch_unit", "g")
        else:
            portions   = 1
            yield_unit = None

        recipe_id = str(uuid.uuid4())
        now       = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).isoformat()

        recipe_record = {
            "id":               recipe_id,
            "client_name":      client_name,
            "outlet":           outlet,
            "name":             name,
            "category":         cat,
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
            lines_to_save.append({
                "id":              str(uuid.uuid4()),
                "recipe_id":       recipe_id,
                "chef_input":      ing["chef_input"].strip(),
                "qty":             ing["qty"],
                "unit":            ing["unit"],
                "is_production":   ing["is_production"],
                "batch_qty":       ing.get("batch_qty"),
                "batch_unit":      ing.get("batch_unit"),
                "ai_resolved":     None,
                "ai_product_code": None,
                "ai_confidence":   None,
                "sub_recipe_id":   None,
                "_temp_sub_id":    ing.get("_temp_sub_id"),
            })

        saved_id = _save_full_recipe(
            supabase,
            recipe_record,
            lines_to_save,
            st.session_state.get("pending_sub_recipes", {}),
        )
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
    show_cost   = str(role).lower() in ["admin", "admin_all", "manager", "viewer"]

    st.markdown("### Recipes")

    # ── Library redirect fix ──
    if st.session_state.pop("go_to_library", False):
        tab_lib, tab_new = st.tabs(["Recipe library", "New recipe"])
        with tab_lib:
            _render_library(supabase, client_name, show_cost)
        with tab_new:
            _render_new_recipe(supabase, client_name, outlet, user, show_cost)
        return

    tab_lib, tab_new = st.tabs(["Recipe library", "New recipe"])

    with tab_lib:
        _render_library(supabase, client_name, show_cost)

    with tab_new:
        _render_new_recipe(supabase, client_name, outlet, user, show_cost)
