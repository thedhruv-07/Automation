# Certification Scheme Field + Filter

## Problem

The dashboard has no way to distinguish which certification *scheme* (ISI, and
eventually FMCS, CRS, etc.) a client's row belongs to. The only grouping today
is `cert_name` — an individual certification code (e.g. "IS 1717") — which
doesn't map cleanly to a scheme once multiple schemes' codes are mixed
together in the same "All Cert Types" dropdown. All ~66,745 real client rows
currently in production are BIS ISI data, with no scheme value recorded
anywhere.

## Scope

This round adds a `scheme` field to the client data model, a dedicated Scheme
filter dropdown (independent of the existing Cert Type filter), and threads it
through every filter-aware code path the existing `cert_type` filter already
reaches (table view, CSV export, eligible-count, and bulk-send scope).

Writing FMCS/CRS importers themselves is still out of scope (as before, no
sample files are in hand yet) — those importers, when written, will simply
set `scheme` to their own value the same way BIS ISI's does.

## 1. Data model and migration

Add `scheme TEXT` to the `clients` table schema in `db.py`. Because
`CREATE TABLE IF NOT EXISTS` does not add a column to an already-existing
table, `init_db()` gains a small migration step, run every time it's called
(cheap and idempotent):

1. `PRAGMA table_info(clients)` — check whether a `scheme` column already
   exists.
2. If not: `ALTER TABLE clients ADD COLUMN scheme TEXT`.
3. `UPDATE clients SET scheme = 'ISI' WHERE scheme IS NULL` — classifies any
   row that predates this migration (all real production data today) as ISI,
   without touching any row that already has an explicit scheme value (so a
   manually-corrected or newly-imported row is never silently overwritten).

This runs automatically on every `init_db()` call, so it self-heals after
Render's free-tier data resets without a manual one-off script.

`scheme` is added to `RECORD_FIELDS` immediately after `cert_name`, so it
flows through `read_clients`, `find_client_by_id`, `upsert_clients`,
`get_clients_page`, and `export_clients_rows` automatically (all of which key
off `RECORD_FIELDS`). It's added to `_SORTABLE_COLUMNS` too, matching
`cert_name`'s existing sortability.

## 2. Import paths

- **BIS ISI importer** (`import_bis_isi_data.py`): every row it produces gets
  `scheme = "ISI"` hardcoded — the source file has no equivalent column, so
  this doesn't come from parsed data, matching how `cert_name` already falls
  back to the sheet name when the source has no "Standard" column.
- **Manual "roster" format** (`REQUIRED_HEADERS`, the Excel
  upload/merge/template/CSV-export contract): gains a required "Scheme"
  column, positioned right after "Certification Name". Existing exported
  templates/CSVs from before this change won't have the column and will need
  re-downloading — this is an accepted breaking change to that format, not a
  concern users hit silently (a header-mismatch 400 already surfaces clearly
  today for any format drift).
- **Future FMCS/CRS importers**: each hardcodes its own scheme value the same
  way BIS ISI does, when written.

## 3. Filtering

`_client_filters_where` (the shared helper introduced in the last round)
gains a `scheme` parameter, applied as `scheme = ?` when set and not `"ALL"` —
exactly mirroring `cert_type`'s existing clause, and independent of it (both
conditions AND together; no cross-narrowing between the two dropdowns).

This threads through every existing consumer of that helper: `get_clients_page`,
`export_clients_rows`, `get_eligible_clients`, `get_eligible_count`. The
corresponding endpoints — `/api/clients`, `/api/clients/export`,
`/api/eligible-count`, `/api/send-all`, `/api/send-all-emails` — each gain an
optional `scheme` query param, passed through exactly where `cert_type` is
today. `run()` and `run_email_alerts()` gain a matching `scheme` keyword
argument.

`get_stats` gains a `schemes` list (distinct non-null `scheme` values, sorted
— the same query shape as the existing `cert_types` list).

## 4. Frontend

- `ClientDataFilters.jsx` gains a new "All Schemes" `<select>` (populated
  from `stats.schemes`, dynamic — so today it only ever shows "ISI" until
  FMCS/CRS data exists), placed before the existing "All Cert Types" dropdown.
  Its "Clear All" visibility check (`hasFilters`) is extended to include an
  active scheme filter.
- `App.jsx` gains `scheme`/`setScheme` state, threaded through `queryParams`
  (table fetch), `exportFilters` (CSV export link), the eligible-count fetch
  effect, and both `handleConfirmSendAll`/`handleConfirmSendAllEmails`
  filter objects — at every one of those call sites, in exactly the same
  shape `certType` already has.
- The client table itself (`ClientTable.jsx`) does **not** gain a new visible
  "Scheme" column — it's exposed via the filter dropdown and CSV export only,
  keeping the table from growing wider.

## Testing

- Backend: a new migration test confirming `init_db()` adds the column to an
  existing pre-migration database and backfills only NULL rows to `'ISI'`,
  leaving any already-set scheme value untouched. New/updated tests for
  `_client_filters_where`, `get_clients_page`, `export_clients_rows`,
  `get_eligible_clients`, `get_eligible_count` filtering by `scheme`. Every
  existing row-tuple fixture across `test_db.py`, `test_main.py`,
  `test_whatsapp_renewal_alerts.py`, and `test_email_alerts.py` gains an
  explicit scheme value (mechanical, one-by-one). BIS ISI import tests confirm
  `scheme == "ISI"` on every produced row. Endpoint tests confirm `scheme` as
  a query param on `/api/clients`, `/api/clients/export`, `/api/eligible-count`,
  `/api/send-all`, `/api/send-all-emails`.
- Frontend: new tests for the Scheme dropdown in `ClientDataFilters.test.jsx`
  (calls `onSchemeChange`, appears in `hasFilters`), and updated/new tests in
  `App.test.jsx` confirming `scheme` flows into `getClients`, `clientsExportUrl`,
  `getEligibleCount`, and both bulk-send confirm handlers' filter objects.
