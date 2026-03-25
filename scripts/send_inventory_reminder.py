"""
Monthly Inventory Reminder — sends email to all users with inv_reminder = true.
Triggered by GitHub Actions on the last day of each month.
"""
import os
import resend
import calendar
from datetime import date
from supabase import create_client

# ── Guard: only run on the actual last day of the month ──────────────────────
today = date.today()
last_day = calendar.monthrange(today.year, today.month)[1]
if today.day != last_day:
    print(f"Today is {today} — not the last day of the month ({last_day}). Skipping.")
    exit(0)

print(f"Running inventory reminder for {today.strftime('%B %Y')} ...")

# ── Supabase ─────────────────────────────────────────────────────────────────
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

res = supabase.table("users").select("full_name, email, outlet").eq("inv_reminder", True).execute()
recipients = [u for u in (res.data or []) if u.get("email", "").strip()]

if not recipients:
    print("No users with inv_reminder=true and a valid email. Nothing to send.")
    exit(0)

print(f"Found {len(recipients)} recipient(s).")

# ── Resend ────────────────────────────────────────────────────────────────────
resend.api_key = os.environ["RESEND_API_KEY"]
month_label    = today.strftime("%B %Y")
SENDER         = "EK Consulting <elie.k@ekconsulting.co>"

errors = []
for user in recipients:
    outlet     = user.get("outlet", "")
    outlet_str = f" — {outlet}" if outlet and outlet.lower() not in ["all", "none", ""] else ""
    to_name    = user.get("full_name") or "Team"

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1B252C;max-width:560px;margin:auto;">
      <div style="background:#1B252C;padding:24px 28px;border-radius:10px 10px 0 0;">
        <h2 style="color:#E3C5AD;margin:0;">&#128230; Inventory Count Reminder</h2>
        <p style="color:#8a9eaa;margin:6px 0 0;">{month_label}{outlet_str}</p>
      </div>
      <div style="background:#f9f5f1;padding:24px 28px;border-radius:0 0 10px 10px;border:1px solid #e8ddd4;">
        <p>Hi <strong>{to_name}</strong>,</p>
        <p>This is your monthly reminder to complete the <strong>inventory count</strong> for <strong>{month_label}</strong>.</p>
        <p>Please log in to the EK Partner Portal and submit your count before end of day.</p>
        <br>
        <p style="color:#888;font-size:13px;">EK Consulting Team<br>elie.k@ekconsulting.co</p>
      </div>
    </body></html>
    """

    try:
        resend.Emails.send({
            "from":    SENDER,
            "to":      [user["email"]],
            "subject": f"Monthly Inventory Count Reminder — {month_label}{outlet_str}",
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
    print(f"\n✅ All reminders sent successfully.")
