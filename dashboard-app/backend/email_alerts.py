"""Email renewal-alert sender for Absolute Veritas -- sends via Brevo's
transactional email API, reusing the same HTML template the dashboard's
/api/email-preview endpoint already builds. Mirrors whatsapp_renewal_alerts.py's
send_message/send_one_alert/run structure so the two channels behave
consistently, but tracks its own dedup log (email_sent_log, independent of
WhatsApp's sent_log) so a client can receive both channels the same day
without one blocking the other."""
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

from db import (
    DEFAULT_DB_PATH, get_eligible_clients, load_email_sent_log, save_email_sent_log,
    count_emails_sent_today,
)
from email_template import build_email_html, _tier
from scheme_templates import get_email_content
from whatsapp_renewal_alerts import dedup_key

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
LOGO_PATH = SCRIPT_DIR.parent / "frontend" / "public" / "company-logo.png"
BACKEND_PUBLIC_URL = os.environ.get("BACKEND_PUBLIC_URL", "https://automation-q3hp.onrender.com")

BREVO_DAILY_LIMIT = 300
REMINDER_INTERVAL_DAYS = 20

EMAIL_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")

ISI_CTA_LABEL = "Proceed with Renewal"
ISI_EXPIRY_LABEL = "BIS License Expiry date:"
ISI_SIGNATURE_HTML = """
    <p style="color:#1F497D;font-size:14px;font-weight:700;margin:0 0 2px;">Absolute Veritas</p>
    <p style="color:#E36C0A;font-size:13px;font-weight:700;margin:0 0 10px;">Inspection, Testing &amp; Certifications</p>
    <p style="color:#52514E;font-size:13px;margin:0 0 3px;">Mobile/Whatsapp: +91-7303215033</p>
    <p style="color:#52514E;font-size:13px;margin:0 0 3px;">Tel: +91-129-4001010</p>
    <p style="color:#52514E;font-size:13px;margin:0 0 3px;">Email: cs@absoluteveritas.com</p>
    <p style="color:#52514E;font-size:13px;margin:0;">Website: www.absoluteveritas.com</p>
"""


def logo_url() -> str:
    """Neither of the two embedding tricks render reliably across real mail
    clients: Brevo's transactional API doesn't support inline CID images at
    all (its `attachment` field never maps back into the HTML body), and a
    data: URI -- while it works in some clients -- is silently stripped by
    Gmail and was seen rendering mis-sized/cropped in Outlook. A plain
    https:// URL is the one approach every client supports, so the logo is
    served from this backend's own /company-logo.png route (see main.py)
    instead of being embedded in the email at all."""
    if not LOGO_PATH.exists():
        return ""
    return f"{BACKEND_PUBLIC_URL}/company-logo.png"


def scheme_html_overrides(rec: dict, scheme: str) -> dict:
    """Returns build_email_html() kwargs for the given scheme's dedicated
    layout, or {} to keep the generic default layout. rec must already carry
    expiry_formatted (see send_email_via_brevo/email_preview). ISI is the
    only scheme with a dedicated layout so far -- ships in code (not env
    vars, unlike subject/intro text) since it's a whole extra table row set
    and signature block, not a short string a non-developer would tweak."""
    if scheme.upper() != "ISI":
        return {}
    _label, tier_color, _message, _hero_label = _tier(rec["days_left"])
    current_validity = f'<span style="color:{tier_color};">{rec["expiry_formatted"]}</span>'
    return {
        "detail_rows": [
            ("Company / Manufacturer", f"M/s {rec['company']}"),
            ("Certification", "ISI Certification"),
            ("Indian Standard", rec["cert_name"]),
            ("BIS Licence No.", rec["cert_id"]),
            ("Current Validity", current_validity),
        ],
        "expiry_label": ISI_EXPIRY_LABEL,
        "cta_label": ISI_CTA_LABEL,
        "signature_html": ISI_SIGNATURE_HTML,
    }


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

    subject_template, intro_text = get_email_content(rec["scheme"])
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", intro_text=intro_text,
        **scheme_html_overrides(template_rec, rec["scheme"]),
    )
    subject = subject_template.format(
        cert_name=rec["cert_name"], company=rec["company"],
        cert_id=rec["cert_id"], expiry_date=template_rec["expiry_formatted"],
    )

    payload = {
        "sender": {"name": org_name, "email": email_sender},
        "to": [{"email": to_email, "name": rec["name"]}],
        "subject": subject,
        "htmlContent": html,
    }
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

    # sent_log stores one entry per day actually sent (dedup_key includes the
    # date), so "already reminded for this status" means the most recent
    # entry for this client+status is within REMINDER_INTERVAL_DAYS -- not a
    # single day/status lookup. A status change (e.g. DUE SOON -> URGENT as
    # the expiry gets closer) has no prior entries, so it still sends
    # immediately -- a 60-day-out client naturally gets ~3 emails total
    # (DUE SOON, a 20-day-later DUE SOON reminder, then URGENT) with no
    # separate reminder counter needed.
    prefix = f"{record['client_id']}|{record['status']}|"
    prior_dates = [k[len(prefix):] for k in sent_log if k.startswith(prefix)]
    if prior_dates:
        last_sent_date = datetime.strptime(max(prior_dates), "%Y-%m-%d").date()
        today_date = datetime.strptime(today, "%Y-%m-%d").date()
        if (today_date - last_sent_date).days < REMINDER_INTERVAL_DAYS:
            return {
                "client_id": record["client_id"], "name": record["name"],
                "status": record["status"], "action": "skipped_duplicate",
                "to": to_email,
            }

    key = dedup_key(record["client_id"], record["status"], today)

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
    sort_by_expiry: bool = False,
    expiry_month: str | None = None,
    ignore_alert_status: bool = False,
) -> list[dict]:
    """limit caps how many actual sends (action == "sent") this call makes --
    e.g. Brevo's 300/day cap. Once hit, remaining eligible records are left
    untouched (not marked sent), so a daily re-run naturally picks them up
    the next day via the same per-day dedup that already skips today's
    sent ones. sort_by_expiry=True processes soonest-expiring clients first,
    so if limit cuts a run short, the most urgent ones were already attempted
    -- see get_eligible_clients for why this defaults to False (insertion
    order is depended on elsewhere). expiry_month/ignore_alert_status let a
    caller send to every client expiring in a specific month regardless of
    their current urgency status -- see get_eligible_clients."""
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme, sort_by_expiry=sort_by_expiry,
        expiry_month=expiry_month, ignore_alert_status=ignore_alert_status,
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

    remaining = max(0, BREVO_DAILY_LIMIT - count_emails_sent_today(DEFAULT_DB_PATH, datetime.now().strftime("%Y-%m-%d")))
    results = run_email_alerts(
        DEFAULT_DB_PATH, api_key, sender, "Absolute Veritas", limit=remaining,
    )
    sent = sum(1 for r in results if r["action"] == "sent")
    skipped = sum(1 for r in results if r["action"] == "skipped_duplicate")
    skipped_no_email = sum(1 for r in results if r["action"] == "skipped_no_email")
    failed = sum(1 for r in results if r["action"] == "failed")
    print(f"{sent} sent, {skipped} skipped (already sent today), {skipped_no_email} skipped (no email), {failed} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
