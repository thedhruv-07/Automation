# Scale to 5 Lakh+ Rows (SQLite Migration) — Design Spec

Date: 2026-07-21
Project: Absolute Veritas certification consultancy

## Purpose

The dashboard currently treats `clients_certifications.xlsx` as a live
database: every request re-parses the entire file with `openpyxl`, and
`/api/clients` returns the whole roster as one JSON payload that the React
frontend holds in memory and filters/sorts in plain JS. Measured live against
the real 56,737-row dataset this session: ~10.5s to read the file once, and
~10–30s+ for a full `/api/clients` response (~17MB of JSON). This does not
scale — at 5 lakh+ rows (the user's actual target), read time and payload
size scale roughly linearly, page loads would take minutes, and the frontend
would hold hundreds of MB of client objects in browser memory.

This spec replaces the xlsx-as-database pattern with SQLite as the live data
store, so a page load costs "fetch one indexed page of rows," never "re-read
everything." `.xlsx` remains the *exchange format* for Excel Sync (Replace and
Merge) — only the underlying storage changes.

## Decisions from brainstorming

- **Database: SQLite via Python's stdlib `sqlite3`**, no ORM. No new
  dependency; matches this project's existing dependency-light style
  (`email_template.py`/`banner_generator.py` were both deliberately kept free
  of heavy libraries). Raw parameterized SQL is easy to read for a two-table
  schema.
- **Bulk send at scale**: `Send All Eligible` becomes a background job with a
  polled progress indicator, instead of one blocking request.
- **Upload/Merge UX unchanged**: still upload `.xlsx` files (roster template
  or raw BIS ISI export, same auto-detection as today); only the destination
  changes, from rewriting an output `.xlsx` to bulk-inserting into SQLite.

## Data layer

New module `client_store.py` (alongside `whatsapp_renewal_alerts.py`), owning
a single SQLite file `clients.db` (path constant `DEFAULT_DB_PATH`, same
directory as the current `clients_certifications.xlsx`).

**Schema:**

```sql
CREATE TABLE clients (
    client_id     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    company       TEXT,
    email         TEXT,
    phone         TEXT,
    cert_name     TEXT,
    cert_id       TEXT,
    issue_date    TEXT,
    expiry_date   TEXT,
    renewal_link  TEXT,
    status        TEXT NOT NULL
);
CREATE INDEX idx_clients_status ON clients(status);
CREATE INDEX idx_clients_expiry ON clients(expiry_date);

CREATE TABLE sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,   -- the existing dedup key's date component
    message_id  TEXT,
    phone       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);
```

Same fields as today's roster (`REQUIRED_HEADERS`/`RECORD_FIELDS`) — nothing
added or removed, per the schema confirmation during brainstorming. The
`sent_log` primary key directly encodes the current `dedup_key()` format
(`client_id|status|date`), so "already sent today" becomes a single indexed
lookup (`SELECT 1 FROM sent_log WHERE client_id=? AND status=? AND
sent_date=?`) instead of loading the whole JSON file.

**Functions provided by `client_store.py`:**

- `init_db(db_path)` — creates tables/indexes if they don't exist.
- `get_clients_page(db_path, page, page_size, status=None, cert_type=None, expiry_before=None, search=None, sort_key=None, sort_dir="asc") -> (rows, total_count)` — one indexed, parameterized `SELECT ... LIMIT ? OFFSET ?` plus a `COUNT(*)` for the total. `search` matches `name`/`company` via `LIKE '%term%'` — sufficient at this scale (SQLite scans lakhs of rows well within acceptable page-load time for a simple substring filter); an FTS5 virtual table is a possible future upgrade if search itself ever becomes the bottleneck, not needed now.
- `get_client(db_path, client_id) -> dict | None` — indexed primary-key lookup, replacing today's `find_client_by_id()` full-table scan.
- `get_alertable_clients(db_path) -> list[dict]` — for the bulk-send job; still loads matching rows into memory, but only the alert-eligible subset (bounded by real eligible counts, not the full roster).
- `get_stats(db_path) -> dict` — status counts and renewals-by-month via `GROUP BY`, for `StatCards`/`RenewalsByMonthChart`, instead of the frontend computing these from a full in-memory array.
- `upsert_clients(db_path, rows, mode)` — `mode="replace"` clears and bulk-inserts (`executemany`, batched); `mode="merge"` inserts only rows whose `client_id` doesn't already exist (`INSERT OR IGNORE`), returning the same `{added, skipped_duplicates}` stats the API already returns today.
- `is_already_sent(db_path, client_id, status, date) -> bool` and `record_sent(db_path, client_id, status, date, message_id, phone)` — replace `load_sent_log`/`save_sent_log`'s whole-file read/write with single-row operations.

`whatsapp_renewal_alerts.py` and `cert_automation.py` (the CLI/scheduled-task
path) import these same functions, so they automatically read from SQLite too
— no separate migration needed for the non-dashboard path.

## Backend API changes (`dashboard-app/backend/main.py`)

- **`GET /api/clients`** — now takes query params (`page`, `page_size`,
  `status`, `cert_type`, `expiry_before`, `search`, `sort_key`, `sort_dir`)
  and returns `{"rows": [...], "total": N, "page": P, "page_size": S}` instead
  of the full array.
- **`GET /api/stats`** (new) — status counts + chart data via
  `get_stats()`, for the dashboard's stat cards and renewals chart.
- **`/api/send/{id}`, `/api/email-preview/{id}`** — use `get_client()`
  (indexed) instead of `find_client_by_id()` (full scan).
- **`/api/upload-clients`, `/api/merge-clients`** — parsing/format-detection
  logic (roster pass-through vs. BIS-ISI conversion) is unchanged; the final
  step calls `upsert_clients(..., mode="replace"|"merge")` instead of writing
  an output `.xlsx`. Response shape (`status`, `row_count`, `added`,
  `skipped_duplicates`, `format`, `stats`) stays the same.
- **`POST /api/send-all`** — starts the existing send loop on a background
  thread (extending the `_send_lock`/`_bulk_in_progress` pattern already in
  this file) and returns `{"job_id": ...}` immediately. Job progress is kept
  in an in-memory dict (`{job_id: {"sent": N, "skipped": M, "failed": K,
  "total": T, "done": bool}}`) — acceptable for a single-process app; if the
  server restarts mid-job, the existing `sent_log` dedup logic prevents
  double-sends on a retry.
- **`GET /api/send-all/status/{job_id}`** (new) — reports the progress dict
  above for polling.

## Frontend changes

- **`ClientTable.jsx`** — stops receiving the full `clients` array; instead
  fetches one page from the server whenever `page`/filters/sort/search
  change. Search input gets a short debounce (e.g. 300ms) since it's now a
  network request per change, not an in-memory filter.
- **`StatCards.jsx` / `RenewalsByMonthChart.jsx`** — fetch from the new
  `/api/stats` endpoint instead of deriving from the full client array.
- **`App.jsx`** — `loadClients()` becomes page/filter-aware; `handleConfirmSendAll` polls `/api/send-all/status/{job_id}` and updates a progress UI (reusing the existing bulk-send confirm modal, extended with a progress bar) until `done`.
- **`api.js`** — `getClients()` takes the query params above; new
  `getStats()`, `sendAllAlerts()` returns a job id, new `getSendAllStatus(jobId)`.

## Migration

One-time script `migrate_to_sqlite.py`: reads the current real
`clients_certifications.xlsx` (56,737 rows) and `sent_log.json`, calls
`init_db()` + `upsert_clients(mode="replace")` + row-by-row `record_sent()`
for existing log entries, and verifies the resulting row counts match the
source files exactly before declaring success. Run once against the real data
as part of this work; the old `.xlsx`/`.json` files are left in place
untouched (not deleted) as a fallback, consistent with how `.backup.xlsx` is
already handled elsewhere in this project.

## Testing

- New tests for `client_store.py`: schema creation, pagination math, each
  filter/sort combination, indexed lookup, replace vs. merge upsert
  semantics, sent-log dedup behavior.
- Existing backend tests that build `.xlsx` fixtures and monkeypatch
  `DEFAULT_EXCEL_PATH` are rewritten to build small SQLite fixtures and
  monkeypatch `DEFAULT_DB_PATH` instead — same test *intent*, new backing
  store.
- `ClientTable.test.jsx` is rewritten around "given one server-returned page
  + total count, render it and request the next page/filter" rather than
  "given the full array, filter/sort/paginate in JS."
- A test against the real migrated dataset (56,737 rows) confirming
  `/api/clients` with no filters returns the correct total and a page loads
  in well under a second (the concrete before/after proof this work is meant
  to deliver).

## Out of scope

- Multi-user concurrent write support beyond SQLite's built-in
  single-writer/multiple-reader behavior — this remains a single-admin tool.
- Full-text search ranking/relevance (FTS5) — plain `LIKE` search is
  sufficient at this scale; noted above as a future option only if it
  actually becomes slow.
- Any change to WhatsApp/Brevo send logic, templates, or rate-limit handling
  — the background job only changes *how* the existing send loop is
  triggered and observed, not what it sends or how fast providers accept it.
- Postgres or any multi-server deployment — SQLite is sufficient for the
  target scale (5 lakh+ rows) on a single-admin desktop-style tool.
- Redesigning the dashboard's visual layout beyond what pagination/progress
  UI requires.
