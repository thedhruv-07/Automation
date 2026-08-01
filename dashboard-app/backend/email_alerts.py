"""Email renewal-alert sender for Absolute Veritas -- sends via Brevo's
transactional email API, reusing the same HTML template the dashboard's
/api/email-preview endpoint already builds. Mirrors whatsapp_renewal_alerts.py's
send_message/send_one_alert/run structure so the two channels behave
consistently, but tracks its own dedup log (email_sent_log, independent of
WhatsApp's sent_log) so a client can receive both channels the same day
without one blocking the other."""
import base64
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from db import DEFAULT_DB_PATH, get_eligible_clients, load_email_sent_log, save_email_sent_log
from email_template import build_email_html
from scheme_templates import get_email_content
from whatsapp_renewal_alerts import dedup_key

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
LOGO_PATH = SCRIPT_DIR.parent / "frontend" / "public" / "company-logo.png"
LOGO_CID = "company-logo.png"

BREVO_DAILY_LIMIT = 300

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


def post_email_via_brevo(payload: dict, brevo_api_key: str) -> tuple[bool, dict]:
    """Low-level Brevo transactional email API call, shared by
    send_email_via_brevo (renewal alerts) and notice_sender.py's notice
    email sending -- the two build very different payload content, but the
    HTTP call and response handling is identical. Returns (success,
    info_dict) matching whatsapp_renewal_alerts.send_message()'s contract."""
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
    subject_template, intro_text = get_email_content(rec["scheme"])
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src, intro_text=intro_text,
    )
    subject = subject_template.format(cert_name=rec["cert_name"], company=rec["company"])

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
    return post_email_via_brevo(payload, brevo_api_key)


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
    status: str | None = None,
    cert_type: str | None = None,
    expiry_before: str | None = None,
    search: str | None = None,
    scheme: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """limit caps how many actual sends (action == "sent") this call makes --
    e.g. Brevo's 300/day cap. Once hit, remaining eligible records are left
    untouched (not marked sent), so a daily re-run naturally picks them up
    the next day via the same per-day dedup that already skips today's
    sent ones."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    sent_log = load_email_sent_log(db_path)
    persist_log = not dry_run and not test_email
    log_dirty = False
    results = []
    sent_count = 0

    for rec in records:
        if limit is not None and sent_count >= limit:
            break

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
                sent_count += 1

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    if persist_log and log_dirty:
        save_email_sent_log(db_path, sent_log)

    return results


def main(argv=None) -> int:
    """CLI entrypoint for a daily scheduled run (e.g. a Render Cron Job at
    9am), capped at BREVO_DAILY_LIMIT sends per run so a big eligible batch
    spills over to the next day's run instead of erroring past Brevo's daily
    cap."""
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("BREVO_API_KEY")
    sender = os.environ.get("EMAIL_SENDER")
    if not api_key or not sender:
        print("❌ BREVO_API_KEY and EMAIL_SENDER must be set in .env.")
        return 1

    results = run_email_alerts(
        DEFAULT_DB_PATH, api_key, sender, "Absolute Veritas", limit=BREVO_DAILY_LIMIT,
    )
    sent = sum(1 for r in results if r["action"] == "sent")
    skipped = sum(1 for r in results if r["action"] == "skipped_duplicate")
    skipped_no_email = sum(1 for r in results if r["action"] == "skipped_no_email")
    failed = sum(1 for r in results if r["action"] == "failed")
    print(f"{sent} sent, {skipped} skipped (already sent today), {skipped_no_email} skipped (no email), {failed} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
