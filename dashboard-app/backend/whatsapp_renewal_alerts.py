"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252, which crashes on emoji output

API_VERSION = "v23.0"


def normalize_phone(raw: str | int) -> str:
    return re.sub(r"\D", "", str(raw))


def format_expiry(value) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(str(value).strip(), fmt)
                break
            except ValueError:
                continue
        if dt is None:
            raise ValueError(f"Unrecognized date format: {value!r}")
    return dt.strftime("%d %B %Y")


def dedup_key(client_id: str, status: str, date_str: str) -> str:
    return f"{client_id}|{status}|{date_str}"


from db import (  # noqa: E402
    DEFAULT_DB_PATH, read_clients, find_client_by_id, load_sent_log, save_sent_log,
    RECORD_FIELDS, get_eligible_clients,
)

ALERT_STATUSES = {"CRITICAL", "URGENT", "DUE SOON", "EXPIRED"}


def filter_alertable(records: list[dict]) -> list[dict]:
    return [r for r in records if r["status"] in ALERT_STATUSES]


def build_payload(record: dict, to_phone: str, template_name: str, template_lang: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": record["name"]},
                        {"type": "text", "text": record["company"]},
                        {"type": "text", "text": record["cert_id"]},
                        {"type": "text", "text": record["cert_name"]},
                        {"type": "text", "text": format_expiry(record["expiry_date"])},
                    ],
                },
            ],
        },
    }


def send_message(payload: dict, token: str, phone_number_id: str, timeout: int = 10):
    url = f"https://graph.facebook.com/{API_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        return False, {"error": str(exc)}

    if response.status_code == 200:
        try:
            data = response.json()
            return True, {"message_id": data["messages"][0]["id"]}
        except (ValueError, KeyError, IndexError):
            return False, {"error": "Invalid response structure from API"}

    try:
        error_message = response.json()["error"]["message"]
    except (ValueError, KeyError):
        error_message = response.text
    return False, {"error": error_message}


def send_one_alert(
    record: dict,
    sent_log: dict,
    today: str,
    token: str,
    phone_number_id: str,
    template_name: str,
    template_lang: str,
    to_phone_override: str | None = None,
    send_fn=send_message,
) -> dict:
    """Send (or skip if already sent today) one alert-eligible client's WhatsApp
    renewal message. Mutates sent_log in place on a successful send. Returns a
    result dict with action one of 'sent' / 'skipped_duplicate' / 'failed'."""
    key = dedup_key(record["client_id"], record["status"], today)
    to_phone = (
        normalize_phone(to_phone_override) if to_phone_override
        else normalize_phone(record["phone"])
    )

    if key in sent_log:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "skipped_duplicate",
            "to": to_phone,
        }

    try:
        payload = build_payload(record, to_phone, template_name, template_lang)
        ok, info = send_fn(payload, token, phone_number_id)
        if ok:
            sent_log[key] = {
                "sent_at": datetime.now().isoformat(),
                "message_id": info.get("message_id"),
                "phone": to_phone,
            }
            return {
                "client_id": record["client_id"], "name": record["name"],
                "status": record["status"], "action": "sent",
                "to": to_phone, "message_id": info.get("message_id"),
            }
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_phone, "error": info.get("error"),
        }
    except Exception as exc:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_phone, "error": str(exc),
        }


def run(
    db_path,
    token: str,
    phone_number_id: str,
    template_name: str,
    template_lang: str,
    dry_run: bool = False,
    test_number: str | None = None,
    today: str | None = None,
    send_fn=send_message,
    on_progress=None,
    status: str | None = None,
    cert_type: str | None = None,
    expiry_before: str | None = None,
    search: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before, search=search,
    )
    sent_log = load_sent_log(db_path)
    persist_log = not dry_run and not test_number
    log_dirty = False
    results = []

    for rec in records:
        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])
        key = dedup_key(rec["client_id"], rec["status"], today)

        if key in sent_log:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "skipped_duplicate",
                "to": to_phone,
            }
        elif dry_run:
            payload = build_payload(rec, to_phone, template_name, template_lang)
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "dry_run",
                "to": to_phone, "payload": payload,
            }
        else:
            result = send_one_alert(
                rec, sent_log, today, token, phone_number_id,
                template_name, template_lang,
                to_phone_override=test_number, send_fn=send_fn,
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
        save_sent_log(db_path, sent_log)

    return results


SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_TEXT_LOG_PATH = REPO_ROOT / "logs" / "whatsapp_automation.log"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send WhatsApp renewal alerts via Meta Cloud API.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without calling the API.")
    parser.add_argument("--test-number", default=None, help="Redirect all sends to this number instead of real client numbers.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to clients.db")
    return parser


def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)


def format_result_line(result: dict) -> str:
    icons = {"sent": "✅ SENT", "skipped_duplicate": "⏭ SKIP",
              "failed": "❌ FAIL", "dry_run": "🧪 DRY-RUN"}
    label = icons[result["action"]]
    line = f"{label} | {result['client_id']} {result['name']} | {result['status']}"
    if result["action"] == "failed":
        line += f" | {result['error']}"
    if result["action"] == "sent":
        line += f" | msg_id={result['message_id']}"
    if result["action"] == "dry_run":
        params = result["payload"]["template"]["components"][0]["parameters"]
        body_text = " | ".join(p["text"] for p in params)
        line += f" | to={result['to']} | body=[{body_text}]"
    return line


def append_text_log(path, lines: list[str]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        timestamp = datetime.now().isoformat(timespec="seconds")
        for line in lines:
            f.write(f"[{timestamp}] {line}\n")


def main(argv=None) -> int:
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args(argv)

    token = os.environ.get("WHATSAPP_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    if not args.dry_run and (not token or not phone_number_id):
        print("❌ WHATSAPP_TOKEN and PHONE_NUMBER_ID must be set in .env (not required for --dry-run).")
        return 1

    template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")

    results = run(
        db_path=args.db,
        token=token,
        phone_number_id=phone_number_id,
        template_name=template_name,
        template_lang=template_lang,
        dry_run=args.dry_run,
        test_number=args.test_number,
    )

    lines = [format_result_line(r) for r in results]
    for line in lines:
        print(line)
    if lines and not args.dry_run:
        append_text_log(DEFAULT_TEXT_LOG_PATH, lines)

    sent = sum(1 for r in results if r["action"] == "sent")
    skipped = sum(1 for r in results if r["action"] == "skipped_duplicate")
    failed = sum(1 for r in results if r["action"] == "failed")
    dry = sum(1 for r in results if r["action"] == "dry_run")
    print(f"\nSummary: {sent} sent, {skipped} skipped (duplicate), {failed} failed, {dry} dry-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
