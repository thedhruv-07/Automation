"""Email renewal-alert sender for Absolute Veritas -- sends via Brevo's
transactional email API, reusing the same HTML template the dashboard's
/api/email-preview endpoint already builds. Mirrors whatsapp_renewal_alerts.py's
send_message/send_one_alert/run structure so the two channels behave
consistently, but tracks its own dedup log (email_sent_log, independent of
WhatsApp's sent_log) so a client can receive both channels the same day
without one blocking the other."""
import base64
from datetime import datetime
from pathlib import Path

import requests

from db import read_clients, load_email_sent_log, save_email_sent_log
from email_template import build_email_html
from whatsapp_renewal_alerts import dedup_key, filter_alertable

SCRIPT_DIR = Path(__file__).parent
LOGO_PATH = SCRIPT_DIR.parent / "frontend" / "public" / "company-logo.png"
LOGO_CID = "company-logo.png"

EMAIL_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")


def _parse_expiry(value) -> datetime:
    if isinstance(value, datetime):
        return value
    for fmt in EMAIL_DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value!r}")


def _is_valid_email(value) -> bool:
    return bool(value) and "@" in str(value)


def send_email_via_brevo(rec: dict, brevo_api_key: str, email_sender: str, org_name: str, to_email: str):
    """Builds the HTML (same build_email_html() the preview endpoint uses) and
    sends via Brevo's transactional email API. Returns (success, info_dict)
    matching whatsapp_renewal_alerts.send_message()'s contract."""
    expiry_dt = _parse_expiry(rec["expiry_date"])
    days_left = (expiry_dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    template_rec = {
        **rec,
        "days_left": days_left,
        "expiry_formatted": expiry_dt.strftime("%d %B %Y"),
    }

    logo_exists = LOGO_PATH.exists()
    logo_src = f"cid:{LOGO_CID}" if logo_exists else ""
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src,
    )
    subject = f"[Action Required] Renew {rec['cert_name']} — {rec['company']}"

    payload = {
        "sender": {"name": org_name, "email": email_sender},
        "to": [{"email": to_email, "name": rec["name"]}],
        "subject": subject,
        "htmlContent": html,
    }
    # Brevo's API doc doesn't guarantee an empty `attachment: []` is accepted,
    # so the key is only included when there's an actual attachment to send --
    # avoids relying on unverified behavior for the common case (no logo file
    # present, e.g. in dev/test environments).
    if logo_exists:
        logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        payload["attachment"] = [{"name": LOGO_CID, "content": logo_b64}]
    headers = {
        "api-key": brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=15,
        )
    except requests.RequestException as exc:
        return False, {"error": str(exc)}

    if response.status_code in (200, 201):
        try:
            data = response.json()
            return True, {"message_id": data.get("messageId")}
        except ValueError:
            return True, {"message_id": None}

    try:
        error_message = response.json().get("message", response.text)
    except ValueError:
        error_message = response.text
    return False, {"error": error_message}


def send_one_email_alert(
    record: dict,
    sent_log: dict,
    today: str,
    brevo_api_key: str,
    email_sender: str,
    org_name: str,
    to_email_override: str | None = None,
    send_fn=send_email_via_brevo,
) -> dict:
    """Send (or skip) one alert-eligible client's renewal email. Mutates
    sent_log in place on a successful send. Returns a result dict with action
    one of 'sent' / 'skipped_duplicate' / 'skipped_no_email' / 'failed'."""
    to_email = to_email_override or record.get("email")

    if not _is_valid_email(to_email):
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "skipped_no_email",
            "to": None,
        }

    key = dedup_key(record["client_id"], record["status"], today)
    if key in sent_log:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "skipped_duplicate",
            "to": to_email,
        }

    try:
        ok, info = send_fn(record, brevo_api_key, email_sender, org_name, to_email=to_email)
        if ok:
            sent_log[key] = {
                "sent_at": datetime.now().isoformat(),
                "message_id": info.get("message_id"),
                "email": to_email,
            }
            return {
                "client_id": record["client_id"], "name": record["name"],
                "status": record["status"], "action": "sent",
                "to": to_email, "message_id": info.get("message_id"),
            }
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_email, "error": info.get("error"),
        }
    except Exception as exc:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_email, "error": str(exc),
        }


def run_email_alerts(
    db_path,
    brevo_api_key: str,
    email_sender: str,
    org_name: str,
    dry_run: bool = False,
    test_email: str | None = None,
    today: str | None = None,
    send_fn=send_email_via_brevo,
    on_progress=None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = filter_alertable(read_clients(db_path))
    sent_log = load_email_sent_log(db_path)
    persist_log = not dry_run and not test_email
    log_dirty = False
    results = []

    for rec in records:
        if dry_run:
            to_email = test_email or rec.get("email")
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "dry_run", "to": to_email,
            }
        else:
            result = send_one_email_alert(
                rec, sent_log, today, brevo_api_key, email_sender, org_name,
                to_email_override=test_email, send_fn=send_fn,
            )
            if result["action"] == "sent":
                log_dirty = True

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    if persist_log and log_dirty:
        save_email_sent_log(db_path, sent_log)

    return results
