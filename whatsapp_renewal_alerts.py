"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import requests

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
        data = response.json()
        return True, {"message_id": data["messages"][0]["id"]}

    try:
        error_message = response.json()["error"]["message"]
    except (ValueError, KeyError):
        error_message = response.text
    return False, {"error": error_message}
