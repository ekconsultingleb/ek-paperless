import json
import resend
import streamlit as st
from supabase import create_client, Client

SENDER = "EK Consulting <elie.k@ekconsulting.co>"


@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def _resend_send(subject: str, html_body: str, recipients: list[str]) -> bool:
    """Send via Resend API. Returns True if sent, False on failure."""
    if not recipients:
        return False
    try:
        resend.api_key = st.secrets["RESEND_API_KEY"]
        resend.Emails.send({
            "from":    SENDER,
            "to":      recipients,
            "subject": subject,
            "html":    html_body,
        })
        return True
    except Exception as e:
        print(f"[email_helper] Failed to send email: {e}")
        return False


# ──────────────────────────────────────────────
# RECIPIENT RESOLVER
# ──────────────────────────────────────────────

def _get_transfer_recipients(client_name: str, outlet: str) -> list[str]:
    """
    Returns emails of all users who have transfer_notification = true and:
    - client_name matches the transfer's client OR is "All"
    - outlet matches the transfer's outlet OR is "All"
    """
    supabase = get_supabase()
    try:
        res = (
            supabase.table("users")
            .select("email, full_name, client_name, outlet")
            .eq("transfer_notification", True)
            .execute()
        )
        emails = []
        for u in (res.data or []):
            email       = (u.get("email") or "").strip()
            user_client = (u.get("client_name") or "").strip().lower()
            user_outlet = (u.get("outlet") or "").strip().lower()
            if not email:
                continue
            client_match = user_client in [client_name.lower(), "all"]
            outlet_match = user_outlet in [outlet.lower(), "all"]
            if client_match and outlet_match:
                emails.append(email)
        return list(set(emails))
    except Exception as e:
        print(f"[email_helper] Could not fetch recipients: {e}")
        return []


# ──────────────────────────────────────────────
# EMAIL TEMPLATES
# ──────────────────────────────────────────────

def _transfer_email_html(transfer: dict) -> str:
    item_name = qty = unit = ""
    try:
        items = json.loads(transfer.get("details") or "[]")
        if items and isinstance(items, list):
            first     = items[0]
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
            <td style="padding: 8px 0; color: #888;">Date &amp; time</td>
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


def _request_email_html(transfer: dict) -> str:
    items_html = ""
    try:
        items = json.loads(transfer.get("details") or "[]")
        if items and isinstance(items, list):
            for item in items:
                name = item.get("item_name", "")
                qty  = item.get("requested_qty", "")
                unit = item.get("requested_unit", "")
                items_html += f"<tr><td style='padding:6px 12px;font-weight:600;border-bottom:1px solid #eee;'>{name}</td><td style='padding:6px 12px;color:#555;border-bottom:1px solid #eee;'>{qty} {unit}</td></tr>"
    except Exception:
        pass

    requester = transfer.get("requester", "")
    from_loc  = transfer.get("from_location", "")
    to_loc    = transfer.get("to_location", "")
    date      = transfer.get("date", "")
    tid       = transfer.get("transfer_id", "")

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1B252C;">
      <div style="background:#1B252C;padding:20px 28px;border-radius:8px 8px 0 0;">
        <p style="color:#E3C5AD;font-size:13px;margin:0;letter-spacing:0.04em;text-transform:uppercase;">EK Consulting · Paperless</p>
        <p style="color:#fff;font-size:18px;font-weight:600;margin:6px 0 0;">New Transfer Request</p>
      </div>
      <div style="background:#f9f8f6;padding:24px 28px;border:1px solid #e8e4de;border-top:none;border-radius:0 0 8px 8px;">
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr><td style="padding:8px 0;color:#888;width:40%;">Requested by</td><td style="padding:8px 0;font-weight:600;">{requester}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Dispatch from</td><td style="padding:8px 0;">{from_loc}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Deliver to</td><td style="padding:8px 0;">{to_loc}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Date &amp; time</td><td style="padding:8px 0;">{date}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Transfer ID</td><td style="padding:8px 0;font-family:monospace;font-size:13px;color:#888;">#{tid}</td></tr>
        </table>
        <p style="font-size:13px;font-weight:600;margin:20px 0 8px;">Items requested:</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px;border:1px solid #e8e4de;border-radius:6px;">
          <thead><tr style="background:#1B252C;color:#E3C5AD;">
            <th style="padding:8px 12px;text-align:left;font-size:12px;">Item</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;">Qty</th>
          </tr></thead>
          <tbody>{items_html}</tbody>
        </table>
        <p style="font-size:12px;color:#aaa;margin-top:24px;border-top:1px solid #e8e4de;padding-top:16px;">
          Automated notification from EK Paperless. Log in to dispatch this request.
        </p>
      </div>
    </div>"""


def _dispatch_email_html(transfer: dict) -> str:
    items_html = ""
    try:
        items = json.loads(transfer.get("details") or "[]")
        if items and isinstance(items, list):
            for item in items:
                name     = item.get("item_name", "")
                ful_qty  = item.get("fulfilled_qty", "")
                ful_unit = item.get("fulfilled_unit", item.get("db_unit", ""))
                items_html += f"<tr><td style='padding:6px 12px;font-weight:600;border-bottom:1px solid #eee;'>{name}</td><td style='padding:6px 12px;color:#555;border-bottom:1px solid #eee;'>{ful_qty} {ful_unit}</td></tr>"
    except Exception:
        pass

    from_loc  = transfer.get("from_location", "")
    to_loc    = transfer.get("to_location", "")
    action_by = transfer.get("action_by", "").replace("Sent by ", "")
    date      = transfer.get("date", "")
    tid       = transfer.get("transfer_id", "")

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;color:#1B252C;">
      <div style="background:#1B252C;padding:20px 28px;border-radius:8px 8px 0 0;">
        <p style="color:#E3C5AD;font-size:13px;margin:0;letter-spacing:0.04em;text-transform:uppercase;">EK Consulting · Paperless</p>
        <p style="color:#fff;font-size:18px;font-weight:600;margin:6px 0 0;">Transfer Dispatched</p>
      </div>
      <div style="background:#f9f8f6;padding:24px 28px;border:1px solid #e8e4de;border-top:none;border-radius:0 0 8px 8px;">
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr><td style="padding:8px 0;color:#888;width:40%;">Dispatched by</td><td style="padding:8px 0;font-weight:600;">{action_by}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">From</td><td style="padding:8px 0;">{from_loc}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">To</td><td style="padding:8px 0;">{to_loc}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Date &amp; time</td><td style="padding:8px 0;">{date}</td></tr>
          <tr><td style="padding:8px 0;color:#888;">Transfer ID</td><td style="padding:8px 0;font-family:monospace;font-size:13px;color:#888;">#{tid}</td></tr>
        </table>
        <p style="font-size:13px;font-weight:600;margin:20px 0 8px;">Items dispatched:</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px;border:1px solid #e8e4de;border-radius:6px;">
          <thead><tr style="background:#1B252C;color:#E3C5AD;">
            <th style="padding:8px 12px;text-align:left;font-size:12px;">Item</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;">Dispatched Qty</th>
          </tr></thead>
          <tbody>{items_html}</tbody>
        </table>
        <p style="font-size:12px;color:#aaa;margin-top:24px;border-top:1px solid #e8e4de;padding-top:16px;">
          Automated notification from EK Paperless. Log in to confirm receipt.
        </p>
      </div>
    </div>"""


# ──────────────────────────────────────────────
# PUBLIC FUNCTIONS — imported by other modules
# ──────────────────────────────────────────────

def send_transfer_notification(transfer: dict, client_name: str = "") -> bool:
    """
    Send a direct transfer notification email to all eligible users
    who have transfer_notification = true.

    Args:
        transfer:    the dict just inserted into the transfers table
        client_name: the client/branch name (pass final_client from the UI)

    Returns:
        True if at least one email was sent, False otherwise.
    """
    outlet    = transfer.get("from_outlet", "")
    item_name = ""
    try:
        items = json.loads(transfer.get("details") or "[]")
        if items:
            item_name = items[0].get("item_name", "")
    except Exception:
        pass

    recipients = _get_transfer_recipients(client_name=client_name, outlet=outlet)

    subject   = f"Direct Transfer — {item_name} · {transfer.get('from_location', '')} → {transfer.get('to_location', '')}"
    html_body = _transfer_email_html(transfer)

    return _resend_send(subject, html_body, recipients)


def send_request_notification(transfer: dict, client_name: str = "") -> bool:
    """Notify dispatchers at from_outlet that a new transfer request needs fulfilling."""
    outlet = transfer.get("from_outlet", "")
    try:
        items   = json.loads(transfer.get("details") or "[]")
        summary = items[0].get("item_name", "") if items else ""
        if len(items) > 1:
            summary += f" +{len(items) - 1} more"
    except Exception:
        summary = ""

    recipients = _get_transfer_recipients(client_name=client_name, outlet=outlet)
    subject    = f"New Transfer Request — {summary} → {transfer.get('to_location', '')}"
    return _resend_send(subject, _request_email_html(transfer), recipients)


def send_dispatch_notification(transfer: dict, client_name: str = "") -> bool:
    """Notify receivers at to_outlet that their transfer has been dispatched."""
    outlet = transfer.get("to_outlet", "")
    try:
        items   = json.loads(transfer.get("details") or "[]")
        summary = items[0].get("item_name", "") if items else ""
        if len(items) > 1:
            summary += f" +{len(items) - 1} more"
    except Exception:
        summary = ""

    recipients = _get_transfer_recipients(client_name=client_name, outlet=outlet)
    subject    = f"Transfer Dispatched — {summary} → {transfer.get('to_location', '')}"
    return _resend_send(subject, _dispatch_email_html(transfer), recipients)
