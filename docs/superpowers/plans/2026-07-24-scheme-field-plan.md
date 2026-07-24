# Certification Scheme Field + Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `scheme` field (e.g. "ISI") to every client row, distinct from `cert_name`, with a self-healing migration for existing data, and thread it through every filter path `cert_type` already reaches (table view, CSV export, eligible-count, bulk-send scope, `run()`/`run_email_alerts()`).

**Architecture:** `scheme` joins `RECORD_FIELDS` immediately after `cert_name` everywhere it's used positionally (SQL schema, roster Excel format, `out_ws.append([...])` row construction). `init_db()` gains a migration step (`ALTER TABLE` + backfill `NULL` rows to `'ISI'`) so it self-heals on every call, including after Render free-tier resets. Because `RECORD_FIELDS`'s 11-column shape is hardcoded positionally into dozens of test row-literals across the backend test suite, most of this plan's bulk is inserting one new element into each of those literals — mechanical, but must be done precisely since a wrong index silently corrupts a different field.

**Tech Stack:** Python/FastAPI/SQLite (`dashboard-app/backend/`), React/Vite (`dashboard-app/frontend/`), pytest, Vitest + React Testing Library.

**Important warning for whoever executes Task 3:** inserting `scheme` after `cert_name` shifts every *positional* index after it by one. `test_import_bis_isi_data.py` has two tests that index into produced rows by position (`row[5]`, `row[6]`) — `row[5]` (cert_name) is unaffected, but anything currently reading `row[6]` (cert_id) must become `row[7]`. This is called out explicitly in Task 3; do not miss it.

---

### Task 1: `db.py` — schema, migration, `RECORD_FIELDS`, filters, `get_stats`

**Files:**
- Modify: `dashboard-app/backend/db.py`

- [ ] **Step 1: Add `scheme` to the schema and to `RECORD_FIELDS`**

Current:

```python
RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]
```

Replace with:

```python
RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name", "scheme",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]
```

Current:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    company         TEXT,
    email           TEXT,
    phone           TEXT,
    cert_name       TEXT,
    cert_id         TEXT,
    issue_date      TEXT,
    expiry_date     TEXT,
    expiry_date_iso TEXT,
    renewal_link    TEXT,
    status          TEXT NOT NULL
);
```

Replace with:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    company         TEXT,
    email           TEXT,
    phone           TEXT,
    cert_name       TEXT,
    scheme          TEXT,
    cert_id         TEXT,
    issue_date      TEXT,
    expiry_date     TEXT,
    expiry_date_iso TEXT,
    renewal_link    TEXT,
    status          TEXT NOT NULL
);
```

- [ ] **Step 2: Add the self-healing migration to `init_db`**

Current:

```python
def init_db(db_path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
```

Replace with:

```python
def init_db(db_path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        # CREATE TABLE IF NOT EXISTS does not add a column to a table that
        # already existed before `scheme` was introduced (e.g. Render's
        # persisted clients.db, or a fresh local db.py predating this
        # migration). This adds it once, then classifies any row that
        # predates the migration as 'ISI' -- the only scheme that has ever
        # existed in this dataset -- without touching a row that already has
        # an explicit scheme value (a newly-imported or manually-corrected
        # row is never silently overwritten).
        columns = {row[1] for row in conn.execute("PRAGMA table_info(clients)")}
        if "scheme" not in columns:
            conn.execute("ALTER TABLE clients ADD COLUMN scheme TEXT")
        conn.execute("UPDATE clients SET scheme = 'ISI' WHERE scheme IS NULL")
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 3: Add `scheme` to `_client_filters_where` and `_SORTABLE_COLUMNS`**

Current:

```python
_SORTABLE_COLUMNS = {
    "client_id", "name", "company", "cert_name", "cert_id", "status",
}
```

Replace with:

```python
_SORTABLE_COLUMNS = {
    "client_id", "name", "company", "cert_name", "scheme", "cert_id", "status",
}
```

Current:

```python
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
```

Replace with:

```python
def _client_filters_where(
    status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
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
    if scheme and scheme != "ALL":
        where.append("scheme = ?")
        params.append(scheme)
    if expiry_before:
        where.append("expiry_date_iso <= ?")
        params.append(expiry_before)
    if search:
        where.append("(name LIKE ? OR company LIKE ?)")
        like_term = f"%{search}%"
        params.extend([like_term, like_term])
    return where, params
```

- [ ] **Step 4: Add `scheme` param to `get_clients_page`, `export_clients_rows`, `get_eligible_clients`, `get_eligible_count`**

Current:

```python
def get_clients_page(
    db_path, page: int = 1, page_size: int = 50, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
    search: str | None = None, sort_key: str | None = None, sort_dir: str = "asc",
) -> tuple[list[dict], int]:
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search)
```

Replace with:

```python
def get_clients_page(
    db_path, page: int = 1, page_size: int = 50, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
    search: str | None = None, sort_key: str | None = None, sort_dir: str = "asc",
    scheme: str | None = None,
) -> tuple[list[dict], int]:
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
```

Current:

```python
def export_clients_rows(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
):
    """Yields a dict per matching client, no pagination — for CSV export."""
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search)
```

Replace with:

```python
def export_clients_rows(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
):
    """Yields a dict per matching client, no pagination — for CSV export."""
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
```

Current:

```python
def get_eligible_clients(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
) -> list[dict]:
    """Alert-eligible (status in ALERT_STATUSES) client records, optionally
    further narrowed by the same status/cert_type/expiry_before/search filters
    get_clients_page's table view supports -- so bulk-send scope can mirror
    exactly what's on screen. ORDER BY rowid pins insertion order regardless
    of which index SQLite's query planner picks for the WHERE clause, so
    callers that depend on result order (run()'s existing tests) see the
    same order read_clients() always gave them."""
    conn = get_connection(db_path)
    try:
        extra_where, extra_params = _client_filters_where(status, cert_type, expiry_before, search)
```

Replace with:

```python
def get_eligible_clients(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    """Alert-eligible (status in ALERT_STATUSES) client records, optionally
    further narrowed by the same status/cert_type/expiry_before/search/scheme
    filters get_clients_page's table view supports -- so bulk-send scope can
    mirror exactly what's on screen. ORDER BY rowid pins insertion order
    regardless of which index SQLite's query planner picks for the WHERE
    clause, so callers that depend on result order (run()'s existing tests)
    see the same order read_clients() always gave them."""
    conn = get_connection(db_path)
    try:
        extra_where, extra_params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
```

Current:

```python
def get_eligible_count(
    db_path, today: str, channel: str, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
    search: str | None = None,
) -> int:
    """Counts alert-eligible clients not yet sent today via the given channel
    ('whatsapp' -> sent_log, 'email' -> email_sent_log), optionally narrowed
    by status/cert_type/expiry_before/search -- used to show a live count for
    the "currently filtered view" bulk-send scope before anything is sent."""
    if channel not in ("whatsapp", "email"):
        raise ValueError(f"Unknown channel: {channel!r}")
    log_table = "sent_log" if channel == "whatsapp" else "email_sent_log"
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        extra_where, extra_params = _client_filters_where(status, cert_type, expiry_before, search)
```

Replace with:

```python
def get_eligible_count(
    db_path, today: str, channel: str, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
    search: str | None = None, scheme: str | None = None,
) -> int:
    """Counts alert-eligible clients not yet sent today via the given channel
    ('whatsapp' -> sent_log, 'email' -> email_sent_log), optionally narrowed
    by status/cert_type/expiry_before/search/scheme -- used to show a live
    count for the "currently filtered view" bulk-send scope before anything
    is sent."""
    if channel not in ("whatsapp", "email"):
        raise ValueError(f"Unknown channel: {channel!r}")
    log_table = "sent_log" if channel == "whatsapp" else "email_sent_log"
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        extra_where, extra_params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
```

- [ ] **Step 5: Add a `schemes` list to `get_stats`**

Current:

```python
        cert_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT cert_name FROM clients WHERE cert_name IS NOT NULL ORDER BY cert_name"
        ).fetchall()]
```

Replace with:

```python
        cert_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT cert_name FROM clients WHERE cert_name IS NOT NULL ORDER BY cert_name"
        ).fetchall()]

        schemes = [r[0] for r in conn.execute(
            "SELECT DISTINCT scheme FROM clients WHERE scheme IS NOT NULL ORDER BY scheme"
        ).fetchall()]
```

Current:

```python
        return {
            "status_counts": status_counts,
            "eligible_not_sent_today": eligible_not_sent,
            "eligible_not_emailed_today": eligible_not_emailed,
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
            "schemes": schemes,
            "renewals_by_month": renewals_by_month,
        }
```

- [ ] **Step 6: Update `upsert_clients`'s docstring reference to row shape (comment only, no behavior change)**

Current:

```python
def upsert_clients(db_path, rows: list[tuple], mode: str) -> dict:
    """rows: list of tuples in RECORD_FIELDS order (client_id first).
```

Replace with:

```python
def upsert_clients(db_path, rows: list[tuple], mode: str) -> dict:
    """rows: list of tuples in RECORD_FIELDS order (client_id first, scheme
    right after cert_name).
```

- [ ] **Step 7: Run the full backend test suite and confirm the expected failures**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: many failures — every existing row-tuple fixture across `test_db.py`, `test_main.py`, `test_whatsapp_renewal_alerts.py`, `test_email_alerts.py` is now missing the `scheme` element `upsert_clients`/`insert_sql` expects at position 6, so inserts will misalign fields (e.g. what used to be `status` lands in the `scheme` column) or raise `sqlite3.ProgrammingError` for a param-count mismatch. This is expected — Tasks 2-6 fix every one of these fixtures.

- [ ] **Step 8: Commit**

```bash
git add dashboard-app/backend/db.py
git commit -m "feat: add a scheme column with a self-healing migration and filter support"
```

---

### Task 2: `test_db.py` — update fixtures, add scheme tests

**Files:**
- Modify: `dashboard-app/backend/test_db.py`

- [ ] **Step 1: Insert `scheme` into every row-tuple fixture**

`ROW_A`/`ROW_B` are each defined once and referenced by name everywhere else in the file, so only their definitions need editing. Current:

```python
ROW_A = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
          "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_B = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
          "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
```

Replace with:

```python
ROW_A = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
          "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_B = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
          "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
```

Current:

```python
    updated_row_a = ("CLT001", "SHOULD NOT OVERWRITE", "TechCorp", "r@x.com",
                       "919876543210", "ISO 9001", "ISO-1", "01-01-2025",
                       "24-07-2026", "https://x", "CRITICAL")
```

Replace with:

```python
    updated_row_a = ("CLT001", "SHOULD NOT OVERWRITE", "TechCorp", "r@x.com",
                       "919876543210", "ISO 9001", "ISI", "ISO-1", "01-01-2025",
                       "24-07-2026", "https://x", "CRITICAL")
```

Current:

```python
    blank_id_row = ("", "No ID Person", "Acme", "n@x.com", "919999999999",
                     "ISO 9001", "ISO-2", "01-01-2025", "01-01-2027", "https://x", "OK")
    none_id_row = (None, "Also No ID", "Acme", "n2@x.com", "919999999998",
                    "ISO 9001", "ISO-3", "01-01-2025", "01-01-2027", "https://x", "OK")
```

Replace with:

```python
    blank_id_row = ("", "No ID Person", "Acme", "n@x.com", "919999999999",
                     "ISO 9001", "ISI", "ISO-2", "01-01-2025", "01-01-2027", "https://x", "OK")
    none_id_row = (None, "Also No ID", "Acme", "n2@x.com", "919999999998",
                    "ISO 9001", "ISI", "ISO-3", "01-01-2025", "01-01-2027", "https://x", "OK")
```

The invalid-name row appears twice, identically. Use `replace_all: true` for this one (it's the same 4-line literal in both `test_upsert_merge_raises_on_constraint_violation_not_miscounted_as_duplicate` and `test_upsert_merge_rolls_back_whole_batch_on_constraint_violation`). Current:

```python
    invalid_row = (
        "CLT099", None, "TechCorp", "r@x.com", "919876543210",
        "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL",
    )
```

Replace with (both occurrences):

```python
    invalid_row = (
        "CLT099", None, "TechCorp", "r@x.com", "919876543210",
        "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL",
    )
```

`FIVE_ROWS` is defined once. Current:

```python
FIVE_ROWS = [
    ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "1", "ISO 9001", "ISO-1",
     "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "2", "OSHA", "OSHA-1",
     "01-01-2025", "11-08-2026", "https://x", "URGENT"),
    ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "3", "ISO 9001", "ISO27-1",
     "01-01-2025", "10-09-2026", "https://x", "DUE SOON"),
    ("CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "4", "GMP", "GMP-1",
     "01-01-2025", "15-10-2026", "https://x", "ACTIVE"),
    ("CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "5", "HACCP", "HACCP-1",
     "01-01-2025", "12-01-2026", "https://x", "EXPIRED"),
]
```

Replace with (CLT001-003 and CLT005 are all "ISI"; CLT004 is deliberately given a different scheme, `"FMCS"`, so Task 2 Step 2's new scheme-filter tests below have two distinct scheme values to filter between):

```python
FIVE_ROWS = [
    ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "1", "ISO 9001", "ISI", "ISO-1",
     "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "2", "OSHA", "ISI", "OSHA-1",
     "01-01-2025", "11-08-2026", "https://x", "URGENT"),
    ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "3", "ISO 9001", "ISI", "ISO27-1",
     "01-01-2025", "10-09-2026", "https://x", "DUE SOON"),
    ("CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "4", "GMP", "FMCS", "GMP-1",
     "01-01-2025", "15-10-2026", "https://x", "ACTIVE"),
    ("CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "5", "HACCP", "ISI", "HACCP-1",
     "01-01-2025", "12-01-2026", "https://x", "EXPIRED"),
]
```

- [ ] **Step 2: Run the file to confirm existing tests pass again**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: all previously-existing tests pass. (CLT004's scheme changing to `"FMCS"` doesn't affect any existing assertion — no existing test in this file filters or asserts on `scheme`.)

- [ ] **Step 3: Add new tests for scheme filtering and the migration**

Add at the end of the file:

```python
def test_init_db_migrates_pre_scheme_database_and_backfills_isi(tmp_path):
    """A database created before the scheme column existed (simulated here
    by creating the clients table without it, bypassing init_db/SCHEMA) must
    gain the column and have every existing row classified as 'ISI' the next
    time init_db runs -- this is what makes the migration self-healing after
    a Render free-tier reset restores an old clients.db."""
    db_path = tmp_path / "clients.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE clients (
            client_id TEXT PRIMARY KEY, name TEXT NOT NULL, company TEXT, email TEXT,
            phone TEXT, cert_name TEXT, cert_id TEXT, issue_date TEXT, expiry_date TEXT,
            expiry_date_iso TEXT, renewal_link TEXT, status TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO clients (client_id, name, cert_name, status) VALUES (?, ?, ?, ?)",
        ("CLT001", "Pre-Migration Client", "IS 1717", "CRITICAL"),
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(clients)")}
    scheme = conn.execute("SELECT scheme FROM clients WHERE client_id = 'CLT001'").fetchone()[0]
    conn.close()
    assert "scheme" in columns
    assert scheme == "ISI"


def test_init_db_migration_does_not_overwrite_an_existing_scheme_value(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Future Scheme Client", "Co", "c@x.com", "1", "FMCS-1", "FMCS", "FMCS-ID-1",
         "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ], mode="replace")

    init_db(db_path)  # must not re-run the backfill over an already-set value

    record = find_client_by_id(db_path, "CLT001")
    assert record["scheme"] == "FMCS"


def test_get_clients_page_filters_by_scheme(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, scheme="FMCS")
    assert total == 1
    assert rows[0]["client_id"] == "CLT004"


def test_export_clients_rows_filters_by_scheme(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = list(export_clients_rows(db_path, scheme="FMCS"))
    assert {r["client_id"] for r in rows} == {"CLT004"}


def test_get_stats_schemes_are_distinct_and_sorted(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    assert stats["schemes"] == ["FMCS", "ISI"]


def test_get_eligible_clients_filters_by_scheme(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = get_eligible_clients(db_path, scheme="ISI")
    # CLT004 is scheme FMCS but also ACTIVE (not alert-eligible) -- this
    # confirms the scheme filter and alert-eligibility both apply, not
    # either alone.
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT002", "CLT003", "CLT005"}


def test_get_eligible_count_filters_by_scheme(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp", scheme="FMCS") == 0
    assert get_eligible_count(db_path, today="2026-07-21", channel="whatsapp", scheme="ISI") == 4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/test_db.py
git commit -m "test: cover scheme migration and filtering in db.py"
```

---

### Task 3: `import_bis_isi_data.py` — hardcode `scheme="ISI"`, fix index-based tests

**Files:**
- Modify: `dashboard-app/backend/import_bis_isi_data.py`
- Modify: `dashboard-app/backend/test_import_bis_isi_data.py`

- [ ] **Step 1: Write the failing test**

Add to `test_import_bis_isi_data.py`, at the end of the file:

```python
def test_produced_rows_are_tagged_with_isi_scheme():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "4631257", "Prayagh Consumer Care Pvt. Unit II", "Addr", "Mahbubnagar",
         "Telangana", "509316", "info@prayagh.com", "2026-08-31", "Operative", "-", ""],
    ])
    collector = RowCollector()

    import_bis_isi_workbook(wb, collector)

    assert collector.rows[0][6] == "ISI"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/backend && python -m pytest test_import_bis_isi_data.py::test_produced_rows_are_tagged_with_isi_scheme -v`
Expected: FAIL — `collector.rows[0][6]` is currently the licence number (cert_id), not `"ISI"`.

- [ ] **Step 3: Insert `scheme="ISI"` into the produced row**

Current:

```python
            out_ws.append([
                client_id,
                firm_name,
                firm_name,
                email,
                None,
                cert_name,
                str(licence_no).strip(),
                None,
                expiry_dt.strftime("%d-%m-%Y"),
                None,
                compute_status(expiry_dt, today),
            ])
```

Replace with:

```python
            out_ws.append([
                client_id,
                firm_name,
                firm_name,
                email,
                None,
                cert_name,
                "ISI",
                str(licence_no).strip(),
                None,
                expiry_dt.strftime("%d-%m-%Y"),
                None,
                compute_status(expiry_dt, today),
            ])
```

Also update `OUTPUT_HEADERS` for consistency with the new roster shape (used by `import_bis_isi()`'s standalone CLI output file, not by the dashboard's own upload path). Current:

```python
OUTPUT_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

Replace with:

```python
OUTPUT_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Scheme", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

- [ ] **Step 4: Fix the two existing tests that index into rows by position**

The new `scheme` element at index 6 shifts what used to be at index 6 (the licence number / cert_id) to index 7. `row[5]` (cert_name) is unaffected since the insertion happens *after* it. Current:

```python
def test_single_sheet_uses_per_row_standard_column_as_cert_name():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "4631257", "Prayagh Consumer Care Pvt. Unit II", "Addr", "Mahbubnagar",
         "Telangana", "509316", "info@prayagh.com", "2026-08-31", "Operative", "-", ""],
        [2, "IS 10124 Part 2", "6298283", "Sudhakar PVC Products Private Limited", "Addr",
         "Suryapet", "Telangana", "508213", "sudhakar@x.com", "2026-12-31", "Operative", "Show Variety", ""],
    ])
    collector = RowCollector()

    stats = import_bis_isi_workbook(wb, collector)

    assert stats["rows_written"] == 2
    cert_name_by_licence = {row[6]: row[5] for row in collector.rows}
    assert cert_name_by_licence["4631257"] == "IS 1008"
    assert cert_name_by_licence["6298283"] == "IS 10124 Part 2"
```

Replace with:

```python
def test_single_sheet_uses_per_row_standard_column_as_cert_name():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "4631257", "Prayagh Consumer Care Pvt. Unit II", "Addr", "Mahbubnagar",
         "Telangana", "509316", "info@prayagh.com", "2026-08-31", "Operative", "-", ""],
        [2, "IS 10124 Part 2", "6298283", "Sudhakar PVC Products Private Limited", "Addr",
         "Suryapet", "Telangana", "508213", "sudhakar@x.com", "2026-12-31", "Operative", "Show Variety", ""],
    ])
    collector = RowCollector()

    stats = import_bis_isi_workbook(wb, collector)

    assert stats["rows_written"] == 2
    # row[6] is now scheme ("ISI" for every row here); the licence number
    # (what used to be at index 6) shifted to index 7.
    cert_name_by_licence = {row[7]: row[5] for row in collector.rows}
    assert cert_name_by_licence["4631257"] == "IS 1008"
    assert cert_name_by_licence["6298283"] == "IS 10124 Part 2"
```

`test_single_sheet_dedups_same_licence_no_across_different_standards` reads `row[0]` (client_id), which is unaffected — no change needed there. `test_row_with_blank_standard_falls_back_to_sheet_name` and `test_old_multi_sheet_format_without_standard_column_still_uses_sheet_name` both read `row[5]` (cert_name), also unaffected — no changes needed for either.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_import_bis_isi_data.py -v`
Expected: all passed.

- [ ] **Step 6: Confirm `test_main.py`'s BIS ISI upload/merge tests still pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k bis_isi -v`
Expected: FAIL at this point — this is expected and fixed in Task 6, which updates `test_main.py`'s own fixtures. Do not attempt to fix `test_main.py` here; just confirm the failure is the same "missing scheme value" class of failure described in Task 1 Step 7, not something new.

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/import_bis_isi_data.py dashboard-app/backend/test_import_bis_isi_data.py
git commit -m "feat: tag every BIS ISI-imported row with scheme='ISI'"
```

---

### Task 4: `whatsapp_renewal_alerts.py` — `run()` accepts `scheme`, fix test fixtures

**Files:**
- Modify: `dashboard-app/backend/whatsapp_renewal_alerts.py`
- Modify: `dashboard-app/backend/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Add `scheme` to `run()`**

Current:

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
    search: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before, search=search,
    )
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
    search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
```

- [ ] **Step 2: Fix the test fixtures**

`ONE_CRITICAL_ROW` is defined once and referenced by name in five tests — only its definition needs editing. Current:

```python
ONE_CRITICAL_ROW = [
    ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
     "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026",
     "https://x/renew?id=ISO-1", "CRITICAL"],
]
```

Replace with:

```python
ONE_CRITICAL_ROW = [
    ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
     "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
     "https://x/renew?id=ISO-1", "CRITICAL"],
]
```

`test_read_clients_and_filter_alertable` has five inline rows, all unique. Current:

```python
    _write_db(db_path, [
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
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
        ["CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919898765432",
         "GMP", "ISI", "GMP-1", "01-01-2025", "10-09-2026",
         "https://x/renew?id=GMP-1", "DUE SOON"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISI", "ISO27-1", "01-01-2025", "15-10-2026",
         "https://x/renew?id=ISO27-1", "ACTIVE"],
        ["CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "919654321098",
         "HACCP", "ISI", "HACCP-1", "01-01-2025", "12-07-2026",
         "https://x/renew?id=HACCP-1", "EXPIRED"],
    ])
```

`test_read_clients_skips_blank_rows`. Current:

```python
    _write_db(db_path, [
        ["CLT001", "Name", "Co", "e@x.com", "919876543210", "Cert", "C-1",
         "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        [None, None, None, None, None, None, None, None, None, None, None],
        ["CLT002", "Name2", "Co2", "e2@x.com", "919876543211", "Cert2", "C-2",
         "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "Name", "Co", "e@x.com", "919876543210", "Cert", "ISI", "C-1",
         "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        [None, None, None, None, None, None, None, None, None, None, None, None],
        ["CLT002", "Name2", "Co2", "e2@x.com", "919876543211", "Cert2", "ISI", "C-2",
         "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
```

`test_run_dry_run_honors_dedup_log_for_already_sent_client`. Current:

```python
    _write_db(db_path, [
        ["CLT001", "Already Sent", "Co1", "a@x.com", "919111111111",
         "Cert1", "C-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-1", "CRITICAL"],
        ["CLT002", "Not Sent Yet", "Co2", "b@x.com", "919222222222",
         "Cert2", "C-2", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-2", "URGENT"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "Already Sent", "Co1", "a@x.com", "919111111111",
         "Cert1", "ISI", "C-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-1", "CRITICAL"],
        ["CLT002", "Not Sent Yet", "Co2", "b@x.com", "919222222222",
         "Cert2", "ISI", "C-2", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-2", "URGENT"],
    ])
```

`test_run_mixed_outcomes_in_single_call_preserves_earlier_successes`. Current:

```python
    _write_db(db_path, [
        ["CLT001", "Already Sent", "Co1", "a@x.com", "919111111111",
         "Cert1", "C-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-1", "CRITICAL"],
        ["CLT002", "New Success", "Co2", "b@x.com", "919222222222",
         "Cert2", "C-2", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-2", "URGENT"],
        ["CLT003", "Bad Date", "Co3", "c@x.com", "919333333333",
         "Cert3", "C-3", "01-01-2025", "not-a-date",
         "https://x/renew?id=C-3", "DUE SOON"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "Already Sent", "Co1", "a@x.com", "919111111111",
         "Cert1", "ISI", "C-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-1", "CRITICAL"],
        ["CLT002", "New Success", "Co2", "b@x.com", "919222222222",
         "Cert2", "ISI", "C-2", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-2", "URGENT"],
        ["CLT003", "Bad Date", "Co3", "c@x.com", "919333333333",
         "Cert3", "ISI", "C-3", "01-01-2025", "not-a-date",
         "https://x/renew?id=C-3", "DUE SOON"],
    ])
```

`test_run_filters_by_cert_type` and `test_run_filters_by_search` share this exact 2-row block — use `replace_all: true` (2 occurrences). Current:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
    ])
```

Replace with (both occurrences):

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
    ])
```

`test_run_calls_on_progress_for_each_record` and `test_run_survives_raising_on_progress_and_still_persists_sent_log` share this exact 2-row block (a slightly different literal than the one above — single-line format, both dated `24-07-2026`) — use `replace_all: true` (2 occurrences). Current:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
```

Replace with (both occurrences):

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
```

- [ ] **Step 3: Run the file to confirm existing tests pass again**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: all previously-existing tests pass.

- [ ] **Step 4: Add a new test for the `scheme` filter**

Add after `test_run_filters_by_search`:

```python
def test_run_filters_by_scheme(tmp_path):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=FMCS-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn, scheme="FMCS")

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/whatsapp_renewal_alerts.py dashboard-app/backend/test_whatsapp_renewal_alerts.py
git commit -m "feat: run() accepts an optional scheme filter"
```

---

### Task 5: `email_alerts.py` — `run_email_alerts()` accepts `scheme`, fix test fixtures

**Files:**
- Modify: `dashboard-app/backend/email_alerts.py`
- Modify: `dashboard-app/backend/test_email_alerts.py`

- [ ] **Step 1: Add `scheme` to `run_email_alerts()`**

Current:

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
    search: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before, search=search,
    )
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
    search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
```

- [ ] **Step 2: Fix the three row fixtures**

`_record_dict` zips `row` against `RECORD_FIELDS` dynamically, so no code changes are needed beyond the row tuples themselves. Current:

```python
ROW_WITH_EMAIL = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
                    "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                 "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
ROW_INVALID_EMAIL = ("CLT003", "Amit Verma", "HealthFirst", "not-an-email", "919800000000",
                       "ISO 9001", "ISO27-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON")
```

Replace with:

```python
ROW_WITH_EMAIL = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
                    "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                 "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
ROW_INVALID_EMAIL = ("CLT003", "Amit Verma", "HealthFirst", "not-an-email", "919800000000",
                       "ISO 9001", "ISI", "ISO27-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON")
```

- [ ] **Step 3: Run the file to confirm existing tests pass again**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all previously-existing tests pass.

- [ ] **Step 4: Add a new test for the `scheme` filter**

Add after `test_run_email_alerts_filters_by_search`:

```python
def test_run_email_alerts_filters_by_scheme(tmp_path):
    db_path = tmp_path / "clients.db"
    fmcs_row = ("CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
                "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
    upsert_clients(db_path, [ROW_WITH_EMAIL, fmcs_row], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn, scheme="FMCS",
    )

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT004"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/email_alerts.py dashboard-app/backend/test_email_alerts.py
git commit -m "feat: run_email_alerts() accepts an optional scheme filter"
```

---

### Task 6: `main.py` — `REQUIRED_HEADERS`, CSV export, all endpoints; fix `test_main.py` fixtures

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Add "Scheme" to `REQUIRED_HEADERS`**

Current:

```python
REQUIRED_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

Replace with:

```python
REQUIRED_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Scheme", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

- [ ] **Step 2: Add `scheme` to `/api/clients`**

Current:

```python
@app.get("/api/clients", dependencies=[Depends(require_auth)])
def get_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    status: str = "ALL", cert_type: str = "ALL",
    expiry_before: str = "", search: str = "", sort_key: str = "", sort_dir: str = "asc",
):
    today = _today_str()
    rows, total = get_clients_page(
        DEFAULT_DB_PATH, page=page, page_size=page_size,
        status=status, cert_type=cert_type, expiry_before=expiry_before or None,
        search=search or None, sort_key=sort_key or None, sort_dir=sort_dir.lower(),
    )
```

Replace with:

```python
@app.get("/api/clients", dependencies=[Depends(require_auth)])
def get_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    status: str = "ALL", cert_type: str = "ALL", scheme: str = "ALL",
    expiry_before: str = "", search: str = "", sort_key: str = "", sort_dir: str = "asc",
):
    today = _today_str()
    rows, total = get_clients_page(
        DEFAULT_DB_PATH, page=page, page_size=page_size,
        status=status, cert_type=cert_type, scheme=scheme, expiry_before=expiry_before or None,
        search=search or None, sort_key=sort_key or None, sort_dir=sort_dir.lower(),
    )
```

- [ ] **Step 3: Add `scheme` to `/api/eligible-count`**

Current:

```python
@app.get("/api/eligible-count", dependencies=[Depends(require_auth)])
def eligible_count(status: str = "", cert_type: str = "", expiry_before: str = "", search: str = ""):
    today = _today_str()
    return {
        "whatsapp": get_eligible_count(
            DEFAULT_DB_PATH, today, "whatsapp",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
            search=search or None,
        ),
        "email": get_eligible_count(
            DEFAULT_DB_PATH, today, "email",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
            search=search or None,
        ),
    }
```

Replace with:

```python
@app.get("/api/eligible-count", dependencies=[Depends(require_auth)])
def eligible_count(
    status: str = "", cert_type: str = "", expiry_before: str = "", search: str = "", scheme: str = "",
):
    today = _today_str()
    return {
        "whatsapp": get_eligible_count(
            DEFAULT_DB_PATH, today, "whatsapp",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
        "email": get_eligible_count(
            DEFAULT_DB_PATH, today, "email",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
    }
```

- [ ] **Step 4: Add `scheme` to `/api/clients/export` and the CSV column list**

Current:

```python
@app.get("/api/clients/export", dependencies=[Depends(require_auth)])
def export_clients(status: str = "ALL", cert_type: str = "ALL", expiry_before: str = "", search: str = ""):
    def generate():
        yield ",".join(_csv_escape(h) for h in REQUIRED_HEADERS) + "\n"
        for rec in export_clients_rows(
            DEFAULT_DB_PATH, status=status, cert_type=cert_type,
            expiry_before=expiry_before or None, search=search or None,
        ):
            values = [
                rec["client_id"], rec["name"], rec["company"], rec["email"], rec["phone"],
                rec["cert_name"], rec["cert_id"], rec["issue_date"], rec["expiry_date"],
                rec["renewal_link"], rec["status"],
            ]
            yield ",".join(_csv_escape(v) for v in values) + "\n"
```

Replace with:

```python
@app.get("/api/clients/export", dependencies=[Depends(require_auth)])
def export_clients(
    status: str = "ALL", cert_type: str = "ALL", expiry_before: str = "", search: str = "", scheme: str = "ALL",
):
    def generate():
        yield ",".join(_csv_escape(h) for h in REQUIRED_HEADERS) + "\n"
        for rec in export_clients_rows(
            DEFAULT_DB_PATH, status=status, cert_type=cert_type, scheme=scheme,
            expiry_before=expiry_before or None, search=search or None,
        ):
            values = [
                rec["client_id"], rec["name"], rec["company"], rec["email"], rec["phone"],
                rec["cert_name"], rec["scheme"], rec["cert_id"], rec["issue_date"], rec["expiry_date"],
                rec["renewal_link"], rec["status"],
            ]
            yield ",".join(_csv_escape(v) for v in values) + "\n"
```

- [ ] **Step 5: Add `scheme` to `/api/send-all` and `_run_send_all_job`**

Current:

```python
def _run_send_all_job(
    job_id, token, phone_number_id, template_name, template_lang, test_number,
    status=None, cert_type=None, expiry_before=None, search=None,
):
```

Replace with:

```python
def _run_send_all_job(
    job_id, token, phone_number_id, template_name, template_lang, test_number,
    status=None, cert_type=None, expiry_before=None, search=None, scheme=None,
):
```

Current:

```python
    try:
        run(
            DEFAULT_DB_PATH, token, phone_number_id, template_name, template_lang,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search,
        )
    except Exception as exc:
        # Without this, an exception here (locked DB, unexpected error mid-
```

Replace with:

```python
    try:
        run(
            DEFAULT_DB_PATH, token, phone_number_id, template_name, template_lang,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
        )
    except Exception as exc:
        # Without this, an exception here (locked DB, unexpected error mid-
```

Current:

```python
@app.post("/api/send-all", dependencies=[Depends(require_auth)])
def send_all_alerts(status: str = "", cert_type: str = "", expiry_before: str = "", search: str = ""):
```

Replace with:

```python
@app.post("/api/send-all", dependencies=[Depends(require_auth)])
def send_all_alerts(
    status: str = "", cert_type: str = "", expiry_before: str = "", search: str = "", scheme: str = "",
):
```

Current:

```python
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(
                job_id, token, phone_number_id, template_name, template_lang, test_number,
                status or None, cert_type or None, expiry_before or None, search or None,
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

Replace with:

```python
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(
                job_id, token, phone_number_id, template_name, template_lang, test_number,
                status or None, cert_type or None, expiry_before or None, search or None, scheme or None,
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

- [ ] **Step 6: Add `scheme` to `/api/send-all-emails` and `_run_send_all_email_job`**

Current:

```python
def _run_send_all_email_job(
    job_id, brevo_api_key, email_sender, test_email,
    status=None, cert_type=None, expiry_before=None, search=None,
):
```

Replace with:

```python
def _run_send_all_email_job(
    job_id, brevo_api_key, email_sender, test_email,
    status=None, cert_type=None, expiry_before=None, search=None, scheme=None,
):
```

Current:

```python
    try:
        run_email_alerts(
            DEFAULT_DB_PATH, brevo_api_key, email_sender, "Absolute Veritas",
            dry_run=False, test_email=test_email, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search,
        )
    except Exception as exc:
        _send_all_email_jobs[job_id]["error"] = str(exc)
```

Replace with:

```python
    try:
        run_email_alerts(
            DEFAULT_DB_PATH, brevo_api_key, email_sender, "Absolute Veritas",
            dry_run=False, test_email=test_email, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before,
            search=search, scheme=scheme,
        )
    except Exception as exc:
        _send_all_email_jobs[job_id]["error"] = str(exc)
```

Current:

```python
@app.post("/api/send-all-emails", dependencies=[Depends(require_auth)])
def send_all_emails(status: str = "", cert_type: str = "", expiry_before: str = "", search: str = ""):
```

Replace with:

```python
@app.post("/api/send-all-emails", dependencies=[Depends(require_auth)])
def send_all_emails(
    status: str = "", cert_type: str = "", expiry_before: str = "", search: str = "", scheme: str = "",
):
```

Current:

```python
        thread = threading.Thread(
            target=_run_send_all_email_job,
            args=(
                job_id, brevo_api_key, email_sender, test_email,
                status or None, cert_type or None, expiry_before or None, search or None,
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

Replace with:

```python
        thread = threading.Thread(
            target=_run_send_all_email_job,
            args=(
                job_id, brevo_api_key, email_sender, test_email,
                status or None, cert_type or None, expiry_before or None, search or None, scheme or None,
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

- [ ] **Step 7: Update the `HEADERS` list in `test_main.py`**

Current:

```python
HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

Replace with:

```python
HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Scheme", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

- [ ] **Step 8: Fix every repeated row-literal pattern in `test_main.py` with `replace_all: true`**

Each block below is one `Edit` call with `replace_all: true`, since the exact text repeats verbatim across multiple tests.

Pattern 1 (appears in `test_get_clients_paginates_and_reports_total`, `test_get_clients_merges_alert_sent_today`, `test_get_stats_returns_counts_and_cert_types`, `test_eligible_count_returns_both_channels`, `test_eligible_count_filters_by_cert_type`, `test_eligible_count_filters_by_search`, `test_eligible_count_excludes_already_sent_today`, `test_send_all_respects_cert_type_filter`, `test_send_all_respects_search_filter`, `test_send_all_emails_respects_cert_type_filter`, `test_send_all_emails_respects_search_filter`, `test_export_clients_streams_csv_with_all_matching_rows`, `test_get_clients_rejects_out_of_range_pagination_params`, `test_email_preview_returns_subject_and_html`, `test_message_log_returns_entries_joined_with_client_data`, `test_send_all_starts_job_and_reports_progress`, `test_send_all_reports_sent_for_all_alertable_statuses`, `test_send_all_uses_dashboard_test_number_override`, `test_send_all_job_reports_error_when_run_raises`, `test_send_all_job_error_is_none_on_success`, `test_send_all_missing_env_var_resets_bulk_in_progress_flag`, plus the `_write_xlsx(...)` occurrences covered by Pattern 7 below — use `replace_all: true` and let it catch every one; the exact count doesn't matter, Step 10's full-file test run is what confirms nothing was missed). Current:

```python
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
```

Replace with (`replace_all: true`):

```python
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
```

Pattern 2 (appears in `test_get_clients_filters_by_status_param`, `test_eligible_count_returns_both_channels`, `test_eligible_count_filters_by_cert_type`, `test_eligible_count_filters_by_search`, `test_send_all_respects_cert_type_filter`, `test_send_all_respects_search_filter`, `test_send_all_emails_respects_cert_type_filter`, `test_send_all_emails_respects_search_filter`, `test_export_clients_streams_csv_with_all_matching_rows`, `test_send_all_reports_sent_for_all_alertable_statuses`, and `test_merge_clients_skips_duplicate_client_ids`'s uploaded CLT002 row — use `replace_all: true` and let it catch every one, this same exact text also appears inside `test_merge_clients_skips_duplicate_client_ids`, which is why that test's Step 9 edit below only touches its CLT001 line, not CLT002). Current:

```python
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
```

Replace with (`replace_all: true`):

```python
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
```

Pattern 3 (appears in `test_get_clients_paginates_and_reports_total`, `test_get_clients_merges_alert_sent_today`, `test_get_clients_filters_by_status_param`, `test_eligible_count_returns_both_channels`, `test_send_all_reports_sent_for_all_alertable_statuses` — 5 occurrences). Current:

```python
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
```

Replace with (`replace_all: true`):

```python
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISI", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
```

Pattern 4 (appears in `test_upload_clients_backs_up_existing_file`, `test_upload_clients_rejects_blank_name_with_400_not_500`, `test_merge_clients_adds_new_and_keeps_existing`, `test_merge_clients_rejects_blank_name_with_400_and_rolls_back_batch`, `test_merge_clients_backs_up_existing_file` — 5 occurrences). Current:

```python
        ["CLT999", "Old Client", "OldCo", "o@x.com", "919999999999",
         "Old Cert", "OLD-1", "01-01-2025", "01-01-2026", "https://x", "ACTIVE"],
```

Replace with (`replace_all: true`):

```python
        ["CLT999", "Old Client", "OldCo", "o@x.com", "919999999999",
         "Old Cert", "ISI", "OLD-1", "01-01-2025", "01-01-2026", "https://x", "ACTIVE"],
```

Pattern 5 (`_setup_one_client`, uses a `status` variable, not a literal — appears once). Current:

```python
def _setup_one_client(tmp_path, monkeypatch, status="CRITICAL"):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
```

Replace with:

```python
def _setup_one_client(tmp_path, monkeypatch, status="CRITICAL"):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
```

Pattern 6 (`_setup_one_email_client`, same shape, appears once). Current:

```python
def _setup_one_email_client(tmp_path, monkeypatch, status="CRITICAL"):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
```

Replace with:

```python
def _setup_one_email_client(tmp_path, monkeypatch, status="CRITICAL"):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
```

Pattern 7 -- `test_upload_clients_success`, `test_upload_clients_backs_up_existing_file` (the *uploaded* row, via `_write_xlsx`), `test_merge_clients_adds_new_and_keeps_existing`, `test_merge_clients_into_empty_roster`, `test_merge_clients_rejects_blank_name_with_400_and_rolls_back_batch` (the first, valid row), `test_merge_clients_backs_up_existing_file` -- this is the same literal as Pattern 1 (`CLT001 Rahul Sharma ... CRITICAL`) but that `replace_all: true` edit in Pattern 1 already covers every occurrence of this exact text anywhere in the file, including inside `_write_xlsx(...)` calls -- no separate step needed.

- [ ] **Step 9: Fix the remaining unique row literals individually**

`test_get_clients_sort_dir_is_case_insensitive`. Current:

```python
    _write_db(db_path, [
        ["CLT001", "B Name", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "A Name", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "B Name", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "A Name", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
```

`test_export_clients_escapes_leading_formula_characters`. Current:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "=cmd|'/c calc'!A1", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "=cmd|'/c calc'!A1", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
```

`test_upload_clients_rejects_blank_name_with_400_not_500`'s uploaded (invalid) row. Current:

```python
    _write_xlsx(upload_path, [
        ["CLT001", None, "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
```

Replace with:

```python
    _write_xlsx(upload_path, [
        ["CLT001", None, "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
```

`test_merge_clients_skips_duplicate_client_ids`'s existing (old-data) row. Current:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma (old data)", "TechCorp", "old@x.com", "919999999999",
         "ISO 9001", "ISO-1", "01-01-2025", "01-01-2026", "https://x", "ACTIVE"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma (old data)", "TechCorp", "old@x.com", "919999999999",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "01-01-2026", "https://x", "ACTIVE"],
    ])
```

`test_merge_clients_skips_duplicate_client_ids`'s uploaded CLT001 row (its CLT002 row right below it is already covered by Pattern 2's `replace_all` above — do not edit it again here, the search string below only spans the CLT001 line so it won't touch CLT002). Current:

```python
        ["CLT001", "Rahul Sharma (new data)", "TechCorp", "new@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
```

Replace with:

```python
        ["CLT001", "Rahul Sharma (new data)", "TechCorp", "new@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
```

`test_merge_clients_converts_and_merges_raw_bis_isi_workbook`'s pre-seeded existing row (this simulates a row the BIS ISI importer already produced, so it must also carry `scheme="ISI"`). Current:

```python
    _write_db(db_path, [
        ["9512485121", "Existing Firm Name", "Existing Firm Name", "existing@x.com", None,
         "IS 302 (Part 2 Sec 30)", "9512485121", None, "01-01-2026", None, "ACTIVE"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["9512485121", "Existing Firm Name", "Existing Firm Name", "existing@x.com", None,
         "IS 302 (Part 2 Sec 30)", "ISI", "9512485121", None, "01-01-2026", None, "ACTIVE"],
    ])
```

`test_merge_clients_rejects_blank_name_with_400_and_rolls_back_batch`'s second (invalid) uploaded row. Current:

```python
        ["CLT002", None, "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
```

Replace with:

```python
        ["CLT002", None, "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
```

`test_send_email_no_email_on_file_returns_400`. Current:

```python
    _write_db(db_path, [
        ["CLT005", "No Email Co", "No Email Co", None, "919000000000",
         "ISO 9001", "ISO-5", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
```

Replace with:

```python
    _write_db(db_path, [
        ["CLT005", "No Email Co", "No Email Co", None, "919000000000",
         "ISO 9001", "ISI", "ISO-5", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
```

- [ ] **Step 10: Run the full file to confirm every previously-existing test passes again**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all previously-existing tests pass. Pay particular attention to the BIS ISI upload/merge tests and `test_client_template_returns_header_only_xlsx` (which asserts against the now-updated `HEADERS`).

- [ ] **Step 11: Add new tests for the `scheme` filter and CSV column**

Add after `test_eligible_count_excludes_already_sent_today` (these don't depend on any specific neighboring test — placement is just for grouping with the other `/api/eligible-count` tests):

```python
def test_get_clients_filters_by_scheme_param(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients", params={"scheme": "FMCS", "page_size": 50})
    data = response.json()["rows"]
    assert len(data) == 1
    assert data[0]["client_id"] == "CLT002"


def test_eligible_count_filters_by_scheme(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/eligible-count", params={"scheme": "FMCS"})
    assert response.json() == {"whatsapp": 1, "email": 1}


def test_send_all_respects_scheme_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all", params={"scheme": "FMCS"})
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


def test_export_clients_includes_scheme_column(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    response = client.get("/api/clients/export")
    assert response.status_code == 200
    lines = response.text.splitlines()
    assert lines[0].split(",")[6] == "Scheme"
    data_line = next(line for line in lines if "CLT001" in line)
    assert data_line.split(",")[6] == "ISI"
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed.

- [ ] **Step 13: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add scheme to REQUIRED_HEADERS, CSV export, and every filterable endpoint"
```

---

### Task 7: Frontend `api.js` — `scheme` in every filter-carrying function

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Update the three existing "adds ... as query params when given" tests to include `scheme`. Current (`sendAllAlerts`):

```javascript
  it("adds status/cert_type/expiry_before/search as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllAlerts({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight",
      { method: "POST", credentials: "include", headers: {} }
    );
  });
```

Replace with:

```javascript
  it("adds status/cert_type/expiry_before/search/scheme as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllAlerts({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight&scheme=ISI",
      { method: "POST", credentials: "include", headers: {} }
    );
  });
```

Current (`sendAllEmailAlerts`):

```javascript
  it("adds status/cert_type/expiry_before/search as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllEmailAlerts({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all-emails?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight",
      { method: "POST", credentials: "include", headers: {} }
    );
  });
```

Replace with:

```javascript
  it("adds status/cert_type/expiry_before/search/scheme as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllEmailAlerts({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all-emails?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight&scheme=ISI",
      { method: "POST", credentials: "include", headers: {} }
    );
  });
```

Current (`getEligibleCount`):

```javascript
  it("passes status/cert_type/expiry_before/search as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 1, email: 1 }) });
    await getEligibleCount({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/eligible-count?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight",
      { credentials: "include", headers: {} }
    );
  });
```

Replace with:

```javascript
  it("passes status/cert_type/expiry_before/search/scheme as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 1, email: 1 }) });
    await getEligibleCount({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/eligible-count?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight&scheme=ISI",
      { credentials: "include", headers: {} }
    );
  });
```

Add a new test to the `describe("getClients", ...)` block, right before its closing `});`:

```javascript
  it("passes scheme as a query param when given", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ rows: [], total: 0, page: 1, page_size: 50 }),
    });
    await getClients({ scheme: "FMCS" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/clients?scheme=FMCS",
      { credentials: "include", headers: {} }
    );
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: FAIL — none of `getClients`/`sendAllAlerts`/`sendAllEmailAlerts`/`getEligibleCount` currently recognize a `scheme` param.

- [ ] **Step 3: Update `api.js`**

Current:

```javascript
export async function getClients(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.sortKey) query.set("sort_key", params.sortKey);
  if (params.sortDir) query.set("sort_dir", params.sortDir);
  const qs = query.toString();
```

Replace with:

```javascript
export async function getClients(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.scheme && params.scheme !== "ALL") query.set("scheme", params.scheme);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.sortKey) query.set("sort_key", params.sortKey);
  if (params.sortDir) query.set("sort_dir", params.sortDir);
  const qs = query.toString();
```

Current:

```javascript
function scopeQueryString(params = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  return query.toString();
}
```

Replace with:

```javascript
function scopeQueryString(params = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.scheme && params.scheme !== "ALL") query.set("scheme", params.scheme);
  return query.toString();
}
```

(`scopeQueryString` is shared by `sendAllAlerts`, `sendAllEmailAlerts`, and `getEligibleCount` — this one change covers all three.)

Current:

```javascript
export function clientsExportUrl({ status, certType, expiryBefore, search } = {}) {
  const query = new URLSearchParams();
  if (status && status !== "ALL") query.set("status", status);
  if (certType && certType !== "ALL") query.set("cert_type", certType);
  if (expiryBefore) query.set("expiry_before", expiryBefore);
  if (search) query.set("search", search);
  const qs = query.toString();
  return `${API_BASE}${qs ? `/api/clients/export?${qs}` : "/api/clients/export"}`;
}
```

Replace with:

```javascript
export function clientsExportUrl({ status, certType, expiryBefore, search, scheme } = {}) {
  const query = new URLSearchParams();
  if (status && status !== "ALL") query.set("status", status);
  if (certType && certType !== "ALL") query.set("cert_type", certType);
  if (scheme && scheme !== "ALL") query.set("scheme", scheme);
  if (expiryBefore) query.set("expiry_before", expiryBefore);
  if (search) query.set("search", search);
  const qs = query.toString();
  return `${API_BASE}${qs ? `/api/clients/export?${qs}` : "/api/clients/export"}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed, including every pre-existing test (all existing calls omit `scheme`, which the `&&` guards treat identically to omitting `certType`).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: add scheme as a filter param to getClients, clientsExportUrl, and the bulk-send/eligible-count helpers"
```

---

### Task 8: `ClientDataFilters.jsx` — Scheme dropdown

**Files:**
- Modify: `dashboard-app/frontend/src/components/ClientDataFilters.jsx`
- Modify: `dashboard-app/frontend/src/components/ClientDataFilters.test.jsx`

- [ ] **Step 1: Write the failing tests**

None of the file's existing tests pass `scheme`/`schemeOptions`/`onSchemeChange` props, so the component must default them gracefully (`scheme = "ALL"`, `schemeOptions = []`, `onSchemeChange = () => {}`) — this means no existing test needs to change. Add these new tests inside the existing `describe("ClientDataFilters", ...)` block, after the "calls onCertTypeChange..." test:

```javascript
  it("calls onSchemeChange when a scheme is selected", () => {
    const onSchemeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        schemeOptions={["ISI", "FMCS"]}
        scheme="ALL"
        onSchemeChange={onSchemeChange}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by scheme"), { target: { value: "FMCS" } });
    expect(onSchemeChange).toHaveBeenCalledWith("FMCS");
  });

  it("shows Clear All when a scheme filter is active", () => {
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        schemeOptions={["ISI", "FMCS"]}
        scheme="FMCS"
        onSchemeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.getByText("Clear All")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ClientDataFilters.test.jsx`
Expected: FAIL — `getByLabelText("Filter by scheme")` finds nothing, since the dropdown doesn't exist yet.

- [ ] **Step 3: Add the Scheme dropdown**

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
```

Replace with:

```javascript
export default function ClientDataFilters({
  certOptions, certType, onCertTypeChange,
  schemeOptions = [], scheme = "ALL", onSchemeChange = () => {},
  expiryBefore, onExpiryBeforeChange, onClearAll,
}) {
  const hasFilters = certType !== "ALL" || scheme !== "ALL" || expiryBefore !== "";

  return (
    <div className="bg-surface border border-line rounded-xl p-4 flex flex-wrap gap-4 items-center">
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
        Filter by
      </span>
      <select
        value={scheme}
        onChange={(e) => onSchemeChange(e.target.value)}
        aria-label="Filter by scheme"
        className="min-w-[150px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <option value="ALL">All Schemes</option>
        {schemeOptions.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ClientDataFilters.test.jsx`
Expected: all passed, including every pre-existing test (all of them omit the three new props, which now default to `"ALL"`/`[]`/a no-op, so `hasFilters` and rendering behave exactly as before for them).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/ClientDataFilters.jsx dashboard-app/frontend/src/components/ClientDataFilters.test.jsx
git commit -m "feat: add a Scheme filter dropdown to ClientDataFilters"
```

---

### Task 9: `App.jsx` — wire `scheme` state everywhere `certType` already flows

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Modify: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

Update every existing exact-shape assertion that currently omits `scheme` (the filters object passed to `sendAllAlerts`/`sendAllEmailAlerts`/`getEligibleCount` always includes every key from `activeStatus`/`certType`/`expiryBefore`/`debouncedSearch`, so adding `scheme` state means each of these now includes `scheme: "ALL"` too). Current:

```javascript
  it("includes the header search term when 'Currently filtered view' is confirmed for Send All Emails", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllEmailsStatus.mockResolvedValue({
      total: 1, sent: 1, skipped: 0, skipped_no_email: 0, failed: 0, done: true,
    });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Emails"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllEmailAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });
```

Replace with:

```javascript
  it("includes the header search term when 'Currently filtered view' is confirmed for Send All Emails", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllEmailsStatus.mockResolvedValue({
      total: 1, sent: 1, skipped: 0, skipped_no_email: 0, failed: 0, done: true,
    });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Emails"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllEmailAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });
```

Current:

```javascript
  it("fetches the eligible count for the current filters when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", expiryBefore: "", search: "",
      })
    );
  });
```

Replace with:

```javascript
  it("fetches the eligible count for the current filters when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "",
      })
    );
  });
```

Current:

```javascript
  it("includes the header search term in the eligible count fetched when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });
```

Replace with:

```javascript
  it("includes the header search term in the eligible count fetched when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });
```

Current:

```javascript
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
      expect(api.sendAllAlerts).toHaveBeenCalledWith({
        status: "CRITICAL", certType: "ALL", expiryBefore: "", search: "",
      })
    );
  });
```

Replace with:

```javascript
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
      expect(api.sendAllAlerts).toHaveBeenCalledWith({
        status: "CRITICAL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "",
      })
    );
  });
```

Current:

```javascript
  it("includes the header search term when 'Currently filtered view' is confirmed for Send All Eligible", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });
```

Replace with:

```javascript
  it("includes the header search term when 'Currently filtered view' is confirmed for Send All Eligible", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });
```

`sendAllAlerts` being called with `{}` for the default "all" scope (in `test("sends with no filters when the default 'all eligible' scope is confirmed...")`) needs no change — `{}` stays `{}` regardless of scheme.

Add one new test after `test("includes the header search term when 'Currently filtered view' is confirmed for Send All Eligible", ...)`, right before the closing `});` of the `describe` block:

```javascript
  it("selecting a scheme filters the table and flows into the eligible count and bulk-send scope", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, schemes: ["FMCS", "ISI"] });
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));

    fireEvent.change(screen.getByLabelText("Filter by scheme"), { target: { value: "FMCS" } });
    await waitFor(() =>
      expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ scheme: "FMCS" }))
    );

    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith(
        expect.objectContaining({ scheme: "FMCS" })
      )
    );
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith(
        expect.objectContaining({ scheme: "FMCS" })
      )
    );
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: FAIL — `App.jsx` has no `scheme` state yet, so none of the filter objects include it, and the "Filter by scheme" dropdown doesn't exist.

- [ ] **Step 3: Add `scheme` state and thread it through**

Current:

```javascript
  const [certType, setCertType] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
```

Replace with:

```javascript
  const [certType, setCertType] = useState("ALL");
  const [scheme, setScheme] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
```

Current:

```javascript
  useEffect(() => {
    setPageNum(1);
  }, [activeStatus, debouncedSearch, certType, expiryBefore, sortKey, sortAsc]);

  const queryParams = useMemo(() => ({
    page: pageNum, pageSize: PAGE_SIZE, status: activeStatus, certType,
    expiryBefore, search: debouncedSearch, sortKey, sortDir: sortAsc ? "asc" : "desc",
  }), [pageNum, activeStatus, certType, expiryBefore, debouncedSearch, sortKey, sortAsc]);
```

Replace with:

```javascript
  useEffect(() => {
    setPageNum(1);
  }, [activeStatus, debouncedSearch, certType, scheme, expiryBefore, sortKey, sortAsc]);

  const queryParams = useMemo(() => ({
    page: pageNum, pageSize: PAGE_SIZE, status: activeStatus, certType, scheme,
    expiryBefore, search: debouncedSearch, sortKey, sortDir: sortAsc ? "asc" : "desc",
  }), [pageNum, activeStatus, certType, scheme, expiryBefore, debouncedSearch, sortKey, sortAsc]);
```

Current:

```javascript
  useEffect(() => {
    if (!bulkModalOpen && !emailBulkModalOpen) return;
    const requestId = ++eligibleCountRequestIdRef.current;
    getEligibleCount({ status: activeStatus, certType, expiryBefore, search: debouncedSearch })
      .then((data) => {
        if (requestId !== eligibleCountRequestIdRef.current) return; // a newer request has since been issued — ignore this stale response
        setFilteredEligibleCount(data);
      })
      .catch(() => {});
  }, [bulkModalOpen, emailBulkModalOpen, activeStatus, certType, expiryBefore, debouncedSearch]);
```

Replace with:

```javascript
  useEffect(() => {
    if (!bulkModalOpen && !emailBulkModalOpen) return;
    const requestId = ++eligibleCountRequestIdRef.current;
    getEligibleCount({ status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch })
      .then((data) => {
        if (requestId !== eligibleCountRequestIdRef.current) return; // a newer request has since been issued — ignore this stale response
        setFilteredEligibleCount(data);
      })
      .catch(() => {});
  }, [bulkModalOpen, emailBulkModalOpen, activeStatus, certType, scheme, expiryBefore, debouncedSearch]);
```

Current:

```javascript
  const certOptions = stats?.cert_types || [];
```

Replace with:

```javascript
  const certOptions = stats?.cert_types || [];
  const schemeOptions = stats?.schemes || [];
```

Current:

```javascript
  function handleClearAllFilters() {
    setActiveStatus("ALL");
    setCertType("ALL");
    setExpiryBefore("");
  }
```

Replace with:

```javascript
  function handleClearAllFilters() {
    setActiveStatus("ALL");
    setCertType("ALL");
    setScheme("ALL");
    setExpiryBefore("");
  }
```

Current:

```javascript
  async function handleConfirmSendAll(scope) {
    try {
      const filters = scope === "filtered"
        ? { status: activeStatus, certType, expiryBefore, search: debouncedSearch }
        : {};
```

Replace with:

```javascript
  async function handleConfirmSendAll(sendScope) {
    try {
      const filters = sendScope === "filtered"
        ? { status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch }
        : {};
```

(Renamed the parameter from `scope` to `sendScope` here only because the component now also has a `scheme` state variable in the same closure — `scope` and `scheme` are visually easy to mistake for each other at a glance, and this avoids that entirely. Its `onConfirm={handleConfirmSendAll}` wiring at the bottom of the file is unaffected — it's still called with one string argument, `"all"` or `"filtered"`.)

Current:

```javascript
  async function handleConfirmSendAllEmails(scope) {
    try {
      const filters = scope === "filtered"
        ? { status: activeStatus, certType, expiryBefore, search: debouncedSearch }
        : {};
```

Replace with:

```javascript
  async function handleConfirmSendAllEmails(sendScope) {
    try {
      const filters = sendScope === "filtered"
        ? { status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch }
        : {};
```

Current:

```javascript
              <ClientDataFilters
                certOptions={certOptions}
                certType={certType}
                onCertTypeChange={setCertType}
                expiryBefore={expiryBefore}
                onExpiryBeforeChange={setExpiryBefore}
                onClearAll={handleClearAllFilters}
              />
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

Replace with:

```javascript
              <ClientDataFilters
                certOptions={certOptions}
                certType={certType}
                onCertTypeChange={setCertType}
                schemeOptions={schemeOptions}
                scheme={scheme}
                onSchemeChange={setScheme}
                expiryBefore={expiryBefore}
                onExpiryBeforeChange={setExpiryBefore}
                onClearAll={handleClearAllFilters}
              />
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
                exportFilters={{ status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch }}
              />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: all passed, including every pre-existing test (each already-passing test's assertions were updated in Step 1 above to include `scheme: "ALL"` everywhere it now appears; tests using `expect.objectContaining` or checking `{}` needed no changes).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "feat: wire scheme filter state through App.jsx"
```

---

### Task 10: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -v`
Expected: all tests pass, zero regressions, with roughly 15-20 new tests added across Tasks 1-6.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Verify the migration against a database shaped like production**

Since the real deployed `clients.db` has ~66,745 rows and predates this migration, this step confirms the migration is safe to run against a large pre-existing database, not just the small fixtures used in Task 2's tests:

```bash
cd dashboard-app/backend
python -c "
import sqlite3
from db import init_db, get_stats

# Simulate a large pre-migration database (no scheme column).
conn = sqlite3.connect('/tmp/premigration_test.db')
conn.execute('''
    CREATE TABLE clients (
        client_id TEXT PRIMARY KEY, name TEXT NOT NULL, company TEXT, email TEXT,
        phone TEXT, cert_name TEXT, cert_id TEXT, issue_date TEXT, expiry_date TEXT,
        expiry_date_iso TEXT, renewal_link TEXT, status TEXT NOT NULL
    )
''')
conn.executemany(
    'INSERT INTO clients (client_id, name, cert_name, status) VALUES (?, ?, ?, ?)',
    [(f'CLT{i}', f'Client {i}', 'IS 1717', 'CRITICAL') for i in range(50000)],
)
conn.commit()
conn.close()

init_db('/tmp/premigration_test.db')
stats = get_stats('/tmp/premigration_test.db', today='2026-07-24')
print('schemes:', stats['schemes'])
print('total:', stats['status_counts']['total'])
"
```

Expected output: `schemes: ['ISI']` and `total: 50000`. Delete `/tmp/premigration_test.db` afterward.

- [ ] **Step 4: Manual smoke test against a real dev server**

Start the backend (`cd dashboard-app/backend && python -m uvicorn main:app --port 8040`) and frontend (`cd dashboard-app/frontend && npm run dev`) locally, against real client data. In the browser:
1. Confirm the "Filter by" bar now shows an "All Schemes" dropdown showing "ISI" (the only scheme in the real data) before the "All Cert Types" dropdown.
2. Select "ISI" — confirm the table doesn't change (since every row is ISI) and no console errors appear.
3. Open "Send All Eligible" — confirm "Currently filtered view" reflects the scheme filter correctly.
4. Export CSV — confirm the downloaded file has a "Scheme" column (7th column) with "ISI" values.

Expected: no console errors; every step matches the description above.
