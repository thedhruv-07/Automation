# Email Renewal Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a working "Send Email" (per-client) and "Send All Emails" (bulk, job-based) capability to the dashboard, mirroring the existing WhatsApp send pattern exactly, since WhatsApp currently cannot reach any client (0 of 66,745 have a phone number) while email is viable for nearly everyone (99.93% have a valid address).

**Architecture:** A new `email_sent_log` table (independent of WhatsApp's `sent_log`, same shape) tracks per-day email dedup. A new `email_alerts.py` module mirrors `whatsapp_renewal_alerts.py`'s `send_message`/`send_one_alert`/`run` trio, sending via the same Brevo API call already proven in `cert_automation.py`, reusing the already-built `email_template.build_email_html()` (the same function `/api/email-preview` already calls). Three new FastAPI endpoints mirror the WhatsApp ones exactly (`/api/send-email/{id}`, `/api/send-all-emails`, `/api/send-all-emails/status/{job_id}`), with their own independent lock/in-progress guards so an email bulk send and a WhatsApp bulk send never block each other. The frontend gets a "Send Email" button per row and a "Send All Emails" header button, reusing `SendConfirmModal`/`SendAllConfirmModal` via a new `channel` prop rather than duplicating those components.

**Tech Stack:** No new dependencies — `requests` (already used for WhatsApp) for the Brevo HTTP call, existing FastAPI/React/pytest/Vitest stack.

**Reference spec:** `docs/superpowers/specs/2026-07-23-email-alerts-design.md`

---

### Task 1: `db.py` — `email_sent_log` table and its data-access functions

**Files:**
- Modify: `dashboard-app/backend/db.py`
- Test: `dashboard-app/backend/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_db.py`:

```python
from db import (
    record_email_sent, is_email_already_sent, load_email_sent_log, save_email_sent_log,
)


def test_is_email_already_sent_false_then_true_after_record_email_sent(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert is_email_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is False
    record_email_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "brevo-msg-1", "r@x.com", "2026-07-21T10:00:00")
    assert is_email_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is True


def test_email_dedup_is_independent_of_whatsapp_dedup(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "919876543210", "2026-07-21T10:00:00")
    # WhatsApp was sent, but email for the same client/status/day should still be unsent
    assert is_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is True
    assert is_email_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is False


def test_save_email_sent_log_then_load_email_sent_log_round_trips_exactly(tmp_path):
    db_path = _seeded_db(tmp_path)
    original = {
        "CLT001|CRITICAL|2026-07-21": {
            "sent_at": "2026-07-21T10:00:00",
            "message_id": "brevo-msg-1",
            "email": "r@x.com",
        },
        "CLT002|URGENT|2026-07-21": {
            "sent_at": "2026-07-21T10:05:00",
            "message_id": "brevo-msg-2",
            "email": "p@x.com",
        },
    }
    save_email_sent_log(db_path, original)
    loaded = load_email_sent_log(db_path)
    assert loaded == original


def test_get_stats_eligible_not_emailed_today_excludes_already_emailed(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_email_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "brevo-msg-1", "r@x.com", "2026-07-21T10:00:00")
    stats = get_stats(db_path, today="2026-07-21")
    # CRITICAL, URGENT, DUE SOON, EXPIRED = 4 alert-eligible rows; CLT001 already emailed today
    assert stats["eligible_not_emailed_today"] == 3
    # WhatsApp's own count is untouched by the email send
    assert stats["eligible_not_sent_today"] == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v -k "email"`
Expected: FAIL with `ImportError: cannot import name 'record_email_sent'`

- [ ] **Step 3: Add the `email_sent_log` table to `db.py`'s `SCHEMA`**

Current:
```python
CREATE TABLE IF NOT EXISTS sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    phone       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);
"""
```

Replace with:
```python
CREATE TABLE IF NOT EXISTS sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    phone       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);

CREATE TABLE IF NOT EXISTS email_sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    email       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);
"""
```

- [ ] **Step 4: Add the four new functions to `db.py`, right after `save_sent_log`**

```python
def record_email_sent(db_path, client_id, status, sent_date, message_id, email, sent_at) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO email_sent_log (client_id, status, sent_date, message_id, email, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, status, sent_date, message_id, email, sent_at),
        )
        conn.commit()
    finally:
        conn.close()


def is_email_already_sent(db_path, client_id, status, sent_date) -> bool:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM email_sent_log WHERE client_id = ? AND status = ? AND sent_date = ?",
            (client_id, status, sent_date),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def load_email_sent_log(db_path) -> dict:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT client_id, status, sent_date, message_id, email, sent_at FROM email_sent_log"
        ).fetchall()
        log = {}
        for r in rows:
            key = f"{r['client_id']}|{r['status']}|{r['sent_date']}"
            log[key] = {"sent_at": r["sent_at"], "message_id": r["message_id"], "email": r["email"]}
        return log
    finally:
        conn.close()


def save_email_sent_log(db_path, log: dict) -> None:
    for key, info in log.items():
        client_id, status, sent_date = key.split("|", 2)
        record_email_sent(
            db_path, client_id, status, sent_date,
            info.get("message_id"), info.get("email"), info.get("sent_at"),
        )
```

- [ ] **Step 5: Add `eligible_not_emailed_today` to `get_stats`**

Current (inside `get_stats`, right after the `eligible_not_sent` query):
```python
        alert_statuses = ("CRITICAL", "URGENT", "DUE SOON", "EXPIRED")
        placeholders = ", ".join(["?"] * len(alert_statuses))
        eligible_not_sent = conn.execute(
            f"""
            SELECT COUNT(*) FROM clients c
            WHERE c.status IN ({placeholders})
            AND NOT EXISTS (
                SELECT 1 FROM sent_log s
                WHERE s.client_id = c.client_id AND s.status = c.status AND s.sent_date = ?
            )
            """,
            (*alert_statuses, today),
        ).fetchone()[0]
```

Add right after it:
```python
        eligible_not_emailed = conn.execute(
            f"""
            SELECT COUNT(*) FROM clients c
            WHERE c.status IN ({placeholders})
            AND NOT EXISTS (
                SELECT 1 FROM email_sent_log s
                WHERE s.client_id = c.client_id AND s.status = c.status AND s.sent_date = ?
            )
            """,
            (*alert_statuses, today),
        ).fetchone()[0]
```

And update the function's `return` statement — current:
```python
        return {
            "status_counts": status_counts,
            "eligible_not_sent_today": eligible_not_sent,
            "cert_types": cert_types,
            "renewals_by_month": renewals_by_month,
        }
```

Replace with:
```python
        return {
            "status_counts": status_counts,
            "eligible_not_sent_today": eligible_not_sent,
            "eligible_not_emailed_today": eligible_not_emailed,
            "cert_types": cert_types,
            "renewals_by_month": renewals_by_month,
        }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: all passed (existing tests plus the 4 new ones — note `test_get_stats_eligible_not_sent_today_excludes_already_sent` and every other existing `get_stats` test must still pass unmodified, since the return dict only gained a key, nothing existing changed shape).

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/test_db.py
git commit -m "feat: add email_sent_log table and eligible_not_emailed_today stat"
```

---

### Task 2: New module `email_alerts.py`

**Files:**
- Create: `dashboard-app/backend/email_alerts.py`
- Create: `dashboard-app/backend/test_email_alerts.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for email_alerts.py."""
from unittest.mock import Mock

from db import upsert_clients, save_email_sent_log
from email_alerts import send_one_email_alert, run_email_alerts

ROW_WITH_EMAIL = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
                    "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                 "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
ROW_INVALID_EMAIL = ("CLT003", "Amit Verma", "HealthFirst", "not-an-email", "919800000000",
                       "ISO 9001", "ISO27-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON")


def _record_dict(row):
    from db import RECORD_FIELDS
    return dict(zip(RECORD_FIELDS, row))


def test_send_one_email_alert_sends_and_updates_log():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "sent"
    assert result["message_id"] == "brevo-1"
    key = "CLT001|CRITICAL|2026-07-17"
    assert key in sent_log
    send_fn.assert_called_once()


def test_send_one_email_alert_skips_duplicate():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {"CLT001|CRITICAL|2026-07-17": {"sent_at": "x", "message_id": "y", "email": "r@x.com"}}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_one_email_alert_skips_when_no_email():
    record = _record_dict(ROW_NO_EMAIL)
    sent_log = {}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_one_email_alert_skips_when_email_missing_at_sign():
    record = _record_dict(ROW_INVALID_EMAIL)
    sent_log = {}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_one_email_alert_reports_failure():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(False, {"error": "Brevo rejected the request"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "failed"
    assert result["error"] == "Brevo rejected the request"
    assert sent_log == {}


def test_send_one_email_alert_test_email_override_redirects_recipient():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas",
        to_email_override="test-inbox@x.com", send_fn=send_fn,
    )

    call_kwargs = send_fn.call_args
    assert call_kwargs.kwargs.get("to_email") == "test-inbox@x.com" or "test-inbox@x.com" in call_kwargs.args


def test_run_email_alerts_processes_all_alert_eligible_clients(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_WITH_EMAIL, ROW_NO_EMAIL, ROW_INVALID_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn,
    )

    actions = {r["client_id"]: r["action"] for r in results}
    assert actions["CLT001"] == "sent"
    assert actions["CLT002"] == "skipped_no_email"
    assert actions["CLT003"] == "skipped_no_email"
    assert send_fn.call_count == 1


def test_run_email_alerts_calls_on_progress_for_each_record(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_WITH_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))
    progress_calls = []

    run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )

    assert progress_calls == [("sent", 1)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'email_alerts'`

- [ ] **Step 3: Write `email_alerts.py`**

```python
"""Email renewal-alert sender for Absolute Veritas -- sends via Brevo's
transactional email API, reusing the same HTML template the dashboard's
/api/email-preview endpoint already builds. Mirrors whatsapp_renewal_alerts.py's
send_message/send_one_alert/run structure so the two channels behave
consistently, but tracks its own dedup log (email_sent_log, independent of
WhatsApp's sent_log) so a client can receive both channels the same day
without one blocking the other."""
import base64
from datetime import datetime
from pathlib import Path

import requests

from db import (
    DEFAULT_DB_PATH, read_clients, load_email_sent_log, save_email_sent_log,
)
from email_template import build_email_html
from whatsapp_renewal_alerts import ALERT_STATUSES, dedup_key, filter_alertable

SCRIPT_DIR = Path(__file__).parent
LOGO_PATH = SCRIPT_DIR.parent / "frontend" / "public" / "company-logo.png"
LOGO_CID = "company-logo.png"

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

    logo_src = f"cid:{LOGO_CID}" if LOGO_PATH.exists() else ""
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src,
    )
    subject = f"[Action Required] Renew {rec['cert_name']} — {rec['company']}"

    attachments = []
    if LOGO_PATH.exists():
        logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        attachments.append({"name": LOGO_CID, "content": logo_b64})

    payload = {
        "sender": {"name": org_name, "email": email_sender},
        "to": [{"email": to_email, "name": rec["name"]}],
        "subject": subject,
        "htmlContent": html,
        "attachment": attachments,
    }
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
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = filter_alertable(read_clients(db_path))
    sent_log = load_email_sent_log(db_path)
    persist_log = not dry_run and not test_email
    log_dirty = False
    results = []

    for rec in records:
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

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    if persist_log and log_dirty:
        save_email_sent_log(db_path, sent_log)

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all passed.

Note: `test_send_one_email_alert_test_email_override_redirects_recipient` calls `send_fn` with `to_email=` as a keyword — since `send_one_email_alert` calls `send_fn(record, brevo_api_key, email_sender, org_name, to_email=to_email)`, this matches `send_email_via_brevo`'s real signature (`to_email` is the last positional-or-keyword param) — if the test's assertion on `call_args` doesn't match exactly how Mock records kwargs, adjust the assertion to `send_fn.call_args.kwargs["to_email"] == "test-inbox@x.com"` (simpler and equivalent) rather than the OR-fallback written above, which was hedging against not knowing Mock's exact call_args shape before writing this — verify and simplify once the test actually runs.

- [ ] **Step 5: Run the full Python suite**

Run: `cd dashboard-app/backend && python -m pytest -q` (or from repo root: `python -m pytest -q`)
Expected: all passed, no regressions in existing WhatsApp/db/main tests.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/email_alerts.py dashboard-app/backend/test_email_alerts.py
git commit -m "feat: add email_alerts.py -- Brevo-backed renewal email sender"
```

---

### Task 3: `main.py` — three new endpoints

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Test: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_main.py`:

```python
from db import load_email_sent_log, save_email_sent_log


def _setup_one_email_client(tmp_path, monkeypatch, status="CRITICAL"):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_SENDER", "sender@x.com")
    monkeypatch.delenv("DASHBOARD_TEST_EMAIL", raising=False)
    return db_path


def test_send_email_success(tmp_path, monkeypatch):
    db_path = _setup_one_email_client(tmp_path, monkeypatch)
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messageId": "brevo-1"},
    })()
    with patch("email_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-email/CLT001")
    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message_id": "brevo-1"}
    log = load_email_sent_log(db_path)
    assert "CLT001|CRITICAL|2026-07-18" in log


def test_send_email_unknown_client_returns_404(tmp_path, monkeypatch):
    _setup_one_email_client(tmp_path, monkeypatch)
    response = client.post("/api/send-email/NOPE")
    assert response.status_code == 404


def test_send_email_ineligible_status_returns_400(tmp_path, monkeypatch):
    _setup_one_email_client(tmp_path, monkeypatch, status="ACTIVE")
    response = client.post("/api/send-email/CLT001")
    assert response.status_code == 400


def test_send_email_no_email_on_file_returns_400(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT005", "No Email Co", "No Email Co", None, "919000000000",
         "ISO 9001", "ISO-5", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_SENDER", "sender@x.com")
    response = client.post("/api/send-email/CLT005")
    assert response.status_code == 400
    assert "email" in response.json()["detail"].lower()


def test_send_email_duplicate_returns_409(tmp_path, monkeypatch):
    db_path = _setup_one_email_client(tmp_path, monkeypatch)
    save_email_sent_log(db_path, {
        "CLT001|CRITICAL|2026-07-18": {"sent_at": "x", "message_id": "y", "email": "r@x.com"},
    })
    response = client.post("/api/send-email/CLT001")
    assert response.status_code == 409


def test_send_all_emails_starts_job_and_reports_progress(tmp_path, monkeypatch):
    _setup_one_email_client(tmp_path, monkeypatch)
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messageId": "brevo-1"},
    })()
    with patch("email_alerts.requests.post", return_value=mock_response):
        start_response = client.post("/api/send-all-emails")
        assert start_response.status_code == 200
        job_id = start_response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/send-all-emails/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["sent"] == 1
    assert final["total"] == 1


def test_send_all_emails_status_returns_404_for_unknown_job():
    response = client.get("/api/send-all-emails/status/does-not-exist")
    assert response.status_code == 404


def test_send_all_emails_blocks_concurrent_calls(tmp_path, monkeypatch):
    _setup_one_email_client(tmp_path, monkeypatch)
    monkeypatch.setattr(main_module, "_email_bulk_in_progress", True)
    response = client.post("/api/send-all-emails")
    assert response.status_code == 409


def test_send_all_emails_does_not_block_on_whatsapp_bulk_in_progress(tmp_path, monkeypatch):
    """The two channels' bulk-send locks must be independent."""
    _setup_one_email_client(tmp_path, monkeypatch)
    monkeypatch.setattr(main_module, "_bulk_in_progress", True)  # WhatsApp's flag, not email's
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messageId": "brevo-1"},
    })()
    with patch("email_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all-emails")
    assert response.status_code == 200
```

This mirrors the real, already-verified pattern the existing WhatsApp send tests in this file use: `patch("email_alerts.requests.post", ...)` (not a wrapper function) — `send_one_email_alert`'s default `send_fn=send_email_via_brevo` parameter is bound at *def time*, so patching a module-level name for the wrapper would not intercept the call; patching `requests.post`, which is looked up by attribute at call time, does. `import time` is local to the polling test, matching the existing file's own convention (not a top-of-file import). No `auth=(...)` tuple is used anywhere in this file's existing tests, since `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` are never set in this test environment, so `require_auth` no-ops — new tests follow the same convention.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v -k "send_email or send_all_emails"`
Expected: FAIL (endpoints don't exist yet — 404s where 200/400/409 expected, `AttributeError` on `main_module._email_bulk_in_progress`).

- [ ] **Step 3: Update `main.py`**

Add to the import block (near the existing `from whatsapp_renewal_alerts import (...)` line):
```python
from email_alerts import (  # noqa: E402
    send_email_via_brevo, send_one_email_alert, run_email_alerts,
)
from db import (  # noqa: E402  -- extends the existing db import, don't duplicate the line, add these names to it
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
)
```

(The second block replaces the *existing* `from db import (...)` block — add the three new names to the existing list rather than creating a second import statement for the same module.)

Add new module-level state, right after the existing `_bulk_in_progress = False` line:
```python
_email_send_lock = threading.Lock()
_pending_email_sends: set[str] = set()

_email_bulk_in_progress = False
```

Add three new endpoints, placed after the existing `/api/send-all/status/{job_id}` endpoint:

```python
@app.post("/api/send-email/{client_id}", dependencies=[Depends(require_auth)])
def send_email(client_id: str):
    today = _today_str()
    record = find_client_by_id(DEFAULT_DB_PATH, client_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown client_id: {client_id}")
    if record["status"] not in ALERT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status {record['status']} is not alert-eligible",
        )
    if not record.get("email") or "@" not in record["email"]:
        raise HTTPException(
            status_code=400,
            detail="This client has no valid email on file",
        )

    sent_log = load_email_sent_log(DEFAULT_DB_PATH)
    key = dedup_key(record["client_id"], record["status"], today)
    if key in sent_log:
        raise HTTPException(
            status_code=409,
            detail="Email already sent today for this client/status",
        )

    with _email_send_lock:
        if client_id in _pending_email_sends:
            raise HTTPException(
                status_code=409,
                detail="An email send for this client is already in progress",
            )
        if _email_bulk_in_progress:
            raise HTTPException(
                status_code=409,
                detail="A bulk email send is in progress; try again after it completes",
            )
        _pending_email_sends.add(client_id)

    try:
        brevo_api_key = os.environ["BREVO_API_KEY"]
        email_sender = os.environ["EMAIL_SENDER"]
        test_email = os.environ.get("DASHBOARD_TEST_EMAIL") or None

        result = send_one_email_alert(
            record, sent_log, today, brevo_api_key, email_sender, "Absolute Veritas",
            to_email_override=test_email,
        )

        if result["action"] == "sent":
            if not test_email:
                save_email_sent_log(DEFAULT_DB_PATH, sent_log)
            return {"status": "sent", "message_id": result["message_id"]}
        if result["action"] == "skipped_duplicate":
            raise HTTPException(
                status_code=409,
                detail="Email already sent today for this client/status",
            )
        raise HTTPException(status_code=502, detail=result.get("error", "Unknown error"))
    finally:
        with _email_send_lock:
            _pending_email_sends.discard(client_id)


_send_all_email_jobs: dict[str, dict] = {}


def _run_send_all_email_job(job_id, brevo_api_key, email_sender, test_email):
    def progress(result, total):
        job = _send_all_email_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "skipped_no_email":
            job["skipped_no_email"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        run_email_alerts(
            DEFAULT_DB_PATH, brevo_api_key, email_sender, "Absolute Veritas",
            dry_run=False, test_email=test_email, on_progress=progress,
        )
    except Exception as exc:
        _send_all_email_jobs[job_id]["error"] = str(exc)
    finally:
        _send_all_email_jobs[job_id]["done"] = True
        global _email_bulk_in_progress
        with _email_send_lock:
            _email_bulk_in_progress = False


@app.post("/api/send-all-emails", dependencies=[Depends(require_auth)])
def send_all_emails():
    global _email_bulk_in_progress
    with _email_send_lock:
        if _email_bulk_in_progress:
            raise HTTPException(status_code=409, detail="A bulk email send is already in progress")
        if _pending_email_sends:
            raise HTTPException(
                status_code=409,
                detail="One or more per-client email sends are in progress; try again shortly",
            )
        _email_bulk_in_progress = True

    try:
        brevo_api_key = os.environ["BREVO_API_KEY"]
        email_sender = os.environ["EMAIL_SENDER"]
        test_email = os.environ.get("DASHBOARD_TEST_EMAIL") or None

        job_id = str(uuid.uuid4())
        _send_all_email_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "skipped_no_email": 0, "failed": 0,
            "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_all_email_job,
            args=(job_id, brevo_api_key, email_sender, test_email),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        with _email_send_lock:
            _email_bulk_in_progress = False
        raise HTTPException(status_code=500, detail="Server is not configured to send emails")


@app.get("/api/send-all-emails/status/{job_id}", dependencies=[Depends(require_auth)])
def send_all_emails_status(job_id: str):
    job = _send_all_email_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v -k "send_email or send_all_emails"`
Expected: all passed.

- [ ] **Step 5: Run the full suite**

Run: `cd dashboard-app/backend && python -m pytest -q` (or `python -m pytest -q` from repo root)
Expected: all passed, no regressions.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add /api/send-email and /api/send-all-emails endpoints"
```

---

### Task 4: Frontend `api.js` — three new functions

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Append to `api.test.js` (add `sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus` to the existing top-of-file import from `"./api"`):

```python
```
```javascript
describe("sendEmailAlert", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "sent", message_id: "brevo-1" }),
    });
    const result = await sendEmailAlert("CLT001");
    expect(result).toEqual({ status: "sent", message_id: "brevo-1" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-email/CLT001",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 400,
      json: async () => ({ detail: "This client has no valid email on file" }),
    });
    await expect(sendEmailAlert("CLT005")).rejects.toThrow("This client has no valid email on file");
  });
});

describe("sendAllEmailAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllEmailAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all-emails", { method: "POST", credentials: "include", headers: {} });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk email send is already in progress" }),
    });
    await expect(sendAllEmailAlerts()).rejects.toThrow("A bulk email send is already in progress");
  });
});

describe("getSendAllEmailsStatus", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ total: 5, sent: 2, skipped: 1, skipped_no_email: 0, failed: 0, done: false }),
    });
    const status = await getSendAllEmailsStatus("abc-123");
    expect(status).toEqual({ total: 5, sent: 2, skipped: 1, skipped_no_email: 0, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all-emails/status/abc-123", { credentials: "include", headers: {} });
  });
});
```

(Ignore the stray ```` ```python ```` fence above the JavaScript block — copy only the `describe(...)` blocks into `api.test.js`; that fence was a drafting artifact and must not appear in the actual file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js -t "sendEmailAlert|sendAllEmailAlerts|getSendAllEmailsStatus"`
Expected: FAIL — the three functions don't exist yet (`TypeError: sendEmailAlert is not a function` or similar).

- [ ] **Step 3: Add the three functions to `api.js`**

Add after the existing `getSendAllStatus` function:

```javascript
export async function sendEmailAlert(clientId) {
  const res = await fetch(`${API_BASE}/api/send-email/${clientId}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Send failed: ${res.status}`);
  }
  return data;
}

export async function sendAllEmailAlerts() {
  const res = await fetch(`${API_BASE}/api/send-all-emails`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}

export async function getSendAllEmailsStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/send-all-emails/status/${jobId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load send-all status: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: add sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus to api.js"
```

---

### Task 5: `SendConfirmModal.jsx` and `SendAllConfirmModal.jsx` — add a `channel` prop

**Files:**
- Modify: `dashboard-app/frontend/src/components/SendConfirmModal.jsx`
- Modify: `dashboard-app/frontend/src/components/SendConfirmModal.test.jsx`
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`

- [ ] **Step 1: Write the failing tests**

Both files were read in full while writing this plan. `SendConfirmModal.test.jsx` (47 lines) imports `{ describe, it, expect, vi } from "vitest"` and `{ render, screen, fireEvent } from "@testing-library/react"`, and every test calls `render(<SendConfirmModal client={{...}} onConfirm={...} onCancel={...} />)` directly (no wrapper helper). `SendAllConfirmModal.test.jsx` (130 lines, 10 existing tests covering the no-job, in-progress, done, error, and focus-trap states) uses the same imports and calls `render(<SendAllConfirmModal open={...} eligibleCount={...} onConfirm={...} onCancel={...} job={...} />)` directly. Add these cases to each, matching that exact style — no new helpers, no changes to existing tests:

`SendConfirmModal.test.jsx` — add:
```javascript
it("shows email-specific text when channel is 'email'", () => {
  render(
    <SendConfirmModal
      client={{ name: "Rahul Sharma", company: "TechCorp" }}
      channel="email"
      onConfirm={() => {}}
      onCancel={() => {}}
    />
  );
  expect(screen.getByText(/Send a renewal email/)).toBeInTheDocument();
});

it("defaults to WhatsApp text when channel is omitted", () => {
  render(
    <SendConfirmModal
      client={{ name: "Rahul Sharma", company: "TechCorp" }}
      onConfirm={() => {}}
      onCancel={() => {}}
    />
  );
  expect(screen.getByText(/Send a real WhatsApp renewal alert/)).toBeInTheDocument();
});
```

`SendAllConfirmModal.test.jsx` — add:
```javascript
it("shows email-specific text and a distinct testid when channel is 'email'", () => {
  render(
    <SendAllConfirmModal
      open={true}
      eligibleCount={5}
      channel="email"
      onConfirm={() => {}}
      onCancel={() => {}}
    />
  );
  expect(screen.getByText(/Send a renewal email to all/)).toBeInTheDocument();
  expect(screen.getByTestId("send-all-confirm-modal-email")).toBeInTheDocument();
});

it("defaults to WhatsApp text and testid when channel is omitted", () => {
  render(
    <SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />
  );
  expect(screen.getByText(/Send a real WhatsApp renewal alert to all/)).toBeInTheDocument();
  expect(screen.getByTestId("send-all-confirm-modal-whatsapp")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendConfirmModal.test.jsx src/components/SendAllConfirmModal.test.jsx`
Expected: FAIL — the new assertions don't match today's hardcoded WhatsApp-only text/testid.

- [ ] **Step 3: Update `SendConfirmModal.jsx`**

Current:
```javascript
export default function SendConfirmModal({ client, onConfirm, onCancel }) {
```

Replace with:
```javascript
export default function SendConfirmModal({ client, channel = "whatsapp", onConfirm, onCancel }) {
```

Current:
```javascript
        <p className="text-sm text-ink-secondary mb-6">
          Send a real WhatsApp renewal alert to <strong>{client.name}</strong> at{" "}
          <strong>{client.company}</strong>?
        </p>
```

Replace with:
```javascript
        <p className="text-sm text-ink-secondary mb-6">
          {channel === "email"
            ? <>Send a renewal email to <strong>{client.name}</strong> at <strong>{client.company}</strong>?</>
            : <>Send a real WhatsApp renewal alert to <strong>{client.name}</strong> at <strong>{client.company}</strong>?</>}
        </p>
```

- [ ] **Step 4: Update `SendAllConfirmModal.jsx`**

Current:
```javascript
export default function SendAllConfirmModal({ open, eligibleCount, onConfirm, onCancel, job = null }) {
```

Replace with:
```javascript
export default function SendAllConfirmModal({ open, eligibleCount, channel = "whatsapp", onConfirm, onCancel, job = null }) {
```

Current:
```javascript
      className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50"
      data-testid="send-all-confirm-modal"
```

Replace with:
```javascript
      className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50"
      data-testid={`send-all-confirm-modal-${channel}`}
```

Current:
```javascript
            <p className="text-sm text-ink-secondary mb-6">
              Send a real WhatsApp renewal alert to all <strong>{eligibleCount}</strong> eligible
              client{eligibleCount === 1 ? "" : "s"} (Critical, Urgent, Due Soon, or Expired, not yet sent today)?
            </p>
```

Replace with:
```javascript
            <p className="text-sm text-ink-secondary mb-6">
              {channel === "email" ? "Send a renewal email" : "Send a real WhatsApp renewal alert"} to all{" "}
              <strong>{eligibleCount}</strong> eligible client{eligibleCount === 1 ? "" : "s"} (Critical,
              Urgent, Due Soon, or Expired, not yet {channel === "email" ? "emailed" : "sent"} today)?
            </p>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendConfirmModal.test.jsx src/components/SendAllConfirmModal.test.jsx`
Expected: all passed, including every pre-existing test in both files (the default `channel = "whatsapp"` value means any test that doesn't pass a `channel` prop keeps seeing exactly today's WhatsApp text/testid — verify this holds for tests that reference `getByTestId("send-all-confirm-modal")` without a suffix; if any exist, they need updating to `"send-all-confirm-modal-whatsapp"` since the testid now always has a channel suffix, even for the default).

- [ ] **Step 6: Fix the two confirmed stale references in `App.test.jsx`, then run the full frontend suite**

`grep -rn "send-all-confirm-modal" dashboard-app/frontend/src` (run while drafting this plan, against the real current files) finds exactly two references to the old bare testid, both in `App.test.jsx`:

In `"does not send-all until the bulk confirmation modal is accepted"`, current:
```javascript
    expect(screen.getByTestId("send-all-confirm-modal")).toBeInTheDocument();
```
Replace with:
```javascript
    expect(screen.getByTestId("send-all-confirm-modal-whatsapp")).toBeInTheDocument();
```

In `"stops polling and shows an error toast if checking send-all status fails"`, current:
```javascript
    expect(screen.queryByTestId("send-all-confirm-modal")).not.toBeInTheDocument();
```
Replace with:
```javascript
    expect(screen.queryByTestId("send-all-confirm-modal-whatsapp")).not.toBeInTheDocument();
```

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed. Re-run `grep -rn "send-all-confirm-modal" dashboard-app/frontend/src` yourself before moving on, in case something changed between plan-writing and execution — it should now only match the component's own `data-testid={...}` template literal and these two now-corrected test lines (no more bare `"send-all-confirm-modal"` string literals).

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/frontend/src/components/SendConfirmModal.jsx dashboard-app/frontend/src/components/SendConfirmModal.test.jsx dashboard-app/frontend/src/components/SendAllConfirmModal.jsx dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx
git commit -m "feat: parameterize SendConfirmModal and SendAllConfirmModal with a channel prop"
```

---

### Task 6: `ClientTable.jsx` — "Send Email" button per row

**Files:**
- Modify: `dashboard-app/frontend/src/components/ClientTable.jsx`
- Modify: `dashboard-app/frontend/src/components/ClientTable.test.jsx`

- [ ] **Step 1: Write the failing tests**

The file's existing fixtures (verified against the real current file): a `pageOf(rows, total, page)` helper returning `{rows, total, page, page_size: 8}`, and a base `oneClient` object:

```javascript
const oneClient = {
  client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
  cert_name: "ISO 9001", cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL",
  alert_sent_today: false,
};
```

Every existing test's `render(<ClientTable ... />)` call passes `onSort`, `onPageChange`, `onSendClick`, `onSendSelected`, `onPreviewEmail` — none currently pass `onSendEmailClick` (it doesn't exist yet). Add these three tests to `ClientTable.test.jsx`, inside the existing `describe("ClientTable", ...)` block, following the exact prop-passing style already used by every other test in the file:

```javascript
it("shows a Send Email button for an alert-eligible client with a valid email", () => {
  render(
    <ClientTable
      page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
      onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
      onSendSelected={() => {}} onPreviewEmail={() => {}} onSendEmailClick={() => {}}
    />
  );
  expect(screen.getByText("Send Email")).toBeInTheDocument();
});

it("calls onSendEmailClick with the client when Send Email is clicked", () => {
  const onSendEmailClick = vi.fn();
  render(
    <ClientTable
      page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
      onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
      onSendSelected={() => {}} onPreviewEmail={() => {}} onSendEmailClick={onSendEmailClick}
    />
  );
  fireEvent.click(screen.getByText("Send Email"));
  expect(onSendEmailClick).toHaveBeenCalledWith(expect.objectContaining({ client_id: "CLT001" }));
});

it("disables Send Email with a title tooltip when the client has no valid email", () => {
  const noEmailClient = { ...oneClient, email: null };
  render(
    <ClientTable
      page={pageOf([noEmailClient])} loading={false} sortKey={null} sortAsc={true}
      onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
      onSendSelected={() => {}} onPreviewEmail={() => {}} onSendEmailClick={() => {}}
    />
  );
  const button = screen.getByText("Send Email").closest("button");
  expect(button).toBeDisabled();
  expect(button).toHaveAttribute("title", "No email on file");
});
```

Note: every *existing* test in this file must also keep passing after Task 6's Step 3 change, even though none of them pass `onSendEmailClick` — since the new "Send Email" button is only rendered for `ALERT_ELIGIBLE` statuses, and the click handler is only invoked on click (never during render), an existing test that never clicks "Send Email" and never passes `onSendEmailClick` will not crash on `undefined` — but the "Preview Email" test at status `"ACTIVE"` (not alert-eligible) proves the new button correctly does *not* render there either, since `ALERT_ELIGIBLE.has("ACTIVE")` is false.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ClientTable.test.jsx`
Expected: FAIL — "Send Email" doesn't exist yet.

- [ ] **Step 3: Update `ClientTable.jsx`**

Current function signature:
```javascript
export default function ClientTable({
  page, loading, sortKey, sortAsc, onSort, onPageChange,
  onSendClick, onSendSelected, onPreviewEmail, exportFilters = {},
}) {
```

Replace with:
```javascript
export default function ClientTable({
  page, loading, sortKey, sortAsc, onSort, onPageChange,
  onSendClick, onSendSelected, onPreviewEmail, onSendEmailClick, exportFilters = {},
}) {
```

Current action-column cell body:
```jsx
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    {!ALERT_ELIGIBLE.has(c.status) ? (
                      <span className="text-ink-muted">—</span>
                    ) : c.alert_sent_today ? (
                      <span className="px-3 py-1 rounded-full text-xs font-semibold border border-line bg-surface text-ink-primary">
                        ✅ Sent
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSendClick(c)}
                        className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
                      >
                        Send Alert
                      </button>
                    )}
                    {c.email && (
                      <button
                        type="button"
                        onClick={() => onPreviewEmail(c.client_id)}
                        className="text-xs font-semibold text-accent hover:underline"
                      >
                        Preview Email
                      </button>
                    )}
                  </div>
                </td>
```

Replace with:
```jsx
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {!ALERT_ELIGIBLE.has(c.status) ? (
                      <span className="text-ink-muted">—</span>
                    ) : c.alert_sent_today ? (
                      <span className="px-3 py-1 rounded-full text-xs font-semibold border border-line bg-surface text-ink-primary">
                        ✅ Sent
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSendClick(c)}
                        className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
                      >
                        Send Alert
                      </button>
                    )}
                    {ALERT_ELIGIBLE.has(c.status) && (
                      <button
                        type="button"
                        onClick={() => onSendEmailClick(c)}
                        disabled={!c.email || !c.email.includes("@")}
                        title={!c.email || !c.email.includes("@") ? "No email on file" : undefined}
                        className="px-3 py-1 rounded-full text-xs font-semibold border border-accent text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                      >
                        Send Email
                      </button>
                    )}
                    {c.email && (
                      <button
                        type="button"
                        onClick={() => onPreviewEmail(c.client_id)}
                        className="text-xs font-semibold text-accent hover:underline"
                      >
                        Preview Email
                      </button>
                    )}
                  </div>
                </td>
```

Note: unlike "Send Alert", "Send Email" does **not** have its own already-sent/deduped state shown inline (no `email_sent_today` field exists on the client row from `/api/clients` today, and adding one is out of this plan's scope per the spec — the 409 "already sent today" response on click is the only feedback for that case, matching how `onSendClick`'s underlying `sendAlert` call already surfaces its own 409 via the toast in `App.jsx`, not via a per-row visual state either... check this against the *actual* current behavior for WhatsApp's duplicate case before assuming it's fine to skip — if `alert_sent_today` inline styling is considered essential UX, that's a valid reason to widen this plan's scope, but the design spec didn't call for it, so it's deliberately omitted here).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ClientTable.test.jsx`
Expected: all passed.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed (check whether `App.test.jsx` renders `<ClientTable>` without an `onSendEmailClick` prop anywhere and now errors on undefined — if so, the App.jsx changes in Task 7 need to land in the same test run before this fully passes; it's acceptable for this task's own test run to show that specific `App.test.jsx` gap if Task 7 hasn't happened yet, as long as `ClientTable.test.jsx` itself is fully green).

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/frontend/src/components/ClientTable.jsx dashboard-app/frontend/src/components/ClientTable.test.jsx
git commit -m "feat: add Send Email button to ClientTable, disabled when no valid email"
```

---

### Task 7: `App.jsx` — wire per-client and bulk email sending

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Modify: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

The file's real current top-of-file fixtures (verified against the actual current file):

```javascript
const samplePage = (rows, total = rows.length, page = 1) => ({ rows, total, page, page_size: 50 });

const sampleClients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
    cert_name: "ISO 9001", cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL",
    alert_sent_today: false },
];

const sampleStats = {
  status_counts: { total: 1, CRITICAL: 1 },
  eligible_not_sent_today: 1,
  cert_types: ["ISO 9001"],
  renewals_by_month: [{ year_month: "2026-07", count: 1 }],
};

beforeEach(() => {
  vi.resetAllMocks();
  api.getClients.mockResolvedValue(samplePage(sampleClients));
  api.getStats.mockResolvedValue(sampleStats);
});
```

`sampleStats` has no `eligible_not_emailed_today` key, so until it's added, `eligibleEmailCount` (computed as `stats?.eligible_not_emailed_today || 0`) will be `0` for every *existing* test, correctly keeping the new "Send All Emails" button disabled in all of them (no existing test needs to touch it). The new tests below explicitly override `sampleStats` where they need the button enabled.

Add these tests to the `describe("App", ...)` block, immediately after the existing WhatsApp equivalents (`"sends and shows a success toast after confirming"`, `"sends all and shows a summary toast once the job finishes"`, `"stops polling and shows an error toast if checking send-all status fails"`), mirroring their exact structure:

```javascript
it("sends an email and shows a success toast after confirming", async () => {
  api.sendEmailAlert.mockResolvedValue({ status: "sent", message_id: "brevo-1" });
  render(<App />);
  await waitFor(() => screen.getByText("Send Email"));
  fireEvent.click(screen.getByText("Send Email"));
  fireEvent.click(screen.getByText("Confirm Send"));
  await waitFor(() => expect(api.sendEmailAlert).toHaveBeenCalledWith("CLT001"));
  await waitFor(() => expect(screen.getByText("Emailed Rahul Sharma")).toBeInTheDocument());
});

it("does not send-all-emails until the bulk email confirmation modal is accepted", async () => {
  api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
  render(<App />);
  await waitFor(() => screen.getByText("Send Email"));
  fireEvent.click(screen.getByText("Send All Emails"));
  expect(screen.getByTestId("send-all-confirm-modal-email")).toBeInTheDocument();
  expect(api.sendAllEmailAlerts).not.toHaveBeenCalled();
});

it("sends all emails and shows a summary toast once the job finishes", async () => {
  api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
  api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
  api.getSendAllEmailsStatus.mockResolvedValue({
    total: 1, sent: 1, skipped: 0, skipped_no_email: 0, failed: 0, done: true,
  });
  render(<App />);
  await waitFor(() => screen.getByText("Send Email"));
  fireEvent.click(screen.getByText("Send All Emails"));
  fireEvent.click(screen.getByText("Confirm Send All"));
  await waitFor(() => expect(api.sendAllEmailAlerts).toHaveBeenCalled());
  await waitFor(() => expect(api.getSendAllEmailsStatus).toHaveBeenCalledWith("job-1"));
  await waitFor(() => expect(screen.getByText(/1 sent, 0 skipped, 0 failed/)).toBeInTheDocument());
});

it("stops polling and shows an error toast if checking send-all-emails status fails", async () => {
  api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
  api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
  api.getSendAllEmailsStatus.mockRejectedValue(new Error("Network error"));
  render(<App />);
  await waitFor(() => screen.getByText("Send Email"));
  fireEvent.click(screen.getByText("Send All Emails"));
  fireEvent.click(screen.getByText("Confirm Send All"));
  await waitFor(() => expect(api.getSendAllEmailsStatus).toHaveBeenCalledWith("job-1"));
  await waitFor(() => expect(screen.getByText("Network error")).toBeInTheDocument());
  expect(screen.queryByTestId("send-all-confirm-modal-email")).not.toBeInTheDocument();
  const callsAfterError = api.getSendAllEmailsStatus.mock.calls.length;
  await new Promise((resolve) => setTimeout(resolve, 700));
  expect(api.getSendAllEmailsStatus.mock.calls.length).toBe(callsAfterError);
});
```

The last test directly verifies Task 7's `handleConfirmSendAllEmails` has the same try/catch-and-clear-interval structure as the existing WhatsApp `handleConfirmSendAll` from the start (that structure was itself added to the WhatsApp version in an earlier review-driven fix, not present in its first draft — the email version must not repeat that gap).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: FAIL — `sendEmailAlert`/`sendAllEmailAlerts`/`getSendAllEmailsStatus` aren't wired into `App.jsx` yet, no "Send All Emails" button exists.

- [ ] **Step 3: Update `App.jsx`**

Update the import block — current:
```javascript
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
} from "./api";
```

Replace with:
```javascript
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus,
} from "./api";
```

Add new state, right after the existing `const [previewClientId, setPreviewClientId] = useState(null);` line:
```javascript
  const [pendingEmailClient, setPendingEmailClient] = useState(null);
  const [emailBulkModalOpen, setEmailBulkModalOpen] = useState(false);
  const [sendAllEmailJob, setSendAllEmailJob] = useState(null);
```

Add new handlers, right after the existing `handleConfirmSend` function:
```javascript
  async function handleConfirmSendEmail() {
    const client = pendingEmailClient;
    setPendingEmailClient(null);
    try {
      await sendEmailAlert(client.client_id);
      setToast({ type: "success", message: `Emailed ${client.name}` });
      loadClients();
      loadStats();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    }
  }
```

Add, right after the existing `handleCloseSendAllModal` function:
```javascript
  const eligibleEmailCount = stats?.eligible_not_emailed_today || 0;
  const emailJobPollRef = useRef(null);

  useEffect(() => {
    return () => {
      if (emailJobPollRef.current) clearInterval(emailJobPollRef.current);
    };
  }, []);

  async function handleConfirmSendAllEmails() {
    try {
      const { job_id: jobId } = await sendAllEmailAlerts();
      setSendAllEmailJob({ total: 0, sent: 0, skipped: 0, skipped_no_email: 0, failed: 0, done: false });
      emailJobPollRef.current = setInterval(async () => {
        try {
          const status = await getSendAllEmailsStatus(jobId);
          setSendAllEmailJob(status);
          if (status.done) {
            clearInterval(emailJobPollRef.current);
            loadClients();
            loadStats();
          }
        } catch (err) {
          clearInterval(emailJobPollRef.current);
          setSendAllEmailJob(null);
          setEmailBulkModalOpen(false);
          setToast({ type: "error", message: err.message });
        }
      }, 500);
    } catch (err) {
      setEmailBulkModalOpen(false);
      setToast({ type: "error", message: err.message });
    }
  }

  function handleCloseSendAllEmailsModal() {
    if (emailJobPollRef.current) clearInterval(emailJobPollRef.current);
    setSendAllEmailJob(null);
    setEmailBulkModalOpen(false);
  }
```

Update the header's button area — current:
```jsx
            {activeView === "clientData" && (
              <button
                type="button"
                onClick={() => setBulkModalOpen(true)}
                disabled={(sendAllJob !== null && !sendAllJob.done) || eligibleCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Send All Eligible
              </button>
            )}
```

Replace with:
```jsx
            {activeView === "clientData" && (
              <button
                type="button"
                onClick={() => setBulkModalOpen(true)}
                disabled={(sendAllJob !== null && !sendAllJob.done) || eligibleCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Send All Eligible
              </button>
            )}
            {activeView === "clientData" && (
              <button
                type="button"
                onClick={() => setEmailBulkModalOpen(true)}
                disabled={(sendAllEmailJob !== null && !sendAllEmailJob.done) || eligibleEmailCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/10 transition-colors disabled:opacity-50"
              >
                Send All Emails
              </button>
            )}
```

Update the `<ClientTable>` usage — current:
```jsx
              <ClientTable
                page={page}
                loading={clientsLoading}
                sortKey={sortKey}
                sortAsc={sortAsc}
                onSort={handleSort}
                onPageChange={setPageNum}
                onSendClick={setPendingClient}
                onSendSelected={bulkSelectedSending ? () => {} : setPendingSelected}
                onPreviewEmail={setPreviewClientId}
                exportFilters={{ status: activeStatus, certType, expiryBefore, search: debouncedSearch }}
              />
```

Replace with:
```jsx
              <ClientTable
                page={page}
                loading={clientsLoading}
                sortKey={sortKey}
                sortAsc={sortAsc}
                onSort={handleSort}
                onPageChange={setPageNum}
                onSendClick={setPendingClient}
                onSendSelected={bulkSelectedSending ? () => {} : setPendingSelected}
                onPreviewEmail={setPreviewClientId}
                onSendEmailClick={setPendingEmailClient}
                exportFilters={{ status: activeStatus, certType, expiryBefore, search: debouncedSearch }}
              />
```

Update the modal-rendering block near the bottom — current:
```jsx
      <SendConfirmModal
        client={pendingClient}
        onConfirm={handleConfirmSend}
        onCancel={() => setPendingClient(null)}
      />
      <SendAllConfirmModal
        open={bulkModalOpen}
        eligibleCount={eligibleCount}
        job={sendAllJob}
        onConfirm={handleConfirmSendAll}
        onCancel={sendAllJob ? handleCloseSendAllModal : () => setBulkModalOpen(false)}
      />
```

Replace with:
```jsx
      <SendConfirmModal
        client={pendingClient}
        channel="whatsapp"
        onConfirm={handleConfirmSend}
        onCancel={() => setPendingClient(null)}
      />
      <SendAllConfirmModal
        open={bulkModalOpen}
        eligibleCount={eligibleCount}
        channel="whatsapp"
        job={sendAllJob}
        onConfirm={handleConfirmSendAll}
        onCancel={sendAllJob ? handleCloseSendAllModal : () => setBulkModalOpen(false)}
      />
      <SendConfirmModal
        client={pendingEmailClient}
        channel="email"
        onConfirm={handleConfirmSendEmail}
        onCancel={() => setPendingEmailClient(null)}
      />
      <SendAllConfirmModal
        open={emailBulkModalOpen}
        eligibleCount={eligibleEmailCount}
        channel="email"
        job={sendAllEmailJob}
        onConfirm={handleConfirmSendAllEmails}
        onCancel={sendAllEmailJob ? handleCloseSendAllEmailsModal : () => setEmailBulkModalOpen(false)}
      />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: all passed.

- [ ] **Step 5: Run the full frontend suite, lint, and production build**

Run: `cd dashboard-app/frontend && npx vitest run && npx oxlint src/App.jsx src/App.test.jsx && npm run build`
Expected: all tests passed, lint clean, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "feat: wire per-client and bulk email sending into App.jsx"
```

---

### Task 8: Document `DASHBOARD_TEST_EMAIL`

**Files:**
- Modify: `.env.example`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Update `.env.example`**

Add, near the existing `DASHBOARD_TEST_NUMBER`-equivalent line if one exists there already (check — if `DASHBOARD_TEST_NUMBER` was never actually added to `.env.example` despite being used in code, add both together for consistency; don't assume one exists without checking):

```
# Optional -- redirects all real WhatsApp/email sends to a single verified
# test recipient instead of real clients. Leave unset for real sends.
DASHBOARD_TEST_NUMBER=
DASHBOARD_TEST_EMAIL=
```

- [ ] **Step 2: Update `docs/DEPLOYMENT.md`**

Find the existing warning in the "Verify end to end" section:
```
4. **Do not** test "Send Alert" / "Send All Eligible" against this deployment
   unless `DASHBOARD_TEST_NUMBER` is also set on Render to a verified test
   number — otherwise a test click sends a real WhatsApp message to a real
   client.
```

Replace with:
```
4. **Do not** test "Send Alert" / "Send All Eligible" (WhatsApp) or "Send
   Email" / "Send All Emails" against this deployment unless
   `DASHBOARD_TEST_NUMBER` / `DASHBOARD_TEST_EMAIL` are also set on Render to
   a verified test number/address — otherwise a test click sends a real
   message to a real client.
```

- [ ] **Step 3: Commit**

```bash
git add .env.example docs/DEPLOYMENT.md
git commit -m "docs: document DASHBOARD_TEST_EMAIL alongside the existing WhatsApp test-number safeguard"
```

---

### Task 9: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `python -m pytest -q` (from the repo root)
Expected: all passed.

- [ ] **Step 2: Run the full frontend test suite and production build**

Run: `cd dashboard-app/frontend && npx vitest run && npm run build`
Expected: all passed, build succeeds.

- [ ] **Step 3: Manual smoke test against real (or a safe copy of) data, locally**

Start both dev servers. With `DASHBOARD_TEST_EMAIL` set locally to a real inbox you control (never a real client's), and `BREVO_API_KEY`/`EMAIL_SENDER` set to real values in `.env`:
- Click "Send Email" on one alert-eligible client with a valid email address — confirm the confirm modal shows email-specific text, confirm the send, and check the test inbox actually receives the email (correct subject, logo renders if `company-logo.png` exists, content matches the same template the "Preview Email" link already shows).
- Click "Send Email" on a client with no email — confirm the button is disabled with a "No email on file" tooltip, not clickable.
- Click "Send All Emails" — confirm the progress UI updates, confirm the job completes, confirm the summary counts (sent/skipped/skipped_no_email/failed) look sane against the real data (recall: only 8 of 11,122 alert-eligible clients currently have a missing/invalid email, so `skipped_no_email` should be a small number, not near-total).
- Confirm sending an email for a client does **not** affect that same client's WhatsApp "Send Alert" button state (independent dedup, per the design's core goal).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify email alerts end-to-end"
```
