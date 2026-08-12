"""Send orchestration for one-time broadcast notices (see notices.py for
the content registry). Mirrors whatsapp_renewal_alerts.run()/
email_alerts.run_email_alerts()'s shape, but targets get_broadcast_clients()
(every matching client regardless of alert status, not just ALERT_STATUSES)
and dedups against notice_sent_log (permanent, not per-day) instead of
sent_log/email_sent_log."""
import base64
import time
from datetime import datetime

from db import get_broadcast_clients, get_adhoc_recipients, is_notice_already_sent, record_notice_sent
from email_alerts import post_email_via_brevo, LOGO_PATH, LOGO_CID
from notices import get_notice_module, get_adhoc_notice_module
from whatsapp_renewal_alerts import normalize_phone, send_message


def send_notice_whatsapp(
    db_path, notice_id: str, token: str, phone_number_id: str,
    dry_run: bool = False, test_number: str | None = None, send_fn=send_message,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
    limit: int | None = None, pace_seconds: float = 0.0,
) -> list[dict]:
    module = get_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown notice_id: {notice_id!r}")

    template = module.get_whatsapp_template()
    records = get_broadcast_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    results = []
    sent_count = 0

    for rec in records:
        if limit is not None and sent_count >= limit:
            break

        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])

        if not test_number and is_notice_already_sent(db_path, rec["client_id"], notice_id, "whatsapp"):
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_duplicate", "to": to_phone,
            }
        elif template is None:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_no_template", "to": to_phone,
            }
        else:
            template_name, template_lang = template
            payload = module.build_whatsapp_payload(rec, to_phone, template_name, template_lang)
            if dry_run:
                result = {
                    "client_id": rec["client_id"], "name": rec["name"],
                    "action": "dry_run", "to": to_phone, "payload": payload,
                }
            else:
                try:
                    ok, info = send_fn(payload, token, phone_number_id)
                    if pace_seconds:
                        time.sleep(pace_seconds)
                    if ok:
                        sent_count += 1
                        if not test_number:
                            record_notice_sent(
                                db_path, rec["client_id"], notice_id, "whatsapp",
                                info.get("message_id"), datetime.now().isoformat(),
                            )
                        result = {
                            "client_id": rec["client_id"], "name": rec["name"], "action": "sent",
                            "to": to_phone, "message_id": info.get("message_id"),
                        }
                    else:
                        result = {
                            "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                            "to": to_phone, "error": info.get("error"),
                        }
                except Exception as exc:
                    if pace_seconds:
                        time.sleep(pace_seconds)
                    result = {
                        "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                        "to": to_phone, "error": str(exc),
                    }

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    return results


def send_adhoc_whatsapp_notice(
    db_path, notice_id: str, token: str, phone_number_id: str,
    dry_run: bool = False, test_number: str | None = None, send_fn=send_message,
    on_progress=None, limit: int | None = None,
) -> list[dict]:
    """Sends a fully static (no personalization) WhatsApp template to every
    phone number imported for this notice_id via adhoc_recipients. Unlike
    send_notice_whatsapp, there's no roster client behind these numbers --
    just a bare phone number, no name/company to build a payload around --
    so this doesn't call get_broadcast_clients or module.build_whatsapp_payload(rec, ...)
    the way the roster-based sender does.

    limit caps real sends per call (the WhatsApp Business Account's actual
    messaging-tier limit) -- once hit, remaining recipients are left
    completely untouched (not attempted), same convention as
    send_notice_email's limit."""
    module = get_adhoc_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown adhoc notice_id: {notice_id!r}")

    template = module.get_whatsapp_template()
    phone_numbers = get_adhoc_recipients(db_path, notice_id)
    results = []
    sent_count = 0

    for phone in phone_numbers:
        if limit is not None and sent_count >= limit:
            break

        to_phone = normalize_phone(test_number) if test_number else phone

        if not test_number and is_notice_already_sent(db_path, phone, notice_id, "whatsapp"):
            result = {"phone": phone, "action": "skipped_duplicate", "to": to_phone}
        elif template is None:
            result = {"phone": phone, "action": "skipped_no_template", "to": to_phone}
        else:
            template_name, template_lang = template
            payload = module.build_whatsapp_payload(to_phone, template_name, template_lang)
            if dry_run:
                result = {"phone": phone, "action": "dry_run", "to": to_phone, "payload": payload}
            else:
                try:
                    ok, info = send_fn(payload, token, phone_number_id)
                    if ok:
                        sent_count += 1
                        if not test_number:
                            record_notice_sent(
                                db_path, phone, notice_id, "whatsapp",
                                info.get("message_id"), datetime.now().isoformat(),
                            )
                        result = {
                            "phone": phone, "action": "sent",
                            "to": to_phone, "message_id": info.get("message_id"),
                        }
                    else:
                        result = {
                            "phone": phone, "action": "failed",
                            "to": to_phone, "error": info.get("error"),
                        }
                except Exception as exc:
                    result = {"phone": phone, "action": "failed", "to": to_phone, "error": str(exc)}

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(phone_numbers))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    return results


def send_notice_email(
    db_path, notice_id: str, brevo_api_key: str, email_sender: str, org_name: str,
    dry_run: bool = False, test_email: str | None = None, send_fn=post_email_via_brevo,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """limit caps how many actual sends (action == "sent") this call makes --
    e.g. Brevo's real daily quota. Once hit, remaining eligible records are
    left untouched (not attempted, not marked sent), so a later call
    naturally picks them up via the same permanent notice_sent_log dedup
    that already skips today's sent ones.

    This cap matters more here than it might look: Brevo's send API
    returns a normal 200/201 with a real message_id even when the account
    is over quota -- there's no synchronous rejection to detect, so
    without this limit the only way to find out a send didn't really
    happen is checking Brevo's own event log after the fact."""
    module = get_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown notice_id: {notice_id!r}")

    records = get_broadcast_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    results = []
    sent_count = 0

    for rec in records:
        if limit is not None and sent_count >= limit:
            break

        to_email = test_email or rec.get("email")

        if not to_email or "@" not in str(to_email):
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_no_email", "to": None,
            }
        elif not test_email and is_notice_already_sent(db_path, rec["client_id"], notice_id, "email"):
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_duplicate", "to": to_email,
            }
        elif dry_run:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "dry_run", "to": to_email,
            }
        else:
            logo_exists = LOGO_PATH.exists()
            logo_src = f"cid:{LOGO_CID}" if logo_exists else ""
            html = module.build_email_html(rec, org_name, logo_src=logo_src)
            payload = {
                "sender": {"name": org_name, "email": email_sender},
                "to": [{"email": to_email, "name": rec["name"]}],
                "subject": module.EMAIL_SUBJECT,
                "htmlContent": html,
            }
            if logo_exists:
                logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
                payload["attachment"] = [{"name": LOGO_CID, "content": logo_b64}]
            try:
                ok, info = send_fn(payload, brevo_api_key)
                if ok:
                    # Counts against the quota limit even for a test send --
                    # it still consumes one real Brevo API call either way.
                    sent_count += 1
                    if not test_email:
                        record_notice_sent(
                            db_path, rec["client_id"], notice_id, "email",
                            info.get("message_id"), datetime.now().isoformat(),
                        )
                    result = {
                        "client_id": rec["client_id"], "name": rec["name"], "action": "sent",
                        "to": to_email, "message_id": info.get("message_id"),
                    }
                else:
                    result = {
                        "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                        "to": to_email, "error": info.get("error"),
                    }
            except Exception as exc:
                result = {
                    "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                    "to": to_email, "error": str(exc),
                }

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    return results
