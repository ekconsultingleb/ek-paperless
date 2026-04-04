# modules/recipe_report.py
"""
Recipe Card Report
------------------
Reads ac_recipes + ac_sub_recipes, groups by menu_item,
renders expandable cards in the UI, and exports a clean
per-item PDF menu card.
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

# ── Brand colours ─────────────────────────────────────────────────────────────
EK_DARK   = colors.HexColor("#1B252C")
EK_SAND   = colors.HexColor("#E3C5AD")
EK_LIGHT  = colors.HexColor("#F5F0EB")
EK_MID    = colors.HexColor("#8C7B6E")
EK_WHITE  = colors.white
EK_GREY   = colors.HexColor("#D3D1C7")
EK_ACCENT = colors.HexColor("#C4A882")
EK_PROD   = colors.HexColor("#2E3D47")   # darker tint for production rows


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _get_client_id(supabase: Client, client_name: str):
    try:
        res = supabase.table("clients").select("id").eq(
            "client_name", client_name
        ).single().execute()
        return res.data["id"] if res.data else None
    except Exception:
        return None


def _load_data(supabase: Client, client_id: int, report_date: str):
    """Return (recipes_rows, sub_recipes_rows) as plain lists of dicts."""
    try:
        r = supabase.table("ac_recipes").select(
            "category,item_group,menu_items,product_description,qty,unit,avg_cost,total_cost,sales"
        ).eq("client_id", client_id).eq("report_date", report_date).execute()
        recipes = r.data or []
    except Exception as e:
        st.error(f"Error loading ac_recipes: {e}")
        recipes = []

    try:
        s = supabase.table("ac_sub_recipes").select(
            "production_name,product_description,qty,unit_name,cost,average_cost,qty_to_prepared,prepared_unit,cost_for_1"
        ).eq("client_id", client_id).eq("report_date", report_date).execute()
        subs = s.data or []
    except Exception as e:
        st.error(f"Error loading ac_sub_recipes: {e}")
        subs = []

    return recipes, subs


def _get_dates(supabase: Client, client_id: int) -> list:
    try:
        res = supabase.table("ac_recipes").select("report_date").eq(
            "client_id", client_id
        ).execute()
        return sorted({r["report_date"] for r in (res.data or [])}, reverse=True)
    except Exception:
        return []


# ── Data builder ──────────────────────────────────────────────────────────────

def _build_cards(recipes: list, subs: list) -> dict:
    """
    Returns:
        {
          category: {
            item_group: [
              {
                name, total_cost, sales,
                ingredients: [
                  { name, qty, unit, avg_cost, total_cost,
                    is_production, sub_ingredients: [...] }
                ]
              }
            ]
          }
        }
    """
    # Build production lookup: production_name → [sub-ingredient rows]
    prod_lookup: dict[str, list] = {}
    for row in subs:
        pn = row.get("production_name") or ""
        prod_lookup.setdefault(pn, []).append(row)

    # Group ac_recipes rows by menu_item
    dishes: dict[str, dict] = {}
    for row in recipes:
        name = row.get("menu_items") or "Unknown"
        if name not in dishes:
            dishes[name] = {
                "name":       name,
                "category":   row.get("category") or "",
                "item_group": row.get("item_group") or "",
                "sales":      row.get("sales"),
                "total_cost": 0.0,
                "ingredients": [],
            }
        desc        = row.get("product_description") or ""
        is_prod     = desc.endswith(("Prdk", "Prdb"))
        tc          = row.get("total_cost") or 0
        dishes[name]["total_cost"] += tc
        dishes[name]["ingredients"].append({
            "name":         desc,
            "qty":          row.get("qty"),
            "unit":         row.get("unit") or "",
            "avg_cost":     row.get("avg_cost"),
            "total_cost":   tc,
            "is_production": is_prod,
            "sub_ingredients": prod_lookup.get(desc, []) if is_prod else [],
        })

    # Nest into category → item_group
    tree: dict[str, dict] = {}
    for dish in dishes.values():
        cat   = dish["category"] or "Other"
        group = dish["item_group"] or "Other"
        tree.setdefault(cat, {}).setdefault(group, []).append(dish)

    # Sort
    for cat in tree:
        for group in tree[cat]:
            tree[cat][group].sort(key=lambda d: d["name"])

    return tree


# ── Streamlit UI ──────────────────────────────────────────────────────────────

def render_recipe_report(supabase: Client, user: str, role: str):
    session_client = st.session_state.get("client_name", "All")

    st.markdown("### 🍽️ Recipe Cards")
    st.caption("Menu item cards with ingredients and production details from Auto Calc.")

    if not REPORTLAB_OK:
        st.warning("reportlab not installed — PDF export unavailable. Add it to requirements.txt.")

    # Client selector for admins
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

    # Date selector
    dates = _get_dates(supabase, client_id)
    if not dates:
        st.info("No Auto Calc data found for this client. Push data via Auto Calc tab first.")
        return

    selected_date = st.selectbox(
        "📅 Report month", dates,
        format_func=lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%B %Y") if d else d,
        key="rr_date",
    )

    # Load data first so category filter has real options
    with st.spinner("Loading…"):
        recipes, subs = _load_data(supabase, client_id, selected_date)

    if not recipes:
        st.warning("No recipe data found for this period.")
        return

    tree = _build_cards(recipes, subs)
    all_cats = ["All"] + sorted(tree.keys())

    # Options row — category selectbox now has real data
    col_opt1, col_opt2, col_opt3 = st.columns(3)
    with col_opt1:
        show_cost = st.toggle("💰 Show cost", value=False, key="rr_show_cost")
    with col_opt2:
        selected_cat = st.selectbox("Filter category", all_cats, key="rr_filter_cat")
    with col_opt3:
        search = st.text_input("🔍 Search item", placeholder="e.g. Risotto", key="rr_search").strip().lower()

    st.divider()

    total_dishes = sum(len(dishes) for cat in tree.values() for dishes in cat.values())
    st.caption(f"**{total_dishes} menu items** · {len(subs and {r.get('production_name') for r in subs} or [])} productions")

    # ── Render cards ──────────────────────────────────────────────────────────
    for cat, groups in sorted(tree.items()):
        if selected_cat not in ("All", cat):
            continue

        # Category header
        st.markdown(
            f"<div style='background:linear-gradient(135deg,#1B252C,#2E3D47);"
            f"border-radius:10px;padding:10px 16px;margin:16px 0 8px;'>"
            f"<span style='color:#E3C5AD;font-size:13px;font-weight:700;"
            f"letter-spacing:0.08em;'>{cat.upper()}</span></div>",
            unsafe_allow_html=True,
        )

        for group, dishes in sorted(groups.items()):
            # Item group sub-header
            st.markdown(
                f"<div style='color:#8C7B6E;font-size:11px;font-weight:600;"
                f"letter-spacing:0.06em;text-transform:uppercase;"
                f"margin:4px 0 4px 4px;'>{group}</div>",
                unsafe_allow_html=True,
            )

            for dish in dishes:
                # Search filter
                if search and search not in dish["name"].lower():
                    continue

                _render_card(dish, show_cost)

    # ── Export button ─────────────────────────────────────────────────────────
    if REPORTLAB_OK:
        st.divider()
        col_exp1, col_exp2 = st.columns([3, 1])
        with col_exp2:
            export_cost = st.toggle("Include cost in PDF", value=False, key="rr_pdf_cost")
        with col_exp1:
            if st.button("📄 Export PDF Menu Cards", type="primary",
                         use_container_width=True, key="rr_export"):
                with st.spinner("Building PDF…"):
                    pdf = _build_pdf(tree, client_name, selected_date, export_cost)
                if pdf:
                    try:
                        d = datetime.strptime(selected_date, "%Y-%m-%d")
                        fname = f"RecipeCards_{client_name.replace(' ','_')}_{d.strftime('%b_%Y')}.pdf"
                    except Exception:
                        fname = f"RecipeCards_{client_name}.pdf"
                    st.success("PDF ready!")
                    st.download_button(
                        "⬇️ Download PDF",
                        data=pdf, file_name=fname,
                        mime="application/pdf",
                        use_container_width=True,
                        key="rr_dl",
                    )


def _render_card(dish: dict, show_cost: bool):
    """Render a single dish as a Streamlit expander card."""
    total = dish["total_cost"]

    with st.expander(dish["name"] + (f"  ·  ${total:,.3f}" if show_cost and total else ""),
                     expanded=False):

        ings = dish["ingredients"]

        cols = ["**Ingredient**", "**Qty**", "**Unit**"]
        if show_cost:
            cols += ["**Avg Cost**", "**Total Cost**"]

        col_widths = [4, 1, 1] + ([1.5, 1.5] if show_cost else [])
        header_cols = st.columns(col_widths)
        for hc, label in zip(header_cols, cols):
            hc.markdown(label)

        st.markdown("<hr style='margin:4px 0;border-color:rgba(227,197,173,0.2);'>",
                    unsafe_allow_html=True)

        for ing in ings:
            row_cols = st.columns(col_widths)
            if ing["is_production"]:
                row_cols[0].markdown(
                    f"<span style='color:#E3C5AD;font-weight:600;'>⚙️ {ing["name"]}</span>",
                    unsafe_allow_html=True,
                )
            else:
                row_cols[0].markdown(ing["name"])

            row_cols[1].markdown(f"{ing['qty']:g}" if ing["qty"] is not None else "—")
            row_cols[2].markdown(ing["unit"] or "—")

            if show_cost:
                ac = ing["avg_cost"]
                tc = ing["total_cost"]
                row_cols[3].markdown(f"${ac:,.4f}" if ac is not None else "—")
                row_cols[4].markdown(f"${tc:,.3f}" if tc is not None else "—")

        if show_cost and total:
            st.markdown(
                f"<div style='text-align:right;color:#E3C5AD;font-size:12px;"
                f"font-weight:600;margin-top:6px;'>Total cost: ${total:,.3f}</div>",
                unsafe_allow_html=True,
            )

        # ── Single card PDF export ─────────────────────────────────────────────
        if REPORTLAB_OK:
            card_key = "pdf_" + dish["name"].replace(" ", "_").replace("/", "_").replace("'", "")
            if st.button("📄 Export this card", key=card_key):
                single_tree = {dish["category"]: {dish["item_group"]: [dish]}}
                pdf = _build_pdf(single_tree, "", "", show_cost)
                if pdf:
                    fname = dish["name"].replace(" ", "_") + ".pdf"
                    st.download_button(
                        "⬇️ Download",
                        data=pdf, file_name=fname,
                        mime="application/pdf",
                        key=card_key + "_dl",
                    )


# ── PDF Builder ───────────────────────────────────────────────────────────────

def _make_styles():
    return {
        "cover_brand": ParagraphStyle(
            "cover_brand", fontSize=10, textColor=EK_SAND,
            fontName="Helvetica", alignment=TA_CENTER, letterSpacing=3, spaceAfter=4,
        ),
        "cover_title": ParagraphStyle(
            "cover_title", fontSize=28, textColor=EK_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER, leading=34, spaceAfter=6,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontSize=12, textColor=EK_SAND,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontSize=9, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER,
        ),
        "cat_header": ParagraphStyle(
            "cat_header", fontSize=12, textColor=EK_WHITE,
            fontName="Helvetica-Bold", letterSpacing=1,
        ),
        "group_header": ParagraphStyle(
            "group_header", fontSize=9, textColor=EK_MID,
            fontName="Helvetica-Bold", letterSpacing=0.5, spaceBefore=8, spaceAfter=4,
        ),
        "dish_name": ParagraphStyle(
            "dish_name", fontSize=13, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceAfter=2,
        ),
        "dish_meta": ParagraphStyle(
            "dish_meta", fontSize=8, textColor=EK_MID,
            fontName="Helvetica", spaceAfter=6,
        ),
        "ing_name": ParagraphStyle(
            "ing_name", fontSize=8, textColor=EK_DARK, fontName="Helvetica",
        ),
        "ing_prod": ParagraphStyle(
            "ing_prod", fontSize=8, textColor=EK_SAND, fontName="Helvetica-Bold",
        ),
        "ing_sub": ParagraphStyle(
            "ing_sub", fontSize=7, textColor=EK_MID, fontName="Helvetica-Oblique",
        ),
        "ing_num": ParagraphStyle(
            "ing_num", fontSize=8, textColor=EK_DARK,
            fontName="Helvetica", alignment=TA_RIGHT,
        ),
        "th": ParagraphStyle(
            "th", fontSize=7, textColor=EK_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=7, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER,
        ),
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


def _pdf_dish_card(dish: dict, styles: dict, show_cost: bool) -> list:
    """Return a list of flowables for one dish card."""
    elements = []

    # Dish name bar
    meta_parts = [dish["category"]]
    if dish["item_group"] and dish["item_group"] != dish["category"]:
        meta_parts.append(dish["item_group"])
    if show_cost and dish["total_cost"]:
        meta_parts.append(f"Total cost: ${dish['total_cost']:,.3f}")

    name_data = [[
        Paragraph(dish["name"], styles["dish_name"]),
        Paragraph(" · ".join(p for p in meta_parts if p), styles["dish_meta"]),
    ]]
    name_tbl = Table(name_data, colWidths=[10 * cm, 7 * cm])
    name_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(name_tbl)
    elements.append(HRFlowable(width="100%", thickness=0.5, color=EK_SAND, spaceAfter=4))

    # Ingredient table
    if show_cost:
        headers  = ["Ingredient", "Qty", "Unit", "Avg Cost", "Total"]
        col_w    = [7.5 * cm, 1.5 * cm, 1.5 * cm, 2 * cm, 2 * cm]
    else:
        headers  = ["Ingredient", "Qty", "Unit"]
        col_w    = [10 * cm, 2.5 * cm, 2 * cm]

    rows = [[Paragraph(h, styles["th"]) for h in headers]]

    for ing in dish["ingredients"]:
        name_style = styles["ing_prod"] if ing["is_production"] else styles["ing_name"]
        prefix     = "⚙ " if ing["is_production"] else ""
        qty_str    = f"{ing['qty']:g}" if ing["qty"] is not None else "—"

        if show_cost:
            ac = ing["avg_cost"]
            tc = ing["total_cost"]
            row = [
                Paragraph(prefix + ing["name"], name_style),
                Paragraph(qty_str, styles["ing_num"]),
                Paragraph(ing["unit"] or "—", styles["ing_name"]),
                Paragraph(f"${ac:,.4f}" if ac is not None else "—", styles["ing_num"]),
                Paragraph(f"${tc:,.3f}" if tc is not None else "—", styles["ing_num"]),
            ]
        else:
            row = [
                Paragraph(prefix + ing["name"], name_style),
                Paragraph(qty_str, styles["ing_num"]),
                Paragraph(ing["unit"] or "—", styles["ing_name"]),
            ]
        rows.append(row)



    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    n_rows = len(rows)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0),      EK_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),      EK_WHITE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),     [EK_WHITE, EK_LIGHT]),
        ("GRID",          (0, 0), (-1, -1),     0.3, EK_GREY),
        ("FONTSIZE",      (0, 0), (-1, -1),     7),
        ("LEFTPADDING",   (0, 0), (-1, -1),     4),
        ("RIGHTPADDING",  (0, 0), (-1, -1),     4),
        ("TOPPADDING",    (0, 0), (-1, -1),     3),
        ("BOTTOMPADDING", (0, 0), (-1, -1),     3),
        ("VALIGN",        (0, 0), (-1, -1),     "MIDDLE"),
        ("ALIGN",         (1, 1), (-1, -1),     "RIGHT"),
    ]
    # Production rows: sand background with dark text — clearly distinct
    for row_idx, ing in enumerate(dish["ingredients"], start=1):
        if ing["is_production"]:
            style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), EK_SAND))
            style_cmds.append(("TEXTCOLOR",  (0, row_idx), (-1, row_idx), EK_DARK))
            style_cmds.append(("FONTNAME",   (0, row_idx), (0, row_idx), "Helvetica-Bold"))

    tbl.setStyle(TableStyle(style_cmds))
    elements.append(tbl)
    elements.append(Spacer(1, 0.6 * cm))

    return elements


def _build_pdf(tree: dict, client_name: str, report_date: str, show_cost: bool) -> bytes | None:
    if not REPORTLAB_OK:
        return None
    try:
        buf    = io.BytesIO()
        doc    = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2.2*cm,
        )
        styles = _make_styles()
        story  = []

        # ── Cover ─────────────────────────────────────────────────────────────
        total_dishes = sum(len(d) for cat in tree.values() for d in cat.values())
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
        story.append(Paragraph("Recipe Cards", styles["cover_title"]))
        story.append(Paragraph(client_name.upper(), styles["cover_sub"]))
        try:
            d = datetime.strptime(report_date, "%Y-%m-%d")
            story.append(Paragraph(d.strftime("%B %Y"), styles["cover_meta"]))
        except Exception:
            story.append(Paragraph(report_date, styles["cover_meta"]))
        story.append(Spacer(1, 1*cm))

        kpi = Table(
            [[Paragraph("MENU ITEMS", styles["cover_meta"]),
              Paragraph("GENERATED", styles["cover_meta"])],
             [Paragraph(str(total_dishes), ParagraphStyle("kv", fontSize=18,
              fontName="Helvetica-Bold", textColor=EK_DARK, alignment=TA_CENTER)),
              Paragraph(datetime.now().strftime("%d %b %Y"), ParagraphStyle("kv2", fontSize=18,
              fontName="Helvetica-Bold", textColor=EK_DARK, alignment=TA_CENTER))]],
            colWidths=[8.5*cm, 8.5*cm],
        )
        kpi.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,-1), EK_LIGHT),
            ("GRID",           (0,0), (-1,-1), 0.5, EK_GREY),
            ("TOPPADDING",     (0,0), (-1,-1), 10),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 10),
            ("ALIGN",          (0,0), (-1,-1), "CENTER"),
        ]))
        story.append(kpi)
        story.append(PageBreak())

        # ── Cards by category ─────────────────────────────────────────────────
        for cat, groups in sorted(tree.items()):
            # Category banner
            cat_tbl = Table(
                [[Paragraph(cat.upper(), styles["cat_header"])]],
                colWidths=[17*cm], rowHeights=[0.7*cm],
            )
            cat_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,-1), EK_DARK),
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
                ("TOPPADDING",    (0,0), (-1,-1), 4),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ]))
            story.append(cat_tbl)
            story.append(Spacer(1, 0.3*cm))

            for group, dishes in sorted(groups.items()):
                story.append(Paragraph(group.upper(), styles["group_header"]))

                for dish in dishes:
                    card_elements = _pdf_dish_card(dish, styles, show_cost)
                    story.append(KeepTogether(card_elements))

        # ── Back page ─────────────────────────────────────────────────────────
        story.append(PageBreak())
        story.append(Spacer(1, 3*cm))
        story.append(HRFlowable(width="40%", thickness=1, color=EK_SAND, hAlign="CENTER"))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"End of Report · {client_name} · {report_date}",
            styles["footer"],
        ))

        doc.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        st.error(f"PDF generation error: {e}")
        return None
