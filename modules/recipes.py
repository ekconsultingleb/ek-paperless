# modules/recipes.py

import streamlit as st
import uuid
from datetime import datetime
import zoneinfo
from supabase import Client

# ─────────────────────────────────────────────

# CONSTANTS

# ─────────────────────────────────────────────

UNITS = ["g", "cl", "kg", "ml", "l", "pcs", "portion", "tbsp", "tsp", "bunch", "slice", "pack"]

EMPTY_ING = {"name": "", "qty": 0.0, "unit": "g"}

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
"""Fetch all sub-recipes for this client."""
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
"""
Single transaction:
1. Insert any pending sub-recipes (not yet in DB)
2. Insert main recipe
3. Insert all lines with correct sub_recipe_id
"""
try:
# Step 1 — insert pending sub-recipes, collect real IDs
resolved_ids = {}  # temp_id -> real supabase id
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


    # Step 2 — insert main recipe
    res = supabase.table("recipes").insert(recipe_record).execute()
    recipe_id = res.data[0]["id"]

    # Step 3 — insert lines, resolve sub_recipe_id
    if lines:
        for line in lines:
            line["recipe_id"] = recipe_id
            tid = line.pop("_temp_sub_id", None)
            if tid:
                # Check if it was a pending new sub or an existing one
                if tid in resolved_ids:
                    line["sub_recipe_id"] = resolved_ids[tid]
                else:
                    # existing sub-recipe — tid is already a real UUID
                    line["sub_recipe_id"] = tid
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
st.error(f”Error deleting recipe: {e}”)
return False

def *upload_recipe_photo(
supabase: Client, recipe_id: str, file_bytes: bytes, mime: str
) -> "str | None":
try:
ext  = mime.split("/")[-1].replace("jpeg", "jpg")
path = f"recipes/{recipe_id}.{ext}"
supabase.storage.from*("recipe-photos").upload(
path=path,
file=file_bytes,
file_options={"content-type": mime, "upsert": "true"}
)
return supabase.storage.from_("recipe-photos").get_public_url(path)
except Exception as e:
st.warning(f"Photo upload error: {e}")
return None

# ─────────────────────────────────────────────

# FUZZY MATCH

# ─────────────────────────────────────────────

def _fuzzy_match(query: str, candidates: list) -> "dict | None":
"""
Word-overlap fuzzy match.
Returns the best candidate if word overlap >= 0.6, else None.
"""
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

def _generate_recipe_pdf(recipe: dict, lines: list) -> “bytes | None”:
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


    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    EK_DARK  = colors.HexColor("#1B252C")
    EK_SAND  = colors.HexColor("#E3C5AD")
    EK_LIGHT = colors.HexColor("#F5F0EB")

    s_title = ParagraphStyle("t",  fontSize=22, textColor=EK_DARK, fontName="Helvetica-Bold", spaceAfter=4)
    s_sub   = ParagraphStyle("s",  fontSize=11, textColor=colors.HexColor("#5F5E5A"), fontName="Helvetica", spaceAfter=2)
    s_sec   = ParagraphStyle("sec",fontSize=10, textColor=EK_DARK, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6)
    s_body  = ParagraphStyle("b",  fontSize=10, textColor=EK_DARK, fontName="Helvetica", leading=16)
    s_foot  = ParagraphStyle("f",  fontSize=8,  textColor=colors.HexColor("#888780"), fontName="Helvetica", alignment=TA_CENTER)

    story = []
    story.append(Paragraph(recipe.get("name", "Recipe"), s_title))
    story.append(Paragraph(
        f"{recipe.get('category','')}  ·  "
        f"{recipe.get('portions',1)} {recipe.get('yield_unit','plate')}",
        s_sub
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND, spaceAfter=10))
    story.append(Paragraph("Ingredients", s_sec))

    if lines:
        table_data = [["#", "Ingredient", "Qty", "Unit", "Type"]]
        for i, line in enumerate(lines, 1):
            display_name = line.get("ai_resolved") or line.get("chef_input", "")
            t = "Produce" if line.get("is_production") else "Buy"
            table_data.append([str(i), display_name, str(line.get("qty", "")), line.get("unit", ""), t])
        tbl = Table(table_data, colWidths=[1*cm, 8*cm, 2*cm, 2*cm, 3*cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),  (-1,0), EK_DARK),
            ("TEXTCOLOR",     (0,0),  (-1,0), colors.white),
            ("FONTNAME",      (0,0),  (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),  (-1,-1), 9),
            ("ROWBACKGROUNDS",(0,1),  (-1,-1), [colors.white, EK_LIGHT]),
            ("GRID",          (0,0),  (-1,-1), 0.3, colors.HexColor("#D3D1C7")),
            ("LEFTPADDING",   (0,0),  (-1,-1), 8),
            ("RIGHTPADDING",  (0,0),  (-1,-1), 8),
            ("TOPPADDING",    (0,0),  (-1,-1), 5),
            ("BOTTOMPADDING", (0,0),  (-1,-1), 5),
        ]))
        story.append(tbl)

    method = recipe.get("method", "")
    if method:
        story.append(Spacer(1, 0.3*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=EK_SAND))
        story.append(Paragraph("Method of preparation", s_sec))
        for ln in method.split("\n"):
            if ln.strip():
                story.append(Paragraph(ln.strip(), s_body))

    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND))
    story.append(Paragraph(
        f"EK Consulting  ·  ek-consulting.co  ·  "
        f"Generated {datetime.now().strftime('%d %b %Y')}",
        s_foot
    ))
    doc.build(story)
    buffer.seek(0)
    return buffer.read()

except ImportError:
    st.error("reportlab not installed.")
    return None
except Exception as e:
    st.error(f"PDF error: {e}")
    return None


# ─────────────────────────────────────────────

# PHOTO DIALOG

# ─────────────────────────────────────────────

@st.dialog(“Add a photo of this dish”, width=“small”)
def _photo_dialog(supabase: Client, recipe_id: str, recipe_name: str):
st.markdown(f”**{recipe_name}** saved!”)
st.caption(“Photo appears as thumbnail in the library and prints on the PDF card.”)
uploaded = st.file_uploader(
“Take a photo or upload”,
type=[“jpg”, “jpeg”, “png”, “webp”, “heic”],
key=“recipe_photo_upload”
)
if uploaded:
st.image(uploaded, use_container_width=True)


c1, c2 = st.columns(2)
with c1:
    if st.button("Skip for now", use_container_width=True):
        st.session_state["form_photo_done"] = True
        st.rerun()
with c2:
    if st.button("Save with photo", type="primary", use_container_width=True, disabled=not uploaded):
        if uploaded:
            url = _upload_recipe_photo(supabase, recipe_id, uploaded.getvalue(), uploaded.type)
            if url:
                try:
                    supabase.table("recipes").update({"photo_url": url}).eq("id", recipe_id).execute()
                except Exception as e:
                    st.warning(f"Photo update failed: {e}")
        st.session_state["form_photo_done"] = True
        st.rerun()


# ─────────────────────────────────────────────

# SUB-RECIPE DIALOG

# ─────────────────────────────────────────────

@st.dialog("Build sub-recipe", width="large")
def _sub_recipe_dialog(ing_name: str, default_unit: str):
"""
Opens when user clicks Add on a Produce ingredient.
Builds a sub-recipe entirely in session_state.
Nothing is pushed to Supabase here.
"""
st.markdown(f"### {ing_name}")
st.caption("Define how this is prepared and what raw materials it needs.")


# ── Prepare qty + unit ──
c1, c2 = st.columns(2)
with c1:
    prep_qty = st.number_input(
        "Prepare qty",
        min_value=0.01, value=1.0, step=0.1,
        key="sub_prep_qty"
    )
with c2:
    prep_unit = st.selectbox(
        "Prepare unit", UNITS,
        index=UNITS.index(default_unit) if default_unit in UNITS else 0,
        key="sub_prep_unit"
    )

st.markdown("---")
st.caption("Raw materials")

# ── Ingredient builder inside dialog ──
if "sub_dialog_lines" not in st.session_state:
    st.session_state["sub_dialog_lines"] = []

col_n, col_q, col_u, col_btn = st.columns([3, 1.2, 1.2, 0.8])
with col_n:
    sub_ing_name = st.text_input(
        "Material", placeholder="Ingredient name",
        key="sub_ing_name", label_visibility="collapsed"
    )
with col_q:
    sub_ing_qty = st.number_input(
        "Qty", min_value=0.0, step=1.0, value=0.0,
        key="sub_ing_qty", label_visibility="collapsed", format="%.0f"
    )
with col_u:
    sub_ing_unit = st.selectbox(
        "Unit", UNITS,
        index=UNITS.index(default_unit) if default_unit in UNITS else 0,
        key="sub_ing_unit", label_visibility="collapsed"
    )
with col_btn:
    if st.button("Add", key="sub_ing_add", type="primary", use_container_width=True):
        if sub_ing_name.strip():
            st.session_state["sub_dialog_lines"].append({
                "name": sub_ing_name.strip(),
                "qty":  sub_ing_qty,
                "unit": sub_ing_unit,
            })
            # Reset inputs
            for k in ["sub_ing_name", "sub_ing_qty", "sub_ing_unit"]:
                st.session_state.pop(k, None)
            st.rerun()
        else:
            st.caption("Enter a name first.")

# ── Material list ──
sub_lines = st.session_state["sub_dialog_lines"]
if sub_lines:
    st.markdown("---")
    to_del = None
    for idx, sl in enumerate(sub_lines):
        c_info, c_del = st.columns([6, 0.5])
        with c_info:
            st.markdown(f"**{sl['name']}** · {int(sl['qty'])} {sl['unit']}")
        with c_del:
            if st.button("✕", key=f"sub_del_{idx}"):
                to_del = idx
    if to_del is not None:
        st.session_state["sub_dialog_lines"].pop(to_del)
        st.rerun()

st.markdown("---")
c_cancel, c_save = st.columns(2)
with c_cancel:
    if st.button("Cancel", use_container_width=True):
        st.session_state.pop("sub_dialog_lines", None)
        st.session_state["sub_dialog_result"] = None
        st.rerun()
with c_save:
    if st.button("Save sub-recipe", type="primary", use_container_width=True):
        # Package the result — no Supabase yet
        temp_id = f"pending_{uuid.uuid4().hex[:8]}"
        st.session_state["sub_dialog_result"] = {
            "temp_id":   temp_id,
            "name":      ing_name,
            "prep_qty":  prep_qty,
            "prep_unit": prep_unit,
            "lines":     list(st.session_state["sub_dialog_lines"]),
        }
        st.session_state.pop("sub_dialog_lines", None)
        st.rerun()


# ─────────────────────────────────────────────

# EXISTING SUB-RECIPE MATCH DIALOG

# ─────────────────────────────────────────────

@st.dialog("Sub-recipe found", width="small")
def _match_dialog(ing_name: str, match: dict):
st.markdown(f"A sub-recipe similar to **{ing_name}** already exists:")
st.markdown(
f"> **{match[‘name’]}** · "
f"{match.get(‘portions’, 1)} {match.get(‘yield_unit’, ‘’)}"
)
st.caption("Use the existing one or create a new version?")
c1, c2 = st.columns(2)
with c1:
if st.button("Use existing", use_container_width=True, type="primary"):
st.session_state[“sub_dialog_result”] = {
"temp_id":   match["id"],   # real existing ID
"name":      match[“name”],
"prep_qty":  None,
"prep_unit": None,
"lines":     [],
"existing":  True,
}
st.rerun()
with c2:
if st.button("Create new", use_container_width=True):
st.session_state["sub_dialog_result"] = {"action": "create_new"}
st.rerun()

# ─────────────────────────────────────────────

# RECIPE LIBRARY

# ─────────────────────────────────────────────

def _render_library(supabase: Client, client_name: str, show_cost: bool):
recipes = _get_recipes(supabase, client_name)
if not recipes:
st.info("No recipes yet. Go to New Recipe to create your first one.")
return

```
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
                    "<div style='height:60px;display:flex;"
                    "align-items:center;justify-content:center;"
                    "border-radius:8px;font-size:22px;"
                    "background:var(--secondary-background-color)'>🍽</div>",
                    unsafe_allow_html=True
                )
            st.markdown(f"**{recipe['name']}**")
            st.caption(
                f"{recipe.get('category','—')} · "
                f"{recipe.get('portions',1)} {recipe.get('yield_unit','')}"
            )
            if show_cost and recipe.get("cost_per_portion") is not None:
                st.caption(f"${recipe['cost_per_portion']:.2f} / portion")

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("View", key=f"view_{recipe['id']}", use_container_width=True):
                    st.session_state["viewing_recipe"] = recipe["id"]
                    st.session_state["confirm_delete"] = None
                    st.rerun()
            with c2:
                lines     = _get_recipe_lines(supabase, recipe["id"])
                pdf_bytes = _generate_recipe_pdf(recipe, lines)
                if pdf_bytes:
                    st.download_button(
                        "PDF", data=pdf_bytes,
                        file_name=f"{recipe['name'].replace(' ','_')}.pdf",
                        mime="application/pdf",
                        key=f"pdf_{recipe['id']}",
                        use_container_width=True
                    )
                else:
                    st.button("PDF", key=f"pdf_na_{recipe['id']}", use_container_width=True, disabled=True)
            with c3:
                if st.session_state["confirm_delete"] == recipe["id"]:
                    if st.button("Confirm", key=f"conf_{recipe['id']}", use_container_width=True, type="primary"):
                        if _delete_recipe(supabase, recipe["id"]):
                            st.session_state["confirm_delete"] = None
                            st.success("Deleted.")
                            st.rerun()
                else:
                    if st.button("Delete", key=f"del_{recipe['id']}", use_container_width=True):
                        st.session_state["confirm_delete"] = recipe["id"]
                        st.rerun()

# Detail view
if st.session_state.get("viewing_recipe"):
    rid    = st.session_state["viewing_recipe"]
    recipe = next((r for r in recipes if r["id"] == rid), None)
    if recipe:
        st.divider()
        photo_url = recipe.get("photo_url", "")
        if photo_url:
            st.image(photo_url, width=280)
        st.markdown(f"### {recipe['name']}")
        caption = f"{recipe.get('category','—')}"
        if recipe.get("yield_unit"):
            caption += f" · {recipe.get('portions')} {recipe.get('yield_unit')}"
        if show_cost and recipe.get("cost_per_portion") is not None:
            caption += f" · ${recipe['cost_per_portion']:.2f}/portion"
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
                ai_tag   = f" *(AI: {resolved})*" if resolved and resolved != raw else ""
                detail   = f"{raw} — {qty} {unit} · {type_tag}{ai_tag}"
                if line.get("is_production") and line.get("batch_qty"):
                    detail += f" · prepare {line['batch_qty']} {line['batch_unit']}"
                st.write(detail)

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
defaults = {
"form_lines":          [],
"form_photo_done":     False,
"form_saved_id":       None,
"form_saved_name":     "",
"form_show_photo":     False,
"pending_sub_recipes": {},   # temp_id -> {record, lines}
"sub_dialog_result":   None,
"sub_dialog_pending":  None, # ing being processed
}
for k, v in defaults.items():
if k not in st.session_state:
st.session_state[k] = v

def _reset_form():
keys = [
"form_lines", "form_photo_done", "form_saved_id",
"form_saved_name", "form_show_photo",
"form_recipe_name", "form_category",
"form_batch_qty", "form_batch_unit", "form_method",
"pending_sub_recipes", "sub_dialog_result", "sub_dialog_pending",
"ing_name_input", "ing_qty_input", "ing_unit_input", "ing_type_input",
]
for k in keys:
st.session_state.pop(k, None)
_init_form()

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


# ── Photo dialog trigger ──
if st.session_state.get("form_show_photo"):
    _photo_dialog(
        supabase,
        st.session_state["form_saved_id"],
        st.session_state["form_saved_name"],
    )

# ── Success screen ──
if st.session_state.get("form_photo_done"):
    st.success(f"**{st.session_state.get('form_saved_name','')}** saved!")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("New recipe", use_container_width=True):
            _reset_form()
            st.rerun()
    with c2:
        if st.button("Go to library", type="primary", use_container_width=True):
            _reset_form()
            st.session_state["recipe_tab"] = "library"
            st.rerun()
    return

# ── Handle sub-recipe dialog result ──
result = st.session_state.get("sub_dialog_result")
if result is not None:
    pending_ing = st.session_state.get("sub_dialog_pending")

    if result == {"action": "create_new"}:
        # User chose to create new — open builder dialog
        st.session_state["sub_dialog_result"] = None
        default_unit = "cl" if st.session_state.get("form_category") == "Beverage" else "g"
        _sub_recipe_dialog(pending_ing["name"], default_unit)

    elif result.get("existing"):
        # Linked to existing sub-recipe
        st.session_state["form_lines"].append({
            "chef_input":    pending_ing["name"],
            "qty":           pending_ing["qty"],
            "unit":          pending_ing["unit"],
            "is_production": True,
            "batch_qty":     result.get("prep_qty"),
            "batch_unit":    result.get("prep_unit"),
            "_temp_sub_id":  result["temp_id"],  # real UUID of existing
        })
        st.session_state["sub_dialog_result"]  = None
        st.session_state["sub_dialog_pending"] = None
        st.rerun()

    elif result.get("temp_id"):
        # New sub-recipe built in dialog — store in pending
        temp_id    = result["temp_id"]
        now        = datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).isoformat()
        sub_record = {
            "id":               str(uuid.uuid4()),
            "client_name":      client_name,
            "outlet":           outlet,
            "name":             result["name"],
            "category":         "Sub-recipe",
            "portions":         result["prep_qty"] or 1,
            "yield_unit":       result["prep_unit"] or "g",
            "method":           None,
            "cost_per_portion": 0,
            "created_by":       user,
            "created_at":       now,
            "photo_url":        None,
        }
        sub_lines = []
        for sl in result["lines"]:
            sub_lines.append({
                "id":              str(uuid.uuid4()),
                "recipe_id":       None,  # filled on save
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
            "lines":  sub_lines,
        }
        # Add line to main recipe
        st.session_state["form_lines"].append({
            "chef_input":    pending_ing["name"],
            "qty":           pending_ing["qty"],
            "unit":          pending_ing["unit"],
            "is_production": True,
            "batch_qty":     result["prep_qty"],
            "batch_unit":    result["prep_unit"],
            "_temp_sub_id":  temp_id,
        })
        st.session_state["sub_dialog_result"]  = None
        st.session_state["sub_dialog_pending"] = None
        st.rerun()

# ── Recipe name ──
st.text_input(
    "Recipe name",
    placeholder="Type here the recipe name",
    key="form_recipe_name",
    label_visibility="collapsed",
)

# ── Category ──
category = st.radio(
    "Category",
    ["Food", "Beverage", "Sub-recipe"],
    horizontal=True,
    key="form_category",
    label_visibility="collapsed",
)
default_unit = "cl" if category == "Beverage" else "g"

# ── Sub-recipe: batch qty + unit ──
if category == "Sub-recipe":
    c1, c2 = st.columns(2)
    with c1:
        st.number_input("Batch qty", min_value=0.01, value=1.0, step=0.1, key="form_batch_qty")
    with c2:
        st.selectbox("Batch unit", UNITS, key="form_batch_unit")

st.markdown("---")

# ── Ingredient entry row ──
col_n, col_q, col_u, col_t, col_btn = st.columns([3, 1.2, 1.2, 1.5, 0.8])
with col_n:
    ing_name = st.text_input(
        "Ingredient", placeholder="Ingredient",
        key="ing_name_input", label_visibility="collapsed"
    )
with col_q:
    ing_qty = st.number_input(
        "Qty", min_value=0.0, step=1.0, value=0.0,
        key="ing_qty_input", label_visibility="collapsed", format="%.0f"
    )
with col_u:
    ing_unit = st.selectbox(
        "Unit", UNITS,
        index=UNITS.index(default_unit) if default_unit in UNITS else 0,
        key="ing_unit_input", label_visibility="collapsed"
    )
with col_t:
    ing_type = st.radio(
        "Type", ["Buy", "Produce"],
        horizontal=True,
        key="ing_type_input", label_visibility="collapsed"
    )
with col_btn:
    add_clicked = st.button(
        "Add", use_container_width=True,
        type="primary", key="ing_add_btn"
    )

if add_clicked:
    if not ing_name.strip():
        st.caption("Enter an ingredient name first.")
    else:
        if ing_type == "Buy":
            # Straight add
            st.session_state["form_lines"].append({
                "chef_input":    ing_name.strip(),
                "qty":           ing_qty,
                "unit":          ing_unit,
                "is_production": False,
                "batch_qty":     None,
                "batch_unit":    None,
                "_temp_sub_id":  None,
            })
            # Reset inputs
            for k in ["ing_name_input", "ing_qty_input", "ing_unit_input", "ing_type_input"]:
                st.session_state.pop(k, None)
            st.rerun()

        else:
            # Produce — check for fuzzy match first
            existing_subs = _get_sub_recipes(supabase, client_name)
            # Also include pending (not yet saved) sub-recipes
            for temp_id, sub in st.session_state.get("pending_sub_recipes", {}).items():
                existing_subs.append({
                    "id":         temp_id,
                    "name":       sub["record"]["name"],
                    "portions":   sub["record"]["portions"],
                    "yield_unit": sub["record"]["yield_unit"],
                })

            match = _fuzzy_match(ing_name.strip(), existing_subs)

            # Store the pending ingredient info
            st.session_state["sub_dialog_pending"] = {
                "name": ing_name.strip(),
                "qty":  ing_qty,
                "unit": ing_unit,
            }
            # Reset inputs
            for k in ["ing_name_input", "ing_qty_input", "ing_unit_input", "ing_type_input"]:
                st.session_state.pop(k, None)

            if match:
                _match_dialog(ing_name.strip(), match)
            else:
                _sub_recipe_dialog(ing_name.strip(), default_unit)

# ── Ingredient list ──
lines = st.session_state["form_lines"]
if lines:
    st.markdown("---")
    to_delete = None
    for idx, line in enumerate(lines):
        with st.container(border=True):
            c_info, c_del = st.columns([6, 0.5])
            with c_info:
                type_tag = "Produce" if line["is_production"] else "Buy"
                label    = (
                    f"**{line['chef_input']}** "
                    f"· {int(line['qty'])} {line['unit']} · {type_tag}"
                )
                if line["is_production"] and line.get("batch_qty"):
                    label += f" · prepare {line['batch_qty']} {line['batch_unit']}"
                st.markdown(label)
            with c_del:
                if st.button("✕", key=f"del_line_{idx}"):
                    to_delete = idx
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
    st.caption(f"{len(st.session_state.get('form_method', ''))} / 500")

# ── Save ──
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
            "sub_recipe_id":   None,  # resolved in _save_full_recipe
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
client_name = st.session_state.get(“client_name”, “Unknown”)
outlet      = st.session_state.get(“assigned_outlet”, “Unknown”)
show_cost   = str(role).lower() in [“admin”, “admin_all”, “manager”, “viewer”]


st.markdown("### Recipes")

if st.session_state.get("recipe_tab") == "library":
    st.session_state.pop("recipe_tab", None)

tab_lib, tab_new = st.tabs(["Recipe library", "New recipe"])

with tab_lib:
    _render_library(supabase, client_name, show_cost)

with tab_new:
    _render_new_recipe(supabase, client_name, outlet, user, show_cost)
```
