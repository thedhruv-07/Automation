# Multi-Scheme Import + Duration Filter + Filtered Bulk Send Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the dashboard scope bulk WhatsApp/email sends to whatever's currently filtered (cert type, expiry window, status), add quick duration-preset buttons (3 months / 6 months / 1 year) to the expiry filter, and turn the existing BIS-ISI-only import path into a pluggable per-scheme registry so FMCS/CRS parsers can be added later without touching the upload endpoints.

**Architecture:** A new `db.get_eligible_clients()`/`get_eligible_count()` pair (built on a shared `_client_filters_where()` helper already implied by `get_clients_page`'s existing filter logic) lets `run()`/`run_email_alerts()` and two new/changed FastAPI endpoints (`/api/eligible-count`, filtered `/api/send-all` and `/api/send-all-emails`) all filter by the same status/cert_type/expiry_before axes the table already supports. Separately, `import_bis_isi_data.py`'s five generic helpers move into a new `import_helpers.py`, and a new `import_formats.py` registers `(name, detector, importer)` tuples that both upload endpoints loop over instead of hardcoding BIS ISI. On the frontend, `SendAllConfirmModal` gains a scope radio choice (all vs. currently filtered) fed by the new endpoint, and `ClientDataFilters` gains three preset buttons that compute a date and reuse the existing "Expiry before" filter.

**Tech Stack:** Python/FastAPI/SQLite (`dashboard-app/backend/`), React/Vite (`dashboard-app/frontend/`), pytest, Vitest + React Testing Library.

---

### Task 1: `db.py` — shared filter helper, `get_eligible_clients`, `get_eligible_count`

**Files:**
- Modify: `dashboard-app/backend/db.py`
- Test: `dashboard-app/backend/test_db.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_db.py`, right after the existing `test_get_stats_eligible_not_emailed_today_excludes_already_emailed` test (end of file) — these use the existing `FIVE_ROWS`/`_seeded_db` fixtures already defined earlier in the file:

```python
from db import get_eligible_clients, get_eligible_count


def test_get_eligible_clients_excludes_active_by_default(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path)
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT002", "CLT003", "CLT005"}


def test_get_eligible_clients_preserves_insertion_order(tmp_path):
    """run()/run_email_alerts() depend on this order matching read_clients()'s
    order exactly -- see whatsapp_renewal_alerts.py's order-sensitive tests
    (e.g. test_run_mixed_outcomes_in_single_call_preserves_earlier_successes)."""
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path)
    assert [r["client_id"] for r in rows] == ["CLT001", "CLT002", "CLT003", "CLT005"]


def test_get_eligible_clients_filters_by_cert_type(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path, cert_type="ISO 9001")
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


def test_get_eligible_clients_filters_by_expiry_before(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path, expiry_before="2026-08-01")
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT005"}


def test_get_eligible_clients_status_filter_narrows_within_alert_eligible_set(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path, status="CRITICAL")
    assert {r["client_id"] for r in rows} == {"CLT001"}


def test_get_eligible_clients_status_active_returns_empty(tmp_path):
    """ACTIVE is never alert-eligible, so filtering to it must yield nothing --
    the alert-eligibility restriction and the status filter are AND'ed
    together, not one replacing the other."""
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path, status="ACTIVE")
    assert rows == []


def test_get_eligible_count_counts_all_eligible_not_sent_today(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp") == 4


def test_get_eligible_count_excludes_already_sent_today(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp") == 3


def test_get_eligible_count_email_channel_is_independent_of_whatsapp(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp") == 3
    assert get_eligible_count(db_path, today="2026-07-21", channel="email") == 4


def test_get_eligible_count_filters_by_cert_type(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp", cert_type="ISO 9001") == 2


def test_get_eligible_count_status_active_returns_zero(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp", status="ACTIVE") == 0


def test_get_eligible_count_rejects_unknown_channel(tmp_path):
    db_path = _seeded_db(tmp_path)
    with pytest.raises(ValueError):
        get_eligible_count(db_path, today="2026-07-21", channel="carrier-pigeon")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_eligible_clients'` (and `get_eligible_count`).

- [ ] **Step 3: Add `_client_filters_where`, refactor `get_clients_page`/`export_clients_rows` to use it, and add `ALERT_STATUSES`**

In `db.py`, current (just before `def get_clients_page`):

```python
_SORTABLE_COLUMNS = {
    "client_id", "name", "company", "cert_name", "cert_id", "status",
}


def get_clients_page(
```

Replace with:

```python
_SORTABLE_COLUMNS = {
    "client_id", "name", "company", "cert_name", "cert_id", "status",
}

ALERT_STATUSES = ("CRITICAL", "URGENT", "DUE SOON", "EXPIRED")


def _client_filters_where(
    status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
) -> tuple[list[str], list]:
    """Builds the WHERE-clause fragments and bound params shared by
    get_clients_page, export_clients_rows, get_eligible_clients, and
    get_eligible_count -- so "currently filtered view" always means the
    same thing everywhere it's used."""
    where = []
    params: list = []
    if status and status != "ALL":
        where.append("status = ?")
        params.append(status)
    if cert_type and cert_type != "ALL":
        where.append("cert_name = ?")
        params.append(cert_type)
    if expiry_before:
        where.append("expiry_date_iso <= ?")
        params.append(expiry_before)
    if search:
        where.append("(name LIKE ? OR company LIKE ?)")
        like_term = f"%{search}%"
        params.extend([like_term, like_term])
    return where, params


def get_clients_page(
```

Current `get_clients_page` body (the WHERE-building block):

```python
    conn = get_connection(db_path)
    try:
        where = []
        params: list = []
        if status and status != "ALL":
            where.append("status = ?")
            params.append(status)
        if cert_type and cert_type != "ALL":
            where.append("cert_name = ?")
            params.append(cert_type)
        if expiry_before:
            where.append("expiry_date_iso <= ?")
            params.append(expiry_before)
        if search:
            where.append("(name LIKE ? OR company LIKE ?)")
            like_term = f"%{search}%"
            params.extend([like_term, like_term])
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(f"SELECT COUNT(*) FROM clients {where_clause}", params).fetchone()[0]
```

Replace with:

```python
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(f"SELECT COUNT(*) FROM clients {where_clause}", params).fetchone()[0]
```

Current `export_clients_rows` body (the identical duplicated WHERE-building block):

```python
    conn = get_connection(db_path)
    try:
        where = []
        params: list = []
        if status and status != "ALL":
            where.append("status = ?")
            params.append(status)
        if cert_type and cert_type != "ALL":
            where.append("cert_name = ?")
            params.append(cert_type)
        if expiry_before:
            where.append("expiry_date_iso <= ?")
            params.append(expiry_before)
        if search:
            where.append("(name LIKE ? OR company LIKE ?)")
            like_term = f"%{search}%"
            params.extend([like_term, like_term])
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        cursor = conn.execute(f"SELECT {', '.join(RECORD_FIELDS)} FROM clients {where_clause}", params)
```

Replace with:

```python
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        cursor = conn.execute(f"SELECT {', '.join(RECORD_FIELDS)} FROM clients {where_clause}", params)
```

- [ ] **Step 4: Refactor `get_stats` to reuse the new `ALERT_STATUSES` constant**

Current, inside `get_stats`:

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

Replace with (only the local `alert_statuses = (...)` line changes, to `ALERT_STATUSES`):

```python
        placeholders = ", ".join(["?"] * len(ALERT_STATUSES))
        eligible_not_sent = conn.execute(
            f"""
            SELECT COUNT(*) FROM clients c
            WHERE c.status IN ({placeholders})
            AND NOT EXISTS (
                SELECT 1 FROM sent_log s
                WHERE s.client_id = c.client_id AND s.status = c.status AND s.sent_date = ?
            )
            """,
            (*ALERT_STATUSES, today),
        ).fetchone()[0]

        eligible_not_emailed = conn.execute(
            f"""
            SELECT COUNT(*) FROM clients c
            WHERE c.status IN ({placeholders})
            AND NOT EXISTS (
                SELECT 1 FROM email_sent_log s
                WHERE s.client_id = c.client_id AND s.status = c.status AND s.sent_date = ?
            )
            """,
            (*ALERT_STATUSES, today),
        ).fetchone()[0]
```

- [ ] **Step 5: Add `get_eligible_clients` and `get_eligible_count`**

Add these two functions right after `export_clients_rows` (before `def record_sent`):

```python
def get_eligible_clients(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None,
) -> list[dict]:
    """Alert-eligible (status in ALERT_STATUSES) client records, optionally
    further narrowed by the same status/cert_type/expiry_before filters
    get_clients_page's table view supports -- so bulk-send scope can mirror
    exactly what's on screen. ORDER BY rowid pins insertion order regardless
    of which index SQLite's query planner picks for the WHERE clause, so
    callers that depend on result order (run()'s existing tests) see the
    same order read_clients() always gave them."""
    conn = get_connection(db_path)
    try:
        extra_where, extra_params = _client_filters_where(status, cert_type, expiry_before)
        placeholders = ", ".join(["?"] * len(ALERT_STATUSES))
        where = [f"status IN ({placeholders})"] + extra_where
        params = list(ALERT_STATUSES) + extra_params
        rows = conn.execute(
            f"SELECT {', '.join(RECORD_FIELDS)} FROM clients WHERE {' AND '.join(where)} ORDER BY rowid",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_eligible_count(
    db_path, today: str, channel: str, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
) -> int:
    """Counts alert-eligible clients not yet sent today via the given channel
    ('whatsapp' -> sent_log, 'email' -> email_sent_log), optionally narrowed
    by status/cert_type/expiry_before -- used to show a live count for the
    "currently filtered view" bulk-send scope before anything is sent."""
    if channel not in ("whatsapp", "email"):
        raise ValueError(f"Unknown channel: {channel!r}")
    log_table = "sent_log" if channel == "whatsapp" else "email_sent_log"
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        extra_where, extra_params = _client_filters_where(status, cert_type, expiry_before)
        placeholders = ", ".join(["?"] * len(ALERT_STATUSES))
        where = [f"c.status IN ({placeholders})"] + extra_where
        params = list(ALERT_STATUSES) + extra_params
        count = conn.execute(
            f"""
            SELECT COUNT(*) FROM clients c
            WHERE {' AND '.join(where)}
            AND NOT EXISTS (
                SELECT 1 FROM {log_table} s
                WHERE s.client_id = c.client_id AND s.status = c.status AND s.sent_date = ?
            )
            """,
            params + [today],
        ).fetchone()[0]
        return count
    finally:
        conn.close()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: all passed, including every pre-existing test in the file (the refactor of `get_clients_page`/`export_clients_rows`/`get_stats` must not change their behavior — only how the WHERE clause is built internally).

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/test_db.py
git commit -m "feat: add get_eligible_clients/get_eligible_count with a shared filter helper"
```

---

### Task 2: `whatsapp_renewal_alerts.py` — `run()` accepts status/cert_type/expiry_before

**Files:**
- Modify: `dashboard-app/backend/whatsapp_renewal_alerts.py`
- Test: `dashboard-app/backend/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Write the failing test**

Add to `test_whatsapp_renewal_alerts.py`, right after `test_run_mixed_outcomes_in_single_call_preserves_earlier_successes` (uses the same `_write_db` helper and `Mock` import already present in the file):

```python
def test_run_filters_by_cert_type(tmp_path):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn, cert_type="OSHA")

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py::test_run_filters_by_cert_type -v`
Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'cert_type'`.

- [ ] **Step 3: Update `run()`**

Current (top of file):

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, read_clients, find_client_by_id, load_sent_log, save_sent_log,
    RECORD_FIELDS,
)
```

Replace with:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, read_clients, find_client_by_id, load_sent_log, save_sent_log,
    RECORD_FIELDS, get_eligible_clients,
)
```

Current `run()` signature and first two body lines:

```python
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
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = filter_alertable(read_clients(db_path))
```

Replace with:

```python
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
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(db_path, status=status, cert_type=cert_type, expiry_before=expiry_before)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: all passed, including every pre-existing `test_run_*` test (calling `run()` with no filter kwargs must behave exactly as before).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/whatsapp_renewal_alerts.py dashboard-app/backend/test_whatsapp_renewal_alerts.py
git commit -m "feat: run() accepts optional status/cert_type/expiry_before filters"
```

---

### Task 3: `email_alerts.py` — `run_email_alerts()` accepts the same filters

**Files:**
- Modify: `dashboard-app/backend/email_alerts.py`
- Test: `dashboard-app/backend/test_email_alerts.py`

- [ ] **Step 1: Write the failing test**

Add to `test_email_alerts.py`, right after `test_run_email_alerts_processes_all_alert_eligible_clients` (uses the existing `ROW_WITH_EMAIL`/`ROW_NO_EMAIL` fixtures and `upsert_clients` import already present in the file):

```python
def test_run_email_alerts_filters_by_cert_type(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_WITH_EMAIL, ROW_NO_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn, cert_type="OSHA",
    )

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"
    assert results[0]["action"] == "skipped_no_email"  # ROW_NO_EMAIL has no email on file
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py::test_run_email_alerts_filters_by_cert_type -v`
Expected: FAIL with `TypeError: run_email_alerts() got an unexpected keyword argument 'cert_type'`.

- [ ] **Step 3: Update `run_email_alerts()`**

Current (top of file):

```python
from db import read_clients, load_email_sent_log, save_email_sent_log
from email_template import build_email_html
from whatsapp_renewal_alerts import dedup_key, filter_alertable
```

Replace with (drops `read_clients`/`filter_alertable`, both now unused in this file since the only call site is being replaced below):

```python
from db import get_eligible_clients, load_email_sent_log, save_email_sent_log
from email_template import build_email_html
from whatsapp_renewal_alerts import dedup_key
```

Current `run_email_alerts()` signature and first two body lines:

```python
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
```

Replace with:

```python
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
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(db_path, status=status, cert_type=cert_type, expiry_before=expiry_before)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/email_alerts.py dashboard-app/backend/test_email_alerts.py
git commit -m "feat: run_email_alerts() accepts optional status/cert_type/expiry_before filters"
```

---

### Task 4: `main.py` — `/api/eligible-count` endpoint and filtered `/api/send-all`(-emails)

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Test: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`, right after `test_get_stats_returns_counts_and_cert_types` (uses the existing `_write_db`/`main_module`/`record_sent` already imported at the top of the file):

```python
def test_eligible_count_returns_both_channels(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/eligible-count")
    assert response.status_code == 200
    assert response.json() == {"whatsapp": 2, "email": 2}


def test_eligible_count_filters_by_cert_type(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/eligible-count", params={"cert_type": "OSHA"})
    assert response.json() == {"whatsapp": 1, "email": 1}


def test_eligible_count_excludes_already_sent_today(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-18", "wamid.ABC", "919876543210", "2026-07-18T10:00:00")
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/eligible-count")
    assert response.json() == {"whatsapp": 0, "email": 1}


def test_send_all_respects_cert_type_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all", params={"cert_type": "OSHA"})
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/send-all/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["total"] == 1
    assert final["sent"] == 1


def test_send_all_emails_respects_cert_type_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("EMAIL_SENDER", "sender@x.com")
    monkeypatch.delenv("DASHBOARD_TEST_EMAIL", raising=False)

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messageId": "brevo-1"},
    })()
    with patch("email_alerts.requests.post", return_value=mock_response):
        start_response = client.post("/api/send-all-emails", params={"cert_type": "OSHA"})
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
    assert final["total"] == 1
    assert final["sent"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k "eligible_count or respects_cert_type" -v`
Expected: FAIL — `/api/eligible-count` returns 404 (route doesn't exist yet), and the two `respects_cert_type` tests fail because `cert_type` is silently ignored by the current endpoints (both CLT001 and CLT002 get sent, `total` is 2 not 1).

- [ ] **Step 3: Add `get_eligible_count` to the `db` import**

Current (top of `main.py`):

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
)
```

Replace with:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
    get_eligible_count,
)
```

- [ ] **Step 4: Add the `/api/eligible-count` endpoint**

Add right after the existing `/api/stats` endpoint:

```python
@app.get("/api/eligible-count", dependencies=[Depends(require_auth)])
def eligible_count(status: str = "", cert_type: str = "", expiry_before: str = ""):
    today = _today_str()
    return {
        "whatsapp": get_eligible_count(
            DEFAULT_DB_PATH, today, "whatsapp",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
        ),
        "email": get_eligible_count(
            DEFAULT_DB_PATH, today, "email",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
        ),
    }
```

- [ ] **Step 5: Thread filters through `/api/send-all` and its job runner**

Current:

```python
def _run_send_all_job(job_id, token, phone_number_id, template_name, template_lang, test_number):
    def progress(result, total):
        job = _send_all_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        run(
            DEFAULT_DB_PATH, token, phone_number_id, template_name, template_lang,
            dry_run=False, test_number=test_number, on_progress=progress,
        )
    except Exception as exc:
```

Replace with:

```python
def _run_send_all_job(
    job_id, token, phone_number_id, template_name, template_lang, test_number,
    status=None, cert_type=None, expiry_before=None,
):
    def progress(result, total):
        job = _send_all_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        run(
            DEFAULT_DB_PATH, token, phone_number_id, template_name, template_lang,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before,
        )
    except Exception as exc:
```

Current:

```python
@app.post("/api/send-all", dependencies=[Depends(require_auth)])
def send_all_alerts():
    global _bulk_in_progress
    with _send_lock:
        if _bulk_in_progress:
            raise HTTPException(status_code=409, detail="A bulk send is already in progress")
        if _pending_sends:
            raise HTTPException(
                status_code=409,
                detail="One or more per-client sends are in progress; try again shortly",
            )
        _bulk_in_progress = True

    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        job_id = str(uuid.uuid4())
        _send_all_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "failed": 0, "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(job_id, token, phone_number_id, template_name, template_lang, test_number),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        with _send_lock:
            _bulk_in_progress = False
        raise HTTPException(status_code=500, detail="Server is not configured to send WhatsApp messages")
```

Replace with:

```python
@app.post("/api/send-all", dependencies=[Depends(require_auth)])
def send_all_alerts(status: str = "", cert_type: str = "", expiry_before: str = ""):
    global _bulk_in_progress
    with _send_lock:
        if _bulk_in_progress:
            raise HTTPException(status_code=409, detail="A bulk send is already in progress")
        if _pending_sends:
            raise HTTPException(
                status_code=409,
                detail="One or more per-client sends are in progress; try again shortly",
            )
        _bulk_in_progress = True

    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        job_id = str(uuid.uuid4())
        _send_all_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "failed": 0, "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(
                job_id, token, phone_number_id, template_name, template_lang, test_number,
                status or None, cert_type or None, expiry_before or None,
            ),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        with _send_lock:
            _bulk_in_progress = False
        raise HTTPException(status_code=500, detail="Server is not configured to send WhatsApp messages")
```

- [ ] **Step 6: Thread filters through `/api/send-all-emails` and its job runner**

Current:

```python
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
```

Replace with:

```python
def _run_send_all_email_job(
    job_id, brevo_api_key, email_sender, test_email,
    status=None, cert_type=None, expiry_before=None,
):
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
            status=status, cert_type=cert_type, expiry_before=expiry_before,
        )
    except Exception as exc:
```

Current:

```python
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
```

Replace with:

```python
@app.post("/api/send-all-emails", dependencies=[Depends(require_auth)])
def send_all_emails(status: str = "", cert_type: str = "", expiry_before: str = ""):
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
            args=(
                job_id, brevo_api_key, email_sender, test_email,
                status or None, cert_type or None, expiry_before or None,
            ),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        with _email_send_lock:
            _email_bulk_in_progress = False
        raise HTTPException(status_code=500, detail="Server is not configured to send emails")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed, including every pre-existing `test_send_all*` test (calling either endpoint with no query params must behave exactly as before).

- [ ] **Step 8: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add /api/eligible-count and filter /api/send-all(-emails) by status/cert_type/expiry_before"
```

---

### Task 5: Extract generic import helpers into `import_helpers.py`

**Files:**
- Create: `dashboard-app/backend/import_helpers.py`
- Modify: `dashboard-app/backend/import_bis_isi_data.py`
- Test: `dashboard-app/backend/test_import_bis_isi_data.py` (no changes expected — this task must not require any)

This is a pure relocation: `import_bis_isi_data.py`'s five generic helpers (`RowCollector`, `parse_validity_date`, `compute_status`, `header_index_map`, `get`) move into a new shared file, unchanged. `import_bis_isi_data.py` re-imports them by name, so its own public API (and every existing importer of it — `main.py` and `test_import_bis_isi_data.py`) needs no changes at all.

- [ ] **Step 1: Create `import_helpers.py`**

```python
"""Generic helpers shared by every per-scheme importer (import_bis_isi_data.py
and future ones like import_fmcs.py/import_crs.py) -- none of this is specific
to any one certification scheme's raw export format."""
from datetime import datetime


class RowCollector:
    """Drop-in stand-in for an openpyxl worksheet's .append() -- lets an
    importer collect rows into a plain list instead of writing to a real
    worksheet, for callers that want the converted rows in memory (e.g. to
    merge with existing data) rather than a saved file."""

    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(tuple(row))


SOURCE_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")


def parse_validity_date(value):
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    for fmt in SOURCE_DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def compute_status(expiry_dt, today=None):
    today = today or datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    days_left = (expiry_dt - today).days
    if days_left < 0:
        return "EXPIRED"
    if days_left <= 7:
        return "CRITICAL"
    if days_left <= 30:
        return "URGENT"
    if days_left <= 60:
        return "DUE SOON"
    return "ACTIVE"


def header_index_map(header_row):
    index_by_name = {}
    for i, name in enumerate(header_row):
        if name is None:
            continue
        index_by_name[str(name).strip().lower()] = i
    return index_by_name


def get(row, index_map, *names):
    for name in names:
        idx = index_map.get(name.lower())
        if idx is not None and idx < len(row):
            return row[idx]
    return None
```

- [ ] **Step 2: Replace the moved definitions in `import_bis_isi_data.py` with an import**

Current (top of file through the `get()` function, i.e. everything before `def looks_like_bis_isi_workbook`):

```python
"""One-off importer: converts a BIS ISI license register export into
clients_certifications.xlsx's single-sheet client roster schema.

Source sheets vary slightly in column set/order, so columns are looked up by
header name per sheet rather than by fixed position. Fields with no source
equivalent (Phone, Issue Date, Renewal Link) are left blank. Certification
Name is taken from each row's "Standard" column when the sheet has one (the
current single-sheet-with-all-standards-mixed template); if a sheet has no
"Standard" column at all -- the older one-sheet-per-standard layout -- or a
given row's Standard cell is blank, the sheet name is used instead (e.g.
"IS 269"), matching the original behavior. Certification ID and Client ID
both use the license number, since a license number is the natural unique
key in this dataset. Status is recomputed from Validity Date using this
project's own urgency thresholds -- the source "Status" column
(Operative/Cancelled/etc.) means something different and is not used.

Usage: python import_bis_isi_data.py "<path to source xlsx>"
"""
import sys
from datetime import datetime
from pathlib import Path

import openpyxl


class RowCollector:
    """Drop-in stand-in for an openpyxl worksheet's .append() — lets
    import_bis_isi_workbook() collect rows into a plain list instead of
    writing to a real worksheet, for callers that want the converted rows
    in memory (e.g. to merge with existing data) rather than a saved file."""

    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(tuple(row))

OUTPUT_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]

SOURCE_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")


def parse_validity_date(value):
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    for fmt in SOURCE_DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def compute_status(expiry_dt, today=None):
    today = today or datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    days_left = (expiry_dt - today).days
    if days_left < 0:
        return "EXPIRED"
    if days_left <= 7:
        return "CRITICAL"
    if days_left <= 30:
        return "URGENT"
    if days_left <= 60:
        return "DUE SOON"
    return "ACTIVE"


def header_index_map(header_row):
    index_by_name = {}
    for i, name in enumerate(header_row):
        if name is None:
            continue
        index_by_name[str(name).strip().lower()] = i
    return index_by_name


def get(row, index_map, *names):
    for name in names:
        idx = index_map.get(name.lower())
        if idx is not None and idx < len(row):
            return row[idx]
    return None
```

Replace with:

```python
"""One-off importer: converts a BIS ISI license register export into
clients_certifications.xlsx's single-sheet client roster schema.

Source sheets vary slightly in column set/order, so columns are looked up by
header name per sheet rather than by fixed position. Fields with no source
equivalent (Phone, Issue Date, Renewal Link) are left blank. Certification
Name is taken from each row's "Standard" column when the sheet has one (the
current single-sheet-with-all-standards-mixed template); if a sheet has no
"Standard" column at all -- the older one-sheet-per-standard layout -- or a
given row's Standard cell is blank, the sheet name is used instead (e.g.
"IS 269"), matching the original behavior. Certification ID and Client ID
both use the license number, since a license number is the natural unique
key in this dataset. Status is recomputed from Validity Date using this
project's own urgency thresholds -- the source "Status" column
(Operative/Cancelled/etc.) means something different and is not used.

Usage: python import_bis_isi_data.py "<path to source xlsx>"
"""
import sys
from pathlib import Path

import openpyxl

from import_helpers import RowCollector, parse_validity_date, compute_status, header_index_map, get

OUTPUT_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

(`datetime` is no longer imported directly here since every use of it moved into `import_helpers.py` along with the functions that used it — `import_bis_isi_workbook`/`import_bis_isi` below only call `parse_validity_date`/`compute_status`, they don't reference `datetime` directly.)

- [ ] **Step 3: Run tests to verify nothing broke**

Run: `cd dashboard-app/backend && python -m pytest test_import_bis_isi_data.py test_main.py -v`
Expected: all passed, with zero changes to `test_import_bis_isi_data.py` (its `from import_bis_isi_data import RowCollector, import_bis_isi_workbook, looks_like_bis_isi_workbook` line still works unchanged since `import_bis_isi_data.py` still defines/re-exports all three names).

- [ ] **Step 4: Commit**

```bash
git add dashboard-app/backend/import_helpers.py dashboard-app/backend/import_bis_isi_data.py
git commit -m "refactor: extract generic import helpers into import_helpers.py"
```

---

### Task 6: Register import formats and loop over them in `main.py`

**Files:**
- Create: `dashboard-app/backend/import_formats.py`
- Modify: `dashboard-app/backend/main.py`
- Test: `dashboard-app/backend/test_main.py` (existing BIS ISI upload/merge tests must pass unmodified)

- [ ] **Step 1: Create `import_formats.py`**

```python
"""Registry of per-scheme import formats. Each entry is
(format_name, detector, importer):
  - detector(wb) -> bool: sniffs an already-open openpyxl Workbook.
  - importer(wb, out_ws, today=None) -> dict: appends converted roster rows
    to out_ws (a real worksheet or an import_helpers.RowCollector) and
    returns a stats dict that must include a "rows_written" key.

To add a new scheme (e.g. FMCS): write import_fmcs.py with
looks_like_fmcs_workbook()/import_fmcs_workbook() following
import_bis_isi_data.py as a template, then add one line below. No endpoint
changes needed -- both /api/upload-clients and /api/merge-clients loop over
this list already.
"""
from import_bis_isi_data import looks_like_bis_isi_workbook, import_bis_isi_workbook

IMPORT_FORMATS = [
    ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook),
]
```

- [ ] **Step 2: Update `main.py`'s imports**

Current:

```python
from import_bis_isi_data import (  # noqa: E402
    looks_like_bis_isi_workbook, import_bis_isi_workbook, RowCollector,
)
```

Replace with:

```python
from import_helpers import RowCollector  # noqa: E402
from import_formats import IMPORT_FORMATS  # noqa: E402
```

- [ ] **Step 3: Replace the hardcoded BIS ISI branch in `/api/upload-clients` with a loop**

Current:

```python
    if looks_like_bis_isi_workbook(wb):
        collector = RowCollector()
        bis_stats = import_bis_isi_workbook(wb, collector)
        wb.close()
        tmp_path.unlink(missing_ok=True)

        if bis_stats["rows_written"] == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Recognized this as a BIS ISI licence file, but no rows had both a "
                    "licence number and a validity date to import."
                ),
            )

        stats = _upsert_clients_or_400(collector.rows, mode="replace")
        return {"status": "ok", "row_count": stats["row_count"], "format": "bis_isi", "stats": bis_stats}

    wb.close()
    tmp_path.unlink(missing_ok=True)
    if header_row is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The active sheet ('{active_title}') has no rows. If this file has "
                "multiple sheets, make sure the one with your client data is the sheet "
                "selected/visible when the file was last saved."
            ),
        )
    raise HTTPException(
        status_code=400,
        detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
    )


@app.post("/api/merge-clients", dependencies=[Depends(require_auth)])
```

Replace with:

```python
    for format_name, detector, importer in IMPORT_FORMATS:
        if not detector(wb):
            continue
        collector = RowCollector()
        format_stats = importer(wb, collector)
        wb.close()
        tmp_path.unlink(missing_ok=True)

        if format_stats["rows_written"] == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Recognized this as a {format_name} file, but no rows had both a "
                    "required identifier and a validity date to import."
                ),
            )

        stats = _upsert_clients_or_400(collector.rows, mode="replace")
        return {"status": "ok", "row_count": stats["row_count"], "format": format_name, "stats": format_stats}

    wb.close()
    tmp_path.unlink(missing_ok=True)
    if header_row is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The active sheet ('{active_title}') has no rows. If this file has "
                "multiple sheets, make sure the one with your client data is the sheet "
                "selected/visible when the file was last saved."
            ),
        )
    raise HTTPException(
        status_code=400,
        detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
    )


@app.post("/api/merge-clients", dependencies=[Depends(require_auth)])
```

- [ ] **Step 4: Replace the hardcoded BIS ISI branch in `/api/merge-clients` with the same loop**

Current:

```python
    actual_headers = list(header_row[: len(REQUIRED_HEADERS)]) if header_row else None
    bis_stats = None

    if actual_headers == REQUIRED_HEADERS:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)  # header
        new_rows = [tuple(row[:len(REQUIRED_HEADERS)]) for row in rows_iter if row and row[0] is not None]
        wb.close()
        upload_format = "roster"
    elif looks_like_bis_isi_workbook(wb):
        collector = RowCollector()
        bis_stats = import_bis_isi_workbook(wb, collector)
        new_rows = collector.rows
        wb.close()
        upload_format = "bis_isi"
        if bis_stats["rows_written"] == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=(
                    "Recognized this as a BIS ISI licence file, but no rows had both a "
                    "licence number and a validity date to import."
                ),
            )
    else:
        wb.close()
        tmp_path.unlink(missing_ok=True)
        if header_row is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The active sheet ('{active_title}') has no rows. If this file has "
                    "multiple sheets, make sure the one with your client data is the sheet "
                    "selected/visible when the file was last saved."
                ),
            )
        raise HTTPException(
            status_code=400,
            detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
        )

    tmp_path.unlink(missing_ok=True)
    stats = _upsert_clients_or_400(new_rows, mode="merge")
    return {
        "status": "ok", "row_count": stats["row_count"], "added": stats["added"],
        "skipped_duplicates": stats["skipped_duplicates"], "format": upload_format, "stats": bis_stats,
    }
```

Replace with:

```python
    actual_headers = list(header_row[: len(REQUIRED_HEADERS)]) if header_row else None
    format_stats = None

    if actual_headers == REQUIRED_HEADERS:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)  # header
        new_rows = [tuple(row[:len(REQUIRED_HEADERS)]) for row in rows_iter if row and row[0] is not None]
        wb.close()
        upload_format = "roster"
    else:
        new_rows = None
        upload_format = None
        for format_name, detector, importer in IMPORT_FORMATS:
            if not detector(wb):
                continue
            collector = RowCollector()
            format_stats = importer(wb, collector)
            new_rows = collector.rows
            wb.close()
            upload_format = format_name
            if format_stats["rows_written"] == 0:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Recognized this as a {format_name} file, but no rows had both a "
                        "required identifier and a validity date to import."
                    ),
                )
            break

        if new_rows is None:
            wb.close()
            tmp_path.unlink(missing_ok=True)
            if header_row is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"The active sheet ('{active_title}') has no rows. If this file has "
                        "multiple sheets, make sure the one with your client data is the sheet "
                        "selected/visible when the file was last saved."
                    ),
                )
            raise HTTPException(
                status_code=400,
                detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
            )

    tmp_path.unlink(missing_ok=True)
    stats = _upsert_clients_or_400(new_rows, mode="merge")
    return {
        "status": "ok", "row_count": stats["row_count"], "added": stats["added"],
        "skipped_duplicates": stats["skipped_duplicates"], "format": upload_format, "stats": format_stats,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed, with zero changes needed to any existing BIS ISI upload/merge test — `body["format"] == "bis_isi"` and `body["stats"]["rows_written"]` assertions still hold since the registry's `format_name` is the literal string `"bis_isi"`.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/import_formats.py dashboard-app/backend/main.py
git commit -m "refactor: loop over an IMPORT_FORMATS registry instead of hardcoding BIS ISI"
```

---

### Task 7: Frontend `api.js` — `getEligibleCount`, filterable `sendAllAlerts`/`sendAllEmailAlerts`

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Test: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Add to `api.test.js`. First, update the import line — current:

```javascript
import {
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus, verifyCredentials,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus,
} from "./api";
```

Replace with:

```javascript
import {
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus, verifyCredentials,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
} from "./api";
```

Then add these new test cases (the `sendAllAlerts`/`sendAllEmailAlerts` cases replace the two existing `describe` blocks' bodies with an extra test each; the `getEligibleCount` block is new):

Current `describe("sendAllAlerts", ...)` block:

```javascript
describe("sendAllAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});
```

Replace with:

```javascript
describe("sendAllAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("adds status/cert_type/expiry_before as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllAlerts({ status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});
```

Current `describe("sendAllEmailAlerts", ...)` block:

```javascript
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
```

Add a new test to that block, right before its closing `});`:

```javascript
  it("adds status/cert_type/expiry_before as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllEmailAlerts({ status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all-emails?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31",
      { method: "POST", credentials: "include", headers: {} }
    );
  });
```

Add a new `describe` block at the end of the file (before the final closing, alongside the other top-level `describe` blocks):

```javascript
describe("getEligibleCount", () => {
  it("returns parsed JSON with no query string when no filters are given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 3, email: 2 }) });
    const result = await getEligibleCount();
    expect(result).toEqual({ whatsapp: 3, email: 2 });
    expect(global.fetch).toHaveBeenCalledWith("/api/eligible-count", { credentials: "include", headers: {} });
  });

  it("passes status/cert_type/expiry_before as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 1, email: 1 }) });
    await getEligibleCount({ status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/eligible-count?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31",
      { credentials: "include", headers: {} }
    );
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getEligibleCount()).rejects.toThrow("Failed to load eligible count: 500");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: FAIL — `getEligibleCount` isn't exported yet, and `sendAllAlerts`/`sendAllEmailAlerts` ignore the params object entirely.

- [ ] **Step 3: Update `api.js`**

Current:

```javascript
export async function sendAllAlerts() {
  const res = await fetch(`${API_BASE}/api/send-all`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}
```

Replace with:

```javascript
function scopeQueryString(params = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  return query.toString();
}

export async function sendAllAlerts(params = {}) {
  const qs = scopeQueryString(params);
  const res = await fetch(`${API_BASE}${qs ? `/api/send-all?${qs}` : "/api/send-all"}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}
```

Current:

```javascript
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
```

Replace with:

```javascript
export async function sendAllEmailAlerts(params = {}) {
  const qs = scopeQueryString(params);
  const res = await fetch(`${API_BASE}${qs ? `/api/send-all-emails?${qs}` : "/api/send-all-emails"}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}
```

Add a new function right after `getSendAllEmailsStatus` (before `clientsExportUrl`):

```javascript
export async function getEligibleCount(params = {}) {
  const qs = scopeQueryString(params);
  const res = await fetch(`${API_BASE}${qs ? `/api/eligible-count?${qs}` : "/api/eligible-count"}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load eligible count: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed, including the pre-existing no-args `sendAllAlerts()`/`sendAllEmailAlerts()` tests (an empty `scopeQueryString` result produces the exact same bare URL as before).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: add getEligibleCount and optional scope filters to sendAllAlerts/sendAllEmailAlerts"
```

---

### Task 8: Duration presets in `ClientDataFilters.jsx`

**Files:**
- Modify: `dashboard-app/frontend/src/sortUtils.js`
- Modify: `dashboard-app/frontend/src/components/ClientDataFilters.jsx`
- Test: `dashboard-app/frontend/src/sortUtils.test.js`
- Test: `dashboard-app/frontend/src/components/ClientDataFilters.test.jsx`

- [ ] **Step 1: Write the failing test for the date helper**

Add to `sortUtils.test.js`, after the `describe("formatDaysLeft", ...)` block (uses the same "compute the expected value the same way the real function does" convention the file's own `futureDateStr` helper already establishes):

```javascript
import { isoDateMonthsFromToday } from "./sortUtils";

describe("isoDateMonthsFromToday", () => {
  function expectedIso(monthsAhead) {
    const d = new Date();
    d.setMonth(d.getMonth() + monthsAhead);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  it("returns today's date shifted 3 months ahead in YYYY-MM-DD format", () => {
    expect(isoDateMonthsFromToday(3)).toBe(expectedIso(3));
  });

  it("returns today's date shifted 12 months ahead", () => {
    expect(isoDateMonthsFromToday(12)).toBe(expectedIso(12));
  });
});
```

(Note: the top-level `import { daysUntil, formatDaysLeft, sortClients, monthlyGroups, initialsFor } from "./sortUtils";` line at the top of the file should have `isoDateMonthsFromToday` added to it instead of a second separate `import` statement — merge it into that existing line rather than duplicating the import.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/frontend && npx vitest run src/sortUtils.test.js`
Expected: FAIL — `isoDateMonthsFromToday` is not exported.

- [ ] **Step 3: Add `isoDateMonthsFromToday` to `sortUtils.js`**

Add at the end of `sortUtils.js`:

```javascript
export function isoDateMonthsFromToday(monthsAhead) {
  // Date.setMonth rolls overflow days into the following month (e.g. 31 Jan +
  // 1 month -> 3 Mar, not a clamped 28/29 Feb) -- that's the native JS
  // behavior and is treated as an acceptable approximation for a quick
  // "N months from now" filter preset, not exact calendar-month arithmetic.
  const d = new Date();
  d.setMonth(d.getMonth() + monthsAhead);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard-app/frontend && npx vitest run src/sortUtils.test.js`
Expected: PASS.

- [ ] **Step 5: Write the failing tests for the preset buttons**

Add to `ClientDataFilters.test.jsx`. Update the import line — current:

```javascript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientDataFilters from "./ClientDataFilters";
```

Replace with:

```javascript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientDataFilters from "./ClientDataFilters";
import { isoDateMonthsFromToday } from "../sortUtils";
```

Add these tests inside the existing `describe("ClientDataFilters", ...)` block, after the "calls onExpiryBeforeChange when the date input changes" test:

```javascript
  it("calls onExpiryBeforeChange with the correct date when '3 months' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("3 months"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(3));
  });

  it("calls onExpiryBeforeChange with the correct date when '6 months' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("6 months"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(6));
  });

  it("calls onExpiryBeforeChange with the correct date when '1 year' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("1 year"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(12));
  });
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ClientDataFilters.test.jsx`
Expected: FAIL — no "3 months"/"6 months"/"1 year" text exists in the rendered output yet.

- [ ] **Step 7: Add the preset buttons to `ClientDataFilters.jsx`**

Current:

```javascript
export default function ClientDataFilters({
  certOptions, certType, onCertTypeChange, expiryBefore, onExpiryBeforeChange, onClearAll,
}) {
  const hasFilters = certType !== "ALL" || expiryBefore !== "";

  return (
    <div className="bg-surface border border-line rounded-xl p-4 flex flex-wrap gap-4 items-center">
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
        Filter by
      </span>
      <select
        value={certType}
        onChange={(e) => onCertTypeChange(e.target.value)}
        aria-label="Filter by certification type"
        className="min-w-[180px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <option value="ALL">All Cert Types</option>
        {certOptions.map((cert) => (
          <option key={cert} value={cert}>{cert}</option>
        ))}
      </select>
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        Expiry before
        <input
          type="date"
          value={expiryBefore}
          onChange={(e) => onExpiryBeforeChange(e.target.value)}
          aria-label="Filter by expiry before date"
          className="bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </label>
      {hasFilters && (
        <button
          type="button"
          onClick={onClearAll}
          className="ml-auto text-sm font-semibold text-accent hover:underline"
        >
          Clear All
        </button>
      )}
    </div>
  );
}
```

Replace with:

```javascript
import { isoDateMonthsFromToday } from "../sortUtils";

const DURATION_PRESETS = [
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
  { label: "1 year", months: 12 },
];

export default function ClientDataFilters({
  certOptions, certType, onCertTypeChange, expiryBefore, onExpiryBeforeChange, onClearAll,
}) {
  const hasFilters = certType !== "ALL" || expiryBefore !== "";

  return (
    <div className="bg-surface border border-line rounded-xl p-4 flex flex-wrap gap-4 items-center">
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
        Filter by
      </span>
      <select
        value={certType}
        onChange={(e) => onCertTypeChange(e.target.value)}
        aria-label="Filter by certification type"
        className="min-w-[180px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <option value="ALL">All Cert Types</option>
        {certOptions.map((cert) => (
          <option key={cert} value={cert}>{cert}</option>
        ))}
      </select>
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        Expiry before
        <input
          type="date"
          value={expiryBefore}
          onChange={(e) => onExpiryBeforeChange(e.target.value)}
          aria-label="Filter by expiry before date"
          className="bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </label>
      <div className="flex items-center gap-1.5">
        {DURATION_PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => onExpiryBeforeChange(isoDateMonthsFromToday(preset.months))}
            className="px-3 py-1.5 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
          >
            {preset.label}
          </button>
        ))}
      </div>
      {hasFilters && (
        <button
          type="button"
          onClick={onClearAll}
          className="ml-auto text-sm font-semibold text-accent hover:underline"
        >
          Clear All
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/sortUtils.test.js src/components/ClientDataFilters.test.jsx`
Expected: all passed, including every pre-existing `ClientDataFilters` test.

- [ ] **Step 9: Commit**

```bash
git add dashboard-app/frontend/src/sortUtils.js dashboard-app/frontend/src/sortUtils.test.js dashboard-app/frontend/src/components/ClientDataFilters.jsx dashboard-app/frontend/src/components/ClientDataFilters.test.jsx
git commit -m "feat: add 3-months/6-months/1-year duration preset buttons to the expiry filter"
```

---

### Task 9: `SendAllConfirmModal.jsx` — scope choice (all eligible vs. currently filtered)

**Files:**
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`
- Test: `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`

- [ ] **Step 1: Write the failing tests**

The two existing tests below must be updated because the static "to all N eligible clients..." sentence is being replaced by a shorter intro plus the new scope radios; every other existing test in the file needs no changes (verified against the real 175-line file, whose 15 existing tests only touch these two "no job" text assertions besides the ones checking `job`-view behavior, which this task doesn't touch).

Current:

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

Replace with:

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
    expect(screen.getByText(/Send a renewal email to:/)).toBeInTheDocument();
    expect(screen.getByTestId("send-all-confirm-modal-email")).toBeInTheDocument();
  });

  it("defaults to WhatsApp text and testid when channel is omitted", () => {
    render(
      <SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByText(/Send a real WhatsApp renewal alert to:/)).toBeInTheDocument();
    expect(screen.getByTestId("send-all-confirm-modal-whatsapp")).toBeInTheDocument();
  });
```

Add these new tests at the end of the `describe` block, right before the closing `});`:

```javascript
  it("shows the filtered count and defaults to the 'all eligible' scope", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    expect(screen.getByLabelText(/All eligible clients/)).toBeChecked();
    expect(screen.getByLabelText(/Currently filtered view/)).not.toBeChecked();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("passes 'all' to onConfirm when the default scope is confirmed", () => {
    const onConfirm = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={onConfirm} onCancel={() => {}}
      />
    );
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalledWith("all");
  });

  it("passes 'filtered' to onConfirm after switching scope", () => {
    const onConfirm = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={onConfirm} onCancel={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalledWith("filtered");
  });

  it("disables Confirm when the filtered scope is selected and its count is 0", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={0} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    expect(screen.getByText("Confirm Send All")).toBeDisabled();
  });

  it("defaults filteredCount to 0 when the prop is omitted", () => {
    render(<SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    expect(screen.getByText("Confirm Send All")).toBeDisabled();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: FAIL — the two updated text assertions don't match today's longer sentence, and `filteredCount`/scope-related queries (`getByLabelText(/All eligible clients/)`, etc.) don't exist yet.

- [ ] **Step 3: Update `SendAllConfirmModal.jsx`**

Current:

```javascript
export default function SendAllConfirmModal({ open, eligibleCount, channel = "whatsapp", onConfirm, onCancel, job = null }) {
  const [confirming, setConfirming] = useState(false);
  const cancelButtonRef = useRef(null);
  const confirmButtonRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (open) {
      setConfirming(false);
      cancelButtonRef.current?.focus();
    }
  }, [open]);
```

Replace with:

```javascript
export default function SendAllConfirmModal({
  open, eligibleCount, filteredCount = 0, channel = "whatsapp", onConfirm, onCancel, job = null,
}) {
  const [confirming, setConfirming] = useState(false);
  const [scope, setScope] = useState("all");
  const cancelButtonRef = useRef(null);
  const confirmButtonRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (open) {
      setConfirming(false);
      setScope("all");
      cancelButtonRef.current?.focus();
    }
  }, [open]);
```

Current:

```javascript
  if (!open) return null;

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm();
  }
```

Replace with:

```javascript
  if (!open) return null;

  const selectedCount = scope === "filtered" ? filteredCount : eligibleCount;

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm(scope);
  }
```

Current (the "no job" idle view):

```javascript
        ) : (
          <>
            <p className="text-sm text-ink-secondary mb-6">
              {channel === "email" ? "Send a renewal email" : "Send a real WhatsApp renewal alert"} to all{" "}
              <strong>{eligibleCount}</strong> eligible client{eligibleCount === 1 ? "" : "s"} (Critical,
              Urgent, Due Soon, or Expired, not yet {channel === "email" ? "emailed" : "sent"} today)?
            </p>
            <div className="flex justify-end gap-3">
              <button
                ref={cancelButtonRef}
                type="button"
                onClick={onCancel}
                className="px-4 py-2 rounded-full text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
              >
                Cancel
              </button>
              <button
                ref={confirmButtonRef}
                type="button"
                onClick={handleConfirmClick}
                disabled={confirming}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Confirm Send All
              </button>
            </div>
          </>
        )}
```

Replace with:

```javascript
        ) : (
          <>
            <p className="text-sm text-ink-secondary mb-3">
              {channel === "email" ? "Send a renewal email" : "Send a real WhatsApp renewal alert"} to:
            </p>
            <div className="mb-6 space-y-2">
              <label className="flex items-center gap-2 text-sm text-ink-primary">
                <input
                  type="radio"
                  name="send-all-scope"
                  checked={scope === "all"}
                  onChange={() => setScope("all")}
                />
                All eligible clients (<strong>{eligibleCount}</strong>)
              </label>
              <label className="flex items-center gap-2 text-sm text-ink-primary">
                <input
                  type="radio"
                  name="send-all-scope"
                  checked={scope === "filtered"}
                  onChange={() => setScope("filtered")}
                />
                Currently filtered view (<strong>{filteredCount}</strong>)
              </label>
            </div>
            <div className="flex justify-end gap-3">
              <button
                ref={cancelButtonRef}
                type="button"
                onClick={onCancel}
                className="px-4 py-2 rounded-full text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
              >
                Cancel
              </button>
              <button
                ref={confirmButtonRef}
                type="button"
                onClick={handleConfirmClick}
                disabled={confirming || selectedCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Confirm Send All
              </button>
            </div>
          </>
        )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: all passed, including every pre-existing test not touched above (the `job`-view tests, the Tab/focus-trap tests, etc. — none of them render the "no job" idle view differently from before, aside from the two text updates already made).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/SendAllConfirmModal.jsx dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx
git commit -m "feat: add an all-eligible-vs-filtered scope choice to SendAllConfirmModal"
```

---

### Task 10: `App.jsx` — wire eligible-count fetching and scope-aware bulk send

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Test: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

First, update the shared `beforeEach` so every test (not just the ones this task adds) has a safe default for the new `getEligibleCount` call `vi.mock("./api")` auto-mocks to `undefined` otherwise — without this, any test that opens a bulk-send modal would throw on `.then` being called on `undefined`. Current:

```javascript
beforeEach(() => {
  vi.resetAllMocks();
  api.getClients.mockResolvedValue(samplePage(sampleClients));
  api.getStats.mockResolvedValue(sampleStats);
});
```

Replace with:

```javascript
beforeEach(() => {
  vi.resetAllMocks();
  api.getClients.mockResolvedValue(samplePage(sampleClients));
  api.getStats.mockResolvedValue(sampleStats);
  api.getEligibleCount.mockResolvedValue({ whatsapp: 0, email: 0 });
});
```

Then add these new tests at the end of the `describe("App", ...)` block, right before its closing `});`:

```javascript
  it("fetches the eligible count for the current filters when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({ status: "ALL", certType: "ALL", expiryBefore: "" })
    );
  });

  it("sends only the filtered scope when 'Currently filtered view' is selected and confirmed", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Critical"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith({ status: "CRITICAL", certType: "ALL", expiryBefore: "" })
    );
  });

  it("sends with no filters when the default 'all eligible' scope is confirmed, even with an active filter", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Critical"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(api.sendAllAlerts).toHaveBeenCalledWith({}));
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: FAIL — `getEligibleCount` is never called by `App.jsx` yet, and `sendAllAlerts` is always called with no arguments regardless of scope.

- [ ] **Step 3: Add state and fetch effect**

Current (top imports):

```javascript
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus,
} from "./api";
```

Replace with:

```javascript
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
} from "./api";
```

Current:

```javascript
  const [pendingEmailClient, setPendingEmailClient] = useState(null);
  const [emailBulkModalOpen, setEmailBulkModalOpen] = useState(false);
  const [sendAllEmailJob, setSendAllEmailJob] = useState(null);
```

Replace with:

```javascript
  const [pendingEmailClient, setPendingEmailClient] = useState(null);
  const [emailBulkModalOpen, setEmailBulkModalOpen] = useState(false);
  const [sendAllEmailJob, setSendAllEmailJob] = useState(null);
  const [filteredEligibleCount, setFilteredEligibleCount] = useState({ whatsapp: 0, email: 0 });
```

Add a new effect right after the existing `loadStats` effect block:

```javascript
  useEffect(() => {
    loadStats();
  }, [loadStats]);
```

(current code — add immediately below it):

```javascript
  useEffect(() => {
    if (!bulkModalOpen && !emailBulkModalOpen) return;
    getEligibleCount({ status: activeStatus, certType, expiryBefore })
      .then(setFilteredEligibleCount)
      .catch(() => {});
  }, [bulkModalOpen, emailBulkModalOpen, activeStatus, certType, expiryBefore]);
```

- [ ] **Step 4: Make the confirm handlers scope-aware**

Current:

```javascript
  async function handleConfirmSendAll() {
    try {
      const { job_id: jobId } = await sendAllAlerts();
      setSendAllJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
```

Replace with:

```javascript
  async function handleConfirmSendAll(scope) {
    try {
      const filters = scope === "filtered" ? { status: activeStatus, certType, expiryBefore } : {};
      const { job_id: jobId } = await sendAllAlerts(filters);
      setSendAllJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
```

Current:

```javascript
  async function handleConfirmSendAllEmails() {
    try {
      const { job_id: jobId } = await sendAllEmailAlerts();
      setSendAllEmailJob({ total: 0, sent: 0, skipped: 0, skipped_no_email: 0, failed: 0, done: false });
```

Replace with:

```javascript
  async function handleConfirmSendAllEmails(scope) {
    try {
      const filters = scope === "filtered" ? { status: activeStatus, certType, expiryBefore } : {};
      const { job_id: jobId } = await sendAllEmailAlerts(filters);
      setSendAllEmailJob({ total: 0, sent: 0, skipped: 0, skipped_no_email: 0, failed: 0, done: false });
```

- [ ] **Step 5: Pass `filteredCount` to both modals**

Current:

```javascript
      <SendAllConfirmModal
        open={bulkModalOpen}
        eligibleCount={eligibleCount}
        channel="whatsapp"
        job={sendAllJob}
        onConfirm={handleConfirmSendAll}
        onCancel={sendAllJob ? handleCloseSendAllModal : () => setBulkModalOpen(false)}
      />
```

Replace with:

```javascript
      <SendAllConfirmModal
        open={bulkModalOpen}
        eligibleCount={eligibleCount}
        filteredCount={filteredEligibleCount.whatsapp}
        channel="whatsapp"
        job={sendAllJob}
        onConfirm={handleConfirmSendAll}
        onCancel={sendAllJob ? handleCloseSendAllModal : () => setBulkModalOpen(false)}
      />
```

Current:

```javascript
      <SendAllConfirmModal
        open={emailBulkModalOpen}
        eligibleCount={eligibleEmailCount}
        channel="email"
        job={sendAllEmailJob}
        onConfirm={handleConfirmSendAllEmails}
        onCancel={sendAllEmailJob ? handleCloseSendAllEmailsModal : () => setEmailBulkModalOpen(false)}
      />
```

Replace with:

```javascript
      <SendAllConfirmModal
        open={emailBulkModalOpen}
        eligibleCount={eligibleEmailCount}
        filteredCount={filteredEligibleCount.email}
        channel="email"
        job={sendAllEmailJob}
        onConfirm={handleConfirmSendAllEmails}
        onCancel={sendAllEmailJob ? handleCloseSendAllEmailsModal : () => setEmailBulkModalOpen(false)}
      />
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: all passed, including every pre-existing test (the default `getEligibleCount` mock in `beforeEach` keeps all previously-passing tests behaving as before; `sendAllAlerts()`/`sendAllEmailAlerts()` called with `{}` produce the same bare-URL request the old no-arg calls did, per Task 7).

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "feat: wire eligible-count fetching and scope-aware bulk send into App.jsx"
```

---

### Task 11: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -v`
Expected: all tests pass (this repo was at 147+ backend/frontend tests combined before this branch; expect that count to grow by roughly 30-35 new tests across Tasks 1-10, zero regressions).

- [ ] **Step 2: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Manual smoke test against a real dev server**

Start the backend (`cd dashboard-app/backend && python -m uvicorn main:app --port 8040`) and frontend (`cd dashboard-app/frontend && npm run dev`) locally. In the browser:
1. Upload a small roster via Excel Sync so the table has a few CRITICAL/URGENT clients across at least two cert types.
2. Click "3 months" in Client Data — confirm the "Expiry before" date field fills in with today's date shifted 3 months, and the table narrows accordingly.
3. Click "Send All Eligible" — confirm the modal shows both "All eligible clients (N)" and "Currently filtered view (M)" with sane counts, defaulting to "All eligible clients" selected.
4. Select a cert-type filter, reopen the modal, pick "Currently filtered view", and confirm the resulting job's `total` matches only that cert type's eligible clients (check the Network tab's `/api/send-all` request URL includes `cert_type=...`).
5. Repeat step 4 for "Send All Emails".

Expected: no console errors; every step matches the description above.

- [ ] **Step 4: Confirm no regressions in existing BIS ISI upload flow**

Upload a real (or synthetic) BIS ISI-format workbook via Excel Sync's "Upload and Replace" and "Upload and Merge" actions. Expected: both still succeed and report `format: "bis_isi"` exactly as before this branch (the registry refactor in Tasks 5-6 must be invisible to this flow).
