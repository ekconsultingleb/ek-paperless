# modules/recipe_report.py
"""
Recipe Report Generator
Reads from ac_recipes, ac_sub_recipes (Auto Calc tables) and the
Paperless recipes / recipe_lines / recipe_sub_lines tables, then
produces a luxury PDF report: cover + summary table + per-recipe detail cards.
"""

import io
import streamlit as st
from datetime import datetime
from supabase import Client

# ─────────────────────────────────────────────
# REPORTLAB IMPORTS
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# BRAND COLOURS
# ─────────────────────────────────────────────
EK_DARK   = colors.HexColor("#1B252C")
EK_SAND   = colors.HexColor("#E3C5AD")
EK_LIGHT  = colors.HexColor("#F5F0EB")
EK_MID    = colors.HexColor("#8C7B6E")
EK_WHITE  = colors.white
EK_GREY   = colors.HexColor("#D3D1C7")
EK_ACCENT = colors.HexColor("#C4A882")


# ─────────────────────────────────────────────
# SUPABASE HELPERS
# ─────────────────────────────────────────────

def _get_client_id(supabase: Client, client_name: str):
    try:
        res = supabase.table("clients").select("id").eq(
            "client_name", client_name
        ).single().execute()
        return res.data["id"] if res.data else None
    except Exception:
        return None


def _get_report_dates(supabase: Client, client_id: int, table: str) -> list:
    try:
        res = supabase.table(table).select("report_date").eq(
            "client_id", client_id
        ).execute()
        dates = sorted(
            {r["report_date"] for r in (res.data or [])}, reverse=True
        )
        return dates
    except Exception:
        return []


def _get_ac_recipes(supabase: Client, client_id: int, report_date: str) -> list:
    try:
        res = supabase.table("ac_recipes").select("*").eq(
            "client_id", client_id
        ).eq("report_date", report_date).order("category").order(
            "menu_items"
        ).execute()
        return res.data or []
    except Exception as e:
        st.error(f"Error fetching ac_recipes: {e}")
        return []


def _get_ac_sub_recipes(supabase: Client, client_id: int, report_date: str) -> list:
    try:
        res = supabase.table("ac_sub_recipes").select("*").eq(
            "client_id", client_id
        ).eq("report_date", report_date).order("production_name").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Error fetching ac_sub_recipes: {e}")
        return []


def _get_paperless_recipes(supabase: Client, client_name: str) -> list:
    """Paperless chef-entered recipes with their lines."""
    try:
        res = supabase.table("recipes").select("*").eq(
            "client_name", client_name
        ).order("category").order("name").execute()
        recipes = res.data or []
        for r in recipes:
            lines_res = supabase.table("recipe_lines").select("*").eq(
                "recipe_id", r["id"]
            ).execute()
            lines = lines_res.data or []
            # Fetch sub_lines per line
            for line in lines:
                sl_res = supabase.table("recipe_sub_lines").select("*").eq(
                    "parent_line_id", line["id"]
                ).execute()
                line["sub_lines_data"] = sl_res.data or []
            r["lines"] = lines
        return recipes
    except Exception as e:
        st.error(f"Error fetching Paperless recipes: {e}")
        return []


# ─────────────────────────────────────────────
# PDF STYLES
# ─────────────────────────────────────────────

def _make_styles():
    return {
        "cover_brand": ParagraphStyle(
            "cover_brand", fontSize=11, textColor=EK_SAND,
            fontName="Helvetica", spaceAfter=4, alignment=TA_CENTER,
            letterSpacing=3
        ),
        "cover_title": ParagraphStyle(
            "cover_title", fontSize=32, textColor=EK_WHITE,
            fontName="Helvetica-Bold", spaceAfter=8, alignment=TA_CENTER,
            leading=38
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", fontSize=13, textColor=EK_SAND,
            fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta", fontSize=9, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER
        ),
        "section_header": ParagraphStyle(
            "section_header", fontSize=14, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceBefore=16, spaceAfter=8,
            letterSpacing=1
        ),
        "card_title": ParagraphStyle(
            "card_title", fontSize=13, textColor=EK_DARK,
            fontName="Helvetica-Bold", spaceAfter=2
        ),
        "card_meta": ParagraphStyle(
            "card_meta", fontSize=9, textColor=EK_MID,
            fontName="Helvetica", spaceAfter=6
        ),
        "table_header": ParagraphStyle(
            "table_header", fontSize=8, textColor=EK_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontSize=8, textColor=EK_DARK,
            fontName="Helvetica"
        ),
        "table_cell_r": ParagraphStyle(
            "table_cell_r", fontSize=8, textColor=EK_DARK,
            fontName="Helvetica", alignment=TA_RIGHT
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", fontSize=7, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", fontSize=13, textColor=EK_DARK,
            fontName="Helvetica-Bold", alignment=TA_CENTER
        ),
        "method_body": ParagraphStyle(
            "method_body", fontSize=9, textColor=EK_DARK,
            fontName="Helvetica", leading=15
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=7, textColor=EK_MID,
            fontName="Helvetica", alignment=TA_CENTER
        ),
        "sub_label": ParagraphStyle(
            "sub_label", fontSize=7, textColor=EK_MID,
            fontName="Helvetica-Oblique"
        ),
    }


# ─────────────────────────────────────────────
# COVER PAGE
# ─────────────────────────────────────────────

def _cover_page(story, client_name: str, report_date: str, styles: dict,
                total_recipes: int, total_sub_recipes: int):
    # Dark full-page feel via a tall coloured table
    cover_data = [[""]]
    cover_tbl = Table(cover_data, colWidths=[17*cm], rowHeights=[3*cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), EK_DARK),
        ("GRID",       (0,0), (-1,-1), 0, EK_DARK),
    ]))
    story.append(cover_tbl)
    story.append(Spacer(1, 1.5*cm))

    story.append(Paragraph("EK CONSULTING", styles["cover_brand"]))
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="60%", thickness=1.5, color=EK_SAND,
                             hAlign="CENTER"))
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph("Recipe &amp; Cost Report", styles["cover_title"]))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(client_name.upper(), styles["cover_sub"]))
    story.append(Spacer(1, 0.2*cm))

    try:
        d = datetime.strptime(report_date, "%Y-%m-%d")
        date_str = d.strftime("%B %Y")
    except Exception:
        date_str = report_date
    story.append(Paragraph(date_str, styles["cover_meta"]))
    story.append(Spacer(1, 1.5*cm))
    story.append(HRFlowable(width="40%", thickness=0.5, color=EK_GREY,
                             hAlign="CENTER"))
    story.append(Spacer(1, 1*cm))

    # KPI boxes
    kpi_data = [[
        Paragraph("MENU ITEMS", styles["kpi_label"]),
        Paragraph("SUB-RECIPES", styles["kpi_label"]),
        Paragraph("GENERATED", styles["kpi_label"]),
    ],[
        Paragraph(str(total_recipes), styles["kpi_value"]),
        Paragraph(str(total_sub_recipes), styles["kpi_value"]),
        Paragraph(datetime.now().strftime("%d %b %Y"), styles["kpi_value"]),
    ]]
    kpi_tbl = Table(kpi_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), EK_LIGHT),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("GRID",        (0,0), (-1,-1), 0.5, EK_GREY),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(kpi_tbl)
    story.append(PageBreak())


# ─────────────────────────────────────────────
# SUMMARY TABLE  — ac_recipes
# ─────────────────────────────────────────────

def _summary_table(story, recipes: list, styles: dict):
    if not recipes:
        return

    story.append(Paragraph("Menu Items — Cost Summary", styles["section_header"]))
    story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND,
                             spaceAfter=8))

    headers = ["Category", "Menu Item", "Description", "Qty", "Unit",
               "Avg Cost", "Total Cost", "Sales"]
    col_w   = [2.5*cm, 4*cm, 3.5*cm, 1.2*cm, 1.2*cm, 2*cm, 2*cm, 2*cm]

    header_row = [Paragraph(h, styles["table_header"]) for h in headers]
    rows = [header_row]

    current_cat = None
    for r in recipes:
        cat = r.get("category") or "—"
        if cat != current_cat:
            current_cat = cat

        def _p(val, right=False):
            s = styles["table_cell_r"] if right else styles["table_cell"]
            return Paragraph(str(val) if val is not None else "—", s)

        avg_cost   = r.get("avg_cost")
        total_cost = r.get("total_cost")
        sales      = r.get("sales")

        rows.append([
            _p(cat),
            _p(r.get("menu_items") or "—"),
            _p(r.get("product_description") or "—"),
            _p(r.get("qty") or "—", right=True),
            _p(r.get("unit") or "—"),
            _p(f"${avg_cost:,.3f}"   if avg_cost   is not None else "—", right=True),
            _p(f"${total_cost:,.2f}" if total_cost is not None else "—", right=True),
            _p(f"${sales:,.2f}"      if sales      is not None else "—", right=True),
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  EK_DARK),
        ("TEXTCOLOR",      (0,0), (-1,0),  EK_WHITE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [EK_WHITE, EK_LIGHT]),
        ("GRID",           (0,0), (-1,-1), 0.3, EK_GREY),
        ("FONTSIZE",       (0,0), (-1,-1), 8),
        ("LEFTPADDING",    (0,0), (-1,-1), 5),
        ("RIGHTPADDING",   (0,0), (-1,-1), 5),
        ("TOPPADDING",     (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 4),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(PageBreak())


# ─────────────────────────────────────────────
# SUB-RECIPE SUMMARY TABLE
# ─────────────────────────────────────────────

def _sub_recipe_summary(story, sub_recipes: list, styles: dict):
    if not sub_recipes:
        return

    story.append(Paragraph("Sub-Recipes — Production Summary", styles["section_header"]))
    story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND,
                             spaceAfter=8))

    headers = ["Production Name", "Description", "Qty to Prep", "Prep Unit",
               "Cost / 1", "Avg Cost", "Total Prd", "Sales"]
    col_w   = [3.5*cm, 3*cm, 1.8*cm, 1.8*cm, 2*cm, 2*cm, 2*cm, 2.4*cm]

    header_row = [Paragraph(h, styles["table_header"]) for h in headers]
    rows = [header_row]

    for r in sub_recipes:
        def _p(val, right=False):
            s = styles["table_cell_r"] if right else styles["table_cell"]
            return Paragraph(str(val) if val is not None else "—", s)

        cost1   = r.get("cost_for_1")
        avg_c   = r.get("average_cost")
        tot_prd = r.get("total_prd")
        sales   = r.get("sales")

        rows.append([
            _p(r.get("production_name") or "—"),
            _p(r.get("product_description") or "—"),
            _p(r.get("qty_to_prepared") or "—", right=True),
            _p(r.get("prepared_unit") or "—"),
            _p(f"${cost1:,.3f}"   if cost1   is not None else "—", right=True),
            _p(f"${avg_c:,.3f}"   if avg_c   is not None else "—", right=True),
            _p(f"{tot_prd:,.2f}"  if tot_prd is not None else "—", right=True),
            _p(f"{sales:,.2f}"    if sales   is not None else "—", right=True),
        ])

    tbl = Table(rows, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  EK_DARK),
        ("TEXTCOLOR",      (0,0), (-1,0),  EK_WHITE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [EK_WHITE, EK_LIGHT]),
        ("GRID",           (0,0), (-1,-1), 0.3, EK_GREY),
        ("FONTSIZE",       (0,0), (-1,-1), 8),
        ("LEFTPADDING",    (0,0), (-1,-1), 5),
        ("RIGHTPADDING",   (0,0), (-1,-1), 5),
        ("TOPPADDING",     (0,0), (-1,-1), 4),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 4),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(PageBreak())


# ─────────────────────────────────────────────
# DETAIL CARDS — Paperless recipes
# ─────────────────────────────────────────────

def _recipe_detail_cards(story, recipes: list, styles: dict):
    if not recipes:
        return

    story.append(Paragraph("Recipe Detail Cards", styles["section_header"]))
    story.append(HRFlowable(width="100%", thickness=1, color=EK_SAND,
                             spaceAfter=12))

    # Group by category
    from collections import defaultdict
    by_cat = defaultdict(list)
    for r in recipes:
        by_cat[r.get("category", "Other")].append(r)

    for cat, cat_recipes in by_cat.items():
        # Category divider
        cat_tbl = Table([[Paragraph(cat.upper(), ParagraphStyle(
            "ch", fontSize=9, textColor=EK_WHITE, fontName="Helvetica-Bold",
            leftIndent=6
        ))]],
            colWidths=[17*cm], rowHeights=[0.6*cm]
        )
        cat_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), EK_ACCENT),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
        ]))
        story.append(cat_tbl)
        story.append(Spacer(1, 0.3*cm))

        for recipe in cat_recipes:
            _single_recipe_card(story, recipe, styles)

    story.append(PageBreak())


def _single_recipe_card(story, recipe: dict, styles: dict):
    elements = []

    # Header bar
    portions   = recipe.get("portions", 1)
    yield_unit = recipe.get("yield_unit") or "portion"
    cost_pp    = recipe.get("cost_per_portion")
    meta_parts = [
        f"{portions} {yield_unit}",
        recipe.get("category", ""),
    ]
    if cost_pp:
        meta_parts.append(f"Cost: ${cost_pp:.3f}/portion")

    name_bar_data = [[
        Paragraph(recipe.get("name", "—"), styles["card_title"]),
        Paragraph(" · ".join(p for p in meta_parts if p), styles["card_meta"]),
    ]]
    name_bar = Table(name_bar_data, colWidths=[9*cm, 8*cm])
    name_bar.setStyle(TableStyle([
        ("VALIGN",       (0,0), (-1,-1), "BOTTOM"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 2),
    ]))
    elements.append(name_bar)
    elements.append(HRFlowable(width="100%", thickness=0.5, color=EK_GREY,
                                spaceAfter=6))

    # Ingredient table
    lines = recipe.get("lines", [])
    if lines:
        ing_headers = ["#", "Ingredient", "Qty", "Unit", "Type", "Sub-lines"]
        ing_col_w   = [0.8*cm, 5.5*cm, 1.5*cm, 1.5*cm, 2*cm, 5.7*cm]

        ing_rows = [[Paragraph(h, styles["table_header"]) for h in ing_headers]]
        for i, line in enumerate(lines, 1):
            display = (
                line.get("ai_resolved") or
                line.get("chef_input") or
                line.get("item_name") or "—"
            )
            qty  = line.get("qty", "")
            unit = line.get("unit", "")
            typ  = "Production" if line.get("is_production") else "Purchase"

            # Sub-lines summary
            sub_lines = line.get("sub_lines_data", [])
            if sub_lines:
                sub_text = ", ".join(
                    f"{sl.get('chef_input','?')} {sl.get('qty','')} {sl.get('unit','')}"
                    for sl in sub_lines
                )
            elif line.get("sub_lines"):
                # JSONB fallback
                import json
                try:
                    sl_data = line["sub_lines"]
                    if isinstance(sl_data, str):
                        sl_data = json.loads(sl_data)
                    sub_text = ", ".join(
                        f"{sl.get('chef_input','?')} {sl.get('qty','')} {sl.get('unit','')}"
                        for sl in (sl_data or [])
                    )
                except Exception:
                    sub_text = "—"
            else:
                sub_text = "—"

            ing_rows.append([
                Paragraph(str(i), styles["table_cell"]),
                Paragraph(display, styles["table_cell"]),
                Paragraph(str(qty) if qty else "—", styles["table_cell_r"]),
                Paragraph(unit or "—", styles["table_cell"]),
                Paragraph(typ, styles["table_cell"]),
                Paragraph(sub_text, styles["sub_label"]),
            ])

        ing_tbl = Table(ing_rows, colWidths=ing_col_w, repeatRows=1)
        ing_tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,0),  EK_DARK),
            ("TEXTCOLOR",      (0,0), (-1,0),  EK_WHITE),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [EK_WHITE, EK_LIGHT]),
            ("GRID",           (0,0), (-1,-1), 0.3, EK_GREY),
            ("FONTSIZE",       (0,0), (-1,-1), 8),
            ("LEFTPADDING",    (0,0), (-1,-1), 4),
            ("RIGHTPADDING",   (0,0), (-1,-1), 4),
            ("TOPPADDING",     (0,0), (-1,-1), 3),
            ("BOTTOMPADDING",  (0,0), (-1,-1), 3),
            ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
        ]))
        elements.append(ing_tbl)

    # Method
    method = recipe.get("method", "")
    if method:
        elements.append(Spacer(1, 0.25*cm))
        elements.append(Paragraph("Method of Preparation", ParagraphStyle(
            "mh", fontSize=8, textColor=EK_MID, fontName="Helvetica-Bold",
            spaceBefore=4, spaceAfter=2
        )))
        for ln in method.split("\n"):
            if ln.strip():
                elements.append(Paragraph(ln.strip(), styles["method_body"]))

    elements.append(Spacer(1, 0.5*cm))
    story.append(KeepTogether(elements))


# ─────────────────────────────────────────────
# FOOTER CALLBACK
# ─────────────────────────────────────────────

def _add_footer(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(EK_MID)
    canvas.drawCentredString(
        w / 2, 1.2*cm,
        f"EK Consulting · ek-consulting.co · Confidential"
    )
    canvas.drawRightString(
        w - 2*cm, 1.2*cm,
        f"Page {doc.page}"
    )
    canvas.setStrokeColor(EK_GREY)
    canvas.setLineWidth(0.5)
    canvas.line(2*cm, 1.5*cm, w - 2*cm, 1.5*cm)
    canvas.restoreState()


# ─────────────────────────────────────────────
# MASTER PDF BUILDER
# ─────────────────────────────────────────────

def generate_recipe_report_pdf(
    client_name:   str,
    report_date:   str,
    ac_recipes:    list,
    ac_sub_recipes: list,
    paperless_recipes: list,
) -> "bytes | None":
    if not REPORTLAB_OK:
        st.error("reportlab not installed. Add it to requirements.txt.")
        return None

    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2*cm, bottomMargin=2.2*cm,
        )
        styles = _make_styles()
        story  = []

        _cover_page(
            story, client_name, report_date, styles,
            total_recipes=len(ac_recipes),
            total_sub_recipes=len(ac_sub_recipes),
        )
        _summary_table(story, ac_recipes, styles)
        _sub_recipe_summary(story, ac_sub_recipes, styles)
        _recipe_detail_cards(story, paperless_recipes, styles)

        # Final footer page
        story.append(Spacer(1, 2*cm))
        story.append(HRFlowable(width="40%", thickness=1, color=EK_SAND,
                                 hAlign="CENTER"))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"End of Report · {client_name} · {report_date}",
            styles["footer"]
        ))

        doc.build(story, onFirstPage=_add_footer, onLaterPages=_add_footer)
        buffer.seek(0)
        return buffer.read()

    except Exception as e:
        st.error(f"PDF generation error: {e}")
        return None


# ─────────────────────────────────────────────
# STREAMLIT UI
# ─────────────────────────────────────────────

def render_recipe_report(supabase: Client, user: str, role: str):
    session_client = st.session_state.get("client_name", "All")

    st.markdown("### Recipe Report Generator")
    st.caption(
        "Combines Auto Calc costing data with Paperless recipe cards "
        "into a single luxury PDF report."
    )

    if not REPORTLAB_OK:
        st.error("reportlab is required. Add `reportlab` to requirements.txt.")
        return

    # Admins see a client selector; outlet users use their assigned client
    if role in ("admin", "admin_all") or session_client.lower() in ("all", "", "none"):
        try:
            clients_res = supabase.table("clients").select("client_name").order("client_name").execute()
            clients_list = [r["client_name"] for r in (clients_res.data or []) if r.get("client_name")]
        except Exception:
            clients_list = []
        if not clients_list:
            st.warning("No clients found in the clients table.")
            return
        client_name = st.selectbox("🏢 Select Client", clients_list, key="rr_client")
    else:
        client_name = session_client

    client_id = _get_client_id(supabase, client_name)
    if not client_id:
        st.warning(f"Client **{client_name}** not found in clients table.")
        return

    # ── Date selector ────────────────────────────────────
    st.markdown("#### Report period")
    ac_dates  = _get_report_dates(supabase, client_id, "ac_recipes")
    sub_dates = _get_report_dates(supabase, client_id, "ac_sub_recipes")
    all_dates = sorted(set(ac_dates + sub_dates), reverse=True)

    if not all_dates:
        st.info(
            "No Auto Calc data found for this client. "
            "Push data via the Auto Calc Reader first."
        )
        return

    selected_date = st.selectbox(
        "Select report month",
        all_dates,
        format_func=lambda d: (
            datetime.strptime(d, "%Y-%m-%d").strftime("%B %Y")
            if d else d
        ),
        key="rr_date",
    )

    # ── Section toggles ──────────────────────────────────
    st.markdown("#### Include sections")
    c1, c2, c3 = st.columns(3)
    with c1:
        inc_menu = st.toggle("Menu items summary", value=True, key="rr_menu")
    with c2:
        inc_sub  = st.toggle("Sub-recipes summary", value=True, key="rr_sub")
    with c3:
        inc_cards = st.toggle("Recipe detail cards", value=True, key="rr_cards")

    # ── Preview counts ───────────────────────────────────
    if selected_date:
        with st.spinner("Loading data…"):
            ac_recipes_data    = _get_ac_recipes(supabase, client_id, selected_date) if inc_menu  else []
            ac_sub_data        = _get_ac_sub_recipes(supabase, client_id, selected_date) if inc_sub else []
            paperless_data     = _get_paperless_recipes(supabase, client_name) if inc_cards else []

        if ac_recipes_data or ac_sub_data or paperless_data:
            m1, m2, m3 = st.columns(3)
            m1.metric("Menu items",   len(ac_recipes_data))
            m2.metric("Sub-recipes",  len(ac_sub_data))
            m3.metric("Recipe cards", len(paperless_data))
        else:
            st.warning("No data found for the selected period and sections.")

        # ── Generate button ──────────────────────────────
        st.markdown("")
        if st.button(
            "Generate PDF Report",
            type="primary",
            use_container_width=True,
            key="rr_generate",
        ):
            if not (ac_recipes_data or ac_sub_data or paperless_data):
                st.error("Nothing to generate — no data available.")
                return

            with st.spinner("Building PDF…"):
                pdf_bytes = generate_recipe_report_pdf(
                    client_name        = client_name,
                    report_date        = selected_date,
                    ac_recipes         = ac_recipes_data if inc_menu  else [],
                    ac_sub_recipes     = ac_sub_data     if inc_sub   else [],
                    paperless_recipes  = paperless_data  if inc_cards else [],
                )

            if pdf_bytes:
                try:
                    d = datetime.strptime(selected_date, "%Y-%m-%d")
                    fname = (
                        f"Recipe_Report_{client_name.replace(' ','_')}"
                        f"_{d.strftime('%b_%Y')}.pdf"
                    )
                except Exception:
                    fname = f"Recipe_Report_{client_name}.pdf"

                st.success("Report ready!")
                st.download_button(
                    label="Download PDF",
                    data=pdf_bytes,
                    file_name=fname,
                    mime="application/pdf",
                    use_container_width=True,
                    key="rr_download",
                )
