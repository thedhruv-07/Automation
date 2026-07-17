"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252, which crashes on emoji output


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
