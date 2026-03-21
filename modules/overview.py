"""
modules/overview.py
EK Consulting — Financial Overview Module
Accessible to EK pilots and admins only. Reads from ac_ tables in Supabase.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
from supabase import create_client, Client


# ── Supabase ───────────────────────────────────────────────────────────────────
@st.cache_resource
def _sb() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])


@st.cache_data(ttl=300)
def fetch(table: str, client: str, month: str) -> pd.DataFrame:
    r = _sb().table(table).select("*").eq("client_name", client).eq("month", month).execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()


@st.cache_data(ttl=300)
def fetch_all_months(table: str, client: str) -> pd.DataFrame:
    r = _sb().table(table).select("*").eq("client_name", client).execute()
    return pd.DataFrame(r.data) if r.data else pd.DataFrame()


@st.cache_data(ttl=300)
def get_available_clients() -> list:
    r = _sb().table("ac_upload_log").select("client_name").execute()
    if not r.data:
        return []
    return sorted(list({row["client_name"] for row in r.data}))


@st.cache_data(ttl=300)
def get_available_months(client: str) -> list:
    r = _sb().table("ac_upload_log").select("month").eq("client_name", client).execute()
    if not r.data:
        return []
    months = sorted(list({row["month"] for row in r.data}), reverse=True)
    return months


# ── Helpers ────────────────────────────────────────────────────────────────────
def n(val, dec=0):
    try:
        v = float(val)
        if v == 0: return "-"
        return f"{v:,.0f}" if dec == 0 else f"{v:,.{dec}f}"
    except:
        return "-"


def pct(num, den):
    try:
        return float(num) / float(den) if float(den) else 0
    except:
        return 0


def agg(df, col):
    if df.empty or col not in df.columns:
        return 0
    return pd.to_numeric(df[col], errors="coerce").fillna(0).sum()


def agg_cat(df, col, cat):
    if df.empty or col not in df.columns:
        return 0
    return pd.to_numeric(df[df["category"] == cat][col], errors="coerce").fillna(0).sum()


def mlabel(m):
    try:
        return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%B %Y")
    except:
        return m


def mshort(m):
    try:
        return datetime.strptime(m[:10], "%Y-%m-%d").strftime("%b %Y")
    except:
        return m


def prev_month(m):
    try:
        d = datetime.strptime(m[:10], "%Y-%m-%d").date()
        return (d.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")
    except:
        return None


# ── EK Colors ──────────────────────────────────────────────────────────────────
EK_DARK   = "#1B252C"
EK_DARK2  = "#2E3D47"
EK_SAND   = "#E3C5AD"
EK_SAND2  = "#F5EBE0"
EK_SAND3  = "#c9a98a"
EK_RED    = "#C0392B"
EK_GREEN  = "#27AE60"
EK_GRAY   = "#6B7B86"

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=EK_SAND, family="sans-serif", size=11),
    margin=dict(l=10, r=10, t=30, b=10),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


# ── KPI Card ───────────────────────────────────────────────────────────────────
def kpi_card(label, value, sub="", delta=None):
    delta_html = ""
    if delta is not None:
        color = EK_GREEN if delta >= 0 else EK_RED
        arrow = "▲" if delta >= 0 else "▼"
        delta_html = f"<div style='color:{color};font-size:12px;margin-top:2px;'>{arrow} {abs(delta):.1f}% vs prev month</div>"

    st.markdown(f"""
        <div style="
            background:linear-gradient(135deg,{EK_DARK} 0%,{EK_DARK2} 100%);
            border-radius:12px; padding:16px 18px;
            border:1px solid rgba(227,197,173,0.15);
            margin-bottom:4px;
        ">
            <div style="color:{EK_SAND3};font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">{label}</div>
            <div style="color:{EK_SAND};font-size:22px;font-weight:700;margin-top:4px;">{value}</div>
            <div style="color:{EK_GRAY};font-size:11px;margin-top:2px;">{sub}</div>
            {delta_html}
        </div>
    """, unsafe_allow_html=True)


def section_header(title, subtitle=""):
    st.markdown(f"""
        <div style="margin:24px 0 12px;">
            <div style="color:{EK_SAND};font-size:16px;font-weight:600;letter-spacing:0.02em;">{title}</div>
            {"<div style='color:"+EK_GRAY+";font-size:12px;margin-top:2px;'>"+subtitle+"</div>" if subtitle else ""}
            <div style="height:2px;background:linear-gradient(90deg,{EK_SAND3},transparent);margin-top:8px;border-radius:2px;"></div>
        </div>
    """, unsafe_allow_html=True)


def alert_box(text, level="info"):
    colors = {"danger": EK_RED, "warning": "#E67E22", "ok": EK_GREEN, "info": EK_GRAY}
    bg     = {"danger": "rgba(192,57,43,0.1)", "warning": "rgba(230,126,34,0.1)",
               "ok": "rgba(39,174,96,0.1)", "info": "rgba(107,123,134,0.1)"}
    c = colors.get(level, EK_GRAY)
    b = bg.get(level, "rgba(0,0,0,0)")
    st.markdown(f"""
        <div style="background:{b};border-left:3px solid {c};
                    border-radius:0 8px 8px 0;padding:10px 14px;margin:4px 0;font-size:13px;color:{EK_SAND};">
            {text}
        </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════
def render_overview(supabase, conn, user, role, client_arg, outlet, location):

    # ── Access control ─────────────────────────────────────────────────────────
    allowed_roles = ["admin", "admin_all", "manager", "pilot"]
    if role not in allowed_roles and client_arg.lower() != "all":
        st.error("⛔ Access restricted to EK team members.")
        return

    st.markdown(f"""
        <div style="
            background:linear-gradient(135deg,{EK_DARK} 0%,{EK_DARK2} 100%);
            border-radius:16px;padding:20px 24px;margin-bottom:20px;
            border:1px solid rgba(227,197,173,0.15);
        ">
            <div style="color:{EK_SAND};font-size:20px;font-weight:600;">📊 Financial Overview</div>
            <div style="color:{EK_GRAY};font-size:13px;margin-top:4px;">EK Consulting · Auto Calc Intelligence</div>
        </div>
    """, unsafe_allow_html=True)

    # ── Client & Month selectors ───────────────────────────────────────────────
    clients = get_available_clients()
    if not clients:
        st.warning("No data found in Supabase. Run the Auto Calc Reader first.")
        return

    col_sel1, col_sel2, col_sel3 = st.columns([2, 2, 1])

    with col_sel1:
        if client_arg.lower() == "all" or role in ["admin", "admin_all"]:
            selected_client = st.selectbox("🏢 Select Client", clients, key="ov_client")
        else:
            selected_client = client_arg
            st.markdown(f"**🏢 Client:** {selected_client}")

    with col_sel2:
        months = get_available_months(selected_client)
        if not months:
            st.warning(f"No data found for {selected_client}.")
            return
        month_labels = {m: mlabel(m) for m in months}
        selected_month_label = st.selectbox("📅 Select Month",
            options=list(month_labels.values()), key="ov_month")
        selected_month = [k for k, v in month_labels.items() if v == selected_month_label][0]

    with col_sel3:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", key="ov_refresh", use_container_width=True)
        if refresh:
            st.cache_data.clear()
            st.rerun()

    prev_m = prev_month(selected_month)

    # ── Fetch data ──────────────────────────────────────────────────────────────
    with st.spinner("Loading data..."):
        cogs_cur  = fetch("ac_cogs",        selected_client, selected_month)
        cogs_prev = fetch("ac_cogs",        selected_client, prev_m) if prev_m else pd.DataFrame()
        cogs_all  = fetch_all_months("ac_cogs", selected_client)
        sales_df  = fetch("ac_sales",       selected_client, selected_month)
        var_df    = fetch("ac_variance",    selected_client, selected_month)
        theo_df   = fetch("ac_theoretical", selected_client, selected_month)
        purch_df  = fetch("ac_purchase",    selected_client, selected_month)

    if cogs_cur.empty:
        st.warning(f"No COGS data found for {selected_client} — {mlabel(selected_month)}.")
        return

    # ── Aggregate KPIs ─────────────────────────────────────────────────────────
    gross = agg(cogs_cur, "gross_sales"); net   = agg(cogs_cur, "net_sales")
    disc  = agg(cogs_cur, "discount");   gcogs = agg(cogs_cur, "gross_cogs")
    ncogs = agg(cogs_cur, "net_cogs");   waste = agg(cogs_cur, "waste")
    tvar  = agg(cogs_cur, "total_variance")
    p_net = agg(cogs_prev, "net_sales") if not cogs_prev.empty else 0
    net_delta = pct(net - p_net, p_net) * 100 if p_net else None

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1 — FINANCIAL OVERVIEW
    # ══════════════════════════════════════════════════════════════════════════
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Financial Overview",
        "🍽️ Category Performance",
        "📉 Variance & Waste",
        "💡 Theoretical Cost"
    ])

    with tab1:
        # ── Narrative alerts ────────────────────────────────────────────────
        section_header("Summary", f"{mlabel(selected_month)} · {selected_client}")

        if p_net:
            chg = pct(net - p_net, p_net) * 100
            direction = "decreased" if chg < 0 else "increased"
            lvl = "danger" if chg < -10 else ("warning" if chg < 0 else "ok")
            alert_box(f"{'📉' if chg<0 else '📈'}  The Sales of {mshort(selected_month)} "
                      f"<b>{direction} by {abs(chg):.1f}%</b> for the month of {mshort(prev_m)}", lvl)

        disc_pct = pct(disc, gross) * 100
        if disc_pct > 20:
            alert_box(f"🚨  <b>{n(disc)}</b> of the discount is alarming — "
                      f"<b>{disc_pct:.2f}%</b> of Gross Sales", "danger")
        else:
            alert_box(f"✅  Discount at <b>{disc_pct:.2f}%</b> of Gross Sales — within normal range", "ok")

        if not cogs_all.empty and "month" in cogs_all.columns:
            monthly = cogs_all.groupby("month").apply(
                lambda df: agg(df, "net_sales")).reset_index()
            monthly.columns = ["month", "net_sales"]
            if len(monthly) > 1:
                best  = monthly.loc[monthly["net_sales"].idxmax()]
                worst = monthly.loc[monthly["net_sales"].idxmin()]
                alert_box(f"📈  <b>{mshort(best['month'])}</b> is the highest monthly sales to date "
                          f"({n(best['net_sales'])} LBP)", "ok")
                alert_box(f"📉  <b>{mshort(worst['month'])}</b> is the lowest monthly sales to date "
                          f"({n(worst['net_sales'])} LBP)", "warning")

        total_fb = agg(cogs_cur, "gross_cogs")
        alert_box(f"📊  Total F&B consumption for <b>{mshort(selected_month)}</b> is "
                  f"<b>{n(total_fb)}</b> LBP", "info")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── KPI Cards ───────────────────────────────────────────────────────
        section_header("Key Metrics")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: kpi_card("Gross Sales", n(gross), mshort(selected_month))
        with c2: kpi_card("Net Sales", n(net), mshort(selected_month), delta=net_delta)
        with c3: kpi_card("Discount", n(disc), f"{disc_pct:.2f}% of Gross")
        with c4: kpi_card("Net COGS", n(ncogs), f"{pct(ncogs,net)*100:.2f}% of Net")
        with c5: kpi_card("Total Variance", n(tvar), "LBP",
                           delta=None)

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Monthly Sales Chart ─────────────────────────────────────────────
        section_header("Monthly Sales vs Net COGS")
        if not cogs_all.empty:
            monthly2 = cogs_all.groupby("month").agg(
                net_sales=("net_sales", lambda x: pd.to_numeric(x, errors="coerce").sum()),
                net_cogs=("net_cogs",   lambda x: pd.to_numeric(x, errors="coerce").sum()),
            ).reset_index().sort_values("month")
            monthly2["month_label"] = monthly2["month"].apply(mshort)

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=monthly2["month_label"], y=monthly2["net_sales"],
                name="Net Sales", marker_color=EK_SAND,
                text=monthly2["net_sales"].apply(lambda v: n(v)),
                textposition="outside", textfont=dict(size=9, color=EK_SAND)
            ))
            fig.add_trace(go.Bar(
                x=monthly2["month_label"], y=monthly2["net_cogs"],
                name="Net COGS", marker_color=EK_DARK2,
                text=monthly2["net_cogs"].apply(lambda v: n(v)),
                textposition="outside", textfont=dict(size=9, color=EK_SAND3)
            ))
            fig.update_layout(**PLOTLY_LAYOUT, barmode="group",
                              xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                              yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig, use_container_width=True)

        # ── Net Sales & Discount Table ──────────────────────────────────────
        section_header("Net Sales & Discount by Category")
        cats = [c for c in sorted(cogs_cur["category"].dropna().unique())
                if c not in ("Extra Category",)] if not cogs_cur.empty else []

        rows = []
        for cat in cats:
            ns = agg_cat(cogs_cur, "net_sales", cat)
            dc = agg_cat(cogs_cur, "discount", cat)
            gs = agg_cat(cogs_cur, "gross_sales", cat)
            if ns == 0 and dc == 0: continue
            rows.append({
                "Category": cat,
                "Net Sales (LBP)": ns,
                "% of Total": f"{pct(ns,net)*100:.1f}%",
                "Discount (LBP)": dc,
                "Disc % of Gross": f"{pct(dc,gs)*100:.2f}%",
            })
        rows.append({
            "Category": "TOTAL",
            "Net Sales (LBP)": net,
            "% of Total": "100.0%",
            "Discount (LBP)": disc,
            "Disc % of Gross": f"{pct(disc,gross)*100:.2f}%",
        })
        df_ns = pd.DataFrame(rows)
        df_ns["Net Sales (LBP)"] = df_ns["Net Sales (LBP)"].apply(lambda v: n(v) if isinstance(v, (int, float)) else v)
        df_ns["Discount (LBP)"]  = df_ns["Discount (LBP)"].apply(lambda v: n(v) if isinstance(v, (int, float)) else v)
        st.dataframe(df_ns, use_container_width=True, hide_index=True)

        # ── Two KPI highlight boxes ─────────────────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        col_net, col_ncogs = st.columns(2)
        with col_net:
            st.markdown(f"""
                <div style="background:{EK_DARK};border-radius:12px;padding:20px 24px;
                            border:1px solid rgba(227,197,173,0.2);text-align:center;">
                    <div style="color:{EK_GRAY};font-size:12px;text-transform:uppercase;letter-spacing:0.08em;">Net Sales</div>
                    <div style="color:{EK_SAND};font-size:32px;font-weight:700;margin:8px 0;">{n(net)}</div>
                    <div style="color:{EK_GRAY};font-size:11px;">{mlabel(selected_month)}</div>
                </div>
            """, unsafe_allow_html=True)
        with col_ncogs:
            st.markdown(f"""
                <div style="background:{EK_DARK};border-radius:12px;padding:20px 24px;
                            border:1px solid rgba(227,197,173,0.2);text-align:center;">
                    <div style="color:{EK_GRAY};font-size:12px;text-transform:uppercase;letter-spacing:0.08em;">Net COGS</div>
                    <div style="color:{EK_SAND};font-size:32px;font-weight:700;margin:8px 0;">{n(ncogs)}</div>
                    <div style="color:{EK_GRAY};font-size:11px;">{pct(ncogs,net)*100:.2f}% of Net Sales</div>
                </div>
            """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — CATEGORY PERFORMANCE
    # ══════════════════════════════════════════════════════════════════════════
    with tab2:
        section_header("Category Performance Metrics")

        for cat in ["Beverages", "Food"]:
            ns_cat  = agg_cat(cogs_cur, "net_sales", cat)
            gc_cat  = agg_cat(cogs_cur, "gross_cogs", cat)
            nc_cat  = agg_cat(cogs_cur, "net_cogs", cat)
            if ns_cat == 0: continue

            st.markdown(f"""
                <div style="background:{EK_DARK};border-radius:10px;padding:14px 18px;
                            margin:8px 0;border:1px solid rgba(227,197,173,0.15);">
                    <span style="color:{EK_SAND};font-weight:600;font-size:14px;">{cat}</span>
                    &nbsp;&nbsp;
                    <span style="color:{EK_GRAY};font-size:12px;">
                        Net Sales: <b style="color:{EK_SAND};">{n(ns_cat)}</b> &nbsp;|&nbsp;
                        Gross COGS: <b style="color:{EK_SAND};">{n(gc_cat)}</b> ({pct(gc_cat,ns_cat)*100:.1f}%) &nbsp;|&nbsp;
                        Net COGS: <b style="color:{EK_SAND};">{n(nc_cat)}</b> ({pct(nc_cat,ns_cat)*100:.1f}%)
                    </span>
                </div>
            """, unsafe_allow_html=True)

            # Top 5 groups by revenue for this category
            if not sales_df.empty and "category" in sales_df.columns:
                sub = sales_df[sales_df["category"] == cat].copy()
                sub["gross_sales"] = pd.to_numeric(sub["gross_sales"], errors="coerce").fillna(0)
                sub["qty_sold"]    = pd.to_numeric(sub["qty_sold"],    errors="coerce").fillna(0)

                if not sub.empty and "group" in sub.columns:
                    grp = sub.groupby("group").agg(
                        revenue=("gross_sales", "sum"), qty=("qty_sold", "sum")
                    ).reset_index().sort_values("revenue", ascending=False)

                    col_list, col_chart = st.columns([1, 2])

                    with col_list:
                        st.markdown(f"**Top 5 Groups — {cat}**")
                        for i, (_, r) in enumerate(grp.head(5).iterrows(), 1):
                            st.markdown(f"<span style='color:{EK_GRAY};font-size:12px;'>"
                                        f"{i}. {r['group'][:30]}</span> &nbsp; "
                                        f"<b style='color:{EK_SAND};font-size:12px;'>{n(r['revenue'])}</b>",
                                        unsafe_allow_html=True)

                        st.markdown("<br>**Top 3 Menu Items**")
                        top3 = sub.nlargest(3, "gross_sales")
                        for i, (_, r) in enumerate(top3.iterrows(), 1):
                            st.markdown(f"<span style='color:{EK_GRAY};font-size:12px;'>"
                                        f"{i}. {str(r.get('description',''))[:25]}</span> &nbsp; "
                                        f"<b style='color:{EK_SAND};font-size:12px;'>"
                                        f"{n(r['qty_sold'],0)} qty | {n(r['gross_sales'])}</b>",
                                        unsafe_allow_html=True)

                    with col_chart:
                        top_grps = grp.head(8)
                        fig2 = go.Figure(go.Bar(
                            x=top_grps["revenue"],
                            y=top_grps["group"],
                            orientation="h",
                            marker_color=EK_SAND,
                            text=top_grps["revenue"].apply(lambda v: n(v)),
                            textposition="outside",
                            textfont=dict(size=9, color=EK_SAND)
                        ))
                        fig2.update_layout(**PLOTLY_LAYOUT,
                                           xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                           yaxis=dict(gridcolor="rgba(255,255,255,0.05)",
                                                      categoryorder="total ascending"),
                                           height=280)
                        st.plotly_chart(fig2, use_container_width=True)

            st.divider()

        # Total Revenue by Group across all categories
        if not sales_df.empty and "group" in sales_df.columns:
            section_header("Total Revenue by Group")
            sales_df["gross_sales"] = pd.to_numeric(sales_df["gross_sales"], errors="coerce").fillna(0)
            all_grp = sales_df.groupby("group")["gross_sales"].sum().reset_index().sort_values("gross_sales", ascending=False)
            fig3 = px.bar(all_grp, x="group", y="gross_sales",
                          labels={"group": "Group", "gross_sales": "Gross Revenue (LBP)"},
                          color_discrete_sequence=[EK_SAND])
            fig3.update_layout(**PLOTLY_LAYOUT,
                               xaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickangle=-30),
                               yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
            st.plotly_chart(fig3, use_container_width=True)

        # Top 10 by qty and revenue side by side
        if not sales_df.empty:
            section_header("Top 10 Items — Quantity vs Revenue")
            for cat in ["Beverages", "Food"]:
                sub = sales_df[sales_df["category"] == cat].copy() if "category" in sales_df.columns else pd.DataFrame()
                if sub.empty: continue
                sub["qty_sold"]    = pd.to_numeric(sub["qty_sold"],    errors="coerce").fillna(0)
                sub["gross_sales"] = pd.to_numeric(sub["gross_sales"], errors="coerce").fillna(0)
                tq = sub.nlargest(10, "qty_sold")
                tr = sub.nlargest(10, "gross_sales")

                st.markdown(f"**{cat}**")
                cq, cr = st.columns(2)
                with cq:
                    st.markdown("<span style='color:#6B7B86;font-size:11px;'>By Quantity</span>", unsafe_allow_html=True)
                    st.dataframe(tq[["description","qty_sold","gross_sales"]].rename(columns={
                        "description":"Item","qty_sold":"Qty","gross_sales":"Revenue (LBP)"}
                    ).assign(**{"Revenue (LBP)": tq["gross_sales"].apply(n)}).reset_index(drop=True),
                    use_container_width=True, hide_index=True)
                with cr:
                    st.markdown("<span style='color:#6B7B86;font-size:11px;'>By Revenue</span>", unsafe_allow_html=True)
                    st.dataframe(tr[["description","qty_sold","gross_sales"]].rename(columns={
                        "description":"Item","qty_sold":"Qty","gross_sales":"Revenue (LBP)"}
                    ).assign(**{"Revenue (LBP)": tr["gross_sales"].apply(n)}).reset_index(drop=True),
                    use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — VARIANCE & WASTE
    # ══════════════════════════════════════════════════════════════════════════
    with tab3:
        section_header("Waste & Variance Metrics")

        for cat in ["Beverages", "Food"]:
            waste_cat = agg_cat(cogs_cur, "waste", cat)
            ns_cat    = agg_cat(cogs_cur, "net_sales", cat)
            waste_pct = pct(waste_cat, ns_cat) * 100

            if waste_pct > 20:
                alert_box(f"🚨 <b>Dangerous:</b> {cat} waste is severely high at <b>{waste_pct:.1f}%</b>. Immediate action required.", "danger")
            elif waste_pct > 5:
                alert_box(f"⚠️ <b>High:</b> {cat} waste at <b>{waste_pct:.1f}%</b>.", "warning")
            elif waste_pct > 0:
                alert_box(f"✅ <b>Normal:</b> {cat} waste is under control at {waste_pct:.1f}%.", "ok")

        if not var_df.empty:
            var_df2 = var_df.copy()
            var_df2["tt_variance_lbp"] = pd.to_numeric(var_df2["tt_variance_lbp"], errors="coerce").fillna(0)
            var_df2["tt_variance_usd"] = pd.to_numeric(var_df2["tt_variance_usd"], errors="coerce").fillna(0)

            for cat in ["Beverages", "Food"]:
                sub = var_df2[var_df2["category"] == cat]
                neg = sub[sub["tt_variance_lbp"] < 0]["tt_variance_lbp"].sum()
                pos = sub[sub["tt_variance_lbp"] > 0]["tt_variance_lbp"].sum()
                if neg == 0 and pos == 0: continue
                lvl = "ok" if abs(neg) < abs(pos) else "warning"
                alert_box(f"{'✅ Acceptable' if lvl=='ok' else '⚠️ Watch'}: "
                          f"<b>{cat}</b> variance — Negative: ({n(abs(neg))}) | Positive: {n(pos)} LBP", lvl)

            st.markdown("<br>", unsafe_allow_html=True)
            section_header("Top Negative Variances (LBP)")

            neg_top = var_df2[var_df2["tt_variance_lbp"] < 0].nsmallest(15, "tt_variance_lbp")
            if not neg_top.empty:
                display_neg = neg_top[["product","category","group","variance","avg_cost","tt_variance_lbp","tt_variance_usd","variance_flag"]].copy()
                display_neg.columns = ["Product","Category","Group","Variance (Unit)","Avg Cost","Tt Variance (LBP)","Tt Variance (USD)","Flag"]
                for col in ["Avg Cost","Tt Variance (LBP)","Tt Variance (USD)"]:
                    display_neg[col] = display_neg[col].apply(lambda v: n(float(v)) if pd.notna(v) else "-")
                display_neg["Variance (Unit)"] = display_neg["Variance (Unit)"].apply(lambda v: n(float(v),3) if pd.notna(v) else "-")
                st.dataframe(display_neg.reset_index(drop=True), use_container_width=True, hide_index=True)

            section_header("Top Positive Variances (LBP)")
            pos_top = var_df2[var_df2["tt_variance_lbp"] > 0].nlargest(10, "tt_variance_lbp")
            if not pos_top.empty:
                display_pos = pos_top[["product","category","group","variance","tt_variance_lbp","variance_flag"]].copy()
                display_pos.columns = ["Product","Category","Group","Variance (Unit)","Tt Variance (LBP)","Flag"]
                display_pos["Tt Variance (LBP)"] = display_pos["Tt Variance (LBP)"].apply(lambda v: n(float(v)))
                display_pos["Variance (Unit)"]   = display_pos["Variance (Unit)"].apply(lambda v: n(float(v),3))
                st.dataframe(display_pos.reset_index(drop=True), use_container_width=True, hide_index=True)

            # Variance chart
            section_header("Variance Distribution")
            top_abs = var_df2.assign(abs_var=var_df2["tt_variance_lbp"].abs()).nlargest(15, "abs_var")
            fig_v = go.Figure(go.Bar(
                x=top_abs["tt_variance_lbp"],
                y=top_abs["product"].apply(lambda v: str(v)[:25]),
                orientation="h",
                marker_color=[EK_RED if v < 0 else EK_GREEN for v in top_abs["tt_variance_lbp"]],
                text=top_abs["tt_variance_lbp"].apply(lambda v: n(v)),
                textposition="outside",
                textfont=dict(size=8)
            ))
            fig_v.update_layout(**PLOTLY_LAYOUT,
                                xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                yaxis=dict(gridcolor="rgba(255,255,255,0.05)", categoryorder="total ascending"),
                                height=420)
            st.plotly_chart(fig_v, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — THEORETICAL COST
    # ══════════════════════════════════════════════════════════════════════════
    with tab4:
        section_header("Theoretical Cost Analysis")

        if theo_df.empty:
            st.info("No theoretical data available for this period.")
        else:
            for col in ["theoretical_cost","total_revenue","cost_pct","sales","gross_sales"]:
                if col in theo_df.columns:
                    theo_df[col] = pd.to_numeric(theo_df[col], errors="coerce").fillna(0)

            # Summary by category
            cat_s = theo_df.groupby("category").agg(
                theo=("theoretical_cost","sum"), rev=("total_revenue","sum")).reset_index()
            cat_s["cost_pct"] = cat_s.apply(lambda r: pct(r["theo"],r["rev"]), axis=1)

            c_sum1, c_sum2 = st.columns(2)
            with c_sum1:
                st.markdown("**Summary by Category**")
                cs_disp = cat_s.copy()
                cs_disp["Theoretical Cost"] = cs_disp["theo"].apply(n)
                cs_disp["Revenue"]          = cs_disp["rev"].apply(n)
                cs_disp["Cost %"]           = cs_disp["cost_pct"].apply(lambda v: f"{v*100:.2f}%")
                st.dataframe(cs_disp[["category","Theoretical Cost","Revenue","Cost %"]].rename(
                    columns={"category":"Category"}), use_container_width=True, hide_index=True)

            with c_sum2:
                fig_t = go.Figure(go.Bar(
                    x=cat_s["category"], y=cat_s["theo"],
                    marker_color=EK_SAND,
                    text=cat_s["theo"].apply(n), textposition="outside",
                    textfont=dict(size=9, color=EK_SAND)
                ))
                fig_t.update_layout(**PLOTLY_LAYOUT, height=220,
                                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)"))
                st.plotly_chart(fig_t, use_container_width=True)

            # Top cost % items
            st.markdown("<br>", unsafe_allow_html=True)
            section_header("Top 5 Highest Cost % by Category")
            for cat in ["Beverages", "Food"]:
                sub = theo_df[(theo_df["category"]==cat) & (theo_df["sales"]>0)].nlargest(5, "cost_pct")
                if sub.empty: continue
                st.markdown(f"**{cat}**")
                disp = sub[["menu_item","group","sales","theoretical_cost","total_revenue","cost_pct"]].copy()
                disp.columns = ["Menu Item","Group","Sales","Theo Cost","Revenue","Cost %"]
                disp["Theo Cost"] = disp["Theo Cost"].apply(n)
                disp["Revenue"]   = disp["Revenue"].apply(n)
                disp["Cost %"]    = disp["Cost %"].apply(lambda v: f"{v*100:.2f}%")
                st.dataframe(disp.reset_index(drop=True), use_container_width=True, hide_index=True)

            # Full item detail
            section_header("Full Theoretical Cost Detail")
            theo_disp = theo_df[theo_df["sales"] > 0].sort_values(["category","group","menu_item"]).copy()
            theo_disp["Theo Cost"] = theo_disp["theoretical_cost"].apply(n)
            theo_disp["Revenue"]   = theo_disp["total_revenue"].apply(n)
            theo_disp["Cost %"]    = theo_disp["cost_pct"].apply(lambda v: f"{v*100:.2f}%")
            theo_disp["Cost of Disc"] = theo_disp["cost_of_discount"].apply(n) if "cost_of_discount" in theo_disp.columns else "-"
            st.dataframe(theo_disp[["category","group","menu_item","sales","Theo Cost","Revenue","Cost %","Cost of Disc"]].rename(
                columns={"category":"Category","group":"Group","menu_item":"Menu Item","sales":"Sales Qty",
                         "Cost of Disc":"Cost of Disc"}
            ).reset_index(drop=True), use_container_width=True, hide_index=True)
