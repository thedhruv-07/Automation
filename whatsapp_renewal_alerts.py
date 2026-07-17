"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
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


def load_sent_log(path) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_sent_log(path, log: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


ALERT_STATUSES = {"CRITICAL", "URGENT", "DUE SOON"}

RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]


def read_clients(xlsx_path) -> list[dict]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    next(rows)  # skip header row
    records = []
    for row in rows:
        if row[0] is None:
            continue
        records.append(dict(zip(RECORD_FIELDS, row)))
    return records


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
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": record["cert_id"]}],
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


def run(
    excel_path,
    log_path,
    token: str,
    phone_number_id: str,
    template_name: str,
    template_lang: str,
    dry_run: bool = False,
    test_number: str | None = None,
    today: str | None = None,
    send_fn=send_message,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = filter_alertable(read_clients(excel_path))
    sent_log = load_sent_log(log_path)
    persist_log = not dry_run and not test_number
    log_dirty = False
    results = []

    for rec in records:
        key = dedup_key(rec["client_id"], rec["status"], today)
        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])

        if key in sent_log:
            results.append({
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "skipped_duplicate",
                "to": to_phone,
            })
            continue

        try:
            payload = build_payload(rec, to_phone, template_name, template_lang)

            if dry_run:
                results.append({
                    "client_id": rec["client_id"], "name": rec["name"],
                    "status": rec["status"], "action": "dry_run",
                    "to": to_phone, "payload": payload,
                })
                continue

            ok, info = send_fn(payload, token, phone_number_id)
            if ok:
                results.append({
                    "client_id": rec["client_id"], "name": rec["name"],
                    "status": rec["status"], "action": "sent",
                    "to": to_phone, "message_id": info.get("message_id"),
                })
                if persist_log:
                    sent_log[key] = {
                        "sent_at": datetime.now().isoformat(),
                        "message_id": info.get("message_id"),
                        "phone": to_phone,
                    }
                    log_dirty = True
            else:
                results.append({
                    "client_id": rec["client_id"], "name": rec["name"],
                    "status": rec["status"], "action": "failed",
                    "to": to_phone, "error": info.get("error"),
                })
        except Exception as exc:
            results.append({
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "failed",
                "to": to_phone, "error": str(exc),
            })

    if persist_log and log_dirty:
        save_sent_log(log_path, sent_log)

    return results


SCRIPT_DIR = Path(__file__).parent
DEFAULT_EXCEL_PATH = SCRIPT_DIR / "clients_certifications.xlsx"
DEFAULT_LOG_PATH = SCRIPT_DIR / "sent_log.json"
DEFAULT_TEXT_LOG_PATH = SCRIPT_DIR / "whatsapp_automation.log"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send WhatsApp renewal alerts via Meta Cloud API.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without calling the API.")
    parser.add_argument("--test-number", default=None, help="Redirect all sends to this number instead of real client numbers.")
    parser.add_argument("--excel", default=str(DEFAULT_EXCEL_PATH), help="Path to clients_certifications.xlsx")
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
    return line


def append_text_log(path, lines: list[str]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        timestamp = datetime.now().isoformat(timespec="seconds")
        for line in lines:
            f.write(f"[{timestamp}] {line}\n")


def main(argv=None) -> int:
    load_dotenv(SCRIPT_DIR / ".env")
    args = parse_args(argv)

    token = os.environ.get("WHATSAPP_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    if not args.dry_run and (not token or not phone_number_id):
        print("❌ WHATSAPP_TOKEN and PHONE_NUMBER_ID must be set in .env (not required for --dry-run).")
        return 1

    template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en_US")

    results = run(
        excel_path=args.excel,
        log_path=DEFAULT_LOG_PATH,
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
    if lines:
        append_text_log(DEFAULT_TEXT_LOG_PATH, lines)

    sent = sum(1 for r in results if r["action"] == "sent")
    skipped = sum(1 for r in results if r["action"] == "skipped_duplicate")
    failed = sum(1 for r in results if r["action"] == "failed")
    dry = sum(1 for r in results if r["action"] == "dry_run")
    print(f"\nSummary: {sent} sent, {skipped} skipped (duplicate), {failed} failed, {dry} dry-run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
