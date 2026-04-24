import smtplib
import streamlit as st
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client, Client


@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


# ──────────────────────────────────────────────
# SMTP CONNECTION
# ──────────────────────────────────────────────

def _get_smtp_connection():
    """Open and return an authenticated SMTP connection to Microsoft 365."""
    smtp_server   = st.secrets["EMAIL_SMTP_SERVER"]
    smtp_port     = int(st.secrets["EMAIL_SMTP_PORT"])
    sender_email  = st.secrets["EMAIL_SENDER"]
    sender_pass   = st.secrets["EMAIL_PASSWORD"]

    server = smtplib.SMTP(smtp_server, smtp_port)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(sender_email, sender_pass)
    return server


def _send(subject: str, html_body: str, recipients: list[str]) -> bool:
    """
    Core send function. Accepts a list of recipient emails.
    Returns True if sent, False if failed.
    """
    if not recipients:
        return False

    sender_email = st.secrets["EMAIL_SENDER"]

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"EK Consulting <{sender_email}>"
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(html_body, "html"))

        server = _get_smtp_connection()
        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()
        return True

    except Exception as e:
        # Log silently — never crash the app because of an email failure
        print(f"[email_helper] Failed to send email: {e}")
        return False


# ──────────────────────────────────────────────
# RECIPIENT RESOLVER
# ──────────────────────────────────────────────

def _get_transfer_recipients(client_name: str, outlet: str) -> list[str]:
    """
    Returns emails of all users in the outlet who have
    transfer_notification = true and a non-empty email address.
    """
    supabase = get_supabase()
    try:
        res = (
            supabase.table("users")
            .select("email, full_name")
            .eq("transfer_notification", True)
            .eq("client_name", client_name)
            .execute()
        )
        emails = []
        for u in (res.data or []):
            email = (u.get("email") or "").strip()
            # Also include users with outlet = "All" (managers with full visibility)
            user_outlet = (u.get("outlet") or "").strip()
            if email and (user_outlet.lower() in [outlet.lower(), "all"]):
                emails.append(email)
        return list(set(emails))  # deduplicate
    except Exception as e:
        print(f"[email_helper] Could not fetch recipients: {e}")
        return []


# ──────────────────────────────────────────────
# EMAIL TEMPLATES
# ──────────────────────────────────────────────

def _transfer_email_html(transfer: dict) -> str:
    """Build the HTML email body for a direct transfer notification."""

    item_name  = ""
    qty        = ""
    unit       = ""

    # Parse the details JSON to get item info
    import json
    try:
        items = json.loads(transfer.get("details") or "[]")
        if items and isinstance(items, list):
            first = items[0]
            item_name = first.get("item_name", "")
            qty       = first.get("requested_qty", "")
            unit      = first.get("requested_unit", "")
    except Exception:
        pass

    from_loc  = transfer.get("from_location", "")
    to_loc    = transfer.get("to_location", "")
    remarks   = transfer.get("remarks", "")
    action_by = transfer.get("action_by", "").replace("Direct by ", "")
    date      = transfer.get("date", "")
    tid       = transfer.get("transfer_id", "")

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; color: #1B252C;">

      <div style="background: #1B252C; padding: 20px 28px; border-radius: 8px 8px 0 0;">
        <p style="color: #E3C5AD; font-size: 13px; margin: 0; letter-spacing: 0.04em; text-transform: uppercase;">EK Consulting · Paperless</p>
        <p style="color: #ffffff; font-size: 18px; font-weight: 600; margin: 6px 0 0;">Direct Transfer Recorded</p>
      </div>

      <div style="background: #f9f8f6; padding: 24px 28px; border: 1px solid #e8e4de; border-top: none; border-radius: 0 0 8px 8px;">

        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <tr>
            <td style="padding: 8px 0; color: #888; width: 40%;">Item</td>
            <td style="padding: 8px 0; font-weight: 600;">{item_name}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">Quantity</td>
            <td style="padding: 8px 0; font-weight: 600;">{qty} {unit}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">From</td>
            <td style="padding: 8px 0;">{from_loc}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">To</td>
            <td style="padding: 8px 0;">{to_loc}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">Remark</td>
            <td style="padding: 8px 0;">
              <span style="background: #1B252C; color: #E3C5AD; font-size: 12px; font-weight: 600;
                           padding: 3px 10px; border-radius: 20px;">{remarks}</span>
            </td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">Recorded by</td>
            <td style="padding: 8px 0;">{action_by}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">Date & time</td>
            <td style="padding: 8px 0;">{date}</td>
          </tr>
          <tr>
            <td style="padding: 8px 0; color: #888;">Transfer ID</td>
            <td style="padding: 8px 0; font-family: monospace; font-size: 13px; color: #888;">#{tid}</td>
          </tr>
        </table>

        <p style="font-size: 12px; color: #aaa; margin-top: 24px; border-top: 1px solid #e8e4de; padding-top: 16px;">
          This is an automated notification from EK Paperless.
          You are receiving this because transfer notifications are enabled for your account.
        </p>

      </div>
    </div>
    """


# ──────────────────────────────────────────────
# PUBLIC FUNCTIONS — imported by other modules
# ──────────────────────────────────────────────

def send_transfer_notification(transfer: dict) -> bool:
    """
    Send a direct transfer notification email to all eligible users
    in the outlet who have transfer_notification = true.

    Args:
        transfer: the dict that was just inserted into supabase transfers table

    Returns:
        True if at least one email was sent, False otherwise.
    """
    client_name = transfer.get("from_outlet", "")
    outlet      = transfer.get("from_outlet", "")
    item_name   = ""

    import json
    try:
        items = json.loads(transfer.get("details") or "[]")
        if items:
            item_name = items[0].get("item_name", "")
    except Exception:
        pass

    recipients = _get_transfer_recipients(
        client_name=transfer.get("requester", ""),  # fallback
        outlet=outlet
    )

    # Try to resolve client_name from session state if available
    try:
        client_name = st.session_state.get("client_name", outlet)
        recipients  = _get_transfer_recipients(client_name=client_name, outlet=outlet)
    except Exception:
        pass

    subject   = f"Direct Transfer — {item_name} · {transfer.get('from_location', '')} → {transfer.get('to_location', '')}"
    html_body = _transfer_email_html(transfer)

    return _send(subject, html_body, recipients)