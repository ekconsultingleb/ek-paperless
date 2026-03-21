"""
modules/overview.py
EK Consulting — Financial Overview Module
Single scrolling page matching the Financial Overview PDF format.
EK pilots only — select client + month → view → export PDF.
"""

import io
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.ticker as mticker
from datetime import datetime, date, timedelta
from supabase import create_client, Client

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, Image as RLImage, KeepTogether
)

# ── Colors ─────────────────────────────────────────────────────────────────────
EK_DARK   = "#1B252C"
EK_DARK2  = "#2E3D47"
EK_SAND   = "#E3C5AD"
EK_SAND2  = "#F5EBE0"
EK_SAND3  = "#c9a98a"
EK_RED    = "#C0392B"
EK_GREEN  = "#27AE60"
EK_GRAY   = "#6B7B86"

RL_CHARCOAL   = colors.HexColor("#1B252C")
RL_SAND       = colors.HexColor("#E3C5AD")
RL_SAND_LIGHT = colors.HexColor("#F5EBE0")
RL_SAND3      = colors.HexColor("#c9a98a")
RL_RED        = colors.HexColor("#C0392B")
RL_GREEN      = colors.HexColor("#27AE60")
RL_GRAY       = colors.HexColor("#6B7B86")
RL_WHITE      = colors.white

W, H = A4

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=EK_SAND, family="sans-serif", size=11),
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)

# ── Supabase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def _sb() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])

@st.cache_data(ttl=300)
def fetch(table, client, month):
    r = _sb().table(table).select("*").eq("client_name", client).eq("month", month).execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_all(table, client):
    r = _sb().table(table).select("*").eq("client_name", client).execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()

@st.cache_data(ttl=300)
def get_clients():
    r = _sb().table("ac_upload_log").select("client_name").execute()
    return sorted(list({row["client_name"] for row in r.data})) if r.data else []

@st.cache_data(ttl=300)
def get_months(client):
    r = _sb().table("ac_upload_log").select("month").eq("client_name", client).execute()
    if not r.data: return []
    return sorted(list({row["month"] for row in r.data}), reverse=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def n(val, dec=0):
    try:
        v = float(val)
        if v == 0: return "-"
        return f"{v:,.0f}" if dec == 0 else f"{v:,.{dec}f}"
    except: return "-"

def pct(num, den):
    try: return float(num) / float(den) if float(den) else 0
    except: return 0

def agg(df, col):
    if df.empty or col not in df.columns: return 0
    return pd.to_numeric(df[col], errors="coerce").fillna(0).sum()

def agg_cat(df, col, cat):
    if df.empty or col not in df.columns: return 0
    return pd.to_numeric(df[df["category"] == cat][col], errors="coerce").fillna(0).sum()

def mlabel(m):
    try: return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%B %Y")
    except: return m

def mshort(m):
    try: return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%b %Y")
    except: return m

def prev_month(m):
    try:
        d = datetime.strptime(m[:10], "%Y-%m-%d").date()
        return (d.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")
    except: return None

# ── Streamlit UI helpers ───────────────────────────────────────────────────────
def section_header(title, subtitle=""):
    sub_html = f"<div style='color:{EK_GRAY};font-size:11px;margin-top:2px;'>{subtitle}</div>" if subtitle else ""
    divider  = "<div style='height:2px;background:#c9a98a;margin-top:6px;border-radius:2px;opacity:0.5;'></div>"
    st.markdown(f"""
        <div style="margin:24px 0 10px;">
            <div style="color:{EK_SAND};font-size:15px;font-weight:600;">{title}</div>
            {sub_html}
            {divider}
        </div>
    """, unsafe_allow_html=True)

def alert_box(text, level="info"):
    clr = {
        "danger":  (EK_RED,   "rgba(192,57,43,0.1)"),
        "warning": ("#E67E22", "rgba(230,126,34,0.1)"),
        "ok":      (EK_GREEN,  "rgba(39,174,96,0.1)"),
        "info":    (EK_GRAY,   "rgba(107,123,134,0.08)"),
    }.get(level, (EK_GRAY, "rgba(0,0,0,0)"))
    st.markdown(f"""
        <div style="background:{clr[1]};border-left:3px solid {clr[0]};
                    border-radius:0 8px 8px 0;padding:9px 14px;margin:3px 0;
                    font-size:13px;color:{EK_SAND};">{text}</div>
    """, unsafe_allow_html=True)

def kpi_box(label, value, sub=""):
    st.markdown(f"""
        <div style="background:linear-gradient(135deg,{EK_DARK} 0%,{EK_DARK2} 100%);
                    border-radius:12px;padding:18px 20px;
                    border:1px solid rgba(227,197,173,0.2);text-align:center;margin:4px 0;">
            <div style="color:{EK_GRAY};font-size:11px;text-transform:uppercase;letter-spacing:0.07em;">{label}</div>
            <div style="color:{EK_SAND};font-size:28px;font-weight:700;margin:8px 0;">{value}</div>
            <div style="color:{EK_SAND3};font-size:12px;">{sub}</div>
        </div>
    """, unsafe_allow_html=True)

def category_metrics_row(label, ns, gc, gc_pct, nc, nc_pct):
    st.markdown(f"""
        <div style="background:{EK_DARK};border-radius:10px;padding:12px 18px;
                    margin:6px 0;border:1px solid rgba(227,197,173,0.12);">
            <span style="color:{EK_SAND};font-weight:600;font-size:13px;">{label}</span>
            &nbsp;&nbsp;&nbsp;
            <span style="color:{EK_GRAY};font-size:12px;">
                Net Sales: <b style="color:{EK_SAND};">{n(ns)}</b>
                &nbsp;|&nbsp;
                Gross COGS: <b style="color:{EK_SAND};">{n(gc)}</b>
                <span style="color:{EK_SAND3};"> ({gc_pct:.1f}%)</span>
                &nbsp;|&nbsp;
                Net COGS: <b style="color:{EK_SAND};">{n(nc)}</b>
                <span style="color:{EK_SAND3};"> ({nc_pct:.1f}%)</span>
            </span>
        </div>
    """, unsafe_allow_html=True)

# ── Matplotlib chart helpers (for PDF embedding) ───────────────────────────────
MPL_BG    = "#1B252C"
MPL_SAND  = "#E3C5AD"
MPL_SAND2 = "#c9a98a"
MPL_DARK2 = "#2E3D47"
MPL_RED   = "#C0392B"
MPL_GREEN = "#27AE60"
MPL_GRAY  = "#6B7B86"

def mpl_style(fig, ax):
    fig.patch.set_facecolor(MPL_BG)
    ax.set_facecolor(MPL_BG)
    ax.tick_params(colors=MPL_SAND, labelsize=8)
    ax.spines["bottom"].set_color(MPL_GRAY)
    ax.spines["left"].set_color(MPL_GRAY)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.label.set_color(MPL_SAND)
    ax.xaxis.label.set_color(MPL_SAND)
    ax.title.set_color(MPL_SAND)


def fig_to_bytes(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


def chart_monthly_bar(monthly_df):
    labels = monthly_df["month_label"].tolist()
    sales  = monthly_df["net_sales"].tolist()
    cogs   = monthly_df["net_cogs"].tolist()
    x = range(len(labels))
    w = 0.35
    fig, ax = plt.subplots(figsize=(7, 3))
    mpl_style(fig, ax)
    b1 = ax.bar([i - w/2 for i in x], sales, w, color=MPL_SAND,  label="Net Sales")
    b2 = ax.bar([i + w/2 for i in x], cogs,  w, color=MPL_DARK2, label="Net COGS",
                edgecolor=MPL_SAND2, linewidth=0.5)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=8, color=MPL_SAND)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1e6:.0f}M"))
    ax.legend(facecolor=MPL_BG, edgecolor=MPL_GRAY, labelcolor=MPL_SAND, fontsize=8)
    ax.set_title("Monthly Sales vs Net COGS", color=MPL_SAND, fontsize=9, pad=8)
    for bar in b1:
        h = bar.get_height()
        if h > 0: ax.text(bar.get_x()+bar.get_width()/2, h*1.01,
                          f"{h/1e6:.0f}M", ha="center", va="bottom",
                          color=MPL_SAND, fontsize=7)
    for bar in b2:
        h = bar.get_height()
        if h > 0: ax.text(bar.get_x()+bar.get_width()/2, h*1.01,
                          f"{h/1e6:.0f}M", ha="center", va="bottom",
                          color=MPL_SAND2, fontsize=7)
    fig.tight_layout()
    return fig_to_bytes(fig)


def chart_horizontal_bar(labels, values, title, color=MPL_SAND, max_items=8):
    labels = labels[:max_items]; values = values[:max_items]
    labels = [str(l)[:28] for l in labels]
    fig, ax = plt.subplots(figsize=(6, max(2.5, len(labels) * 0.42)))
    mpl_style(fig, ax)
    bars = ax.barh(labels, values, color=color, edgecolor="none", height=0.6)
    ax.set_title(title, color=MPL_SAND, fontsize=9, pad=6)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1e6:.0f}M"))
    ax.invert_yaxis()
    for bar, val in zip(bars, values):
        ax.text(val * 1.01, bar.get_y() + bar.get_height()/2,
                f"{val/1e6:.1f}M", va="center", color=MPL_SAND, fontsize=7.5)
    fig.tight_layout()
    return fig_to_bytes(fig)


def chart_variance_bar(products, values, title, max_items=12):
    products = [str(p)[:25] for p in products[:max_items]]
    values   = values[:max_items]
    bar_colors = [MPL_RED if v < 0 else MPL_GREEN for v in values]
    fig, ax = plt.subplots(figsize=(6, max(3, len(products) * 0.45)))
    mpl_style(fig, ax)
    ax.barh(products, values, color=bar_colors, edgecolor="none", height=0.6)
    ax.set_title(title, color=MPL_SAND, fontsize=9, pad=6)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M"))
    ax.axvline(0, color=MPL_GRAY, linewidth=0.5)
    ax.invert_yaxis()
    fig.tight_layout()
    return fig_to_bytes(fig)


# ══════════════════════════════════════════════════════════════════════════════
# PDF BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def build_pdf(client, month, prev_m, cogs_cur, cogs_prev, cogs_all,
              sales_df, var_df, theo_df):

    buf = io.BytesIO()

    def S():
        return {
            "title":  ParagraphStyle("t1", fontName="Helvetica-Bold", fontSize=20, textColor=RL_WHITE),
            "sub":    ParagraphStyle("t2", fontName="Helvetica", fontSize=10, textColor=RL_SAND),
            "h1":     ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=12, textColor=RL_CHARCOAL, spaceBefore=10, spaceAfter=4),
            "h2":     ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10, textColor=RL_CHARCOAL, spaceBefore=6, spaceAfter=3),
            "body":   ParagraphStyle("bd", fontName="Helvetica", fontSize=9, textColor=RL_CHARCOAL, leading=13),
            "alert":  ParagraphStyle("al", fontName="Helvetica-Bold", fontSize=9, textColor=RL_RED),
            "small":  ParagraphStyle("sm", fontName="Helvetica", fontSize=7.5, textColor=RL_GRAY),
            "th":     ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=RL_WHITE, alignment=TA_CENTER),
            "td":     ParagraphStyle("td", fontName="Helvetica", fontSize=8, textColor=RL_CHARCOAL),
            "td_r":   ParagraphStyle("tr", fontName="Helvetica", fontSize=8, textColor=RL_CHARCOAL, alignment=TA_RIGHT),
            "td_b":   ParagraphStyle("tb", fontName="Helvetica-Bold", fontSize=8, textColor=RL_CHARCOAL),
            "td_br":  ParagraphStyle("tbr",fontName="Helvetica-Bold", fontSize=8, textColor=RL_CHARCOAL, alignment=TA_RIGHT),
        }

    s = S()
    story = []
    ml = mlabel(month); pml = mshort(prev_m) if prev_m else ""

    # ── Aggregates ─────────────────────────────────────────────────────────────
    gross = agg(cogs_cur, "gross_sales"); net   = agg(cogs_cur, "net_sales")
    disc  = agg(cogs_cur, "discount");   gcogs = agg(cogs_cur, "gross_cogs")
    ncogs = agg(cogs_cur, "net_cogs");   waste = agg(cogs_cur, "waste")
    tvar  = agg(cogs_cur, "total_variance")
    p_net = agg(cogs_prev, "net_sales") if not cogs_prev.empty else 0

    def ts_base(hr=1):
        return TableStyle([
            ("BACKGROUND",(0,0),(-1,hr-1), RL_CHARCOAL),
            ("TEXTCOLOR",(0,0),(-1,hr-1), RL_WHITE),
            ("FONTNAME",(0,0),(-1,hr-1),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),8),
            ("ROWBACKGROUNDS",(0,hr),(-1,-1),[RL_WHITE, RL_SAND_LIGHT]),
            ("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#D0D0D0")),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),3),
            ("BOTTOMPADDING",(0,0),(-1,-1),3),
            ("LEFTPADDING",(0,0),(-1,-1),5),
            ("RIGHTPADDING",(0,0),(-1,-1),5),
        ])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(RL_GRAY)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18*mm, 10*mm, "EK Consulting — Confidential")
        canvas.drawRightString(A4[0]-18*mm, 10*mm,
            f"Page {doc.page} | {date.today().strftime('%d %b %Y')}")
        canvas.restoreState()

    # ── Banner ─────────────────────────────────────────────────────────────────
    banner = Table([[
        Paragraph("EK CONSULTING", s["title"]),
        Paragraph(f"Financial Overview — {ml}", s["sub"])
    ]], colWidths=[W*0.5, W*0.4])
    banner.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),RL_CHARCOAL),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),16),
        ("TOPPADDING",(0,0),(-1,-1),14),
        ("BOTTOMPADDING",(0,0),(-1,-1),14),
    ]))
    story.append(banner)

    meta = Table([[
        Paragraph(f"<b>Client:</b> {client}", s["body"]),
        Paragraph(f"<b>Month:</b> {ml}", s["body"]),
        Paragraph(f"<b>Generated:</b> {date.today().strftime('%d %B %Y')}", s["body"]),
    ]], colWidths=[W*0.33, W*0.27, W*0.30])
    meta.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),RL_SAND_LIGHT),
        ("LEFTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story.append(meta)
    story.append(Spacer(1, 10))

    # ── Page 1: Narrative + KPIs + Chart ──────────────────────────────────────
    story.append(Paragraph(f"Month: {mshort(month)}", s["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=RL_SAND, spaceAfter=6))

    # Narrative lines
    if p_net:
        chg = pct(net - p_net, p_net) * 100
        direction = "decreased" if chg < 0 else "increased"
        story.append(Paragraph(
            f"The Sales of {mshort(month)} {direction} by {abs(chg):.1f}% for the month of {pml}",
            s["alert"] if chg < 0 else s["body"]))
        story.append(Spacer(1, 3))

    disc_pct = pct(disc, gross) * 100
    if disc_pct > 20:
        story.append(Paragraph(
            f"{n(disc)} of the discount is alarming, indicating a percentage of {disc_pct:.2f}%",
            s["alert"]))
        story.append(Spacer(1, 3))

    if not cogs_all.empty and "month" in cogs_all.columns:
        monthly = cogs_all.groupby("month").apply(
            lambda df: agg(df, "net_sales")).reset_index()
        monthly.columns = ["month", "net_sales"]
        if len(monthly) > 1:
            best  = monthly.loc[monthly["net_sales"].idxmax()]
            worst = monthly.loc[monthly["net_sales"].idxmin()]
            story.append(Paragraph(
                f"{mshort(best['month'])} is the highest monthly sales till Day", s["body"]))
            story.append(Spacer(1, 2))
            story.append(Paragraph(
                f"{mshort(worst['month'])} is the lowest monthly sales till Day", s["body"]))
            story.append(Spacer(1, 3))

    story.append(Paragraph(
        f"Total F&B consumption for the month of {mshort(month)} is {n(gcogs)}", s["body"]))
    story.append(Spacer(1, 12))

    # KPI boxes
    kpi_table = Table([[
        Table([[Paragraph("Net Sales", s["small"]),
                Paragraph(n(net), ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=18,
                                                  textColor=RL_CHARCOAL, alignment=TA_CENTER))]],
               colWidths=[W*0.35]),
        Table([[Paragraph(f"Net COGS", s["small"]),
                Paragraph(f"{n(ncogs)}  {pct(ncogs,net)*100:.1f}%",
                           ParagraphStyle("kv2", fontName="Helvetica-Bold", fontSize=14,
                                          textColor=RL_CHARCOAL, alignment=TA_CENTER))]],
               colWidths=[W*0.35]),
    ]], colWidths=[W*0.42, W*0.42])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,0),RL_SAND_LIGHT),
        ("BACKGROUND",(1,0),(1,0),RL_SAND_LIGHT),
        ("BOX",(0,0),(0,0),0.5,RL_SAND),
        ("BOX",(1,0),(1,0),0.5,RL_SAND),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),12),
        ("BOTTOMPADDING",(0,0),(-1,-1),12),
        ("LEFTPADDING",(0,0),(-1,-1),14),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # Monthly chart
    if not cogs_all.empty:
        monthly2 = cogs_all.groupby("month").agg(
            net_sales=("net_sales", lambda x: pd.to_numeric(x, errors="coerce").sum()),
            net_cogs=("net_cogs",   lambda x: pd.to_numeric(x, errors="coerce").sum()),
        ).reset_index().sort_values("month")
        monthly2["month_label"] = monthly2["month"].apply(mshort)
        chart_buf = chart_monthly_bar(monthly2)
        story.append(RLImage(chart_buf, width=W-60, height=140))

    story.append(PageBreak())

    # ── Pages 2–3: Category sections ──────────────────────────────────────────
    for cat in ["Beverages", "Food"]:
        ns_cat  = agg_cat(cogs_cur, "net_sales", cat)
        gc_cat  = agg_cat(cogs_cur, "gross_cogs", cat)
        nc_cat  = agg_cat(cogs_cur, "net_cogs", cat)
        if ns_cat == 0: continue

        story.append(Paragraph(f"{cat} Category", s["h1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=RL_SAND, spaceAfter=6))

        # Category metrics row
        metrics_row = Table([[
            Paragraph("Net Sales", s["small"]),
            Paragraph("Gross COGS", s["small"]),
            Paragraph("Net COGS", s["small"]),
        ],[
            Paragraph(n(ns_cat), ParagraphStyle("mv", fontName="Helvetica-Bold", fontSize=11, textColor=RL_CHARCOAL)),
            Paragraph(f"{n(gc_cat)}  {pct(gc_cat,ns_cat)*100:.1f}%",
                      ParagraphStyle("mv2", fontName="Helvetica-Bold", fontSize=10, textColor=RL_CHARCOAL)),
            Paragraph(f"{n(nc_cat)}  {pct(nc_cat,ns_cat)*100:.1f}%",
                      ParagraphStyle("mv3", fontName="Helvetica-Bold", fontSize=10, textColor=RL_CHARCOAL)),
        ]], colWidths=[W*0.28, W*0.28, W*0.28])
        metrics_row.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1),RL_SAND_LIGHT),
            ("BOX",(0,0),(-1,-1),0.5,RL_SAND),
            ("INNERGRID",(0,0),(-1,-1),0.25,RL_SAND),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),8),
            ("BOTTOMPADDING",(0,0),(-1,-1),8),
            ("LEFTPADDING",(0,0),(-1,-1),10),
        ]))
        story.append(metrics_row)
        story.append(Spacer(1, 10))

        if not sales_df.empty and "category" in sales_df.columns:
            sub = sales_df[sales_df["category"] == cat].copy()
            sub["gross_sales"] = pd.to_numeric(sub["gross_sales"], errors="coerce").fillna(0)
            sub["qty_sold"]    = pd.to_numeric(sub["qty_sold"],    errors="coerce").fillna(0)

            if not sub.empty and "group" in sub.columns:
                grp = sub.groupby("group").agg(
                    revenue=("gross_sales","sum"), qty=("qty_sold","sum")
                ).reset_index().sort_values("revenue", ascending=False)

                top3 = sub.nlargest(3, "gross_sales")

                # Two columns: text lists + chart
                left_rows = []

                left_rows.append(Paragraph("<b>Top 5 Groups by Revenue</b>", s["h2"]))
                left_rows.append(Spacer(1, 4))
                for i, (_, r) in enumerate(grp.head(5).iterrows(), 1):
                    left_rows.append(Paragraph(
                        f"{i}. {str(r['group'])[:30]}  —  {n(r['revenue'])}",
                        s["body"]))
                    left_rows.append(Spacer(1, 2))

                left_rows.append(Spacer(1, 8))
                left_rows.append(Paragraph("<b>Top 3 Menu Items by Revenue</b>", s["h2"]))
                left_rows.append(Spacer(1, 4))

                # Header
                hdr_t = Table([["Qty", "Revenue"]], colWidths=[40, 90])
                hdr_t.setStyle(TableStyle([
                    ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),
                    ("FONTSIZE",(0,0),(-1,-1),8),
                    ("TEXTCOLOR",(0,0),(-1,-1),RL_GRAY),
                ]))
                left_rows.append(hdr_t)

                for i, (_, r) in enumerate(top3.iterrows(), 1):
                    item_t = Table([[
                        Paragraph(f"{i}. {str(r.get('description',''))[:22]}", s["body"]),
                        Paragraph(n(r["qty_sold"],0), s["td_r"]),
                        Paragraph(n(r["gross_sales"]), s["td_r"]),
                    ]], colWidths=[130, 40, 90])
                    left_rows.append(item_t)
                    left_rows.append(Spacer(1, 2))

                # Chart
                chart_buf2 = chart_horizontal_bar(
                    grp["group"].tolist(),
                    grp["revenue"].tolist(),
                    f"{cat} Revenue by Group"
                )
                chart_img = RLImage(chart_buf2, width=W*0.45, height=160)

                # Layout: left content + right chart
                content_col = left_rows
                layout = Table([[content_col, chart_img]],
                               colWidths=[W*0.43, W*0.47])
                layout.setStyle(TableStyle([
                    ("VALIGN",(0,0),(-1,-1),"TOP"),
                ]))
                story.append(layout)

        story.append(PageBreak())

    # ── Page 4: Waste & Variance ───────────────────────────────────────────────
    story.append(Paragraph("Waste & Variance Metrics", s["h1"]))
    story.append(HRFlowable(width="100%", thickness=1, color=RL_SAND, spaceAfter=8))

    for cat in ["Beverages", "Food"]:
        waste_cat = agg_cat(cogs_cur, "waste", cat)
        ns_cat    = agg_cat(cogs_cur, "net_sales", cat)
        waste_pct = pct(waste_cat, ns_cat) * 100

        if waste_pct > 20:
            story.append(Paragraph(
                f"🚨 Dangerous: {cat} waste is severely high {waste_pct:.1f}%. Immediate action required.",
                s["alert"]))
        elif waste_pct > 5:
            story.append(Paragraph(
                f"⚠️ High: {cat} waste at {waste_pct:.1f}%.", s["body"]))
        elif waste_pct > 0:
            story.append(Paragraph(
                f"✅ Normal: {cat} waste is under {waste_pct:.1f}%.", s["body"]))
        else:
            story.append(Paragraph(f"✅ Normal: {cat} waste is under 3%.", s["body"]))

        story.append(Spacer(1, 3))

    if not var_df.empty:
        var_df2 = var_df.copy()
        var_df2["tt_variance_lbp"] = pd.to_numeric(var_df2["tt_variance_lbp"], errors="coerce").fillna(0)

        story.append(Spacer(1, 8))
        for cat in ["Beverages", "Food"]:
            sub = var_df2[var_df2["category"] == cat]
            neg = sub[sub["tt_variance_lbp"] < 0]["tt_variance_lbp"].sum()
            pos = sub[sub["tt_variance_lbp"] > 0]["tt_variance_lbp"].sum()
            lvl = "✅ Acceptable" if abs(neg) < 5000000 else "⚠️ Watch"
            story.append(Paragraph(
                f"{lvl}: {cat} variance — Negative: ({n(abs(neg))}) | Positive: {n(pos)} LBP",
                s["body"]))
            story.append(Spacer(1, 3))

        # Variance chart
        story.append(Spacer(1, 10))
        top_abs = var_df2.assign(abs_var=var_df2["tt_variance_lbp"].abs()).nlargest(12, "abs_var")
        v_buf = chart_variance_bar(
            top_abs["product"].tolist(),
            top_abs["tt_variance_lbp"].tolist(),
            "Top Variances by Absolute Value (LBP)"
        )
        story.append(RLImage(v_buf, width=W-60, height=180))

    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=14*mm, bottomMargin=20*mm,
        title=f"Financial Overview — {client} — {ml}",
        author="EK Consulting")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════
def render_overview(supabase, conn, user, role, client_arg, outlet, location):

    allowed_roles = ["admin", "admin_all", "manager", "pilot"]
    if role not in allowed_roles and client_arg.lower() != "all":
        st.error("⛔ Access restricted to EK team members.")
        return

    # ── Header ─────────────────────────────────────────────────────────────────
    st.markdown(f"""
        <div style="background:linear-gradient(135deg,{EK_DARK} 0%,{EK_DARK2} 100%);
                    border-radius:16px;padding:20px 24px;margin-bottom:20px;
                    border:1px solid rgba(227,197,173,0.15);">
            <div style="color:{EK_SAND};font-size:20px;font-weight:600;">📊 Financial Overview</div>
            <div style="color:{EK_GRAY};font-size:13px;margin-top:4px;">
                EK Consulting · Select client and month to generate the report
            </div>
        </div>
    """, unsafe_allow_html=True)

    # ── Selectors ──────────────────────────────────────────────────────────────
    clients = get_clients()
    if not clients:
        st.warning("No data found. Run the Auto Calc Reader first.")
        return

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        if client_arg.lower() == "all" or role in ["admin", "admin_all"]:
            selected_client = st.selectbox("🏢 Client", clients, key="ov_client")
        else:
            selected_client = client_arg
            st.markdown(f"**🏢 {selected_client}**")

    with col2:
        months = get_months(selected_client)
        if not months:
            st.warning(f"No data for {selected_client}.")
            return
        month_labels = {m: mlabel(m) for m in months}
        sel_label = st.selectbox("📅 Month", list(month_labels.values()), key="ov_month")
        selected_month = [k for k, v in month_labels.items() if v == sel_label][0]

    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄", key="ov_refresh", help="Refresh data"):
            st.cache_data.clear(); st.rerun()

    prev_m = prev_month(selected_month)

    # ── Fetch ───────────────────────────────────────────────────────────────────
    with st.spinner("Loading..."):
        cogs_cur  = fetch("ac_cogs",        selected_client, selected_month)
        cogs_prev = fetch("ac_cogs",        selected_client, prev_m) if prev_m else pd.DataFrame()
        cogs_all  = fetch_all("ac_cogs",    selected_client)
        sales_df  = fetch("ac_sales",       selected_client, selected_month)
        var_df    = fetch("ac_variance",    selected_client, selected_month)
        theo_df   = fetch("ac_theoretical", selected_client, selected_month)

    if cogs_cur.empty:
        st.warning(f"No COGS data for {selected_client} — {mlabel(selected_month)}.")
        return

    # ── Aggregates ──────────────────────────────────────────────────────────────
    gross = agg(cogs_cur,"gross_sales"); net   = agg(cogs_cur,"net_sales")
    disc  = agg(cogs_cur,"discount");   gcogs = agg(cogs_cur,"gross_cogs")
    ncogs = agg(cogs_cur,"net_cogs");   waste = agg(cogs_cur,"waste")
    tvar  = agg(cogs_cur,"total_variance")
    p_net = agg(cogs_prev,"net_sales") if not cogs_prev.empty else 0
    disc_pct = pct(disc, gross) * 100

    # ── Export PDF button ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_exp, col_info = st.columns([1, 3])
    with col_exp:
        if st.button("📄 Export PDF", type="primary", use_container_width=True, key="ov_pdf"):
            with st.spinner("Generating PDF..."):
                try:
                    pdf_buf = build_pdf(
                        selected_client, selected_month, prev_m,
                        cogs_cur, cogs_prev, cogs_all,
                        sales_df, var_df, theo_df
                    )
                    slug = selected_client.replace(" ","_").replace("/","-")
                    ml_  = mlabel(selected_month).replace(" ","_")
                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_buf,
                        file_name=f"Financial_Overview_{slug}_{ml_}.pdf",
                        mime="application/pdf",
                        key="ov_download"
                    )
                    st.success("PDF ready — click Download above.")
                except Exception as e:
                    st.error(f"PDF generation error: {e}")
    with col_info:
        st.markdown(f"<div style='color:{EK_GRAY};font-size:12px;padding-top:10px;'>"
                    f"Generates Financial Overview PDF for <b style='color:{EK_SAND};'>"
                    f"{selected_client}</b> — {mlabel(selected_month)}</div>",
                    unsafe_allow_html=True)

    st.divider()

    # ══════════════════════════════════════════════════════════════════════════
    # ON-SCREEN PREVIEW (matches PDF layout)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Section 1: Narrative ────────────────────────────────────────────────────
    section_header(f"Month: {mshort(selected_month)}", selected_client)

    if p_net:
        chg = pct(net - p_net, p_net) * 100
        direction = "decreased" if chg < 0 else "increased"
        lvl = "danger" if chg < -10 else ("warning" if chg < 0 else "ok")
        alert_box(f"{'📉' if chg<0 else '📈'}  The Sales of {mshort(selected_month)} "
                  f"<b>{direction} by {abs(chg):.1f}%</b> for the month of {mshort(prev_m)}", lvl)

    if disc_pct > 20:
        alert_box(f"🚨  <b>{n(disc)}</b> of the discount is alarming — "
                  f"<b>{disc_pct:.2f}%</b> of Gross Sales", "danger")

    if not cogs_all.empty and "month" in cogs_all.columns:
        monthly = cogs_all.groupby("month").apply(
            lambda df: agg(df, "net_sales")).reset_index()
        monthly.columns = ["month", "net_sales"]
        if len(monthly) > 1:
            best  = monthly.loc[monthly["net_sales"].idxmax()]
            worst = monthly.loc[monthly["net_sales"].idxmin()]
            alert_box(f"📈  <b>{mshort(best['month'])}</b> is the highest monthly sales to date", "ok")
            alert_box(f"📉  <b>{mshort(worst['month'])}</b> is the lowest monthly sales to date", "warning")

    alert_box(f"📊  Total F&B consumption for <b>{mshort(selected_month)}</b> is "
              f"<b>{n(gcogs)}</b> LBP", "info")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section 2: KPI Boxes ────────────────────────────────────────────────────
    ck1, ck2 = st.columns(2)
    with ck1: kpi_box("Net Sales", n(net), mlabel(selected_month))
    with ck2: kpi_box("Net COGS", n(ncogs), f"{pct(ncogs,net)*100:.2f}% of Net Sales")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Section 3: Monthly Bar Chart ────────────────────────────────────────────
    section_header("Monthly Sales vs Net COGS")
    if not cogs_all.empty:
        monthly2 = cogs_all.groupby("month").agg(
            net_sales=("net_sales", lambda x: pd.to_numeric(x,errors="coerce").sum()),
            net_cogs=("net_cogs",   lambda x: pd.to_numeric(x,errors="coerce").sum()),
        ).reset_index().sort_values("month")
        monthly2["month_label"] = monthly2["month"].apply(mshort)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=monthly2["month_label"], y=monthly2["net_sales"],
                             name="Net Sales", marker_color=EK_SAND,
                             text=monthly2["net_sales"].apply(lambda v: n(v)),
                             textposition="outside", textfont=dict(size=9)))
        fig.add_trace(go.Bar(x=monthly2["month_label"], y=monthly2["net_cogs"],
                             name="Net COGS", marker_color=EK_DARK2,
                             text=monthly2["net_cogs"].apply(lambda v: n(v)),
                             textposition="outside", textfont=dict(size=9, color=EK_SAND3)))
        fig.update_layout(**PLOTLY_LAYOUT, barmode="group", height=280,
                          xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                          yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Section 4: Category Sections ────────────────────────────────────────────
    for cat in ["Beverages", "Food"]:
        ns_cat  = agg_cat(cogs_cur, "net_sales", cat)
        gc_cat  = agg_cat(cogs_cur, "gross_cogs", cat)
        nc_cat  = agg_cat(cogs_cur, "net_cogs", cat)
        if ns_cat == 0: continue

        section_header(f"{cat} Category")
        category_metrics_row(cat, ns_cat, gc_cat,
                             pct(gc_cat,ns_cat)*100,
                             nc_cat, pct(nc_cat,ns_cat)*100)

        if not sales_df.empty and "category" in sales_df.columns:
            sub = sales_df[sales_df["category"] == cat].copy()
            sub["gross_sales"] = pd.to_numeric(sub["gross_sales"], errors="coerce").fillna(0)
            sub["qty_sold"]    = pd.to_numeric(sub["qty_sold"],    errors="coerce").fillna(0)

            if not sub.empty and "group" in sub.columns:
                grp = sub.groupby("group").agg(
                    revenue=("gross_sales","sum")).reset_index().sort_values("revenue",ascending=False)
                top3 = sub.nlargest(3, "gross_sales")

                col_left, col_right = st.columns([1, 2])

                with col_left:
                    st.markdown(f"**Top 5 Groups by Revenue**")
                    for i, (_, r) in enumerate(grp.head(5).iterrows(), 1):
                        st.markdown(
                            f"<span style='color:{EK_GRAY};font-size:12px;'>{i}. {r['group'][:28]}</span>"
                            f"&nbsp;&nbsp;<b style='color:{EK_SAND};font-size:12px;'>{n(r['revenue'])}</b>",
                            unsafe_allow_html=True)

                    st.markdown("<br>**Top 3 Menu Items by Revenue**")
                    for i, (_, r) in enumerate(top3.iterrows(), 1):
                        st.markdown(
                            f"<span style='color:{EK_GRAY};font-size:12px;'>{i}. "
                            f"{str(r.get('description',''))[:22]}</span>&nbsp;&nbsp;"
                            f"<b style='color:{EK_SAND};font-size:12px;'>"
                            f"{n(r['qty_sold'],0)} qty | {n(r['gross_sales'])}</b>",
                            unsafe_allow_html=True)

                with col_right:
                    top_grps = grp.head(8)
                    fig2 = go.Figure(go.Bar(
                        x=top_grps["revenue"],
                        y=top_grps["group"],
                        orientation="h",
                        marker_color=EK_SAND,
                        text=top_grps["revenue"].apply(n),
                        textposition="outside",
                        textfont=dict(size=9, color=EK_SAND)
                    ))
                    fig2.update_layout(**PLOTLY_LAYOUT, height=260,
                                       xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                       yaxis=dict(gridcolor="rgba(255,255,255,0.05)",
                                                  categoryorder="total ascending"))
                    st.plotly_chart(fig2, use_container_width=True)

        st.divider()

    # Total Revenue by Group
    if not sales_df.empty and "group" in sales_df.columns:
        section_header("Total Revenue by Group")
        sales_df["gross_sales"] = pd.to_numeric(sales_df["gross_sales"], errors="coerce").fillna(0)
        all_grp = sales_df.groupby("group")["gross_sales"].sum().reset_index().sort_values(
            "gross_sales", ascending=False)
        import plotly.express as px
        fig3 = px.bar(all_grp, x="group", y="gross_sales",
                      color_discrete_sequence=[EK_SAND],
                      labels={"group":"Group","gross_sales":"Gross Revenue (LBP)"})
        fig3.update_layout(**PLOTLY_LAYOUT, height=300,
                           xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickangle=-30),
                           yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
        st.plotly_chart(fig3, use_container_width=True)
        st.divider()

    # ── Section 5: Waste & Variance ─────────────────────────────────────────────
    section_header("Waste & Variance Metrics")

    for cat in ["Beverages", "Food"]:
        waste_cat = agg_cat(cogs_cur, "waste", cat)
        ns_cat    = agg_cat(cogs_cur, "net_sales", cat)
        w_pct     = pct(waste_cat, ns_cat) * 100

        if w_pct > 20:
            alert_box(f"🚨 <b>Dangerous:</b> {cat} waste is severely high at <b>{w_pct:.1f}%</b>. Immediate action required.", "danger")
        elif w_pct > 5:
            alert_box(f"⚠️ <b>High:</b> {cat} waste at <b>{w_pct:.1f}%</b>.", "warning")
        elif w_pct > 0:
            alert_box(f"✅ <b>Normal:</b> {cat} waste is under control at {w_pct:.1f}%.", "ok")
        else:
            alert_box(f"✅ <b>Normal:</b> {cat} waste is under 3%.", "ok")

    if not var_df.empty:
        var_df2 = var_df.copy()
        var_df2["tt_variance_lbp"] = pd.to_numeric(var_df2["tt_variance_lbp"], errors="coerce").fillna(0)

        st.markdown("<br>", unsafe_allow_html=True)
        for cat in ["Beverages", "Food"]:
            sub = var_df2[var_df2["category"] == cat]
            neg = sub[sub["tt_variance_lbp"] < 0]["tt_variance_lbp"].sum()
            pos = sub[sub["tt_variance_lbp"] > 0]["tt_variance_lbp"].sum()
            lvl = "ok" if abs(neg) < 5000000 else "warning"
            alert_box(f"{'✅ Acceptable' if lvl=='ok' else '⚠️ Watch'}: "
                      f"<b>{cat}</b> variance — "
                      f"Negative: <b style='color:{EK_RED};'>({n(abs(neg))})</b> | "
                      f"Positive: <b style='color:{EK_GREEN};'>{n(pos)}</b> LBP", lvl)

        # Variance chart
        st.markdown("<br>", unsafe_allow_html=True)
        top_abs = var_df2.assign(abs_var=var_df2["tt_variance_lbp"].abs()).nlargest(12,"abs_var")
        fig_v = go.Figure(go.Bar(
            x=top_abs["tt_variance_lbp"],
            y=top_abs["product"].apply(lambda v: str(v)[:25]),
            orientation="h",
            marker_color=[EK_RED if v < 0 else EK_GREEN for v in top_abs["tt_variance_lbp"]],
            text=top_abs["tt_variance_lbp"].apply(n),
            textposition="outside",
            textfont=dict(size=8)
        ))
        fig_v.update_layout(**PLOTLY_LAYOUT, height=400,
                            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                            yaxis=dict(gridcolor="rgba(255,255,255,0.05)",
                                       categoryorder="total ascending"))
        st.plotly_chart(fig_v, use_container_width=True)