"""Send orchestration for one-time broadcast notices (see notices.py for
the content registry). Mirrors whatsapp_renewal_alerts.run()/
email_alerts.run_email_alerts()'s shape, but targets get_broadcast_clients()
(every matching client regardless of alert status, not just ALERT_STATUSES)
and dedups against notice_sent_log (permanent, not per-day) instead of
sent_log/email_sent_log."""
import base64
from datetime import datetime

from db import get_broadcast_clients, is_notice_already_sent, record_notice_sent
from email_alerts import post_email_via_brevo, LOGO_PATH, LOGO_CID
from notices import get_notice_module
from whatsapp_renewal_alerts import normalize_phone, send_message


def send_notice_whatsapp(
    db_path, notice_id: str, token: str, phone_number_id: str,
    dry_run: bool = False, test_number: str | None = None, send_fn=send_message,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
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

    for rec in records:
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
                    if ok:
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


def send_notice_email(
    db_path, notice_id: str, brevo_api_key: str, email_sender: str, org_name: str,
    dry_run: bool = False, test_email: str | None = None, send_fn=post_email_via_brevo,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
) -> list[dict]:
    module = get_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown notice_id: {notice_id!r}")

    records = get_broadcast_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    results = []

    for rec in records:
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
