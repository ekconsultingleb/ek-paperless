"""
Flash Cost Report — sends a cost summary email every 3 days to users with cost_reminder = true.
Triggered by GitHub Actions on a schedule or manually.
"""
import os
import resend
from datetime import date, timedelta
from supabase import create_client

# ── Supabase ──────────────────────────────────────────────────────────────────
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

today      = date.today()
start_date = today - timedelta(days=3)
period     = f"{start_date.strftime('%d %b')} – {today.strftime('%d %b %Y')}"

print(f"Running flash cost report for {period} ...")

# ── Recipients ────────────────────────────────────────────────────────────────
rec_res    = supabase.table("users").select("full_name, email, client_name, outlet").eq("cost_reminder", True).execute()
recipients = [u for u in (rec_res.data or []) if u.get("email", "").strip()]

if not recipients:
    print("No users with cost_reminder=true and a valid email. Nothing to send.")
    exit(0)

print(f"Found {len(recipients)} recipient(s).")

# ── Invoice totals ────────────────────────────────────────────────────────────
inv_res = supabase.table("invoices_log") \
    .select("client_name, outlet, supplier, total_amount, currency, created_at") \
    .gte("created_at", f"{start_date}T00:00:00") \
    .lte("created_at", f"{today}T23:59:59") \
    .not_.is_("total_amount", "null") \
    .execute()

invoices = inv_res.data or []

# ── Daily cash totals ─────────────────────────────────────────────────────────
cash_res = supabase.table("daily_cash") \
    .select("client_name, outlet, main_reading, cash_val, visa_val, exp_val, on_acc_val, date") \
    .gte("date", str(start_date)) \
    .lte("date", str(today)) \
    .execute()

cash_rows = cash_res.data or []

# ── Resend ────────────────────────────────────────────────────────────────────
resend.api_key = os.environ["RESEND_API_KEY"]
SENDER         = "EK Consulting <elie.k@ekconsulting.co>"

errors = []
for user in recipients:
    u_client = user.get("client_name", "All")
    u_outlet = user.get("outlet", "All")
    to_name  = user.get("full_name") or "Team"

    # Filter invoices for this user's scope
    if u_client.lower() not in ["all", "", "none"]:
        u_invoices = [i for i in invoices if i.get("client_name") == u_client]
    else:
        u_invoices = invoices

    if u_outlet.lower() not in ["all", "", "none"]:
        u_invoices = [i for i in u_invoices if i.get("outlet") == u_outlet]

    # Filter cash for this user's scope
    if u_client.lower() not in ["all", "", "none"]:
        u_cash = [c for c in cash_rows if c.get("client_name") == u_client]
    else:
        u_cash = cash_rows

    if u_outlet.lower() not in ["all", "", "none"]:
        u_cash = [c for c in u_cash if c.get("outlet") == u_outlet]

    # Totals
    total_usd = sum(float(i["total_amount"]) for i in u_invoices if i.get("currency", "").upper() == "USD" and i.get("total_amount"))
    total_lbp = sum(float(i["total_amount"]) for i in u_invoices if i.get("currency", "").upper() == "LBP" and i.get("total_amount"))
    invoice_count = len(u_invoices)

    # Revenue from daily cash (m_reading is total sales)
    total_revenue = sum(float(c.get("main_reading") or 0) for c in u_cash)
    has_cash_data = len(u_cash) > 0

    # Build supplier breakdown rows
    supplier_rows = ""
    from collections import defaultdict
    sup_totals = defaultdict(lambda: {"USD": 0.0, "LBP": 0.0})
    for i in u_invoices:
        sup = i.get("supplier", "Unknown")
        cur = i.get("currency", "USD").upper()
        amt = float(i.get("total_amount") or 0)
        sup_totals[sup][cur] += amt

    for sup, totals in sorted(sup_totals.items()):
        parts = []
        if totals["USD"] > 0: parts.append(f"${totals['USD']:,.2f}")
        if totals["LBP"] > 0: parts.append(f"LBP {totals['LBP']:,.0f}")
        supplier_rows += f"<tr><td style='padding:6px 12px;border-bottom:1px solid #e8ddd4;'>{sup}</td><td style='padding:6px 12px;border-bottom:1px solid #e8ddd4;text-align:right;'>{' / '.join(parts)}</td></tr>"

    if not supplier_rows:
        supplier_rows = "<tr><td colspan='2' style='padding:8px 12px;color:#888;'>No invoices with amounts recorded for this period.</td></tr>"

    # Cash comparison row
    cash_section = ""
    if has_cash_data:
        margin_usd = total_revenue - total_usd if total_usd > 0 else None
        margin_html = f"<p style='margin:8px 0;'>💰 <strong>Revenue (Cash):</strong> ${total_revenue:,.2f} USD</p>" if total_revenue > 0 else ""
        margin_html += f"<p style='margin:8px 0;'>🛒 <strong>Purchases (USD):</strong> ${total_usd:,.2f}</p>" if total_usd > 0 else ""
        if margin_usd is not None and margin_usd > 0:
            margin_html += f"<p style='margin:8px 0;color:#3B6D11;'>✅ <strong>Gross Margin:</strong> ${margin_usd:,.2f}</p>"
        elif margin_usd is not None:
            margin_html += f"<p style='margin:8px 0;color:#A32D2D;'>⚠️ <strong>Costs exceed revenue by:</strong> ${abs(margin_usd):,.2f}</p>"
        cash_section = f"""
        <div style='background:#f0f7ea;padding:16px 20px;border-radius:8px;margin-top:16px;border:1px solid #c8e6c9;'>
          <p style='font-weight:600;margin:0 0 8px;'>📊 Flash Margin Snapshot</p>
          {margin_html}
        </div>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1B252C;max-width:600px;margin:auto;">
      <div style="background:#1B252C;padding:24px 28px;border-radius:10px 10px 0 0;">
        <h2 style="color:#E3C5AD;margin:0;">💰 Flash Cost Report</h2>
        <p style="color:#8a9eaa;margin:6px 0 0;">{period}</p>
      </div>
      <div style="background:#f9f5f1;padding:24px 28px;border-radius:0 0 10px 10px;border:1px solid #e8ddd4;">
        <p>Hi <strong>{to_name}</strong>,</p>
        <p>Here is your flash cost summary for the last 3 days (<strong>{period}</strong>).</p>
        <p style='margin:4px 0;'>📄 <strong>{invoice_count}</strong> invoice(s) recorded</p>
        {"<p style='margin:4px 0;'>💵 <strong>Total USD:</strong> ${:,.2f}</p>".format(total_usd) if total_usd > 0 else ""}
        {"<p style='margin:4px 0;'>🇱🇧 <strong>Total LBP:</strong> {:,.0f}</p>".format(total_lbp) if total_lbp > 0 else ""}
        <br>
        <table style='width:100%;border-collapse:collapse;background:#fff;border-radius:6px;overflow:hidden;'>
          <thead>
            <tr style='background:#1B252C;color:#E3C5AD;'>
              <th style='padding:8px 12px;text-align:left;'>Supplier</th>
              <th style='padding:8px 12px;text-align:right;'>Amount</th>
            </tr>
          </thead>
          <tbody>{supplier_rows}</tbody>
        </table>
        {cash_section}
        <br>
        <p style="color:#888;font-size:13px;">EK Consulting Team<br>elie.k@ekconsulting.co</p>
      </div>
    </body></html>
    """

    try:
        resend.Emails.send({
            "from":    SENDER,
            "to":      [user["email"]],
            "subject": f"💰 Flash Cost Report — {period}",
            "html":    html,
        })
        print(f"  ✓ Sent to {user['email']}")
    except Exception as e:
        print(f"  ✗ Failed for {user['email']}: {e}")
        errors.append(user["email"])

if errors:
    print(f"\n⚠️  Failed to send to: {', '.join(errors)}")
    exit(1)
else:
    print(f"\n✅ All flash cost reports sent successfully.")
