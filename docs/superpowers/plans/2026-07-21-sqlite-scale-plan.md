# SQLite Scale Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the xlsx-as-database pattern in the Absolute Veritas certification dashboard with SQLite, so the app can hold and browse 5 lakh+ client rows without a page load costing a full-file re-read.

**Architecture:** A new `db.py` module owns a single SQLite file (`clients.db`) with a `clients` table (indexed on `status` and `expiry_date_iso`) and a `sent_log` table. `whatsapp_renewal_alerts.py` keeps its existing public function names/signatures wherever possible (minimizing churn to its already-tested send logic) but swaps their internals from xlsx/JSON to SQLite. The FastAPI backend gains pagination, aggregate stats, CSV export, and a background job (with progress polling) for bulk sends. The React frontend's `ClientTable` stops holding the full dataset in memory and fetches one page at a time.

**Tech Stack:** Python stdlib `sqlite3` (no new dependency), existing FastAPI/React stack.

**Reference spec:** `docs/superpowers/specs/2026-07-21-sqlite-scale-design.md`

---

## Design decisions locked in during planning (read before starting)

1. **Date sorting bug avoided:** `expiry_date` is stored as `DD-MM-YYYY` text (matching what the roster/frontend already use for display). Plain string comparison of that format sorts incorrectly (e.g. year boundaries break lexical order). The `clients` table therefore has a second column, `expiry_date_iso` (`YYYY-MM-DD`), computed at insert time and used for all sorting/filtering by date. `expiry_date` (original display string) is still what's returned to the frontend — no frontend date-parsing code changes.
2. **`whatsapp_renewal_alerts.py` keeps its interface:** `read_clients`, `find_client_by_id`, `filter_alertable`, `dedup_key`, `load_sent_log`, `save_sent_log`, `send_one_alert` all keep their current signatures and behavior (backed by `db.py` internally instead of xlsx/JSON). This means the ~30 existing tests for `send_one_alert`/`run`/`dedup_key` need only fixture changes (SQLite instead of xlsx), not logic rewrites. The one real signature change: `run()` collapses its two separate `excel_path`/`log_path` parameters into one `db_path` (they were always two different files; now they're the same database), and gains an optional `on_progress` callback (default `None`, fully backward compatible) so the new background bulk-send job can report live progress without duplicating `run()`'s loop.
3. **`/api/clients` per-page dedup check uses a new indexed `is_already_sent()`** (one small query per row on a page, i.e. ≤50 queries), rather than loading the whole `sent_log` table just to render one page. `run()`/`send_one_alert()`/`/api/send/{id}` keep using the existing `load_sent_log`/`save_sent_log` dict-based pattern (sent_log stays far smaller than the client roster, so this remains fast, and keeping it as-is avoids touching already-tested code).
4. **CSV export becomes a streaming backend endpoint** (`/api/clients/export`, same filters as the page view but no `LIMIT`/`OFFSET`), because the current client-side `downloadClientsCsv` only has the current page in memory after this change — exporting "all matching rows" needs to come from the database directly.
5. **The "Send All Eligible" confirm modal's shown count is an upper-bound estimate** (`eligible_not_sent_today` from `/api/stats`, computed live via SQL — not a rough guess), and the actual send job reports precise sent/skipped/failed counts as it runs.
6. **Backups**: `upsert_clients()` copies `clients.db` to `clients.backup.db` before any write (replace or merge), mirroring the existing `.backup.xlsx` safety net.

---

## File Structure

**New files:**
- `cert_automation_scripts/db.py` — SQLite schema, connection helper, and all data-access functions (pagination, stats, upsert, export, sent-log).
- `cert_automation_scripts/test_db.py` — tests for `db.py`.
- `cert_automation_scripts/migrate_to_sqlite.py` — one-time script: reads the real `clients_certifications.xlsx` + `sent_log.json` and populates `clients.db`.

**Modified files:**
- `cert_automation_scripts/whatsapp_renewal_alerts.py` — internals swapped to `db.py`; `DEFAULT_EXCEL_PATH`/`DEFAULT_LOG_PATH` → `DEFAULT_DB_PATH`; `run()` signature collapses two paths into one, gains `on_progress`.
- `cert_automation_scripts/test_whatsapp_renewal_alerts.py` — fixtures rebuilt on SQLite instead of xlsx/JSON.
- `cert_automation_scripts/dashboard-app/backend/main.py` — paginated `/api/clients`, new `/api/stats` and `/api/clients/export`, `upsert_clients`-backed upload/merge, background job + status endpoint for `/api/send-all`.
- `cert_automation_scripts/dashboard-app/backend/test_main.py` — SQLite fixtures instead of xlsx.
- `cert_automation_scripts/dashboard-app/frontend/src/api.js` — `getClients(params)`, new `getStats()`/`getSendAllStatus(jobId)`, `sendAllAlerts()` returns a job id, CSV export via URL.
- `cert_automation_scripts/dashboard-app/frontend/src/api.test.js` — updated.
- `cert_automation_scripts/dashboard-app/frontend/src/components/ClientTable.jsx` — server-paginated rewrite.
- `cert_automation_scripts/dashboard-app/frontend/src/components/ClientTable.test.jsx` — rewritten.
- `cert_automation_scripts/dashboard-app/frontend/src/components/StatCards.jsx` — reads from a `stats` prop instead of deriving from `clients`.
- `cert_automation_scripts/dashboard-app/frontend/src/components/StatCards.test.jsx` — updated.
- `cert_automation_scripts/dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx` — reads `renewals_by_month` from stats instead of computing from `clients`.
- `cert_automation_scripts/dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx` — updated.
- `cert_automation_scripts/dashboard-app/frontend/src/components/SendAllConfirmModal.jsx` — shows live progress once a job starts.
- `cert_automation_scripts/dashboard-app/frontend/src/App.jsx` — pagination/filter state, debounced search, stats fetch, job polling.
- `cert_automation_scripts/dashboard-app/frontend/src/App.test.jsx` — updated for the new `getClients` shape and job-based send-all.

---

### Task 1: `db.py` — schema, connection, `read_clients`/`find_client_by_id`

**Files:**
- Create: `cert_automation_scripts/db.py`
- Test: `cert_automation_scripts/test_db.py`

- [ ] **Step 1: Write the failing tests**

```python
# cert_automation_scripts/test_db.py
import sqlite3
from db import (
    init_db, read_clients, find_client_by_id, RECORD_FIELDS,
)

ROW_A = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
          "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_B = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
          "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")


def _insert_raw(db_path, rows):
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    for row in rows:
        expiry_iso = _ddmmyyyy_to_iso(row[8])
        conn.execute(
            f"INSERT INTO clients ({', '.join(RECORD_FIELDS)}, expiry_date_iso) "
            f"VALUES ({', '.join(['?'] * (len(RECORD_FIELDS) + 1))})",
            row + (expiry_iso,),
        )
    conn.commit()
    conn.close()


def _ddmmyyyy_to_iso(value):
    d, m, y = value.split("-")
    return f"{y}-{m}-{d}"


def test_init_db_creates_tables_and_is_idempotent(tmp_path):
    db_path = tmp_path / "clients.db"
    init_db(db_path)
    init_db(db_path)  # must not raise on second call
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "clients" in tables
    assert "sent_log" in tables


def test_read_clients_returns_all_rows(tmp_path):
    db_path = tmp_path / "clients.db"
    _insert_raw(db_path, [ROW_A, ROW_B])
    records = read_clients(db_path)
    assert len(records) == 2
    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}
    assert records[0]["expiry_date"] in ("24-07-2026", "11-08-2026")  # original display format preserved


def test_find_client_by_id_returns_matching_record(tmp_path):
    db_path = tmp_path / "clients.db"
    _insert_raw(db_path, [ROW_A, ROW_B])
    record = find_client_by_id(db_path, "CLT002")
    assert record["name"] == "Priya Mehta"
    assert record["status"] == "URGENT"


def test_find_client_by_id_returns_none_for_unknown_id(tmp_path):
    db_path = tmp_path / "clients.db"
    init_db(db_path)
    assert find_client_by_id(db_path, "NOPE") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Write `db.py`**

```python
"""SQLite-backed client roster storage. Replaces xlsx-as-database for
clients_certifications.xlsx so pagination, filtering, and single-client
lookups stay fast regardless of dataset size.

expiry_date is stored as the original DD-MM-YYYY display string (unchanged
from the roster format the frontend already expects); expiry_date_iso is a
YYYY-MM-DD copy used for correct sorting/filtering, since plain string
comparison of DD-MM-YYYY does not sort chronologically.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB_PATH = SCRIPT_DIR / "clients.db"

RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]

DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")

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
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_expiry ON clients(expiry_date_iso);

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


def get_connection(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def to_iso_date(value) -> str | None:
    """Converts a DD-MM-YYYY/YYYY-MM-DD/DD/MM/YYYY value (or datetime) to
    YYYY-MM-DD for sorting/filtering. Returns None if unparseable/blank."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {field: row[field] for field in RECORD_FIELDS}


def read_clients(db_path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(f"SELECT {', '.join(RECORD_FIELDS)} FROM clients").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def find_client_by_id(db_path, client_id: str) -> dict | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            f"SELECT {', '.join(RECORD_FIELDS)} FROM clients WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/db.py cert_automation_scripts/test_db.py
git commit -m "feat: add SQLite data layer with schema init and basic client reads"
```

---

### Task 2: `db.py` — `upsert_clients` (replace + merge modes, with backup)

**Files:**
- Modify: `cert_automation_scripts/db.py`
- Test: `cert_automation_scripts/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_db.py`:

```python
from db import upsert_clients


def test_upsert_replace_inserts_all_rows_and_reports_counts(tmp_path):
    db_path = tmp_path / "clients.db"
    rows = [ROW_A, ROW_B]
    stats = upsert_clients(db_path, rows, mode="replace")
    assert stats == {"row_count": 2, "added": 2, "skipped_duplicates": 0}
    assert len(read_clients(db_path)) == 2


def test_upsert_replace_clears_previous_data(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")
    stats = upsert_clients(db_path, [ROW_B], mode="replace")
    assert stats["row_count"] == 1
    records = read_clients(db_path)
    assert [r["client_id"] for r in records] == ["CLT002"]


def test_upsert_replace_backs_up_existing_db(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")
    upsert_clients(db_path, [ROW_B], mode="replace")
    backup_path = tmp_path / "clients.backup.db"
    assert backup_path.exists()


def test_upsert_merge_adds_new_and_skips_existing_ids(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")

    updated_row_a = ("CLT001", "SHOULD NOT OVERWRITE", "TechCorp", "r@x.com",
                       "919876543210", "ISO 9001", "ISO-1", "01-01-2025",
                       "24-07-2026", "https://x", "CRITICAL")
    stats = upsert_clients(db_path, [updated_row_a, ROW_B], mode="merge")

    assert stats == {"row_count": 2, "added": 1, "skipped_duplicates": 1}
    record = find_client_by_id(db_path, "CLT001")
    assert record["name"] == "Rahul Sharma"  # kept, not overwritten


def test_upsert_computes_expiry_date_iso_for_sorting(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")
    conn = sqlite3.connect(str(db_path))
    iso = conn.execute("SELECT expiry_date_iso FROM clients WHERE client_id = 'CLT001'").fetchone()[0]
    conn.close()
    assert iso == "2026-07-24"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v -k upsert`
Expected: FAIL with `ImportError: cannot import name 'upsert_clients'`

- [ ] **Step 3: Add `upsert_clients` to `db.py`**

```python
def upsert_clients(db_path, rows: list[tuple], mode: str) -> dict:
    """rows: list of tuples in RECORD_FIELDS order (client_id first).
    mode="replace": clears the table and inserts all rows.
    mode="merge": inserts only rows whose client_id isn't already present."""
    if mode not in ("replace", "merge"):
        raise ValueError(f"Unknown mode: {mode!r}")

    init_db(db_path)
    db_path = Path(db_path)
    if db_path.exists():
        backup_path = db_path.parent / "clients.backup.db"
        shutil.copyfile(db_path, backup_path)

    columns = RECORD_FIELDS + ["expiry_date_iso"]
    placeholders = ", ".join(["?"] * len(columns))
    prepared_rows = [tuple(row) + (to_iso_date(row[8]),) for row in rows]

    conn = get_connection(db_path)
    try:
        if mode == "replace":
            conn.execute("DELETE FROM clients")
            conn.executemany(
                f"INSERT INTO clients ({', '.join(columns)}) VALUES ({placeholders})",
                prepared_rows,
            )
            conn.commit()
            row_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            return {"row_count": row_count, "added": row_count, "skipped_duplicates": 0}

        added = 0
        skipped = 0
        for row in prepared_rows:
            cursor = conn.execute(
                f"INSERT OR IGNORE INTO clients ({', '.join(columns)}) VALUES ({placeholders})",
                row,
            )
            if cursor.rowcount == 1:
                added += 1
            else:
                skipped += 1
        conn.commit()
        row_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        return {"row_count": row_count, "added": added, "skipped_duplicates": skipped}
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/db.py cert_automation_scripts/test_db.py
git commit -m "feat: add upsert_clients with replace/merge modes and auto-backup"
```

---

### Task 3: `db.py` — `get_clients_page` (pagination, filtering, sorting)

**Files:**
- Modify: `cert_automation_scripts/db.py`
- Test: `cert_automation_scripts/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_db.py`:

```python
from db import get_clients_page

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


def _seeded_db(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, FIVE_ROWS, mode="replace")
    return db_path


def test_get_clients_page_returns_page_and_total(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=2)
    assert total == 5
    assert len(rows) == 2


def test_get_clients_page_second_page_has_remaining_rows(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=3, page_size=2)
    assert total == 5
    assert len(rows) == 1


def test_get_clients_page_filters_by_status(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, status="URGENT")
    assert total == 1
    assert rows[0]["client_id"] == "CLT002"


def test_get_clients_page_filters_by_cert_type(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, cert_type="ISO 9001")
    assert total == 2
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


def test_get_clients_page_filters_by_search_matches_name_or_company(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, search="tech")
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT004"}  # TechCorp, EduTech... wait


def test_get_clients_page_filters_by_expiry_before(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, expiry_before="2026-08-01")
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT005"}


def test_get_clients_page_sorts_by_expiry_date_chronologically_not_lexically(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, _ = get_clients_page(db_path, page=1, page_size=50, sort_key="expiry_date", sort_dir="asc")
    assert [r["client_id"] for r in rows] == ["CLT005", "CLT001", "CLT002", "CLT003", "CLT004"]


def test_get_clients_page_sorts_descending(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, _ = get_clients_page(db_path, page=1, page_size=50, sort_key="name", sort_dir="desc")
    assert rows[0]["client_id"] == "CLT002"  # Priya Mehta sorts last alphabetically... verify below
```

Note before running: the `test_get_clients_page_filters_by_search_matches_name_or_company` and
`test_get_clients_page_sorts_descending` assertions above must be checked against the actual
alphabetical order of the fixture data — fix any wrong expected values by computing them from
`FIVE_ROWS` directly (sorted by `name` descending: "Sneha Kapoor", "Rajesh Nair", "Priya Mehta",
"Amit Verma", "Rahul Sharma" — so `rows[0]["client_id"]` should be `"CLT004"`, not `"CLT002"`;
correct the test to `assert rows[0]["client_id"] == "CLT004"` before running). Similarly confirm
the "tech" search only matches "TechCorp" (`CLT001`) — "EduTech" also contains "tech" as a
substring, so the correct expected set is `{"CLT001", "CLT004"}` as written (both match).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v -k get_clients_page`
Expected: FAIL with `ImportError: cannot import name 'get_clients_page'`

- [ ] **Step 3: Add `get_clients_page` to `db.py`**

```python
_SORTABLE_COLUMNS = {
    "client_id", "name", "company", "cert_name", "cert_id", "status",
}


def get_clients_page(
    db_path, page: int = 1, page_size: int = 50, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
    search: str | None = None, sort_key: str | None = None, sort_dir: str = "asc",
) -> tuple[list[dict], int]:
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

        if sort_key in ("expiry_date", "days_left"):
            order_column = "expiry_date_iso"
        elif sort_key in _SORTABLE_COLUMNS:
            order_column = sort_key
        else:
            order_column = "client_id"
        direction = "DESC" if sort_dir == "desc" else "ASC"

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT {', '.join(RECORD_FIELDS)} FROM clients {where_clause} "
            f"ORDER BY {order_column} {direction} LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()
```

- [ ] **Step 4: Fix the two test assertions flagged in Step 1's note, then run tests to verify they pass**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/db.py cert_automation_scripts/test_db.py
git commit -m "feat: add get_clients_page with filtering, search, and correct chronological sort"
```

---

### Task 4: `db.py` — `get_stats` and `export_clients_rows`

**Files:**
- Modify: `cert_automation_scripts/db.py`
- Test: `cert_automation_scripts/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_db.py`:

```python
from db import get_stats, export_clients_rows, record_sent


def test_get_stats_counts_by_status_and_total(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    assert stats["status_counts"]["total"] == 5
    assert stats["status_counts"]["CRITICAL"] == 1
    assert stats["status_counts"]["URGENT"] == 1
    assert stats["status_counts"]["ACTIVE"] == 1
    assert stats["status_counts"]["EXPIRED"] == 1


def test_get_stats_cert_types_are_distinct_and_sorted(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    assert stats["cert_types"] == ["GMP", "HACCP", "ISO 9001", "OSHA"]


def test_get_stats_renewals_by_month_groups_by_year_month(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    by_month = {r["year_month"]: r["count"] for r in stats["renewals_by_month"]}
    assert by_month["2026-07"] == 1
    assert by_month["2026-08"] == 1


def test_get_stats_eligible_not_sent_today_excludes_already_sent(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    stats = get_stats(db_path, today="2026-07-21")
    # CRITICAL, URGENT, DUE SOON, EXPIRED = 4 alert-eligible rows; CLT001 already sent today
    assert stats["eligible_not_sent_today"] == 3


def test_export_clients_rows_yields_all_matching_rows_no_pagination(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = list(export_clients_rows(db_path, cert_type="ISO 9001"))
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v -k "stats or export_clients"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add `get_stats`, `export_clients_rows`, and `record_sent` to `db.py`**

```python
def get_stats(db_path, today: str) -> dict:
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        status_counts = {"total": total}
        for status in ("CRITICAL", "URGENT", "DUE SOON", "ACTIVE", "EXPIRED"):
            status_counts[status] = conn.execute(
                "SELECT COUNT(*) FROM clients WHERE status = ?", (status,)
            ).fetchone()[0]

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

        cert_types = [r[0] for r in conn.execute(
            "SELECT DISTINCT cert_name FROM clients WHERE cert_name IS NOT NULL ORDER BY cert_name"
        ).fetchall()]

        monthly_rows = conn.execute(
            "SELECT substr(expiry_date_iso, 1, 7) AS ym, COUNT(*) AS cnt "
            "FROM clients WHERE expiry_date_iso IS NOT NULL GROUP BY ym ORDER BY ym"
        ).fetchall()
        renewals_by_month = [{"year_month": r["ym"], "count": r["cnt"]} for r in monthly_rows]

        return {
            "status_counts": status_counts,
            "eligible_not_sent_today": eligible_not_sent,
            "cert_types": cert_types,
            "renewals_by_month": renewals_by_month,
        }
    finally:
        conn.close()


def export_clients_rows(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
):
    """Yields a dict per matching client, no pagination — for CSV export."""
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
        for row in cursor:
            yield _row_to_dict(row)
    finally:
        conn.close()


def record_sent(db_path, client_id, status, sent_date, message_id, phone, sent_at) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sent_log (client_id, status, sent_date, message_id, phone, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, status, sent_date, message_id, phone, sent_at),
        )
        conn.commit()
    finally:
        conn.close()


def is_already_sent(db_path, client_id, status, sent_date) -> bool:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM sent_log WHERE client_id = ? AND status = ? AND sent_date = ?",
            (client_id, status, sent_date),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def load_sent_log(db_path) -> dict:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT client_id, status, sent_date, message_id, phone, sent_at FROM sent_log"
        ).fetchall()
        log = {}
        for r in rows:
            key = f"{r['client_id']}|{r['status']}|{r['sent_date']}"
            log[key] = {"sent_at": r["sent_at"], "message_id": r["message_id"], "phone": r["phone"]}
        return log
    finally:
        conn.close()


def save_sent_log(db_path, log: dict) -> None:
    for key, info in log.items():
        client_id, status, sent_date = key.split("|", 2)
        record_sent(
            db_path, client_id, status, sent_date,
            info.get("message_id"), info.get("phone"), info.get("sent_at"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts && python -m pytest test_db.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/db.py cert_automation_scripts/test_db.py
git commit -m "feat: add stats, streaming CSV export, and sent-log functions to db.py"
```

---

### Task 5: Rewire `whatsapp_renewal_alerts.py` onto `db.py`

**Files:**
- Modify: `cert_automation_scripts/whatsapp_renewal_alerts.py`
- Modify: `cert_automation_scripts/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Replace the xlsx/JSON-backed functions in `whatsapp_renewal_alerts.py`**

Remove `import json`, `import openpyxl`, `read_clients`, `find_client_by_id`, `load_sent_log`,
`save_sent_log`, `RECORD_FIELDS`, `DEFAULT_EXCEL_PATH`, `DEFAULT_LOG_PATH` (lines 3, 10, 43-56,
64-101, 258-260 in the current file) and replace with:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, read_clients, find_client_by_id, load_sent_log, save_sent_log,
    RECORD_FIELDS,
)

ALERT_STATUSES = {"CRITICAL", "URGENT", "DUE SOON", "EXPIRED"}


def filter_alertable(records: list[dict]) -> list[dict]:
    return [r for r in records if r["status"] in ALERT_STATUSES]
```

Update `SCRIPT_DIR`/path constants section (previously `DEFAULT_EXCEL_PATH`/`DEFAULT_LOG_PATH`,
now just `DEFAULT_TEXT_LOG_PATH` remains local to this file):

```python
SCRIPT_DIR = Path(__file__).parent
DEFAULT_TEXT_LOG_PATH = SCRIPT_DIR / "whatsapp_automation.log"
```

- [ ] **Step 2: Update `run()`'s signature and body to take one `db_path` and an `on_progress` callback**

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
            on_progress(result, len(records))

    if persist_log and log_dirty:
        save_sent_log(db_path, sent_log)

    return results
```

- [ ] **Step 3: Update `build_arg_parser()`, `parse_args()`, and `main()` to use `--db`/`DEFAULT_DB_PATH`**

```python
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send WhatsApp renewal alerts via Meta Cloud API.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent without calling the API.")
    parser.add_argument("--test-number", default=None, help="Redirect all sends to this number instead of real client numbers.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to clients.db")
    return parser
```

In `main()`, change:
```python
    results = run(
        db_path=args.db,
        token=token,
        phone_number_id=phone_number_id,
        template_name=template_name,
        template_lang=template_lang,
        dry_run=args.dry_run,
        test_number=args.test_number,
    )
```

- [ ] **Step 4: Update `test_whatsapp_renewal_alerts.py` fixtures and calls**

Replace the `_write_xlsx`/`HEADERS` helper block (and its one `import openpyxl`) with:

```python
from db import upsert_clients, DEFAULT_DB_PATH


def _write_db(path, rows):
    upsert_clients(path, rows, mode="replace")
```

Replace every occurrence of `_write_xlsx(xlsx_path, ...)` with `_write_db(db_path, ...)` and every
`xlsx_path = tmp_path / "clients.xlsx"` with `db_path = tmp_path / "clients.db"` throughout the
file (this affects `test_read_clients_and_filter_alertable`, `test_read_clients_skips_blank_rows`,
and every `test_run_*` test).

For every `run(excel_path=xlsx_path, log_path=log_path, ...)` call, replace with
`run(db_path=db_path, ...)` — e.g.:

```python
def test_run_dry_run_makes_no_calls_and_no_log_writes(tmp_path):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, ONE_CRITICAL_ROW)
    send_fn = Mock()

    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )

    assert len(results) == 1
    assert results[0]["action"] == "dry_run"
    send_fn.assert_not_called()
```

Apply the same `db_path`-only pattern to `test_run_dry_run_honors_dedup_log_for_already_sent_client`,
`test_run_live_sends_and_dedups_on_second_call`, `test_run_test_number_overrides_phone_and_skips_log_write`,
`test_run_failed_send_does_not_write_log`, and `test_run_mixed_outcomes_in_single_call_preserves_earlier_successes`
— each currently creates a separate `xlsx_path`/`log_path` pair; use one `db_path` for both,
`_write_db(db_path, rows)` to seed clients, and `save_sent_log(db_path, {...})` (already imported)
to seed prior sent-log entries where a test does that.

Update `test_parse_args_defaults`:
```python
from whatsapp_renewal_alerts import parse_args
from db import DEFAULT_DB_PATH


def test_parse_args_defaults():
    args = parse_args([])
    assert args.dry_run is False
    assert args.test_number is None
    assert args.db == str(DEFAULT_DB_PATH)
```

Add one new test for `on_progress`:

```python
def test_run_calls_on_progress_for_each_record(tmp_path):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ONE_CRITICAL_ROW[0],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))
    progress_calls = []

    run(
        db_path=db_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )

    assert progress_calls == [("sent", 2), ("sent", 2)]
```

- [ ] **Step 5: Run the full test file and fix any remaining path references**

Run: `cd cert_automation_scripts && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: all passed. If any test still references `xlsx_path`/`log_path`/`DEFAULT_EXCEL_PATH`, fix it per the pattern above.

- [ ] **Step 6: Commit**

```bash
git add cert_automation_scripts/whatsapp_renewal_alerts.py cert_automation_scripts/test_whatsapp_renewal_alerts.py
git commit -m "refactor: back whatsapp_renewal_alerts.py with db.py instead of xlsx/JSON"
```

---

### Task 6: Migration script for the real data

**Files:**
- Create: `cert_automation_scripts/migrate_to_sqlite.py`

- [ ] **Step 1: Write the script**

```python
"""One-time migration: reads the real clients_certifications.xlsx and
sent_log.json and populates clients.db. Run once: python migrate_to_sqlite.py
Verifies row counts match the source files before declaring success.
"""
import json
import sys
from pathlib import Path

import openpyxl

from db import DEFAULT_DB_PATH, RECORD_FIELDS, upsert_clients, record_sent, read_clients

SCRIPT_DIR = Path(__file__).parent
SOURCE_XLSX = SCRIPT_DIR / "clients_certifications.xlsx"
SOURCE_LOG = SCRIPT_DIR / "sent_log.json"


def _read_xlsx_rows(path) -> list[tuple]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)  # header
        return [tuple(row[:len(RECORD_FIELDS)]) for row in rows_iter if row and row[0] is not None]
    finally:
        wb.close()


def migrate() -> None:
    if not SOURCE_XLSX.exists():
        print(f"No source file at {SOURCE_XLSX} — nothing to migrate.")
        return

    rows = _read_xlsx_rows(SOURCE_XLSX)
    stats = upsert_clients(DEFAULT_DB_PATH, rows, mode="replace")
    print(f"Migrated {stats['row_count']} client rows into {DEFAULT_DB_PATH}")

    migrated_count = len(read_clients(DEFAULT_DB_PATH))
    if migrated_count != len(rows):
        print(f"MISMATCH: source had {len(rows)} rows, db has {migrated_count}")
        sys.exit(1)

    if SOURCE_LOG.exists():
        log = json.loads(SOURCE_LOG.read_text(encoding="utf-8"))
        for key, info in log.items():
            client_id, status, sent_date = key.split("|", 2)
            record_sent(
                DEFAULT_DB_PATH, client_id, status, sent_date,
                info.get("message_id"), info.get("phone"), info.get("sent_at"),
            )
        print(f"Migrated {len(log)} sent-log entries")

    print("Migration verified OK. Source files left untouched.")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 2: Run it against the real data**

Run: `cd cert_automation_scripts && python migrate_to_sqlite.py`
Expected: `Migrated 56737 client rows into ...clients.db`, no mismatch, migration verified.

- [ ] **Step 3: Spot-check the real migrated data**

Run:
```bash
cd cert_automation_scripts && python -c "
from db import read_clients, DEFAULT_DB_PATH, get_clients_page, get_stats
print('total:', len(read_clients(DEFAULT_DB_PATH)))
rows, total = get_clients_page(DEFAULT_DB_PATH, page=1, page_size=5)
print('page 1:', [r['client_id'] for r in rows], 'total:', total)
print('stats:', get_stats(DEFAULT_DB_PATH, today='2026-07-21')['status_counts'])
"
```
Expected: total 56737, a 5-row page, and status counts that sum to 56737.

- [ ] **Step 4: Commit**

```bash
git add cert_automation_scripts/migrate_to_sqlite.py
git commit -m "feat: add one-time xlsx/JSON to SQLite migration script"
```

(`clients.db` and `clients.backup.db` should already be covered by the existing `.gitignore`
pattern for data files — verify `cert_automation_scripts/.gitignore` includes `*.db`, and add it
if missing, before committing.)

---

### Task 7: `main.py` — paginated `/api/clients`, `/api/stats`, `/api/clients/export`

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/backend/main.py`
- Modify: `cert_automation_scripts/dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Replace the `_write_xlsx`/`HEADERS` helper at the top of `test_main.py` with a SQLite equivalent,
and update the two existing `/api/clients` tests plus add pagination/stats/export tests:

```python
import io
import main as main_module
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch
from db import upsert_clients, record_sent

client = TestClient(app)

HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]


def _write_db(path, rows):
    upsert_clients(path, rows, mode="replace")


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_clients_paginates_and_reports_total(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients", params={"page": 1, "page_size": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert len(data["rows"]) == 1


def test_get_clients_merges_alert_sent_today(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-18", "wamid.ABC", "919876543210", "2026-07-18T10:00:00")
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients", params={"page_size": 50})
    data = response.json()["rows"]

    critical = next(r for r in data if r["client_id"] == "CLT001")
    assert critical["alert_sent_today"] is True
    active = next(r for r in data if r["client_id"] == "CLT004")
    assert active["alert_sent_today"] is None


def test_get_clients_filters_by_status_param(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients", params={"status": "URGENT", "page_size": 50})
    data = response.json()["rows"]
    assert len(data) == 1
    assert data[0]["client_id"] == "CLT002"


def test_get_stats_returns_counts_and_cert_types(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["status_counts"]["total"] == 1
    assert data["cert_types"] == ["ISO 9001"]


def test_export_clients_streams_csv_with_all_matching_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    response = client.get("/api/clients/export", params={"status": "CRITICAL"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    body = response.text
    assert "CLT001" in body
    assert "CLT002" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/backend && python -m pytest test_main.py -v -k "clients or stats or export"`
Expected: FAIL (old `/api/clients` returns a bare list, not `{rows, total, ...}`; `/api/stats` and `/api/clients/export` don't exist)

- [ ] **Step 3: Update `main.py`**

Replace the import block:
```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, read_clients, load_sent_log, save_sent_log,
    is_already_sent,
)
from whatsapp_renewal_alerts import (  # noqa: E402
    ALERT_STATUSES, dedup_key, filter_alertable, normalize_phone,
    send_one_alert, run,
)
```

Replace `/api/clients`:
```python
@app.get("/api/clients")
def get_clients(
    page: int = 1, page_size: int = 50, status: str = "ALL", cert_type: str = "ALL",
    expiry_before: str = "", search: str = "", sort_key: str = "", sort_dir: str = "asc",
):
    today = _today_str()
    rows, total = get_clients_page(
        DEFAULT_DB_PATH, page=page, page_size=page_size,
        status=status, cert_type=cert_type, expiry_before=expiry_before or None,
        search=search or None, sort_key=sort_key or None, sort_dir=sort_dir,
    )
    result = []
    for rec in rows:
        if rec["status"] in ALERT_STATUSES:
            alert_sent_today = is_already_sent(DEFAULT_DB_PATH, rec["client_id"], rec["status"], today)
        else:
            alert_sent_today = None
        result.append({**rec, "alert_sent_today": alert_sent_today})
    return {"rows": result, "total": total, "page": page, "page_size": page_size}


@app.get("/api/stats")
def stats():
    return get_stats(DEFAULT_DB_PATH, _today_str())


def _csv_escape(value) -> str:
    text = str(value if value is not None else "")
    if any(c in text for c in ('"', ",", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


@app.get("/api/clients/export")
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

    return StreamingResponse(
        generate(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=clients_export.csv"},
    )
```

Every other reference to `DEFAULT_EXCEL_PATH`/`DEFAULT_LOG_PATH` in the file (in
`/api/email-preview/{id}`, `/api/message-log`, `/api/send/{id}`, `/api/send-all`,
`/api/upload-clients`, `/api/merge-clients`) is updated to `DEFAULT_DB_PATH` in Tasks 8-9 below —
leave those endpoints as-is for now (they'll still reference the old names and fail to import
until Task 8; that's expected and fixed there, not in this task).

- [ ] **Step 4: Run the new/updated tests to verify they pass**

Run: `cd cert_automation_scripts/dashboard-app/backend && python -m pytest test_main.py -v -k "clients or stats or export"`
Expected: the tests from Step 1 pass (other tests in the file will still fail until Task 8 — that's expected)

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/dashboard-app/backend/main.py cert_automation_scripts/dashboard-app/backend/test_main.py
git commit -m "feat: paginate /api/clients, add /api/stats and streaming /api/clients/export"
```

---

### Task 8: `main.py` — single-client endpoints and message log onto `db.py`

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/backend/main.py`
- Modify: `cert_automation_scripts/dashboard-app/backend/test_main.py`

- [ ] **Step 1: Update remaining `DEFAULT_EXCEL_PATH`/`DEFAULT_LOG_PATH` references**

In `/api/email-preview/{client_id}`, `/api/message-log`, `/api/send/{client_id}`, and
`/api/send-all`: replace every `DEFAULT_EXCEL_PATH` and `DEFAULT_LOG_PATH` with `DEFAULT_DB_PATH`.
`/api/message-log` additionally changes from building a full `{client_id: record}` dict via
`read_clients()` (a full-table read just to enrich log entries) to per-entry indexed lookups:

```python
@app.get("/api/message-log")
def message_log():
    sent_log = load_sent_log(DEFAULT_DB_PATH)
    entries = []
    for key, info in sent_log.items():
        client_id, status_tier, _date = key.split("|", 2)
        found = find_client_by_id(DEFAULT_DB_PATH, client_id) or {}
        entries.append({
            "client_id": client_id,
            "name": found.get("name", "Unknown"),
            "company": found.get("company", ""),
            "cert_name": found.get("cert_name", ""),
            "status_tier": status_tier,
            "phone": info.get("phone"),
            "message_id": info.get("message_id"),
            "sent_at": info.get("sent_at"),
        })
    entries.sort(key=lambda e: e["sent_at"] or "", reverse=True)
    return entries
```

- [ ] **Step 2: Update `test_main.py`'s remaining tests for these endpoints**

Every test in the file that currently does `_write_xlsx(xlsx_path, ...)` +
`monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)` (and, where present,
`monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)`) is updated to:
`_write_db(db_path, ...)` + `monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)` (one
patch target instead of two). This affects the email-preview tests, the send/send-all tests, and
the message-log tests. Sent-log seeding that currently does
`log_path.write_text(json.dumps({...}))` becomes a call to `record_sent(db_path, ...)` (imported
from `db`) with the equivalent fields, e.g.:

```python
def test_message_log_returns_entries_enriched_with_client_data(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-18", "wamid.ABC", "919876543210", "2026-07-18T10:00:00")
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    response = client.get("/api/message-log")
    assert response.status_code == 200
    entries = response.json()
    assert entries[0]["client_id"] == "CLT001"
    assert entries[0]["name"] == "Rahul Sharma"
    assert entries[0]["message_id"] == "wamid.ABC"
```

Apply the same `_write_db` + single `DEFAULT_DB_PATH` monkeypatch pattern to every remaining test
in the file that isn't already updated by Task 7 or Task 9.

- [ ] **Step 3: Run the full backend test file**

Run: `cd cert_automation_scripts/dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all tests pass except the upload/merge/send-all ones still pending Task 9 (those are
expected to fail until that task) — confirm the failures at this point are only in
`test_upload_clients_*`, `test_merge_clients_*`, and `test_send_all*`.

- [ ] **Step 4: Commit**

```bash
git add cert_automation_scripts/dashboard-app/backend/main.py cert_automation_scripts/dashboard-app/backend/test_main.py
git commit -m "refactor: point single-client and message-log endpoints at db.py"
```

---

### Task 9: `main.py` — upload/merge onto `upsert_clients`, and background `/api/send-all`

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/backend/main.py`
- Modify: `cert_automation_scripts/dashboard-app/backend/test_main.py`

- [ ] **Step 1: Update the failing upload/merge/send-all tests**

Every `test_upload_clients_*` and `test_merge_clients_*` test currently asserts against
`excel_path.exists()`/`backup_path` as `.xlsx` files and reads results back with
`openpyxl.load_workbook(excel_path)`. Update each to use a `db_path = tmp_path / "clients.db"`,
assert `db_path.exists()` / `(db_path.parent / "clients.backup.db").exists()`, and read results
back with `read_clients(db_path)` instead of opening a workbook. For example:

```python
def test_upload_clients_success(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    upload_path = tmp_path / "upload.xlsx"
    _write_xlsx_fixture(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "row_count": 1, "format": "roster"}
    assert db_path.exists()
    assert read_clients(db_path)[0]["client_id"] == "CLT001"
```

(`_write_xlsx_fixture` is the original `_write_xlsx` helper, kept under this name specifically for
building the *uploaded* `.xlsx` file content — since the upload endpoint's INPUT is still an xlsx
file, only the destination storage changed. Keep this helper in the test file; only the assertions
about the destination move to `db_path`/`read_clients`.)

Apply the same `db_path`/`read_clients`-based assertion pattern to
`test_upload_clients_converts_raw_bis_isi_workbook`, `test_upload_clients_backs_up_existing_file`,
`test_merge_clients_adds_new_and_keeps_existing`, `test_merge_clients_skips_duplicate_client_ids`,
`test_merge_clients_converts_and_merges_raw_bis_isi_workbook`, `test_merge_clients_into_empty_roster`,
and `test_merge_clients_backs_up_existing_file`. `test_upload_clients_rejects_wrong_headers`,
`test_upload_clients_rejects_empty_active_sheet_with_clear_message`, and
`test_merge_clients_rejects_non_xlsx_extension` need no changes beyond the `DEFAULT_DB_PATH`
monkeypatch swap, since they assert on rejection, not on stored data.

Add a send-all job test:

```python
def test_send_all_starts_job_and_reports_progress(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")

    with patch("whatsapp_renewal_alerts.send_message", return_value=(True, {"message_id": "wamid.ABC"})):
        response = client.post("/api/send-all")
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        import time
        for _ in range(50):
            status_response = client.get(f"/api/send-all/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["sent"] == 1
    assert final["total"] == 1


def test_send_all_status_returns_404_for_unknown_job(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", tmp_path / "clients.db")
    response = client.get("/api/send-all/status/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/backend && python -m pytest test_main.py -v -k "upload or merge or send_all"`
Expected: FAIL (endpoints still write/expect xlsx; send-all still returns the full result list synchronously, not a job id)

- [ ] **Step 3: Update `main.py`'s upload, merge, and send-all endpoints**

```python
@app.post("/api/upload-clients")
async def upload_clients(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    contents = await file.read()
    tmp_path = DEFAULT_DB_PATH.parent / "_upload_tmp.xlsx"
    tmp_path.write_bytes(contents)

    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        active_title = wb.active.title
        try:
            header_row = next(wb.active.iter_rows(values_only=True))
        except StopIteration:
            header_row = None
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Could not read the uploaded file as a valid .xlsx spreadsheet")

    actual_headers = list(header_row[: len(REQUIRED_HEADERS)]) if header_row else None

    if actual_headers == REQUIRED_HEADERS:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)
        rows = [tuple(row[:len(REQUIRED_HEADERS)]) for row in rows_iter if row and row[0] is not None]
        wb.close()
        tmp_path.unlink(missing_ok=True)
        stats = upsert_clients(DEFAULT_DB_PATH, rows, mode="replace")
        return {"status": "ok", "row_count": stats["row_count"], "format": "roster"}

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

        stats = upsert_clients(DEFAULT_DB_PATH, collector.rows, mode="replace")
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


@app.post("/api/merge-clients")
async def merge_clients(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    contents = await file.read()
    tmp_path = DEFAULT_DB_PATH.parent / "_merge_upload_tmp.xlsx"
    tmp_path.write_bytes(contents)

    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        active_title = wb.active.title
        try:
            header_row = next(wb.active.iter_rows(values_only=True))
        except StopIteration:
            header_row = None
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Could not read the uploaded file as a valid .xlsx spreadsheet")

    actual_headers = list(header_row[: len(REQUIRED_HEADERS)]) if header_row else None
    bis_stats = None

    if actual_headers == REQUIRED_HEADERS:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)
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
    stats = upsert_clients(DEFAULT_DB_PATH, new_rows, mode="merge")
    return {
        "status": "ok", "row_count": stats["row_count"], "added": stats["added"],
        "skipped_duplicates": stats["skipped_duplicates"], "format": upload_format, "stats": bis_stats,
    }
```

Replace `/api/send-all` with a background-job version, adding `import uuid` to the top imports:

```python
_send_all_jobs: dict[str, dict] = {}


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
    finally:
        _send_all_jobs[job_id]["done"] = True
        global _bulk_in_progress
        with _send_lock:
            _bulk_in_progress = False


@app.post("/api/send-all")
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

    token = os.environ["WHATSAPP_TOKEN"]
    phone_number_id = os.environ["PHONE_NUMBER_ID"]
    template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
    test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

    job_id = str(uuid.uuid4())
    _send_all_jobs[job_id] = {"total": 0, "sent": 0, "skipped": 0, "failed": 0, "done": False}
    thread = threading.Thread(
        target=_run_send_all_job,
        args=(job_id, token, phone_number_id, template_name, template_lang, test_number),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/api/send-all/status/{job_id}")
def send_all_status(job_id: str):
    job = _send_all_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
```

Also update the `/api/send/{client_id}` endpoint's two `DEFAULT_EXCEL_PATH`/`DEFAULT_LOG_PATH`
references (already renamed to `DEFAULT_DB_PATH` in Task 8) to keep using
`load_sent_log`/`save_sent_log`/`send_one_alert` exactly as before — no other change needed there.

- [ ] **Step 4: Run the full backend test suite**

Run: `cd cert_automation_scripts/dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/dashboard-app/backend/main.py cert_automation_scripts/dashboard-app/backend/test_main.py
git commit -m "feat: back upload/merge on upsert_clients; make send-all a background job with progress"
```

---

### Task 10: Frontend `api.js` — paginated `getClients`, `getStats`, job-based send-all

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/api.js`
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Replace the `getClients` and `sendAllAlerts` describe blocks in `api.test.js`, and add new ones:

```javascript
describe("getClients", () => {
  it("returns the paginated response and passes query params", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 50 }),
    });
    const result = await getClients({ page: 1, pageSize: 50, status: "CRITICAL", search: "tech" });
    expect(result).toEqual({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 50 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/clients?page=1&page_size=50&status=CRITICAL&search=tech"
    );
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getClients({})).rejects.toThrow("Failed to load clients: 500");
  });
});

describe("getStats", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status_counts: { total: 5 }, cert_types: ["ISO 9001"] }),
    });
    const stats = await getStats();
    expect(stats).toEqual({ status_counts: { total: 5 }, cert_types: ["ISO 9001"] });
    expect(global.fetch).toHaveBeenCalledWith("/api/stats");
  });
});

describe("sendAllAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});

describe("getSendAllStatus", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ total: 5, sent: 2, skipped: 1, failed: 0, done: false }),
    });
    const status = await getSendAllStatus("abc-123");
    expect(status).toEqual({ total: 5, sent: 2, skipped: 1, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all/status/abc-123");
  });
});
```

Update the top import to include `getStats, getSendAllStatus`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: FAIL (`getClients` still calls `fetch("/api/clients")` with no params; `getStats`/`getSendAllStatus` don't exist; `sendAllAlerts`'s existing test — now replaced — no longer applies)

- [ ] **Step 3: Update `api.js`**

Replace `getClients` and `sendAllAlerts`, and add `getStats`/`getSendAllStatus`:

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
  const res = await fetch(qs ? `/api/clients?${qs}` : "/api/clients");
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch("/api/stats");
  if (!res.ok) throw new Error(`Failed to load stats: ${res.status}`);
  return res.json();
}

export async function sendAllAlerts() {
  const res = await fetch("/api/send-all", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}

export async function getSendAllStatus(jobId) {
  const res = await fetch(`/api/send-all/status/${jobId}`);
  if (!res.ok) throw new Error(`Failed to load send-all status: ${res.status}`);
  return res.json();
}

export function clientsExportUrl({ status, certType, expiryBefore, search } = {}) {
  const query = new URLSearchParams();
  if (status && status !== "ALL") query.set("status", status);
  if (certType && certType !== "ALL") query.set("cert_type", certType);
  if (expiryBefore) query.set("expiry_before", expiryBefore);
  if (search) query.set("search", search);
  const qs = query.toString();
  return qs ? `/api/clients/export?${qs}` : "/api/clients/export";
}
```

Note the query-string assertion in Step 1's `getClients` test lists params in a specific order
(`page, page_size, status, search`) — `URLSearchParams` preserves insertion order, so the
`query.set(...)` call order above must match the order asserted in the test exactly (page,
pageSize, status, certType, expiryBefore, search, sortKey, sortDir); adjust either the test or the
implementation order so they agree before running.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/dashboard-app/frontend/src/api.js cert_automation_scripts/dashboard-app/frontend/src/api.test.js
git commit -m "feat: paginated getClients, getStats, job-based sendAllAlerts, CSV export URL helper"
```

---

### Task 11: `ClientTable.jsx` — server-side pagination rewrite

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/ClientTable.jsx`
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/ClientTable.test.jsx`

- [ ] **Step 1: Write the failing tests**

Replace `ClientTable.test.jsx` entirely — it now takes a `page` object (`{rows, total, page, page_size}`)
and a `loading` flag, and calls `onPageChange`/`onSortChange`/etc. instead of filtering internally:

```javascript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientTable from "./ClientTable";

const pageOf = (rows, total = rows.length, page = 1) => ({ rows, total, page, page_size: 8 });

const oneClient = {
  client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
  cert_name: "ISO 9001", cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL",
  alert_sent_today: false,
};

describe("ClientTable", () => {
  it("renders rows from the given page", () => {
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
  });

  it("shows a loading message while the page is loading and no rows are cached yet", () => {
    render(
      <ClientTable
        page={pageOf([])} loading={true} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Loading clients…")).toBeInTheDocument();
  });

  it("shows the total row count from the server, not just the rendered page", () => {
    render(
      <ClientTable
        page={pageOf([oneClient], 137, 1)} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText(/of 137 clients/)).toBeInTheDocument();
  });

  it("calls onPageChange with the next page number", () => {
    const onPageChange = vi.fn();
    render(
      <ClientTable
        page={pageOf([oneClient], 20, 1)} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={onPageChange} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("shows a Send Alert button for eligible, not-yet-sent clients", () => {
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Send Alert")).toBeInTheDocument();
  });

  it("shows Preview Email for any status with an email on file", () => {
    const activeWithEmail = { ...oneClient, status: "ACTIVE", alert_sent_today: null };
    render(
      <ClientTable
        page={pageOf([activeWithEmail])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Preview Email")).toBeInTheDocument();
  });

  it("selects a row and calls onSendSelected with the selected client objects", () => {
    const onSendSelected = vi.fn();
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={onSendSelected} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    fireEvent.click(screen.getByText("Send Reminder to Selected"));
    expect(onSendSelected).toHaveBeenCalledWith([oneClient]);
  });

  it("calls onSort with the clicked column key", () => {
    const onSort = vi.fn();
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={onSort} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByText("Full Name"));
    expect(onSort).toHaveBeenCalledWith("name");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/components/ClientTable.test.jsx`
Expected: FAIL (component still expects a flat `clients` array and does its own filtering/pagination)

- [ ] **Step 3: Rewrite `ClientTable.jsx`**

```javascript
import { useEffect, useState } from "react";
import { formatDaysLeft, initialsFor } from "../sortUtils";
import { clientsExportUrl } from "../api";

const STATUS_DOT = {
  EXPIRED: "bg-status-critical",
  CRITICAL: "bg-status-critical",
  URGENT: "bg-status-serious",
  "DUE SOON": "bg-status-warning",
  ACTIVE: "bg-status-good",
};

const ALERT_ELIGIBLE = new Set(["CRITICAL", "URGENT", "DUE SOON", "EXPIRED"]);

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
  page, loading, sortKey, sortAsc, onSort, onPageChange,
  onSendClick, onSendSelected, onPreviewEmail, exportFilters = {},
}) {
  const [selectedIds, setSelectedIds] = useState(new Set());
  const { rows, total, page: currentPage, page_size: pageSize } = page;

  useEffect(() => {
    setSelectedIds(new Set());
  }, [currentPage, sortKey, sortAsc]);

  function toggleRow(clientId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(clientId)) next.delete(clientId);
      else next.add(clientId);
      return next;
    });
  }

  function toggleSelectAllOnPage() {
    setSelectedIds((prev) => {
      const allSelected = rows.length > 0 && rows.every((c) => prev.has(c.client_id));
      if (allSelected) return new Set();
      return new Set(rows.map((c) => c.client_id));
    });
  }

  const allOnPageSelected = rows.length > 0 && rows.every((c) => selectedIds.has(c.client_id));
  const selectedClients = rows.filter((c) => selectedIds.has(c.client_id));
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const start = (currentPage - 1) * pageSize;
  const isEmptyLoading = loading && rows.length === 0;

  return (
    <div className="bg-surface rounded-xl border border-line overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h5 className="font-semibold text-ink-primary">Client Renewals</h5>
        <a
          href={clientsExportUrl(exportFilters)}
          className="px-3 py-1.5 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
        >
          Export CSV
        </a>
      </div>

      {selectedIds.size > 0 && (
        <div className="px-4 py-2 bg-surface-page border-b border-line flex items-center gap-3 text-sm">
          <span className="text-ink-primary font-medium">{selectedIds.size} selected</span>
          <button
            type="button"
            onClick={() => onSendSelected(selectedClients)}
            className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
          >
            Send Reminder to Selected
          </button>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="text-ink-secondary hover:text-ink-primary transition-colors"
          >
            Clear selection
          </button>
        </div>
      )}

      <table className="w-full" data-testid="client-table">
        <thead>
          <tr className="bg-surface-page text-xs uppercase tracking-wide text-ink-secondary border-b-2 border-line">
            <th className="px-3 py-2 w-8">
              <input
                type="checkbox"
                aria-label="Select all on this page"
                checked={allOnPageSelected}
                onChange={toggleSelectAllOnPage}
              />
            </th>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                onClick={() => onSort(col.key)}
                aria-sort={sortKey === col.key ? (sortAsc ? "ascending" : "descending") : "none"}
                className="px-3 py-2 text-left font-semibold cursor-pointer select-none hover:text-ink-primary transition-colors"
              >
                {col.label}
                {sortKey === col.key ? (sortAsc ? " ▲" : " ▼") : ""}
              </th>
            ))}
            <th className="px-3 py-2 text-left font-semibold">Action</th>
          </tr>
        </thead>
        <tbody>
          {isEmptyLoading && (
            <tr>
              <td colSpan={COLUMNS.length + 2} className="px-3 py-10 text-center text-ink-secondary">
                Loading clients…
              </td>
            </tr>
          )}
          {rows.map((c) => {
            const dot = STATUS_DOT[c.status] || "bg-ink-muted";
            return (
              <tr key={c.client_id} className="border-b border-line text-sm text-ink-primary hover:bg-surface-page transition-colors">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Select ${c.name}`}
                    checked={selectedIds.has(c.client_id)}
                    onChange={() => toggleRow(c.client_id)}
                  />
                </td>
                <td className="px-3 py-2">{c.client_id}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="h-8 w-8 shrink-0 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold">
                      {initialsFor(c.company)}
                    </span>
                    <div>
                      <p className="font-medium">{c.name}</p>
                      {c.email && <p className="text-xs text-ink-muted">{c.email}</p>}
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2">{c.company}</td>
                <td className="px-3 py-2">{c.cert_name}</td>
                <td className="px-3 py-2">{c.cert_id}</td>
                <td className="px-3 py-2 tabular-nums">{c.expiry_date}</td>
                <td className="px-3 py-2 tabular-nums">{formatDaysLeft(c.expiry_date)}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line bg-surface text-ink-primary">
                    <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
                    {c.status}
                  </span>
                </td>
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
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="px-4 py-3 border-t border-line flex items-center justify-between">
        <p className="text-sm text-ink-secondary">
          {isEmptyLoading
            ? "Loading clients…"
            : total === 0
            ? "Showing 0 of 0 clients"
            : `Showing ${start + 1}–${Math.min(start + pageSize, total)} of ${total} clients`}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            disabled={currentPage <= 1}
            aria-label="Previous page"
            className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
            disabled={currentPage >= pageCount}
            aria-label="Next page"
            className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}
```

Note this drops the client-side `sortClients`/`parseDate`/`downloadClientsCsv` imports entirely —
sorting is now server-side (via `onSort` triggering a refetch in `App.jsx`) and CSV export is a
direct link to the new backend endpoint.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/components/ClientTable.test.jsx`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/dashboard-app/frontend/src/components/ClientTable.jsx cert_automation_scripts/dashboard-app/frontend/src/components/ClientTable.test.jsx
git commit -m "refactor: ClientTable renders one server-paginated page instead of filtering a full array"
```

---

### Task 12: `StatCards.jsx` and `RenewalsByMonthChart.jsx` onto `/api/stats`

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/StatCards.jsx`
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/StatCards.test.jsx`
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx`
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx`

- [ ] **Step 1: Write the failing tests**

Replace `StatCards.test.jsx`:

```javascript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatCards from "./StatCards";

describe("StatCards", () => {
  it("shows counts from the given stats object", () => {
    const stats = { status_counts: { total: 5, CRITICAL: 1, URGENT: 2, "DUE SOON": 1 } };
    render(<StatCards stats={stats} />);
    expect(screen.getByTestId("stat-total")).toHaveTextContent("5");
    expect(screen.getByTestId("stat-CRITICAL")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-URGENT")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-DUE SOON")).toHaveTextContent("1");
  });

  it("shows zero for a status with no matching clients", () => {
    const stats = { status_counts: { total: 0 } };
    render(<StatCards stats={stats} />);
    expect(screen.getByTestId("stat-CRITICAL")).toHaveTextContent("0");
  });
});
```

Replace `RenewalsByMonthChart.test.jsx`:

```javascript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RenewalsByMonthChart from "./RenewalsByMonthChart";

describe("RenewalsByMonthChart", () => {
  it("renders a bar with the count and month label for each bucket", () => {
    render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    expect(screen.getByText("Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("Sep 2026")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows an empty state when there are no buckets", () => {
    render(<RenewalsByMonthChart renewalsByMonth={[]} />);
    expect(screen.getByText("No certification expiry dates to chart yet.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/components/StatCards.test.jsx src/components/RenewalsByMonthChart.test.jsx`
Expected: FAIL (`clients` prop-based components don't accept `stats`/`renewalsByMonth`)

- [ ] **Step 3: Update `StatCards.jsx`**

Replace the `counts` computation and the function signature:

```javascript
export default function StatCards({ stats }) {
  const statusCounts = stats?.status_counts || {};
  const counts = CARD_CONFIG.reduce((acc, { key }) => {
    acc[key] = statusCounts[key] || 0;
    return acc;
  }, {});

  return (
```

(rest of the component body is unchanged — only the `counts` computation source changes).

- [ ] **Step 4: Update `RenewalsByMonthChart.jsx`**

```javascript
const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function labelFor(yearMonth) {
  const [year, month] = yearMonth.split("-").map(Number);
  return `${MONTH_LABELS[month - 1]} ${year}`;
}

export default function RenewalsByMonthChart({ renewalsByMonth }) {
  const groups = renewalsByMonth.map((g) => ({ key: g.year_month, label: labelFor(g.year_month), count: g.count }));
  const max = Math.max(1, ...groups.map((g) => g.count));

  return (
    <div className="bg-surface rounded-xl border border-line p-6" data-testid="renewals-by-month-chart">
      <h5 className="font-semibold text-ink-primary mb-6">Renewals by Month</h5>
      {groups.length === 0 ? (
        <p className="text-sm text-ink-muted">No certification expiry dates to chart yet.</p>
      ) : (
        <div className="flex items-end justify-between gap-3 h-40">
          {groups.map((g) => (
            <div key={g.key} className="flex flex-col items-center flex-1 h-full justify-end group" title={`${g.label}: ${g.count} renewal${g.count === 1 ? "" : "s"}`}>
              <span className="text-xs font-semibold text-ink-secondary mb-1 tabular-nums">{g.count}</span>
              <div
                className="w-full max-w-[36px] bg-accent rounded-t group-hover:bg-accent-dark transition-colors"
                style={{ height: `${Math.max(6, (g.count / max) * 100)}%` }}
              />
              <span className="text-xs text-ink-muted mt-2 whitespace-nowrap">{g.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/components/StatCards.test.jsx src/components/RenewalsByMonthChart.test.jsx`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add cert_automation_scripts/dashboard-app/frontend/src/components/StatCards.jsx cert_automation_scripts/dashboard-app/frontend/src/components/StatCards.test.jsx cert_automation_scripts/dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx cert_automation_scripts/dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx
git commit -m "refactor: StatCards and RenewalsByMonthChart read from /api/stats instead of the full client array"
```

---

### Task 13: `SendAllConfirmModal.jsx` — live progress display

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`
- Test: `cert_automation_scripts/dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`

- [ ] **Step 1: Check the existing test file and write the new failing tests**

Read `SendAllConfirmModal.test.jsx` first (`cat` it) to see its current assertions, then add these
to it (keep existing tests that still apply — the modal's cancel/confirm-before-progress behavior
is unchanged; only the additional in-progress states are new):

```javascript
it("shows a progress bar once a job is in progress", () => {
  render(
    <SendAllConfirmModal
      open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
      job={{ total: 10, sent: 4, skipped: 1, failed: 0, done: false }}
    />
  );
  expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
  expect(screen.getByText(/of 10/)).toBeInTheDocument();
});

it("shows a done summary and a Close button once the job finishes", () => {
  const onCancel = vi.fn();
  render(
    <SendAllConfirmModal
      open={true} eligibleCount={10} onConfirm={() => {}} onCancel={onCancel}
      job={{ total: 10, sent: 9, skipped: 1, failed: 0, done: true }}
    />
  );
  fireEvent.click(screen.getByText("Close"));
  expect(onCancel).toHaveBeenCalled();
});
```

(Add `import { vi } from "vitest";` and `fireEvent` to the test file's imports if not already
present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: FAIL (`job` prop not handled, no progress/Close UI)

- [ ] **Step 3: Update `SendAllConfirmModal.jsx`**

Add a `job` prop (default `null`) and render progress/done states before the confirm/cancel
buttons when a job is active:

```javascript
export default function SendAllConfirmModal({ open, eligibleCount, onConfirm, onCancel, job = null }) {
```

Inside the dialog body, replace the confirm/cancel button block with a conditional:

```javascript
        {job ? (
          <div className="mb-2">
            <p className="text-sm text-ink-secondary mb-3">
              {job.sent} sent, {job.skipped} skipped, {job.failed} failed
              {job.total ? ` (of ${job.total})` : ""}
            </p>
            {job.done ? (
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={onCancel}
                  className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
                >
                  Close
                </button>
              </div>
            ) : (
              <div className="w-full bg-surface-page rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-accent transition-all"
                  style={{ width: `${job.total ? Math.round(((job.sent + job.skipped + job.failed) / job.total) * 100) : 0}%` }}
                />
              </div>
            )}
          </div>
        ) : (
          <>
            <p className="text-sm text-ink-secondary mb-6">
              Send a real WhatsApp renewal alert to all <strong>{eligibleCount}</strong> eligible
              client{eligibleCount === 1 ? "" : "s"} (Critical, Urgent, Due Soon, or Expired, not yet sent today)?
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: all passed (existing tests plus the two new ones)

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/dashboard-app/frontend/src/components/SendAllConfirmModal.jsx cert_automation_scripts/dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx
git commit -m "feat: show live progress and a Close button in SendAllConfirmModal once a job is running"
```

---

### Task 14: `App.jsx` — pagination/filter state, debounced search, stats, job polling

**Files:**
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/App.jsx`
- Modify: `cert_automation_scripts/dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

Update the shared `beforeEach` mock and the tests that assumed a flat client array or a
synchronous send-all result. Replace the top of `App.test.jsx`:

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

Update the "sends all" test to reflect the job-based flow:

```javascript
it("sends all and shows a summary toast once the job finishes", async () => {
  api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
  api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
  render(<App />);
  await waitFor(() => screen.getByText("Send Alert"));
  fireEvent.click(screen.getByText("Send All Eligible"));
  fireEvent.click(screen.getByText("Confirm Send All"));
  await waitFor(() => expect(api.sendAllAlerts).toHaveBeenCalled());
  await waitFor(() => expect(api.getSendAllStatus).toHaveBeenCalledWith("job-1"));
  await waitFor(() => expect(screen.getByText(/1 sent, 0 skipped, 0 failed/)).toBeInTheDocument());
});
```

Update the search test to be async (server-side, debounced):

```javascript
it("filters the table via the top-bar search input", async () => {
  render(<App />);
  await waitFor(() => screen.getByText("Rahul Sharma"));
  api.getClients.mockResolvedValue(samplePage([]));
  fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
    target: { value: "nobody" },
  });
  await waitFor(
    () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "nobody" })),
    { timeout: 1000 }
  );
  await waitFor(() => expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument());
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: FAIL (old `getClients()` no-arg call, `sendAllAlerts` result treated as an array, no debounce/job polling)

- [ ] **Step 3: Rewrite the relevant parts of `App.jsx`**

Replace the state/imports/`loadClients`/`eligibleCount`/`handleConfirmSendAll` section:

```javascript
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import Sidebar from "./components/Sidebar";
import StatCards from "./components/StatCards";
import RenewalsByMonthChart from "./components/RenewalsByMonthChart";
import FilterBar from "./components/FilterBar";
import ClientDataFilters from "./components/ClientDataFilters";
import ClientTable from "./components/ClientTable";
import ExcelSyncView from "./components/ExcelSyncView";
import MessageLogView from "./components/MessageLogView";
import WhatsAppSettingsView from "./components/WhatsAppSettingsView";
import SendConfirmModal from "./components/SendConfirmModal";
import SendAllConfirmModal from "./components/SendAllConfirmModal";
import SendSelectedConfirmModal from "./components/SendSelectedConfirmModal";
import EmailPreviewModal from "./components/EmailPreviewModal";
import Toast from "./components/Toast";
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
} from "./api";

const ALERT_ELIGIBLE_STATUSES = new Set(["CRITICAL", "URGENT", "DUE SOON", "EXPIRED"]);
const PAGE_SIZE = 8;
const SEARCH_DEBOUNCE_MS = 300;

export default function App() {
  const [activeView, setActiveView] = useState("clientData");
  const [page, setPage] = useState({ rows: [], total: 0, page: 1, page_size: PAGE_SIZE });
  const [clientsLoading, setClientsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [stats, setStats] = useState(null);
  const [activeStatus, setActiveStatus] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [certType, setCertType] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
  const [pageNum, setPageNum] = useState(1);
  const [sortKey, setSortKey] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [pendingClient, setPendingClient] = useState(null);
  const [toast, setToast] = useState(null);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [sendAllJob, setSendAllJob] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingSelected, setPendingSelected] = useState([]);
  const [bulkSelectedSending, setBulkSelectedSending] = useState(false);
  const [previewClientId, setPreviewClientId] = useState(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    setPageNum(1);
  }, [activeStatus, debouncedSearch, certType, expiryBefore, sortKey, sortAsc]);

  const queryParams = useMemo(() => ({
    page: pageNum, pageSize: PAGE_SIZE, status: activeStatus, certType,
    expiryBefore, search: debouncedSearch, sortKey, sortDir: sortAsc ? "asc" : "desc",
  }), [pageNum, activeStatus, certType, expiryBefore, debouncedSearch, sortKey, sortAsc]);

  const loadClients = useCallback(() => {
    setClientsLoading(true);
    return getClients(queryParams)
      .then((data) => {
        setPage(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setClientsLoading(false));
  }, [queryParams]);

  const loadStats = useCallback(() => {
    return getStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const certOptions = stats?.cert_types || [];

  function handleRefreshClick() {
    setRefreshing(true);
    Promise.all([loadClients(), loadStats()]).finally(() => setRefreshing(false));
  }

  function handleClearAllFilters() {
    setActiveStatus("ALL");
    setCertType("ALL");
    setExpiryBefore("");
  }

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
      loadStats();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    }
  }

  const eligibleCount = stats?.eligible_not_sent_today || 0;
  const jobPollRef = useRef(null);

  async function handleConfirmSendAll() {
    try {
      const { job_id: jobId } = await sendAllAlerts();
      setSendAllJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
      jobPollRef.current = setInterval(async () => {
        const status = await getSendAllStatus(jobId);
        setSendAllJob(status);
        if (status.done) {
          clearInterval(jobPollRef.current);
          loadClients();
          loadStats();
        }
      }, 500);
    } catch (err) {
      setBulkModalOpen(false);
      setToast({ type: "error", message: err.message });
    }
  }

  function handleCloseSendAllModal() {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    setSendAllJob(null);
    setBulkModalOpen(false);
  }

  async function handleConfirmSendSelected() {
    const selected = pendingSelected;
    setPendingSelected([]);
    setBulkSelectedSending(true);
    let sent = 0;
    let skipped = 0;
    let failed = 0;
    for (const client of selected) {
      if (!ALERT_ELIGIBLE_STATUSES.has(client.status) || client.alert_sent_today) {
        skipped += 1;
        continue;
      }
      try {
        await sendAlert(client.client_id);
        sent += 1;
      } catch {
        failed += 1;
      }
    }
    setToast({
      type: failed > 0 ? "error" : "success",
      message: `${sent} sent, ${skipped} already sent, ${failed} failed`,
    });
    loadClients();
    loadStats();
    setBulkSelectedSending(false);
  }

  async function handleUploadClients(file) {
    try {
      const result = await uploadClientsFile(file);
      setToast({
        type: "success",
        message: `Imported ${result.row_count} client${result.row_count === 1 ? "" : "s"}.`,
      });
      loadClients();
      loadStats();
      return result;
    } catch (err) {
      setToast({ type: "error", message: err.message });
      throw err;
    }
  }

  async function handleMergeClients(file) {
    try {
      const result = await mergeClientsFile(file);
      setToast({
        type: "success",
        message: `Merged — added ${result.added} new client${result.added === 1 ? "" : "s"}, `
          + `skipped ${result.skipped_duplicates} already on file (${result.row_count} total).`,
      });
      loadClients();
      loadStats();
      return result;
    } catch (err) {
      setToast({ type: "error", message: err.message });
      throw err;
    }
  }
```

Update the render section: `<StatCards clients={clients} />` → `<StatCards stats={stats} />`;
`<RenewalsByMonthChart clients={clients} />` → `<RenewalsByMonthChart renewalsByMonth={stats?.renewals_by_month || []} />`;
the `<ClientTable ...>` block becomes:

```javascript
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

`ClientDataFilters` keeps its existing props (`certOptions` now comes from `stats.cert_types`
instead of being computed from a full client array — no prop shape change on that component).

`SendAllConfirmModal`'s usage becomes:
```javascript
      <SendAllConfirmModal
        open={bulkModalOpen}
        eligibleCount={eligibleCount}
        job={sendAllJob}
        onConfirm={handleConfirmSendAll}
        onCancel={sendAllJob ? handleCloseSendAllModal : () => setBulkModalOpen(false)}
      />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npx vitest run src/App.test.jsx`
Expected: all passed. If the "Send All Eligible" button's disabled condition (`bulkSending ||
eligibleCount === 0`) still references a removed `bulkSending` state variable, replace it with
`sendAllJob !== null && !sendAllJob.done`.

- [ ] **Step 5: Commit**

```bash
git add cert_automation_scripts/dashboard-app/frontend/src/App.jsx cert_automation_scripts/dashboard-app/frontend/src/App.test.jsx
git commit -m "refactor: App.jsx drives server-side pagination, debounced search, and send-all job polling"
```

---

### Task 15: Full-stack verification against the real migrated data

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `cd cert_automation_scripts && python -m pytest -q`
Expected: all tests pass (this now includes `test_db.py`, the rewritten
`test_whatsapp_renewal_alerts.py`, and `dashboard-app/backend/test_main.py`).

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd cert_automation_scripts/dashboard-app/frontend && npm test -- --run`
Expected: all tests pass.

- [ ] **Step 3: Confirm `migrate_to_sqlite.py` was run against the real data (Task 6) and re-verify counts**

Run:
```bash
cd cert_automation_scripts && python -c "
from db import read_clients, DEFAULT_DB_PATH
print('total clients in clients.db:', len(read_clients(DEFAULT_DB_PATH)))
"
```
Expected: `56737` (or whatever the current real row count is, matching `clients_certifications.xlsx`).

- [ ] **Step 4: Start both servers and time a real page load**

Run the backend (`python -m uvicorn main:app --reload --port <port>` from
`dashboard-app/backend`) and frontend (`npm run dev` from `dashboard-app/frontend`) per this
project's established pattern (check for a free port first; if `--reload` has gone stale after a
prior run in this environment, do a full manual restart rather than trusting it — this project has
hit that exact issue repeatedly).

Then measure:
```bash
python -c "
import time, requests
t0 = time.time()
r = requests.get('http://127.0.0.1:<port>/api/clients', params={'page': 1, 'page_size': 50})
print('elapsed:', time.time() - t0, 'status:', r.status_code, 'total:', r.json()['total'])
"
```
Expected: well under 1 second (down from the ~10-30s full-file read this migration replaces),
`total` matching the real row count.

- [ ] **Step 5: Manual smoke test in the browser**

Open the dashboard, confirm: Dashboard stat cards and chart render; Client Data page loads a
page of rows with working pagination, search (after the debounce delay), status/cert/expiry
filters, and sort; Export CSV downloads a file; Excel Sync Replace and Merge both still work
against a small test `.xlsx`; Send Alert and Send All Eligible (test against a small,
non-production `clients.db` or with `DASHBOARD_TEST_NUMBER` set, never against real client
phone numbers) show progress and complete.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: verify SQLite migration end-to-end against real data"
```
