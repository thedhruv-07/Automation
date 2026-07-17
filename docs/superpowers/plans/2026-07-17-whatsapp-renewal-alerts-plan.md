# WhatsApp Renewal Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `whatsapp_renewal_alerts.py`, a script that sends WhatsApp Cloud API template messages to clients whose Status is CRITICAL, URGENT, or DUE SOON, with dry-run, test-number redirection, and per-day duplicate prevention.

**Architecture:** Pure functions (phone normalization, date formatting, dedup key, payload building, log I/O) are unit-tested in isolation. A single `run()` function orchestrates them with an injectable `send_fn` so the full send/dedup/test-number logic is testable without hitting the network. `main()` is a thin CLI wrapper around `run()`.

**Tech Stack:** Python 3.14, `openpyxl` (xlsx reading), `requests` (HTTP), `python-dotenv` (env vars), `pytest` + `unittest.mock` (testing).

Spec: `docs/superpowers/specs/2026-07-17-whatsapp-renewal-alerts-design.md`

---

## File Structure

```
cert_automation_scripts/
  whatsapp_renewal_alerts.py        (new — main script)
  test_whatsapp_renewal_alerts.py   (new — pytest suite)
  requirements.txt                  (new)
  .env.example                      (new, committed)
  .env                              (new, gitignored — real secrets)
  .gitignore                        (new)
  run_whatsapp_alerts.ps1           (new — Task Scheduler wrapper)
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `cert_automation_scripts/requirements.txt`
- Create: `cert_automation_scripts/.env.example`
- Create: `cert_automation_scripts/.gitignore`

- [ ] **Step 1: Create `requirements.txt`**

```
openpyxl>=3.1.5
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Create `.env.example`**

```
WHATSAPP_TOKEN=your_permanent_system_user_token_here
PHONE_NUMBER_ID=2128020858096338
WHATSAPP_TEMPLATE_NAME=cert_renewal_alert
WHATSAPP_TEMPLATE_LANG=en_US
```

- [ ] **Step 3: Create `.gitignore`**

```
.env
sent_log.json
whatsapp_automation.log
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: all four packages install without error.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example .gitignore
git commit -m "Add project scaffolding for WhatsApp renewal alerts script"
```

---

### Task 2: Phone number normalization

**Files:**
- Create: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Create: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# test_whatsapp_renewal_alerts.py
from whatsapp_renewal_alerts import normalize_phone


def test_normalize_phone_strips_plus_sign():
    assert normalize_phone("+919876543210") == "919876543210"


def test_normalize_phone_handles_bare_digits():
    assert normalize_phone("919876543210") == "919876543210"


def test_normalize_phone_handles_int_input():
    assert normalize_phone(919876543210) == "919876543210"


def test_normalize_phone_strips_spaces_and_hyphens():
    assert normalize_phone("+91 98765-43210") == "919876543210"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL (or collection error) — `whatsapp_renewal_alerts` module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
# whatsapp_renewal_alerts.py
"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")


def normalize_phone(raw) -> str:
    return re.sub(r"\D", "", str(raw))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add phone number normalization"
```

---

### Task 3: Expiry date formatting

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
from datetime import datetime
from whatsapp_renewal_alerts import format_expiry


def test_format_expiry_from_ddmmyyyy_string():
    assert format_expiry("24-07-2026") == "24 July 2026"


def test_format_expiry_from_datetime_object():
    assert format_expiry(datetime(2026, 7, 24)) == "24 July 2026"


def test_format_expiry_raises_on_unparseable_value():
    import pytest as pytest_mod
    with pytest_mod.raises(ValueError):
        format_expiry("not-a-date")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `format_expiry` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py (near the top, with other imports)
from datetime import datetime

# add function
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (7 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add expiry date formatting"
```

---

### Task 4: Dedup key and sent-log persistence

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
from whatsapp_renewal_alerts import dedup_key, load_sent_log, save_sent_log


def test_dedup_key_format():
    assert dedup_key("CLT001", "CRITICAL", "2026-07-17") == "CLT001|CRITICAL|2026-07-17"


def test_load_sent_log_missing_file_returns_empty_dict(tmp_path):
    assert load_sent_log(tmp_path / "missing.json") == {}


def test_save_and_load_sent_log_round_trip(tmp_path):
    path = tmp_path / "sent_log.json"
    save_sent_log(path, {"CLT001|CRITICAL|2026-07-17": {"message_id": "wamid.ABC"}})
    result = load_sent_log(path)
    assert result == {"CLT001|CRITICAL|2026-07-17": {"message_id": "wamid.ABC"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `dedup_key`, `load_sent_log`, `save_sent_log` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py (with other imports)
import json
from pathlib import Path

# add functions
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (10 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add dedup key and sent-log persistence"
```

---

### Task 5: Reading and filtering clients from the xlsx

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
import openpyxl
from whatsapp_renewal_alerts import read_clients, filter_alertable

HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date",
    "Expiry Date", "Renewal Link", "Status",
]


def _write_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_read_clients_and_filter_alertable(tmp_path):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
        ["CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919898765432",
         "GMP", "GMP-1", "01-01-2025", "10-09-2026",
         "https://x/renew?id=GMP-1", "DUE SOON"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026",
         "https://x/renew?id=ISO27-1", "ACTIVE"],
        ["CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "919654321098",
         "HACCP", "HACCP-1", "01-01-2025", "12-07-2026",
         "https://x/renew?id=HACCP-1", "EXPIRED"],
    ])

    records = read_clients(xlsx_path)
    assert len(records) == 5
    assert records[0]["client_id"] == "CLT001"
    assert records[0]["cert_id"] == "ISO-1"
    assert records[0]["status"] == "CRITICAL"

    alertable = filter_alertable(records)
    assert [r["client_id"] for r in alertable] == ["CLT001", "CLT002", "CLT003"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `read_clients`, `filter_alertable` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py (with other imports)
import openpyxl

# add constant near top of file
ALERT_STATUSES = {"CRITICAL", "URGENT", "DUE SOON"}

RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]

# add functions
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (11 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add xlsx reading and status filtering"
```

---

### Task 6: Template payload builder

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
from whatsapp_renewal_alerts import build_payload


def test_build_payload_structure_and_placeholder_order():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp India Pvt Ltd",
        "cert_name": "ISO 9001:2015 Quality Management", "cert_id": "ISO-2021-4521",
        "expiry_date": "24-07-2026", "status": "CRITICAL",
    }

    payload = build_payload(record, "919876543210", "cert_renewal_alert", "en_US")

    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "919876543210"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "cert_renewal_alert"
    assert payload["template"]["language"] == {"code": "en_US"}

    body_params = payload["template"]["components"][0]["parameters"]
    assert body_params[0] == {"type": "text", "text": "Rahul Sharma"}
    assert body_params[1] == {"type": "text", "text": "TechCorp India Pvt Ltd"}
    assert body_params[2] == {"type": "text", "text": "ISO-2021-4521"}
    assert body_params[3] == {"type": "text", "text": "ISO 9001:2015 Quality Management"}
    assert body_params[4] == {"type": "text", "text": "24 July 2026"}

    button = payload["template"]["components"][1]
    assert button["type"] == "button"
    assert button["sub_type"] == "url"
    assert button["parameters"] == [{"type": "text", "text": "ISO-2021-4521"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `build_payload` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add WhatsApp template payload builder"
```

---

### Task 7: Send function (mocked HTTP)

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
from unittest.mock import patch, Mock
import requests
from whatsapp_renewal_alerts import send_message


def test_send_message_success():
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"messages": [{"id": "wamid.ABC"}]}
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response) as mock_post:
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is True
    assert info == {"message_id": "wamid.ABC"}
    mock_post.assert_called_once()
    called_url = mock_post.call_args.args[0]
    assert called_url == "https://graph.facebook.com/v23.0/pid123/messages"


def test_send_message_api_error():
    mock_response = Mock(status_code=400)
    mock_response.json.return_value = {"error": {"message": "Invalid parameter"}}
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is False
    assert info == {"error": "Invalid parameter"}


def test_send_message_network_error():
    with patch("whatsapp_renewal_alerts.requests.post", side_effect=requests.exceptions.ConnectionError("boom")):
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is False
    assert "boom" in info["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `send_message` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py (with other imports)
import requests

# add constant near top of file
API_VERSION = "v23.0"

# add function
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (15 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add Cloud API send function with mocked tests"
```

---

### Task 8: Core orchestration — `run()` with dedup and test-number logic

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing tests**

```python
# add to test_whatsapp_renewal_alerts.py
from whatsapp_renewal_alerts import run

ONE_CRITICAL_ROW = [
    ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
     "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026",
     "https://x/renew?id=ISO-1", "CRITICAL"],
]


def test_run_dry_run_makes_no_calls_and_no_log_writes(tmp_path):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, ONE_CRITICAL_ROW)
    log_path = tmp_path / "sent_log.json"
    send_fn = Mock()

    results = run(
        excel_path=xlsx_path, log_path=log_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )

    assert len(results) == 1
    assert results[0]["action"] == "dry_run"
    send_fn.assert_not_called()
    assert not log_path.exists()


def test_run_live_sends_and_dedups_on_second_call(tmp_path):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, ONE_CRITICAL_ROW)
    log_path = tmp_path / "sent_log.json"
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    first = run(excel_path=xlsx_path, log_path=log_path, token="tok", phone_number_id="pid",
                template_name="cert_renewal_alert", template_lang="en_US",
                today="2026-07-17", send_fn=send_fn)
    assert first[0]["action"] == "sent"
    assert send_fn.call_count == 1
    assert log_path.exists()

    second = run(excel_path=xlsx_path, log_path=log_path, token="tok", phone_number_id="pid",
                 template_name="cert_renewal_alert", template_lang="en_US",
                 today="2026-07-17", send_fn=send_fn)
    assert second[0]["action"] == "skipped_duplicate"
    assert send_fn.call_count == 1


def test_run_test_number_overrides_phone_and_skips_log_write(tmp_path):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, ONE_CRITICAL_ROW)
    log_path = tmp_path / "sent_log.json"
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(excel_path=xlsx_path, log_path=log_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  test_number="+919999999999", today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    assert not log_path.exists()


def test_run_failed_send_does_not_write_log(tmp_path):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, ONE_CRITICAL_ROW)
    log_path = tmp_path / "sent_log.json"
    send_fn = Mock(return_value=(False, {"error": "Invalid parameter"}))

    results = run(excel_path=xlsx_path, log_path=log_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "failed"
    assert results[0]["error"] == "Invalid parameter"
    assert not log_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `run` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py (with other imports)
from datetime import datetime

# add function
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
    results = []

    for rec in records:
        key = dedup_key(rec["client_id"], rec["status"], today)

        if key in sent_log:
            results.append({
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "skipped_duplicate",
            })
            continue

        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])
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
        else:
            results.append({
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "failed",
                "to": to_phone, "error": info.get("error"),
            })

    if persist_log:
        save_sent_log(log_path, sent_log)

    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (19 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add run() orchestration with dedup and test-number logic"
```

---

### Task 9: CLI argument parsing

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
from whatsapp_renewal_alerts import parse_args, DEFAULT_EXCEL_PATH


def test_parse_args_defaults():
    args = parse_args([])
    assert args.dry_run is False
    assert args.test_number is None
    assert args.excel == str(DEFAULT_EXCEL_PATH)


def test_parse_args_dry_run_and_test_number():
    args = parse_args(["--dry-run", "--test-number", "919999999999"])
    assert args.dry_run is True
    assert args.test_number == "919999999999"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `parse_args`, `DEFAULT_EXCEL_PATH` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py (with other imports)
import argparse
from pathlib import Path

# add constants near top of file
SCRIPT_DIR = Path(__file__).parent
DEFAULT_EXCEL_PATH = SCRIPT_DIR / "clients_certifications.xlsx"
DEFAULT_LOG_PATH = SCRIPT_DIR / "sent_log.json"
DEFAULT_TEXT_LOG_PATH = SCRIPT_DIR / "whatsapp_automation.log"

# add functions
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send WhatsApp renewal alerts via Meta Cloud API.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without calling the API.")
    parser.add_argument("--test-number", default=None, help="Redirect all sends to this number instead of real client numbers.")
    parser.add_argument("--excel", default=str(DEFAULT_EXCEL_PATH), help="Path to clients_certifications.xlsx")
    return parser


def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (21 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add CLI argument parsing"
```

---

### Task 10: Result formatting and text log

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# add to test_whatsapp_renewal_alerts.py
from whatsapp_renewal_alerts import format_result_line, append_text_log


def test_format_result_line_sent():
    result = {"action": "sent", "client_id": "CLT001", "name": "Rahul Sharma",
              "status": "CRITICAL", "message_id": "wamid.ABC"}
    assert format_result_line(result) == "✅ SENT | CLT001 Rahul Sharma | CRITICAL | msg_id=wamid.ABC"


def test_format_result_line_failed():
    result = {"action": "failed", "client_id": "CLT001", "name": "Rahul Sharma",
              "status": "CRITICAL", "error": "Invalid parameter"}
    assert format_result_line(result) == "❌ FAIL | CLT001 Rahul Sharma | CRITICAL | Invalid parameter"


def test_format_result_line_skipped():
    result = {"action": "skipped_duplicate", "client_id": "CLT001",
              "name": "Rahul Sharma", "status": "CRITICAL"}
    assert format_result_line(result) == "⏭ SKIP | CLT001 Rahul Sharma | CRITICAL"


def test_append_text_log_writes_lines(tmp_path):
    log_path = tmp_path / "log.txt"
    append_text_log(log_path, ["✅ SENT | CLT001 Rahul Sharma | CRITICAL | msg_id=wamid.ABC"])
    content = log_path.read_text(encoding="utf-8")
    assert "✅ SENT | CLT001 Rahul Sharma | CRITICAL | msg_id=wamid.ABC" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: FAIL — `format_result_line`, `append_text_log` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
# add to whatsapp_renewal_alerts.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (25 tests total)

- [ ] **Step 5: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Add console/log result formatting"
```

---

### Task 11: Wire up `main()` and manual dry-run smoke test

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`

- [ ] **Step 1: Add `main()` and the `__main__` block**

```python
# add to whatsapp_renewal_alerts.py (with other imports)
import os
from dotenv import load_dotenv

# add function and entry point at the end of the file
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
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: PASS (25 tests total, unchanged — `main` has no dedicated unit test since it's a thin CLI wrapper; verified manually next)

- [ ] **Step 3: Manual dry-run smoke test against the real fixture data**

Run: `python whatsapp_renewal_alerts.py --dry-run`
Expected console output: exactly 5 lines with `🧪 DRY-RUN`, for clients CLT001 (CRITICAL), CLT002 (URGENT), CLT003 (DUE SOON), CLT007 (URGENT), CLT008 (DUE SOON) — matching the 8-row fixture from `create_dummy_data.py`. Confirm no `sent_log.json` is created and no crash occurs (Unicode-safe console output).

- [ ] **Step 4: Commit**

```bash
git add whatsapp_renewal_alerts.py
git commit -m "Wire up CLI entry point"
```

---

### Task 12: Task Scheduler wrapper

**Files:**
- Create: `cert_automation_scripts/run_whatsapp_alerts.ps1`

- [ ] **Step 1: Create the wrapper script**

```powershell
# run_whatsapp_alerts.ps1
Set-Location -Path $PSScriptRoot
& "C:\Python314\python.exe" "whatsapp_renewal_alerts.py" *>> "whatsapp_automation.log"
```

- [ ] **Step 2: Register the daily 9:30 AM IST task**

Run:
```powershell
schtasks /Create /SC DAILY /ST 09:30 /TN "AbsoluteVeritas_WhatsAppRenewalAlerts" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"C:\Users\dhruv\OneDrive\Desktop\files\cert_automation_scripts\run_whatsapp_alerts.ps1\"" /RL LIMITED
```
Expected: `SUCCESS: The scheduled task "AbsoluteVeritas_WhatsAppRenewalAlerts" has successfully been created.`

- [ ] **Step 3: Verify registration (read-only check, does not trigger a live send)**

Run: `schtasks /Query /TN "AbsoluteVeritas_WhatsAppRenewalAlerts" /V /FO LIST`
Expected: shows `Status: Ready`, `Start Time: 9:30:00`, `Schedule Type: Daily`.

- [ ] **Step 4: Commit**

```bash
git add run_whatsapp_alerts.ps1
git commit -m "Add Task Scheduler wrapper script"
```

---

### Task 13: Full regression run

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite one final time**

Run: `pytest test_whatsapp_renewal_alerts.py -v`
Expected: all 25 tests PASS.

- [ ] **Step 2: Confirm working tree is clean**

Run: `git status`
Expected: `nothing to commit, working tree clean`

---

## After This Plan

Real end-to-end testing (per the spec's testing plan) happens after this code is built, and after the `cert_renewal_alert` template is approved in Meta's dashboard:
1. `python whatsapp_renewal_alerts.py --dry-run`
2. `python whatsapp_renewal_alerts.py --test-number <your number>`
3. `python whatsapp_renewal_alerts.py` (live)

This is manual, guided testing with the user — not part of this automated plan.
