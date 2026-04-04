# modules/recipe_report.py
"""
Recipe Cards — Productions & Menu Items
Two tabs: Productions (from ac_sub_recipes) and Menu Items (from ac_recipes).
Each tab has group exclude + item-by-item editor + PDF export.
Export All button generates one PDF with productions first, then menu items.
"""

import io
import streamlit as st
from datetime import datetime
from supabase import Client

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, HRFlowable, PageBreak, KeepTogether
    )
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ── Brand colours ──────────────────────────────────────────────────────────────
EK_DARK   = colors.HexColor("#1B252C")
EK_SAND   = colors.HexColor("#E3C5AD")
EK_LIGHT  = colors.HexColor("#F5F0EB")
EK_MID    = colors.HexColor("#8C7B6E")
EK_WHITE  = colors.white
EK_GREY   = colors.HexColor("#D3D1C7")
EK_ACCENT = colors.HexColor("#C4A882")

# item_groups to auto-untick
_REMARK_GROUPS = {"bar remarks", "kitchen remarks", "gls add on"}


# ── Supabase helpers ───────────────────────────────────────────────────────────

def _get_client_id(supabase: Client, client_name: str):
    try:
        res = supabase.table("clients").select("id").eq(
            "client_name", client_name
        ).single().execute()
        return res.data["id"] if res.data else None
    except Exception:
        return None


def _get_dates(supabase: Client, client_id: int) -> list:
    try:
        res = supabase.table("ac_recipes").select("report_date").eq(
            "client_id", client_id
        ).execute()
        return sorted({r["report_date"] for r in (res.data or [])}, reverse=True)
    except Exception:
        return []


def _load_recipes(supabase: Client, client_id: int, report_date: str) -> list:
    try:
        r = supabase.table("ac_recipes").select(
            "category,item_group,menu_items,product_description,qty,unit,avg_cost,total_cost"
        ).eq("client_id", client_id).eq("report_date", report_date).execute()
        return r.data or []
    except Exception as e:
        st.error(f"Error loading ac_recipes: {e}")
        return []


def _load_subs(supabase: Client, client_id: int, report_date: str) -> list:
    try:
        s = supabase.table("ac_sub_recipes").select(
            "production_name,product_description,qty,unit_name,qty_to_prepared,prepared_unit,item_group,average_cost,cost_for_1"
        ).eq("client_id", client_id).eq("report_date", report_date).execute()
        return s.data or []
    except Exception as e:
        st.error(f"Error loading ac_sub_recipes: {e}")
        return []


# ── Data builders ──────────────────────────────────────────────────────────────

def _is_no_recipe(ings: list) -> bool:
    """True if the only ingredient is 'No Recipe' with qty 0."""
    if len(ings) == 1:
        return (str(ings[0].get("name", "")).lower() == "no recipe" and
                (ings[0].get("qty") or 0) == 0)
    return False


def _build_menu_items(recipes: list) -> list:
    """
    Returns list of dish dicts sorted by category → item_group → name.
    Each dish: { name, category, item_group, total_cost, ingredients[], auto_exclude }
    """
    dishes: dict[str, dict] = {}
    for row in recipes:
        name = row.get("menu_items") or "Unknown"
        if name not in dishes:
            dishes[name] = {
                "name":        name,
                "category":    row.get("category") or "",
                "item_group":  row.get("item_group") or "",
                "total_cost":  0.0,
                "ingredients": [],
            }
        desc    = row.get("product_description") or ""
        is_prod = desc.endswith(("Prdk", "Prdb"))
        tc      = row.get("total_cost") or 0
        dishes[name]["total_cost"] += tc
        dishes[name]["ingredients"].append({
            "name":          desc,
            "qty":           row.get("qty"),
            "unit":          row.get("unit") or "",
            "avg_cost":      row.get("avg_cost"),
            "total_cost":    tc,
            "is_production": is_prod,
        })

    result = []
    for d in dishes.values():
        ig = (d["item_group"] or "").lower()
        auto_excl = (
            ig in _REMARK_GROUPS or
            _is_no_recipe(d["ingredients"])
        )
        d["auto_exclude"] = auto_excl
        result.append(d)

    return sorted(result, key=lambda d: (d["category"], d["item_group"], d["name"]))


def _build_productions(subs: list) -> list:
    """
    Returns list of production dicts sorted by item_group → production_name.
    Each production: { name, item_group, yield_qty, yield_unit, ingredients[], auto_exclude }
    """
    prods: dict[str, dict] = {}
    for row in subs:
        name = row.get("production_name") or "Unknown"
        if name not in prods:
            prods[name] = {
                "name":       name,
                "item_group": row.get("item_group") or "",
                "yield_qty":  row.get("qty_to_prepared"),
                "yield_unit": row.get("prepared_unit") or "",
                "ingredients": [],
            }
        prods[name]["ingredients"].append({
            "name":  row.get("product_description") or "",
            "qty":   row.get("qty"),
            "unit":  row.get("unit_name") or "",
            "cost":  row.get("average_cost"),
        })

    result = list(prods.values())
    return sorted(result, key=lambda p: (p["item_group"], p["name"]))


# ── Group excluder helper ──────────────────────────────────────────────────────

def _group_excluder(items: list, group_key: str, tab_prefix: str,
                    extra_group_key: str = None) -> set:
    """
    Show checkboxes for groups. Returns set of item names that are excluded.
    """
    # Collect groups
    groups1 = sorted({i[group_key] for i in items if i.get(group_key)})
    groups2 = sorted({i[extra_group_key] for i in items if i.get(extra_group_key)}) \
        if extra_group_key else []

    excl_names: set[str] = set()

    with st.expander("🗂️ Bulk exclude by group", expanded=False):
        st.caption("Uncheck a group to exclude all its items. Row-level checkboxes below can still override.")

        if extra_group_key:
            gc1, gc2 = st.columns(2)
        else:
            gc1 = st.container()
            gc2 = None

        excl_g1: set[str] = set()
        with gc1:
            st.markdown(f"**By {group_key.replace('_',' ').title()}**")
            for g in groups1:
                count = sum(1 for i in items if i.get(group_key) == g)
                if not st.checkbox(f"{g}  ({count})", value=True,
                                   key=f"{tab_prefix}_g1_{g}"):
                    excl_g1.add(g)

        excl_g2: set[str] = set()
        if gc2 and extra_group_key:
            with gc2:
                st.markdown(f"**By {extra_group_key.replace('_',' ').title()}**")
                for g in groups2:
                    count = sum(1 for i in items if i.get(extra_group_key) == g)
                    if not st.checkbox(f"{g}  ({count})", value=True,
                                       key=f"{tab_prefix}_g2_{g}"):
                        excl_g2.add(g)

    for item in items:
        if (item.get(group_key) in excl_g1 or
                (extra_group_key and item.get(extra_group_key) in excl_g2)):
            excl_names.add(item["name"])

    return excl_names


# ── Item editor ────────────────────────────────────────────────────────────────

def _item_editor(items: list, excl_from_groups: set,
                 tab_prefix: str, show_cost: bool) -> list:
    """
    Show data_editor with include checkboxes.
    Returns list of selected item dicts.
    """
    import pandas as pd

    rows = []
    for item in items:
        auto = item.get("auto_exclude", False)
        group_excl = item["name"] in excl_from_groups
        include = not auto and not group_excl
        rows.append({
            "include":    include,
            "name":       item["name"],
            "group":      item.get("item_group") or item.get("item_group", ""),
            "category":   item.get("category", ""),
        })

    df = pd.DataFrame(rows)

    col_cfg = {
        "include":  st.column_config.CheckboxColumn("✅ Include", width="small"),
        "name":     st.column_config.TextColumn("Name", width="large"),
        "group":    st.column_config.TextColumn("Group"),
        "category": st.column_config.TextColumn("Category"),
    }
    # Hide category col for productions (they don't have it)
    if all(r["category"] == "" for r in rows):
        col_cfg.pop("category")
        display_cols = ["include", "name", "group"]
    else:
        display_cols = ["include", "name", "group", "category"]

    edited = st.data_editor(
        df[display_cols],
        column_config=col_cfg,
        hide_index=True,
        use_container_width=True,
        key=f"{tab_prefix}_editor",
    )

    selected_names = set(edited[edited["include"]]["name"].tolist())
    selected = [i for i in items if i["name"] in selected_names]
    total_excl = len(items) - len(selected)
    st.caption(f"**{len(selected)}** selected · **{total_excl}** excluded")
    return selected


# ── Streamlit UI ───────────────────────────────────────────────────────────────

def render_recipe_report(supabase: Client, user: str, role: str):
    session_client = st.session_state.get("client_name", "All")

    st.markdown("### 🍽️ Recipe Cards")
    st.caption("Productions & Menu Items from Auto Calc data.")

    if not REPORTLAB_OK:
        st.warning("reportlab not installed — PDF export unavailable.")

    # Client selector
    if role in ("admin", "admin_all") or session_client.lower() in ("all", "", "none"):
        try:
            cl_res = supabase.table("clients").select("client_name").order("client_name").execute()
            cl_list = [r["client_name"] for r in (cl_res.data or []) if r.get("client_name")]
        except Exception:
            cl_list = []
        if not cl_list:
            st.warning("No clients found.")
            return
        client_name = st.selectbox("🏢 Client", cl_list, key="rr_client")
    else:
        client_name = session_client

    client_id = _get_client_id(supabase, client_name)
    if not client_id:
        st.warning(f"Client **{client_name}** not found in clients table.")
        return

    dates = _get_dates(supabase, client_id)
    if not dates:
        st.info("No Auto Calc data found for this client.")
        return

    col_d, col_c = st.columns([2, 1])
    with col_d:
        selected_date = st.selectbox(
            "📅 Report month", dates,
            format_func=lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%B %Y") if d else d,
            key="rr_date",
        )
    with col_c:
        show_cost = st.toggle("💰 Show cost", value=False, key="rr_show_cost")

    # Load
    with st.spinner("Loading…"):
        raw_recipes = _load_recipes(supabase, client_id, selected_date)
        raw_subs    = _load_subs(supabase, client_id, selected_date)

    if not raw_recipes and not raw_subs:
        st.warning("No data found for this period.")
        return

    menu_items  = _build_menu_items(raw_recipes)
    productions = _build_productions(raw_subs)

    st.divider()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_prod, tab_menu = st.tabs(["⚙️ Productions", "🍽️ Menu Items"])

    # ── Productions tab ───────────────────────────────────────────────────────
    with tab_prod:
        if not productions:
            st.info("No production data found.")
        else:
            st.markdown(f"**{len(productions)} productions** found")

            excl_prod = _group_excluder(
                productions, "item_group", "prod"
            )
            selected_prods = _item_editor(
                productions, excl_prod, "prod", show_cost
            )

            if REPORTLAB_OK:
                st.divider()
                if st.button("📄 Export Productions PDF", type="primary",
                             use_container_width=True, key="exp_prod"):
                    with st.spinner("Building PDF…"):
                        pdf = _build_productions_pdf(
                            selected_prods, client_name, selected_date, show_cost
                        )
                    if pdf:
                        fname = f"Productions_{client_name.replace(' ','_')}_{_fmt_date(selected_date)}.pdf"
                        st.success("Ready!")
                        st.download_button("⬇️ Download Productions PDF",
                                           data=pdf, file_name=fname,
                                           mime="application/pdf",
                                           key="dl_prod")

    # ── Menu Items tab ────────────────────────────────────────────────────────
    with tab_menu:
        if not menu_items:
            st.info("No menu item data found.")
        else:
            auto_excl = sum(1 for i in menu_items if i["auto_exclude"])
            st.markdown(f"**{len(menu_items)} menu items** · {auto_excl} auto-excluded (remarks/no recipe)")

            excl_menu = _group_excluder(
                menu_items, "item_group", "menu", extra_group_key="category"
            )
            selected_menu = _item_editor(
                menu_items, excl_menu, "menu", show_cost
            )

            if REPORTLAB_OK:
                st.divider()
                if st.button("📄 Export Menu Items PDF", type="primary",
                             use_container_width=True, key="exp_menu"):
                    with st.spinner("Building PDF…"):
                        pdf = _build_menu_pdf(
                            selected_menu, client_name, selected_date, show_cost
                        )
                    if pdf:
                        fname = f"MenuCards_{client_name.replace(' ','_')}_{_fmt_date(selected_date)}.pdf"
                        st.success("Ready!")
                        st.download_button("⬇️ Download Menu Items PDF",
                                           data=pdf, file_name=fname,
                                           mime="application/pdf",
                                           key="dl_menu")

    # ── Export All ────────────────────────────────────────────────────────────
    if REPORTLAB_OK:
        st.divider()
        if st.button("📦 Export All (Productions + Menu Items)", type="secondary",
                     use_container_width=True, key="exp_all"):
            # Use whatever is selected in each tab's editor — fall back to all non-excluded
            sel_p = [i for i in productions if not i.get("auto_exclude", False)]
            sel_m = [i for i in menu_items  if not i.get("auto_exclude", False)]
            with st.spinner("Building full PDF…"):
                pdf = _build_all_pdf(sel_p, sel_m, client_name, selected_date, show_cost)
            if pdf:
                fname = f"RecipeCards_{client_name.replace(' ','_')}_{_fmt_date(selected_date)}.pdf"
                st.success("Ready!")
                st.download_button("⬇️ Download Full PDF",
                                   data=pdf, file_name=fname,
                                   mime="application/pdf",
                                   key="dl_all")


def _fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%b_%Y")
    except Exception:
        return d


# ── PDF styles ─────────────────────────────────────────────────────────────────

def _make_styles():
    return {
        "cover_brand": ParagraphStyle(
            "cover_brand", fontSize=10, textColor=EK_SAND,
            fontName="Helvetica", alignment=TA_CENTER, letterSpacing=3, spaceAfter=4),
        "cover_title": ParagraphStyle(
            "cover_title", fontSize=28, textColor=EK_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER, leading=34, spaceAfter=6),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontSize=12, textColor=EK_SAND,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontSize=9, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER),
        "section_banner": ParagraphStyle(
            "section_banner", fontSize=13, textColor=EK_WHITE,
            fontName="Helvetica-Bold", letterSpacing=1),
        "group_header": ParagraphStyle(
            "group_header", fontSize=9, textColor=EK_MID,
            fontName="Helvetica-Bold", letterSpacing=0.5, spaceBefore=10, spaceAfter=4),
        "card_title": ParagraphStyle(
            "card_title", fontSize=13, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceAfter=2),
        "card_meta": ParagraphStyle(
            "card_meta", fontSize=8, textColor=EK_MID,
            fontName="Helvetica", spaceAfter=4),
        "ing_name": ParagraphStyle(
            "ing_name", fontSize=8, textColor=EK_DARK, fontName="Helvetica"),
        "ing_prod": ParagraphStyle(
            "ing_prod", fontSize=8, textColor=EK_DARK, fontName="Helvetica-Bold"),
        "ing_num": ParagraphStyle(
            "ing_num", fontSize=8, textColor=EK_DARK,
            fontName="Helvetica", alignment=TA_RIGHT),
        "th": ParagraphStyle(
            "th", fontSize=7, textColor=EK_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER),
        "yield_label": ParagraphStyle(
            "yield_label", fontSize=8, textColor=EK_SAND,
            fontName="Helvetica-Bold"),
        "footer": ParagraphStyle(
            "footer", fontSize=7, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER),
    }


def _add_footer(canvas, doc):
    canvas.saveState()
    w, _ = A4
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(EK_MID)
    canvas.drawCentredString(w / 2, 1.2 * cm, "EK Consulting · ek-consulting.co · Confidential")
    canvas.drawRightString(w - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.setStrokeColor(EK_GREY)
    canvas.setLineWidth(0.3)
    canvas.line(2 * cm, 1.5 * cm, w - 2 * cm, 1.5 * cm)
    canvas.restoreState()


def _cover(story, client_name, report_date, styles, subtitle="Recipe Cards"):
    cover_bg = Table([[""]], colWidths=[17*cm], rowHeights=[2.5*cm])
    cover_bg.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), EK_DARK),
        ("GRID",       (0,0), (-1,-1), 0, EK_DARK),
    ]))
    story.append(cover_bg)
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("EK CONSULTING", styles["cover_brand"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="50%", thickness=1.5, color=EK_SAND, hAlign="CENTER"))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(subtitle, styles["cover_title"]))
    story.append(Paragraph(client_name.upper(), styles["cover_sub"]))
    try:
        story.append(Paragraph(
            datetime.strptime(report_date, "%Y-%m-%d").strftime("%B %Y"),
            styles["cover_meta"]))
    except Exception:
        story.append(Paragraph(report_date, styles["cover_meta"]))
    story.append(PageBreak())


def _section_banner(story, title, styles):
    tbl = Table([[Paragraph(title.upper(), styles["section_banner"])]],
                colWidths=[17*cm], rowHeights=[0.7*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), EK_DARK),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING",   (0,0), (-1,-1), 10),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.3*cm))


# ── Production card PDF ────────────────────────────────────────────────────────

def _pdf_production_card(prod: dict, styles: dict, show_cost: bool) -> list:
    elements = []

    yq = prod.get("yield_qty")
    yu = prod.get("yield_unit") or ""
    yield_str = f"YIELD: {yq:g} {yu}" if yq is not None else ""

    meta_parts = [prod.get("item_group", "")]
    if yield_str:
        meta_parts.append(yield_str)

    name_data = [[
        Paragraph(prod["name"], styles["card_title"]),
        Paragraph(" · ".join(p for p in meta_parts if p), styles["card_meta"]),
    ]]
    name_tbl = Table(name_data, colWidths=[10*cm, 7*cm])
    name_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    elements.append(name_tbl)
    elements.append(HRFlowable(width="100%", thickness=0.5, color=EK_SAND, spaceAfter=4))

    ings = prod.get("ingredients", [])
    if ings:
        if show_cost:
            headers = ["Ingredient", "Qty", "Unit", "Avg Cost"]
            col_w   = [9*cm, 2*cm, 2*cm, 4*cm]
        else:
            headers = ["Ingredient", "Qty", "Unit"]
            col_w   = [10*cm, 3*cm, 4*cm]

        rows = [[Paragraph(h, styles["th"]) for h in headers]]
        for ing in ings:
            qty_str = f"{ing['qty']:g}" if ing.get("qty") is not None else "—"
            if show_cost:
                ac = ing.get("cost")
                row = [
                    Paragraph(ing["name"], styles["ing_name"]),
                    Paragraph(qty_str, styles["ing_num"]),
                    Paragraph(ing["unit"] or "—", styles["ing_name"]),
                    Paragraph(f"${ac:,.4f}" if ac is not None else "—", styles["ing_num"]),
                ]
            else:
                row = [
                    Paragraph(ing["name"], styles["ing_name"]),
                    Paragraph(qty_str, styles["ing_num"]),
                    Paragraph(ing["unit"] or "—", styles["ing_name"]),
                ]
            rows.append(row)

        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,0),  EK_DARK),
            ("TEXTCOLOR",      (0,0), (-1,0),  EK_WHITE),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [EK_WHITE, EK_LIGHT]),
            ("GRID",           (0,0), (-1,-1), 0.3, EK_GREY),
            ("FONTSIZE",       (0,0), (-1,-1), 7),
            ("LEFTPADDING",    (0,0), (-1,-1), 4),
            ("RIGHTPADDING",   (0,0), (-1,-1), 4),
            ("TOPPADDING",     (0,0), (-1,-1), 3),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 3),
            ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN",          (1,1), (-1,-1), "RIGHT"),
        ]))
        elements.append(tbl)

    elements.append(Spacer(1, 0.5*cm))
    return elements


# ── Menu item card PDF ─────────────────────────────────────────────────────────

def _pdf_menu_card(dish: dict, styles: dict, show_cost: bool) -> list:
    elements = []

    meta_parts = [dish.get("category", ""), dish.get("item_group", "")]
    if show_cost and dish.get("total_cost"):
        meta_parts.append(f"Cost: ${dish['total_cost']:,.3f}")

    name_data = [[
        Paragraph(dish["name"], styles["card_title"]),
        Paragraph(" · ".join(p for p in meta_parts if p), styles["card_meta"]),
    ]]
    name_tbl = Table(name_data, colWidths=[10*cm, 7*cm])
    name_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    elements.append(name_tbl)
    elements.append(HRFlowable(width="100%", thickness=0.5, color=EK_SAND, spaceAfter=4))

    ings = dish.get("ingredients", [])
    if ings:
        if show_cost:
            headers = ["Ingredient", "Qty", "Unit", "Avg Cost", "Total"]
            col_w   = [7.5*cm, 1.5*cm, 1.5*cm, 2*cm, 2*cm]
        else:
            headers = ["Ingredient", "Qty", "Unit"]
            col_w   = [10*cm, 2.5*cm, 2*cm]

        rows = [[Paragraph(h, styles["th"]) for h in headers]]
        style_cmds = [
            ("GRID",           (0,0), (-1,-1), 0.3, EK_GREY),
            ("FONTSIZE",       (0,0), (-1,-1), 7),
            ("LEFTPADDING",    (0,0), (-1,-1), 4),
            ("RIGHTPADDING",   (0,0), (-1,-1), 4),
            ("TOPPADDING",     (0,0), (-1,-1), 3),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 3),
            ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN",          (1,1), (-1,-1), "RIGHT"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [EK_WHITE, EK_LIGHT]),
            ("BACKGROUND",     (0,0), (-1,0),  EK_DARK),
            ("TEXTCOLOR",      (0,0), (-1,0),  EK_WHITE),
        ]

        for row_idx, ing in enumerate(ings, start=1):
            qty_str    = f"{ing['qty']:g}" if ing.get("qty") is not None else "—"
            name_style = styles["ing_prod"] if ing["is_production"] else styles["ing_name"]

            if show_cost:
                ac = ing.get("avg_cost")
                tc = ing.get("total_cost")
                row = [
                    Paragraph(ing["name"], name_style),
                    Paragraph(qty_str, styles["ing_num"]),
                    Paragraph(ing["unit"] or "—", styles["ing_name"]),
                    Paragraph(f"${ac:,.4f}" if ac is not None else "—", styles["ing_num"]),
                    Paragraph(f"${tc:,.3f}" if tc is not None else "—", styles["ing_num"]),
                ]
            else:
                row = [
                    Paragraph(ing["name"], name_style),
                    Paragraph(qty_str, styles["ing_num"]),
                    Paragraph(ing["unit"] or "—", styles["ing_name"]),
                ]
            rows.append(row)

            # Production rows: sand bg, dark bold text — appended last to win
            if ing["is_production"]:
                style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), EK_SAND))
                style_cmds.append(("TEXTCOLOR",  (0, row_idx), (-1, row_idx), EK_DARK))
                style_cmds.append(("FONTNAME",   (0, row_idx), (0, row_idx),  "Helvetica-Bold"))

        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle(style_cmds))
        elements.append(tbl)

    elements.append(Spacer(1, 0.5*cm))
    return elements


# ── PDF builders ───────────────────────────────────────────────────────────────

def _build_productions_pdf(productions: list, client_name: str,
                            report_date: str, show_cost: bool):
    if not REPORTLAB_OK or not productions:
        return None
    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2.2*cm)
        styles = _make_styles()
        story  = []
        _cover(story, client_name, report_date, styles, subtitle="Production Cards")

        current_group = None
        for prod in sorted(productions, key=lambda p: (p["item_group"], p["name"])):
            if prod["item_group"] != current_group:
                current_group = prod["item_group"]
                _section_banner(story, current_group or "Productions", styles)
            story.append(KeepTogether(_pdf_production_card(prod, styles, show_cost)))

        doc.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.error(f"PDF error: {e}")
        return None


def _build_menu_pdf(menu_items: list, client_name: str,
                    report_date: str, show_cost: bool):
    if not REPORTLAB_OK or not menu_items:
        return None
    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2.2*cm)
        styles = _make_styles()
        story  = []
        _cover(story, client_name, report_date, styles, subtitle="Menu Item Cards")

        current_cat   = None
        current_group = None
        for dish in sorted(menu_items, key=lambda d: (d["category"], d["item_group"], d["name"])):
            if dish["category"] != current_cat:
                current_cat = dish["category"]
                _section_banner(story, current_cat or "Menu Items", styles)
                current_group = None
            if dish["item_group"] != current_group:
                current_group = dish["item_group"]
                story.append(Paragraph(
                    (current_group or "").upper(), styles["group_header"]
                ))
            story.append(KeepTogether(_pdf_menu_card(dish, styles, show_cost)))

        doc.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.error(f"PDF error: {e}")
        return None


def _build_all_pdf(productions: list, menu_items: list,
                   client_name: str, report_date: str, show_cost: bool):
    if not REPORTLAB_OK:
        return None
    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2.2*cm)
        styles = _make_styles()
        story  = []
        _cover(story, client_name, report_date, styles, subtitle="Recipe Cards")

        # ── Productions section ───────────────────────────────────────────────
        if productions:
            _section_banner(story, "Productions", styles)
            current_group = None
            for prod in sorted(productions, key=lambda p: (p["item_group"], p["name"])):
                if prod["item_group"] != current_group:
                    current_group = prod["item_group"]
                    story.append(Paragraph(
                        (current_group or "").upper(), styles["group_header"]
                    ))
                story.append(KeepTogether(_pdf_production_card(prod, styles, show_cost)))
            story.append(PageBreak())

        # ── Menu Items section ────────────────────────────────────────────────
        if menu_items:
            current_cat   = None
            current_group = None
            for dish in sorted(menu_items, key=lambda d: (d["category"], d["item_group"], d["name"])):
                if dish["category"] != current_cat:
                    current_cat = dish["category"]
                    _section_banner(story, current_cat or "Menu Items", styles)
                    current_group = None
                if dish["item_group"] != current_group:
                    current_group = dish["item_group"]
                    story.append(Paragraph(
                        (current_group or "").upper(), styles["group_header"]
                    ))
                story.append(KeepTogether(_pdf_menu_card(dish, styles, show_cost)))

        doc.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        st.error(f"PDF error: {e}")
        return None
