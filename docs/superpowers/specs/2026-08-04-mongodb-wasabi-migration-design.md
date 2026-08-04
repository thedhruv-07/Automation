# MongoDB + Wasabi Migration

## Problem

The dashboard's data layer is SQLite (`data/clients.db`), which works fine
functionally but has no home on the current hosting (Render's free tier
wipes it on every redeploy/spin-down). A persistent Render Disk would fix
that with zero code changes, but the decision has been made to instead
move the whole data layer to MongoDB (a managed, persistent document
store) and archive every uploaded Excel roster to Wasabi (S3-compatible
object storage), with the archive's URL recorded in MongoDB. This is a
bigger change than the disk fix, taken deliberately rather than as the
minimal fix for the redeploy-wipe problem alone.

## Scope

Full migration: all 4 existing SQLite tables (`clients`, `sent_log`,
`email_sent_log`, `notice_sent_log`) move to MongoDB collections. No
migration of existing SQLite data — this is a fresh start; the roster gets
re-uploaded via Excel Sync once the MongoDB-backed system is live, and
reminder-interval history (the WhatsApp/email "already sent" logs) resets
to empty rather than being ported over.

## Architecture

**Keep the interface, swap the internals.** `db.py` currently exposes ~25
functions (`get_clients_page`, `upsert_clients`, `is_already_sent`,
`get_eligible_clients`, `record_notice_sent`, etc.) that `main.py` and
every sender module (`email_alerts.py`, `whatsapp_renewal_alerts.py`,
`notice_sender.py`) call directly. This migration rewrites what's *inside*
those functions to talk to MongoDB via `pymongo` instead of `sqlite3`, but
keeps every function's name, parameters, and return shape identical.
Nothing outside `db.py` changes — no caller needs to be touched, and the
frontend/API contract is completely unaffected.

A new `wasabi.py` module handles the upload-archival piece (see below),
called from the existing `/api/upload-clients` and `/api/merge-clients`
endpoints in `main.py` — those endpoints gain one additional step (archive
to Wasabi, record in MongoDB) but keep their existing request/response
shape.

## Data Model

Four collections mirror the four current SQLite tables, using the same
field names as `RECORD_FIELDS` and the existing table schemas (so the
JSON shape returned by `/api/clients`, `/api/stats`, etc. doesn't change):

- **`clients`** — one document per client. `client_id` is the document's
  `_id` (mirrors SQLite's primary key), giving natural upsert semantics
  via `replace_one(..., upsert=True)`.
- **`sent_log`** — one document per WhatsApp renewal-alert send:
  `{client_id, status, sent_date, message_id, phone, sent_at}`. Indexed
  on `(client_id, status)` to support the 20-day reminder-interval lookup
  (find the most recent `sent_date` for a given client+status).
- **`email_sent_log`** — same shape as `sent_log`, with `email` instead of
  `phone`, for renewal-alert emails.
- **`notice_sent_log`** — one document per broadcast-notice send:
  `{client_id, notice_id, channel, message_id, sent_at}`, indexed on
  `(client_id, notice_id, channel)` for the permanent (non-expiring)
  notice dedup check.

**New collection — `uploads`**: one document per Excel upload/merge event:
`{uploaded_at, filename, import_format, mode, row_count, wasabi_url}`.
Pure audit trail — nothing else reads from this collection; it exists so
there's a record of what was uploaded and when, with a link back to the
archived original file.

## Wasabi Upload Archival

When `/api/upload-clients` or `/api/merge-clients` receives a file:
1. The file is parsed and imported into MongoDB exactly as it is into
   SQLite today (via the existing per-format importers — `import_crs.py`,
   `import_bis_isi_data.py`, etc. — unaffected by this migration).
2. The original file bytes are uploaded to the configured Wasabi bucket
   under a timestamped key (e.g. `uploads/2026-08-04T14-30-00_roster.xlsx`).
3. A new document is inserted into the `uploads` collection recording the
   Wasabi URL alongside the upload's metadata (filename, row count, mode).

If the Wasabi upload fails, the client import still succeeds (the archive
is a nice-to-have audit record, not a dependency of the core import path)
— the failure is logged but doesn't roll back or block the response.

## Testing Strategy

The existing 307 tests create a fresh temp SQLite file per test via
pytest's `tmp_path` fixture for isolation. That pattern is replaced with
**`mongomock`** (a new dev dependency) — an in-memory fake MongoDB
implementing the same `pymongo` API. Each test gets a fresh
`mongomock.MongoClient()` instance instead of a temp file path, giving the
same per-test isolation guarantee with no real database connection needed
during test runs. Test *assertions* (what's returned, what counts as
eligible, dedup behavior) stay conceptually the same — only the
setup/fixture plumbing changes from "write rows to a temp SQLite file" to
"insert documents into a mock collection."

Wasabi calls in tests are mocked at the `boto3` client level (matching the
existing pattern already used for WhatsApp/Brevo API calls in this
codebase — `patch("module.requests.post", ...)`), so no test ever makes a
real network call to Wasabi.

## Deployment

New required environment variables, replacing `DASHBOARD_DB_PATH`:
- `MONGODB_URI` — Atlas connection string
- `WASABI_ACCESS_KEY`, `WASABI_SECRET_KEY`, `WASABI_BUCKET`,
  `WASABI_ENDPOINT`

`render.yaml` and `docs/DEPLOYMENT.md` are updated to reflect this new
config instead of the persistent-disk instructions written earlier. This
migration incidentally solves the Render free-tier redeploy-wipe problem,
since both MongoDB Atlas and Wasabi are external, persistent stores
entirely decoupled from Render's filesystem — no paid Render disk is
needed after this migration.

## What Does Not Change

- The frontend (no changes at all — it only talks to the same `/api/*`
  endpoints with the same shapes).
- Every endpoint URL, request format, and response JSON shape in `main.py`.
- The notice/email/WhatsApp sending logic, content modules, and per-scheme
  template selection (`scheme_templates.py`, `notice_meity_series_guidelines_2026.py`,
  etc.) — none of these touch the database directly, they all go through
  `db.py`'s functions.
- The per-format Excel importers (`import_crs.py`, `import_bis_isi_data.py`,
  `import_helpers.py`) — they still produce the same row tuples; only what
  `upsert_clients` does with those tuples changes internally.

## Testing

- `db.py`: every existing test in `test_db.py` is ported to use
  `mongomock` instead of a temp SQLite file, and must pass with identical
  assertions — proving the MongoDB-backed implementation is behaviorally
  identical to the SQLite one it replaces.
- `wasabi.py`: unit tests for the archive-on-upload function, mocking the
  `boto3` S3 client, covering both the success path (document inserted
  into `uploads` with the correct Wasabi URL) and the failure path (Wasabi
  upload fails, but the client import still succeeds and returns 200).
- `main.py`: existing `test_main.py` upload/merge endpoint tests continue
  to pass unchanged in their assertions on the API response; new
  assertions added for the `uploads` collection side effect.
- Full-stack: after migration, manually verify Excel Sync → Replace
  against a real (free-tier) MongoDB Atlas cluster and Wasabi bucket, not
  just the mocked test suite, before considering this done.
