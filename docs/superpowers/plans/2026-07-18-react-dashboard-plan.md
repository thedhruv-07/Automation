# Professional React Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI backend + React frontend that displays the certification client list with a professional "Vibrant Gradient SaaS" design and lets the user send real WhatsApp renewal alerts per-client directly from the UI.

**Architecture:** `dashboard-app/backend/` (FastAPI, reusing functions from `whatsapp_renewal_alerts.py` directly — one small refactor extracts a shared `send_one_alert()` function) serves three JSON endpoints and, once built, the React app's static files. `dashboard-app/frontend/` (Vite + React + Tailwind CSS + Framer Motion) is a single-page app: stat cards, filter/search bar, sortable client table with per-row Send Alert buttons, a confirmation modal, and toast notifications.

**Tech Stack:** Python (FastAPI, pytest), React (Vite, Tailwind CSS, Framer Motion, Vitest + React Testing Library)

Spec: `docs/superpowers/specs/2026-07-18-react-dashboard-design.md`

---

## File Structure

```
cert_automation_scripts/
  whatsapp_renewal_alerts.py        (modified — extract send_one_alert())
  test_whatsapp_renewal_alerts.py   (modified — tests for send_one_alert())
  .gitignore                        (modified — ignore frontend build artifacts)
  dashboard-app/
    backend/
      requirements.txt               (new)
      main.py                        (new — FastAPI app, 3 endpoints + static serving)
      test_main.py                   (new — pytest + FastAPI TestClient)
    frontend/
      (Vite-scaffolded React project)
      src/
        main.jsx
        App.jsx
        App.test.jsx
        index.css
        api.js
        api.test.js
        sortUtils.js
        sortUtils.test.js
        setupTests.js
        components/
          StatCards.jsx
          StatCards.test.jsx
          FilterBar.jsx
          FilterBar.test.jsx
          ClientTable.jsx
          ClientTable.test.jsx
          SendConfirmModal.jsx
          SendConfirmModal.test.jsx
          Toast.jsx
          Toast.test.jsx
```

---

### Task 1: Extract `send_one_alert()` from `run()`

**Files:**
- Modify: `whatsapp_renewal_alerts.py`
- Modify: `test_whatsapp_renewal_alerts.py`

**Context:** `run()` currently has the "check dedup → build payload → send → update log" sequence inline inside its loop. This task pulls that into a standalone `send_one_alert()` function that both `run()` (CLI, loops over all eligible clients) and the future `POST /api/send/{client_id}` endpoint (handles one client) will call — so the send logic exists in exactly one place. `send_one_alert()` takes the already-loaded `sent_log` dict and mutates it in place on success (it does NOT do file I/O itself — callers control when to persist, exactly like `run()` already does today by writing the log once after its loop, not once per record).

- [ ] **Step 1: Write the failing tests**

Add to `test_whatsapp_renewal_alerts.py` (near the existing `send_message`/`run` tests):

```python
from whatsapp_renewal_alerts import send_one_alert


def test_send_one_alert_success_updates_log_in_place():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return True, {"message_id": "wamid.ABC"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        "cert_renewal_alert", "en", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "sent", "to": "919876543210", "message_id": "wamid.ABC",
    }
    assert "CLT001|CRITICAL|2026-07-18" in sent_log
    assert sent_log["CLT001|CRITICAL|2026-07-18"]["message_id"] == "wamid.ABC"


def test_send_one_alert_skips_when_already_in_log():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.OLD"}}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called when already sent")

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        "cert_renewal_alert", "en", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "skipped_duplicate", "to": "919876543210",
    }


def test_send_one_alert_uses_override_phone_and_reports_failure():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return False, {"error": "Invalid parameter"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        "cert_renewal_alert", "en", to_phone_override="919000000000",
        send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "failed", "to": "919000000000", "error": "Invalid parameter",
    }
    assert sent_log == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_whatsapp_renewal_alerts.py -k send_one_alert -v`
Expected: FAIL with `ImportError: cannot import name 'send_one_alert'`

- [ ] **Step 3: Implement `send_one_alert()`**

Add to `whatsapp_renewal_alerts.py`, directly above the existing `def run(`:

```python
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
```

- [ ] **Step 4: Run tests to verify the 3 new tests pass**

Run: `python -m pytest test_whatsapp_renewal_alerts.py -k send_one_alert -v`
Expected: 3 passed

- [ ] **Step 5: Refactor `run()` to call `send_one_alert()`**

Replace the body of `run()` in `whatsapp_renewal_alerts.py` with:

```python
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
        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])

        if dry_run:
            payload = build_payload(rec, to_phone, template_name, template_lang)
            results.append({
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "dry_run",
                "to": to_phone, "payload": payload,
            })
            continue

        result = send_one_alert(
            rec, sent_log, today, token, phone_number_id,
            template_name, template_lang,
            to_phone_override=test_number, send_fn=send_fn,
        )
        results.append(result)
        if result["action"] == "sent":
            log_dirty = True

    if persist_log and log_dirty:
        save_sent_log(log_path, sent_log)

    return results
```

This preserves every existing behavior exactly: dry-run still short-circuits before any send/dedup logic, `sent_log` is still loaded once and written at most once per call, and the log is still only written when something was actually sent (this exact "only write when dirty" guard was fixed once before — a regression here would silently reintroduce writing an empty/unchanged log file on every run).

- [ ] **Step 6: Run the full existing test suite**

Run: `python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: 35 passed (32 existing + 3 new)

- [ ] **Step 7: Verify `--dry-run` still works against the real fixture**

Run: `python whatsapp_renewal_alerts.py --dry-run`
Expected: same 5-client dry-run output as before (CLT001/002/003/007/008), unchanged.

- [ ] **Step 8: Commit**

```bash
git add whatsapp_renewal_alerts.py test_whatsapp_renewal_alerts.py
git commit -m "Extract send_one_alert() so CLI and future API share one send path"
```

---

### Task 2: FastAPI scaffold with `/api/health`

**Files:**
- Create: `dashboard-app/backend/requirements.txt`
- Create: `dashboard-app/backend/main.py`
- Create: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Create `dashboard-app/backend/requirements.txt`**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
httpx>=0.27.0
openpyxl>=3.1.5
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 2: Install dependencies**

Run: `python -m pip install -r dashboard-app/backend/requirements.txt`
Expected: installs successfully, no errors.

- [ ] **Step 3: Write the failing test**

Create `dashboard-app/backend/test_main.py`:

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 5: Create `dashboard-app/backend/main.py`**

```python
"""FastAPI backend for the Absolute Veritas React dashboard."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app = FastAPI(title="Absolute Veritas Renewal Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: 1 passed

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/requirements.txt dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "Scaffold FastAPI backend with a health check endpoint"
```

---

### Task 3: `GET /api/clients` endpoint

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/backend/test_main.py`:

```python
import json
import openpyxl
import main as main_module

HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]


def _write_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_get_clients_merges_alert_sent_today(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text(json.dumps({"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.ABC"}}))

    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    critical = next(r for r in data if r["client_id"] == "CLT001")
    assert critical["alert_sent_today"] is True

    active = next(r for r in data if r["client_id"] == "CLT004")
    assert active["alert_sent_today"] is None


def test_get_clients_alert_eligible_not_yet_sent(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")

    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["alert_sent_today"] is False
```

Note: this introduces a `_today_str()` helper in `main.py` (wrapping `datetime.now().strftime("%Y-%m-%d")`) purely so tests can monkeypatch "today" deterministically instead of depending on the real system clock.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: FAIL with `AttributeError: module 'main' has no attribute 'DEFAULT_EXCEL_PATH'` (or 404 for the route)

- [ ] **Step 3: Implement the endpoint**

Add to `dashboard-app/backend/main.py` (after the existing imports, before `app = FastAPI(...)`):

```python
from datetime import datetime  # noqa: E402

from whatsapp_renewal_alerts import (  # noqa: E402
    read_clients, ALERT_STATUSES, dedup_key, load_sent_log,
    DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH,
)


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
```

Add the endpoint at the end of `main.py`:

```python
@app.get("/api/clients")
def get_clients():
    today = _today_str()
    records = read_clients(DEFAULT_EXCEL_PATH)
    sent_log = load_sent_log(DEFAULT_LOG_PATH)
    result = []
    for rec in records:
        if rec["status"] in ALERT_STATUSES:
            key = dedup_key(rec["client_id"], rec["status"], today)
            alert_sent_today = key in sent_log
        else:
            alert_sent_today = None
        result.append({**rec, "alert_sent_today": alert_sent_today})
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "Add GET /api/clients endpoint with alert-sent-today overlay"
```

---

### Task 4: `POST /api/send/{client_id}` endpoint

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/backend/test_main.py`:

```python
from unittest.mock import patch


def _setup_one_client(tmp_path, monkeypatch, status="CRITICAL"):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en")
    monkeypatch.delenv("DASHBOARD_TEST_NUMBER", raising=False)
    return log_path


def test_send_alert_success(tmp_path, monkeypatch):
    log_path = _setup_one_client(tmp_path, monkeypatch)
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send/CLT001")
    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message_id": "wamid.ABC"}
    assert "CLT001|CRITICAL|2026-07-18" in json.loads(log_path.read_text())


def test_send_alert_unknown_client_returns_404(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch)
    response = client.post("/api/send/NOPE")
    assert response.status_code == 404


def test_send_alert_ineligible_status_returns_400(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch, status="ACTIVE")
    response = client.post("/api/send/CLT001")
    assert response.status_code == 400


def test_send_alert_duplicate_returns_409(tmp_path, monkeypatch):
    log_path = _setup_one_client(tmp_path, monkeypatch)
    log_path.write_text(json.dumps({"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.OLD"}}))
    response = client.post("/api/send/CLT001")
    assert response.status_code == 409


def test_send_alert_api_failure_returns_502(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch)
    mock_response = type("Resp", (), {
        "status_code": 400,
        "json": lambda self: {"error": {"message": "Invalid parameter"}},
        "text": "Invalid parameter",
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send/CLT001")
    assert response.status_code == 502
    assert "Invalid parameter" in response.json()["detail"]


def test_send_alert_uses_dashboard_test_number_override(tmp_path, monkeypatch):
    log_path = _setup_one_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DASHBOARD_TEST_NUMBER", "919000000000")
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.TEST"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response) as mock_post:
        response = client.post("/api/send/CLT001")
    assert response.status_code == 200
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["to"] == "919000000000"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k send_alert -v`
Expected: FAIL with 404 (route doesn't exist) for all of them

- [ ] **Step 3: Implement the endpoint**

Add to the imports section near the top of `main.py`:

```python
import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from whatsapp_renewal_alerts import (  # noqa: E402
    read_clients, ALERT_STATUSES, dedup_key, load_sent_log, save_sent_log,
    send_one_alert, DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH,
)

load_dotenv(REPO_ROOT / ".env")
```

(This replaces the earlier, narrower import of `read_clients, ALERT_STATUSES, dedup_key, load_sent_log, DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH` from Task 3 — the full set of names now needed is listed above.)

Add the endpoint at the end of `main.py`:

```python
@app.post("/api/send/{client_id}")
def send_alert(client_id: str):
    today = _today_str()
    records = read_clients(DEFAULT_EXCEL_PATH)
    record = next((r for r in records if r["client_id"] == client_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown client_id: {client_id}")
    if record["status"] not in ALERT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status {record['status']} is not alert-eligible",
        )

    sent_log = load_sent_log(DEFAULT_LOG_PATH)
    key = dedup_key(record["client_id"], record["status"], today)
    if key in sent_log:
        raise HTTPException(
            status_code=409,
            detail="Alert already sent today for this client/status",
        )

    token = os.environ["WHATSAPP_TOKEN"]
    phone_number_id = os.environ["PHONE_NUMBER_ID"]
    template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
    test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

    result = send_one_alert(
        record, sent_log, today, token, phone_number_id,
        template_name, template_lang, to_phone_override=test_number,
    )

    if result["action"] == "sent":
        save_sent_log(DEFAULT_LOG_PATH, sent_log)
        return {"status": "sent", "message_id": result["message_id"]}

    raise HTTPException(status_code=502, detail=result.get("error", "Unknown error"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: 9 passed (3 from Task 3 + 6 new)

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "Add POST /api/send/:client_id endpoint with dedup and test-number override"
```

---

### Task 5: Scaffold the Vite + React + Tailwind + Framer Motion + Vitest project

**Files:**
- Create: `dashboard-app/frontend/` (via `npm create vite`)
- Modify: `dashboard-app/frontend/vite.config.js`
- Modify: `dashboard-app/frontend/tailwind.config.js`
- Create: `dashboard-app/frontend/postcss.config.js`
- Modify: `dashboard-app/frontend/src/index.css`
- Create: `dashboard-app/frontend/src/setupTests.js`
- Modify: `dashboard-app/frontend/src/App.jsx`
- Create: `dashboard-app/frontend/src/App.test.jsx`
- Modify: `.gitignore`

- [ ] **Step 1: Scaffold the Vite React project**

Run (from `dashboard-app/`):
```bash
cd dashboard-app
npm create vite@latest frontend -- --template react
cd frontend
npm install
```
Expected: `frontend/` created with `package.json`, `src/App.jsx`, `src/main.jsx`, `vite.config.js`, etc.

- [ ] **Step 2: Install Tailwind, Framer Motion, and test tooling**

Run (from `dashboard-app/frontend/`):
```bash
npm install -D tailwindcss postcss autoprefixer vitest @testing-library/react @testing-library/jest-dom jsdom
npm install framer-motion
```

- [ ] **Step 3: Create `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

- [ ] **Step 4: Create `postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Replace `src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 6: Create `src/setupTests.js`**

```js
import "@testing-library/jest-dom";
```

- [ ] **Step 7: Update `vite.config.js` to add Vitest config**

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.js",
    globals: true,
  },
});
```

- [ ] **Step 8: Add a `test` script to `package.json`**

In the `"scripts"` section of `dashboard-app/frontend/package.json`, add:
```json
"test": "vitest run"
```

- [ ] **Step 9: Write a failing smoke test**

Create `src/App.test.jsx`:

```jsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App", () => {
  it("renders the Absolute Veritas heading", () => {
    render(<App />);
    expect(screen.getByText("Absolute Veritas")).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Run test to verify it fails**

Run: `npm test`
Expected: FAIL — the default Vite scaffold's `App.jsx` doesn't contain "Absolute Veritas"

- [ ] **Step 11: Replace `src/App.jsx` with a minimal placeholder**

```jsx
export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <h1 className="text-2xl font-extrabold bg-gradient-to-r from-sky-500 to-indigo-500 bg-clip-text text-transparent">
        Absolute Veritas
      </h1>
    </div>
  );
}
```

- [ ] **Step 12: Run test to verify it passes**

Run: `npm test`
Expected: 1 passed

- [ ] **Step 13: Verify the dev server boots**

Run: `npm run dev` (then stop it with Ctrl+C once you see the "Local: http://localhost:5173" message)
Expected: server starts with no errors, prints the local URL.

- [ ] **Step 14: Ignore build artifacts**

Add to `.gitignore` (repo root):
```
dashboard-app/frontend/node_modules/
dashboard-app/frontend/dist/
```

- [ ] **Step 15: Commit**

```bash
git add dashboard-app/frontend/tailwind.config.js dashboard-app/frontend/postcss.config.js \
        dashboard-app/frontend/src/index.css dashboard-app/frontend/src/setupTests.js \
        dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx \
        dashboard-app/frontend/vite.config.js dashboard-app/frontend/package.json \
        dashboard-app/frontend/package-lock.json .gitignore
git commit -m "Scaffold React frontend with Tailwind, Framer Motion, and Vitest"
```

---

### Task 6: `sortUtils.js` — shared date/sort logic

**Files:**
- Create: `dashboard-app/frontend/src/sortUtils.js`
- Create: `dashboard-app/frontend/src/sortUtils.test.js`

**Context:** This ports the numeric-aware sorting logic from the static `dashboard.html` (built and fixed earlier in this project) into a reusable module. The regression test below directly encodes the lesson from that earlier bug: sorting dates as raw strings puts `"in 10 days"`-style or `"13-01-2027"`-style values in the wrong order.

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/sortUtils.test.js`:

```js
import { describe, it, expect } from "vitest";
import { daysUntil, formatDaysLeft, sortClients } from "./sortUtils";

function futureDateStr(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}-${mm}-${d.getFullYear()}`;
}

describe("daysUntil", () => {
  it("computes positive day difference for future dates", () => {
    expect(daysUntil(futureDateStr(5))).toBe(5);
  });

  it("computes negative day difference for past dates", () => {
    expect(daysUntil(futureDateStr(-3))).toBe(-3);
  });
});

describe("formatDaysLeft", () => {
  it("returns 'today' for zero days", () => {
    expect(formatDaysLeft(futureDateStr(0))).toBe("today");
  });

  it("returns singular 'day' for exactly 1 day out", () => {
    expect(formatDaysLeft(futureDateStr(1))).toBe("in 1 day");
  });

  it("returns plural 'days' for multiple days out", () => {
    expect(formatDaysLeft(futureDateStr(6))).toBe("in 6 days");
  });

  it("returns 'ago' phrasing for past dates", () => {
    expect(formatDaysLeft(futureDateStr(-10))).toBe("10 days ago");
  });
});

describe("sortClients", () => {
  const clients = [
    { client_id: "A", name: "Charlie", expiry_date: "15-10-2026" },
    { client_id: "B", name: "Alice", expiry_date: "13-01-2027" },
    { client_id: "C", name: "Bob", expiry_date: "15-09-2026" },
  ];

  it("sorts expiry_date chronologically ascending, not lexicographically", () => {
    const sorted = sortClients(clients, "expiry_date", true);
    expect(sorted.map((c) => c.client_id)).toEqual(["C", "A", "B"]);
  });

  it("sorts expiry_date chronologically descending", () => {
    const sorted = sortClients(clients, "expiry_date", false);
    expect(sorted.map((c) => c.client_id)).toEqual(["B", "A", "C"]);
  });

  it("sorts by name ascending using localeCompare", () => {
    const sorted = sortClients(clients, "name", true);
    expect(sorted.map((c) => c.name)).toEqual(["Alice", "Bob", "Charlie"]);
  });

  it("returns original order unchanged when sortKey is null", () => {
    const sorted = sortClients(clients, null, true);
    expect(sorted.map((c) => c.client_id)).toEqual(["A", "B", "C"]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `sortUtils.js` doesn't exist

- [ ] **Step 3: Implement `sortUtils.js`**

Create `dashboard-app/frontend/src/sortUtils.js`:

```js
export function parseDate(str) {
  const [d, m, y] = String(str).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function daysUntil(expiryStr) {
  const expiry = parseDate(expiryStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  expiry.setHours(0, 0, 0, 0);
  return Math.round((expiry - today) / 86400000);
}

export function formatDaysLeft(expiryStr) {
  const diffDays = daysUntil(expiryStr);
  if (diffDays === 0) return "today";
  if (diffDays > 0) return `in ${diffDays} day${diffDays === 1 ? "" : "s"}`;
  return `${Math.abs(diffDays)} day${Math.abs(diffDays) === 1 ? "" : "s"} ago`;
}

export function sortClients(clients, sortKey, sortAsc) {
  if (!sortKey) return clients;
  const rows = clients.slice();
  rows.sort((a, b) => {
    if (sortKey === "days_left") {
      const av = daysUntil(a.expiry_date);
      const bv = daysUntil(b.expiry_date);
      return sortAsc ? av - bv : bv - av;
    }
    if (sortKey === "expiry_date") {
      const av = parseDate(a.expiry_date);
      const bv = parseDate(b.expiry_date);
      return sortAsc ? av - bv : bv - av;
    }
    const av = String(a[sortKey] ?? "");
    const bv = String(b[sortKey] ?? "");
    return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  return rows;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed (App.test.jsx + sortUtils.test.js)

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/sortUtils.js dashboard-app/frontend/src/sortUtils.test.js
git commit -m "Add sortUtils with numeric-aware date sorting"
```

---

### Task 7: `api.js` — backend fetch wrapper

**Files:**
- Create: `dashboard-app/frontend/src/api.js`
- Create: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/api.test.js`:

```js
import { describe, it, expect, vi, beforeEach } from "vitest";
import { getClients, sendAlert } from "./api";

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("getClients", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ client_id: "CLT001" }],
    });
    const clients = await getClients();
    expect(clients).toEqual([{ client_id: "CLT001" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/clients");
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getClients()).rejects.toThrow("Failed to load clients: 500");
  });
});

describe("sendAlert", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "sent", message_id: "wamid.ABC" }),
    });
    const result = await sendAlert("CLT001");
    expect(result).toEqual({ status: "sent", message_id: "wamid.ABC" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send/CLT001", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Alert already sent today for this client/status" }),
    });
    await expect(sendAlert("CLT001")).rejects.toThrow(
      "Alert already sent today for this client/status"
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `api.js` doesn't exist

- [ ] **Step 3: Implement `api.js`**

Create `dashboard-app/frontend/src/api.js`:

```js
export async function getClients() {
  const res = await fetch("/api/clients");
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
  return res.json();
}

export async function sendAlert(clientId) {
  const res = await fetch(`/api/send/${clientId}`, { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Send failed: ${res.status}`);
  }
  return data;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "Add api.js fetch wrapper for the backend"
```

---

### Task 8: `StatCards` component

**Files:**
- Create: `dashboard-app/frontend/src/components/StatCards.jsx`
- Create: `dashboard-app/frontend/src/components/StatCards.test.jsx`

- [ ] **Step 1: Write the failing test**

Create `dashboard-app/frontend/src/components/StatCards.test.jsx`:

```jsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatCards from "./StatCards";

const clients = [
  { client_id: "1", status: "CRITICAL" },
  { client_id: "2", status: "URGENT" },
  { client_id: "3", status: "URGENT" },
  { client_id: "4", status: "DUE SOON" },
  { client_id: "5", status: "ACTIVE" },
];

describe("StatCards", () => {
  it("shows correct counts per status and total", () => {
    render(<StatCards clients={clients} />);
    expect(screen.getByTestId("stat-total")).toHaveTextContent("5");
    expect(screen.getByTestId("stat-CRITICAL")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-URGENT")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-DUE SOON")).toHaveTextContent("1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test`
Expected: FAIL — `StatCards.jsx` doesn't exist

- [ ] **Step 3: Implement `StatCards.jsx`**

Create `dashboard-app/frontend/src/components/StatCards.jsx`:

```jsx
import { motion } from "framer-motion";

const CARD_CONFIG = [
  { key: "total", label: "Total Clients", gradient: "from-sky-500 to-indigo-500" },
  { key: "CRITICAL", label: "Critical", gradient: "from-rose-500 to-orange-500" },
  { key: "URGENT", label: "Urgent", gradient: "from-amber-500 to-orange-400" },
  { key: "DUE SOON", label: "Due Soon", gradient: "from-yellow-400 to-amber-500" },
];

export default function StatCards({ clients }) {
  const counts = {
    total: clients.length,
    CRITICAL: clients.filter((c) => c.status === "CRITICAL").length,
    URGENT: clients.filter((c) => c.status === "URGENT").length,
    "DUE SOON": clients.filter((c) => c.status === "DUE SOON").length,
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="stat-cards">
      {CARD_CONFIG.map((card) => (
        <motion.div
          key={card.key}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-2xl p-4 text-white shadow-lg bg-gradient-to-br ${card.gradient}`}
        >
          <div className="text-sm font-medium opacity-90">{card.label}</div>
          <div className="text-3xl font-bold" data-testid={`stat-${card.key}`}>
            {counts[card.key]}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/StatCards.jsx dashboard-app/frontend/src/components/StatCards.test.jsx
git commit -m "Add StatCards component"
```

---

### Task 9: `FilterBar` component

**Files:**
- Create: `dashboard-app/frontend/src/components/FilterBar.jsx`
- Create: `dashboard-app/frontend/src/components/FilterBar.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/FilterBar.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FilterBar from "./FilterBar";

describe("FilterBar", () => {
  it("calls onStatusChange with the clicked status", () => {
    const onStatusChange = vi.fn();
    render(
      <FilterBar activeStatus="ALL" onStatusChange={onStatusChange} searchTerm="" onSearchChange={() => {}} />
    );
    fireEvent.click(screen.getByText("Critical"));
    expect(onStatusChange).toHaveBeenCalledWith("CRITICAL");
  });

  it("calls onSearchChange as the user types", () => {
    const onSearchChange = vi.fn();
    render(
      <FilterBar activeStatus="ALL" onStatusChange={() => {}} searchTerm="" onSearchChange={onSearchChange} />
    );
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "rahul" },
    });
    expect(onSearchChange).toHaveBeenCalledWith("rahul");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `FilterBar.jsx` doesn't exist

- [ ] **Step 3: Implement `FilterBar.jsx`**

Create `dashboard-app/frontend/src/components/FilterBar.jsx`:

```jsx
const STATUS_TABS = ["ALL", "CRITICAL", "URGENT", "DUE SOON", "ACTIVE", "EXPIRED"];

export default function FilterBar({ activeStatus, onStatusChange, searchTerm, onSearchChange }) {
  return (
    <div className="flex flex-wrap items-center gap-3" data-testid="filter-bar">
      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => onStatusChange(status)}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${
              activeStatus === status
                ? "bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow"
                : "bg-white text-slate-600 border border-slate-200"
            }`}
          >
            {status === "ALL" ? "All" : status.charAt(0) + status.slice(1).toLowerCase()}
          </button>
        ))}
      </div>
      <input
        type="text"
        value={searchTerm}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search name or company..."
        className="ml-auto px-4 py-1.5 rounded-full border border-slate-200 text-sm min-w-[220px] focus:outline-none focus:ring-2 focus:ring-indigo-400"
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/FilterBar.jsx dashboard-app/frontend/src/components/FilterBar.test.jsx
git commit -m "Add FilterBar component"
```

---

### Task 10: `ClientTable` component

**Files:**
- Create: `dashboard-app/frontend/src/components/ClientTable.jsx`
- Create: `dashboard-app/frontend/src/components/ClientTable.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/ClientTable.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientTable from "./ClientTable";

const clients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
    cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL", alert_sent_today: false },
  { client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", cert_name: "OSHA",
    cert_id: "OSHA-1", expiry_date: "11-08-2026", status: "URGENT", alert_sent_today: true },
  { client_id: "CLT004", name: "Sneha Kapoor", company: "EduTech", cert_name: "ISO 27001",
    cert_id: "ISO27-1", expiry_date: "15-10-2026", status: "ACTIVE", alert_sent_today: null },
];

describe("ClientTable", () => {
  it("shows a Send Alert button for eligible, not-yet-sent clients", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Send Alert")).toBeInTheDocument();
  });

  it("shows a Sent pill for eligible clients already sent today, with no button", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("✅ Sent")).toBeInTheDocument();
  });

  it("shows a dash for non-eligible statuses", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("calls onSendClick with the client when Send Alert is clicked", () => {
    const onSendClick = vi.fn();
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={onSendClick} />
    );
    fireEvent.click(screen.getByText("Send Alert"));
    expect(onSendClick).toHaveBeenCalledWith(clients[0]);
  });

  it("filters rows by active status", () => {
    render(
      <ClientTable clients={clients} activeStatus="URGENT" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument();
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
  });

  it("filters rows by search term", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="rahul" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.queryByText("Priya Mehta")).not.toBeInTheDocument();
  });

  it("calls onSort with the column key when a header is clicked", () => {
    const onSort = vi.fn();
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={onSort} onSendClick={() => {}} />
    );
    fireEvent.click(screen.getByText("Days Left"));
    expect(onSort).toHaveBeenCalledWith("days_left");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `ClientTable.jsx` doesn't exist

- [ ] **Step 3: Implement `ClientTable.jsx`**

Create `dashboard-app/frontend/src/components/ClientTable.jsx`:

```jsx
import { sortClients, formatDaysLeft } from "../sortUtils";

const STATUS_COLORS = {
  EXPIRED: "bg-red-500 text-white",
  CRITICAL: "bg-orange-500 text-white",
  URGENT: "bg-amber-400 text-slate-900",
  "DUE SOON": "bg-yellow-300 text-slate-900",
  ACTIVE: "bg-emerald-500 text-white",
};

const ALERT_ELIGIBLE = new Set(["CRITICAL", "URGENT", "DUE SOON"]);

const COLUMNS = [
  { key: "client_id", label: "Client ID" },
  { key: "name", label: "Full Name" },
  { key: "company", label: "Company" },
  { key: "cert_name", label: "Certification" },
  { key: "cert_id", label: "Cert ID" },
  { key: "expiry_date", label: "Expiry Date" },
  { key: "days_left", label: "Days Left" },
  { key: "status", label: "Status" },
];

export default function ClientTable({
  clients, activeStatus, searchTerm, sortKey, sortAsc, onSort, onSendClick,
}) {
  let rows = clients;
  if (activeStatus !== "ALL") {
    rows = rows.filter((c) => c.status === activeStatus);
  }
  if (searchTerm) {
    const term = searchTerm.toLowerCase();
    rows = rows.filter(
      (c) => c.name.toLowerCase().includes(term) || c.company.toLowerCase().includes(term)
    );
  }
  rows = sortClients(rows, sortKey, sortAsc);

  return (
    <table className="w-full bg-white rounded-2xl overflow-hidden shadow" data-testid="client-table">
      <thead>
        <tr className="bg-gradient-to-r from-slate-800 to-slate-700 text-white text-sm">
          {COLUMNS.map((col) => (
            <th
              key={col.key}
              onClick={() => onSort(col.key)}
              className="px-3 py-2 text-left cursor-pointer select-none"
            >
              {col.label}
            </th>
          ))}
          <th className="px-3 py-2 text-left">Action</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.client_id} className="border-b border-slate-100 text-sm hover:bg-slate-50 transition-colors">
            <td className="px-3 py-2">{c.client_id}</td>
            <td className="px-3 py-2">{c.name}</td>
            <td className="px-3 py-2">{c.company}</td>
            <td className="px-3 py-2">{c.cert_name}</td>
            <td className="px-3 py-2">{c.cert_id}</td>
            <td className="px-3 py-2">{c.expiry_date}</td>
            <td className="px-3 py-2">{formatDaysLeft(c.expiry_date)}</td>
            <td className="px-3 py-2">
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${STATUS_COLORS[c.status] || "bg-slate-300"}`}>
                {c.status}
              </span>
            </td>
            <td className="px-3 py-2">
              {!ALERT_ELIGIBLE.has(c.status) ? (
                <span className="text-slate-400">—</span>
              ) : c.alert_sent_today ? (
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
                  ✅ Sent
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onSendClick(c)}
                  className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 shadow hover:opacity-90 transition-opacity"
                >
                  Send Alert
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/ClientTable.jsx dashboard-app/frontend/src/components/ClientTable.test.jsx
git commit -m "Add ClientTable component with sort/filter/search and per-row send action"
```

---

### Task 11: `SendConfirmModal` component

**Files:**
- Create: `dashboard-app/frontend/src/components/SendConfirmModal.jsx`
- Create: `dashboard-app/frontend/src/components/SendConfirmModal.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/SendConfirmModal.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SendConfirmModal from "./SendConfirmModal";

describe("SendConfirmModal", () => {
  it("renders nothing when client is null", () => {
    const { container } = render(<SendConfirmModal client={null} onConfirm={() => {}} onCancel={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the client's name and company when open", () => {
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.getByText("TechCorp")).toBeInTheDocument();
  });

  it("calls onConfirm when Confirm Send is clicked", () => {
    const onConfirm = vi.fn();
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={onConfirm} onCancel={() => {}} />
    );
    fireEvent.click(screen.getByText("Confirm Send"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={() => {}} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `SendConfirmModal.jsx` doesn't exist

- [ ] **Step 3: Implement `SendConfirmModal.jsx`**

Create `dashboard-app/frontend/src/components/SendConfirmModal.jsx`:

```jsx
export default function SendConfirmModal({ client, onConfirm, onCancel }) {
  if (!client) return null;
  return (
    <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50" data-testid="send-confirm-modal">
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full">
        <h3 className="text-lg font-bold text-slate-800 mb-2">Send renewal alert?</h3>
        <p className="text-sm text-slate-600 mb-6">
          Send a real WhatsApp renewal alert to <strong>{client.name}</strong> at{" "}
          <strong>{client.company}</strong>?
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500"
          >
            Confirm Send
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/SendConfirmModal.jsx dashboard-app/frontend/src/components/SendConfirmModal.test.jsx
git commit -m "Add SendConfirmModal component"
```

---

### Task 12: `Toast` component

**Files:**
- Create: `dashboard-app/frontend/src/components/Toast.jsx`
- Create: `dashboard-app/frontend/src/components/Toast.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/Toast.test.jsx`:

```jsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Toast from "./Toast";

describe("Toast", () => {
  it("renders nothing when toast is null", () => {
    render(<Toast toast={null} onDismiss={() => {}} />);
    expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
  });

  it("shows the toast message when set", () => {
    render(<Toast toast={{ type: "success", message: "Sent to Rahul Sharma" }} onDismiss={() => {}} />);
    expect(screen.getByText("Sent to Rahul Sharma")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `Toast.jsx` doesn't exist

- [ ] **Step 3: Implement `Toast.jsx`**

Create `dashboard-app/frontend/src/components/Toast.jsx`:

```jsx
import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(onDismiss, 4000);
    return () => clearTimeout(timer);
  }, [toast, onDismiss]);

  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          data-testid="toast"
          className={`fixed bottom-6 right-6 px-5 py-3 rounded-xl shadow-lg text-sm font-medium text-white ${
            toast.type === "error" ? "bg-rose-500" : "bg-emerald-500"
          }`}
        >
          {toast.message}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/Toast.jsx dashboard-app/frontend/src/components/Toast.test.jsx
git commit -m "Add Toast component"
```

---

### Task 13: Wire everything together in `App.jsx`

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Modify: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

Replace `dashboard-app/frontend/src/App.test.jsx` with:

```jsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";

vi.mock("./api");

const sampleClients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
    cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL", alert_sent_today: false },
];

beforeEach(() => {
  vi.resetAllMocks();
  api.getClients.mockResolvedValue(sampleClients);
});

describe("App", () => {
  it("renders the Absolute Veritas heading", async () => {
    render(<App />);
    expect(screen.getByText("Absolute Veritas")).toBeInTheDocument();
  });

  it("loads and displays clients on mount", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("Rahul Sharma")).toBeInTheDocument());
  });

  it("does not send until the confirmation modal is accepted", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send Alert"));
    expect(screen.getByTestId("send-confirm-modal")).toBeInTheDocument();
    expect(api.sendAlert).not.toHaveBeenCalled();
  });

  it("sends and shows a success toast after confirming", async () => {
    api.sendAlert.mockResolvedValue({ status: "sent", message_id: "wamid.ABC" });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Confirm Send"));
    await waitFor(() => expect(api.sendAlert).toHaveBeenCalledWith("CLT001"));
    await waitFor(() => expect(screen.getByText("Sent to Rahul Sharma")).toBeInTheDocument());
  });

  it("shows an error toast when the send fails", async () => {
    api.sendAlert.mockRejectedValue(new Error("Alert already sent today for this client/status"));
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Confirm Send"));
    await waitFor(() =>
      expect(screen.getByText("Alert already sent today for this client/status")).toBeInTheDocument()
    );
  });

  it("shows a load error message when getClients fails", async () => {
    api.getClients.mockRejectedValue(new Error("Failed to load clients: 500"));
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("load-error")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `App.jsx` doesn't fetch/render clients yet, no send flow exists

- [ ] **Step 3: Implement the full `App.jsx`**

Replace `dashboard-app/frontend/src/App.jsx`:

```jsx
import { useState, useEffect, useCallback } from "react";
import StatCards from "./components/StatCards";
import FilterBar from "./components/FilterBar";
import ClientTable from "./components/ClientTable";
import SendConfirmModal from "./components/SendConfirmModal";
import Toast from "./components/Toast";
import { getClients, sendAlert } from "./api";

export default function App() {
  const [clients, setClients] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [activeStatus, setActiveStatus] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [sortKey, setSortKey] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [pendingClient, setPendingClient] = useState(null);
  const [toast, setToast] = useState(null);

  const loadClients = useCallback(() => {
    getClients()
      .then((data) => {
        setClients(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  function handleSort(key) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  async function handleConfirmSend() {
    const client = pendingClient;
    setPendingClient(null);
    try {
      await sendAlert(client.client_id);
      setToast({ type: "success", message: `Sent to ${client.name}` });
      loadClients();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold bg-gradient-to-r from-sky-500 to-indigo-500 bg-clip-text text-transparent">
          Absolute Veritas
        </h1>
        <button
          type="button"
          onClick={loadClients}
          className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200 bg-white"
        >
          Refresh
        </button>
      </div>

      {loadError && (
        <div className="text-sm text-rose-600" data-testid="load-error">
          Could not load clients: {loadError}. Is the backend running?
        </div>
      )}

      <StatCards clients={clients} />
      <FilterBar
        activeStatus={activeStatus}
        onStatusChange={setActiveStatus}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
      />
      <ClientTable
        clients={clients}
        activeStatus={activeStatus}
        searchTerm={searchTerm}
        sortKey={sortKey}
        sortAsc={sortAsc}
        onSort={handleSort}
        onSendClick={setPendingClient}
      />
      <SendConfirmModal
        client={pendingClient}
        onConfirm={handleConfirmSend}
        onCancel={() => setPendingClient(null)}
      />
      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed (every component test suite plus the full App integration suite)

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "Wire StatCards, FilterBar, ClientTable, SendConfirmModal, and Toast together in App"
```

---

### Task 14: Serve the built frontend from FastAPI

**Files:**
- Modify: `dashboard-app/backend/main.py`

- [ ] **Step 1: Build the frontend**

Run (from `dashboard-app/frontend/`):
```bash
npm run build
```
Expected: creates `dashboard-app/frontend/dist/` with `index.html` and asset files.

- [ ] **Step 2: Mount the built files in FastAPI**

Add to the end of `dashboard-app/backend/main.py` (after every `@app.get`/`@app.post` route — this must come last, since a catch-all mount at `/` declared earlier would shadow the API routes):

```python
from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_DIST = REPO_ROOT / "dashboard-app" / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
```

- [ ] **Step 3: Verify the API routes still work and the frontend is served**

Run (from `dashboard-app/backend/`):
```bash
python -m pytest test_main.py -v
```
Expected: all tests still pass (mounting static files after the routes doesn't affect them).

Run (from `dashboard-app/backend/`), in one terminal:
```bash
python -m uvicorn main:app --port 8000
```
Then, in another terminal:
```bash
curl -s http://localhost:8000/api/health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/
```
Expected: first command prints `{"status":"ok"}`; second prints `200` (the built `index.html` is served).
Stop the server with Ctrl+C afterward.

- [ ] **Step 4: Commit**

```bash
git add dashboard-app/backend/main.py
git commit -m "Serve built frontend as static files from the FastAPI backend"
```

---

### Task 15: Final manual walkthrough

**Files:** none (verification only, done by the user)

- [ ] **Step 1: Add a test number to `.env`**

Add a line to the repo's real `.env` (not `.env.example`):
```
DASHBOARD_TEST_NUMBER=<a real WhatsApp number you control, digits only with country code>
```

- [ ] **Step 2: Start the backend**

```bash
cd dashboard-app/backend
python -m uvicorn main:app --port 8000
```

- [ ] **Step 3: Open the dashboard**

Open `http://localhost:8000` in a browser. Confirm:
- Stat cards show correct counts (Total, Critical, Urgent, Due Soon) matching the real client data
- Status tabs filter correctly; search narrows by name/company
- Every column header sorts both directions; Days Left and Expiry Date sort chronologically, not alphabetically
- Clients already sent today (per `sent_log.json`) show a disabled "✅ Sent" pill; other eligible clients show a "Send Alert" button; ACTIVE/EXPIRED clients show "—"
- Clicking "Send Alert" opens the confirmation modal; Cancel closes it with no API call
- Confirming sends a real WhatsApp message to `DASHBOARD_TEST_NUMBER` (not the real client's number), shows a success toast, and the row updates to "✅ Sent" without a page reload
- Clicking Send Alert again on that same row is not offered (already shows "✅ Sent")
- Refresh button reloads the data correctly

- [ ] **Step 4: Remove the test number before real use**

Once confirmed working, delete the `DASHBOARD_TEST_NUMBER` line from `.env` so future sends go to real clients.

- [ ] **Step 5: Confirm working tree is clean**

Run: `git status`
Expected: `nothing to commit, working tree clean` (aside from any pre-existing unrelated untracked files already present before this project started)
