# Multi-Scheme Import Framework + Duration Filter + Filtered Bulk Send

## Problem

The dashboard currently only ingests one certification scheme cleanly (BIS ISI, via a
bespoke parser). Absolute Veritas needs to bring in more schemes over time (FMCS, CRS,
and others), each arriving as a raw registry export with its own quirky column layout —
same situation BIS ISI was in before its parser was written.

Two smaller gaps compound this:

1. There's no quick way to look at "what's expiring in the next N months" — only a raw
   date picker.
2. "Send All Eligible" and "Send All Emails" always target every alert-eligible client
   system-wide, ignoring whatever filters are currently applied to the table. There's no
   way to send only to, say, "FMCS clients expiring in the next 3 months."

## Scope

This round ships:

- A pluggable per-scheme import framework, with BIS ISI migrated into it as the first
  (and so far only) registered scheme.
- Duration preset buttons (3 months / 6 months / 1 year) next to the existing "Expiry
  before" date field.
- A scope choice (all eligible vs. currently filtered) in the bulk-send confirmation
  flow, backed by filter-aware bulk-send endpoints.

Writing actual FMCS/CRS parsers is **out of scope** for this round — no sample files are
in hand yet. That's a follow-up once real files are available, and should be a small
addition on top of the framework built here (new `import_<scheme>.py` + one registry
line), not a new design.

## 1. Pluggable per-scheme import framework

### Current state

`dashboard-app/backend/import_bis_isi_data.py` mixes two kinds of code:

- Generic helpers usable by *any* scheme parser: `RowCollector`, `parse_validity_date`,
  `compute_status`, `header_index_map`, `get`.
- BIS-ISI-specific code: `looks_like_bis_isi_workbook` (detector) and
  `import_bis_isi_workbook` (importer).

`main.py`'s `/api/upload-clients` and `/api/merge-clients` each contain their own copy of
the same detection chain:

```python
if actual_headers == REQUIRED_HEADERS:
    ...  # generic "roster" format
elif looks_like_bis_isi_workbook(wb):
    ...  # BIS ISI format
else:
    raise HTTPException(400, ...)
```

### New structure

- **`dashboard-app/backend/import_helpers.py`** (new file) — the five generic helpers,
  moved out of `import_bis_isi_data.py` unchanged.
- **`dashboard-app/backend/import_bis_isi_data.py`** — keeps only
  `looks_like_bis_isi_workbook` and `import_bis_isi_workbook`, importing the generic
  helpers from `import_helpers`. The module's CLI entry point (`import_bis_isi`,
  `if __name__ == "__main__"`) is untouched.
- **`dashboard-app/backend/import_formats.py`** (new file) — the registry:

  ```python
  from import_bis_isi_data import looks_like_bis_isi_workbook, import_bis_isi_workbook

  IMPORT_FORMATS = [
      ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook),
  ]
  ```

  Each entry is `(format_name: str, detector: Callable[[Workbook], bool], importer:
  Callable[[Workbook, RowCollector | Worksheet, today=None], dict])`. `detector` and
  `importer`'s signatures exactly match `looks_like_bis_isi_workbook` /
  `import_bis_isi_workbook` today, so BIS ISI needs no behavior change — only relocation.

- **`main.py`** — both endpoints replace their hardcoded `elif looks_like_bis_isi_workbook`
  branch with a loop over `IMPORT_FORMATS`, trying each detector in order and calling the
  matching importer. The exact-header "roster" check stays a special case checked first
  in both endpoints (it isn't a registry entry — it's the trivial identity format with no
  detector function, matching today's precedence order unchanged).

### Adding a future scheme (e.g. FMCS)

1. Write `import_fmcs.py` with `looks_like_fmcs_workbook(wb) -> bool` and
   `import_fmcs_workbook(wb, out_ws, today=None) -> dict`, using `import_helpers`
   functions and following `import_bis_isi_data.py` as a template.
2. Add `("fmcs", looks_like_fmcs_workbook, import_fmcs_workbook)` to `IMPORT_FORMATS` in
   `import_formats.py`.

No endpoint changes required.

### Multiple schemes coexisting

Different schemes' client rows coexist in the same `clients` table as long as their
`client_id`s don't collide (already true for BIS ISI, whose `client_id` is the licence
number — a different scheme's parser must pick an equally scheme-unique key). Uploading
a new scheme's file uses `/api/merge-clients` (not `/api/upload-clients`, which replaces
the whole table) so existing schemes' data is preserved.

## 2. Duration presets

Three buttons — "3 months", "6 months", "1 year" — next to the existing "Expiry before"
date input in `ClientTable.jsx`. Clicking one computes `today + N months` (calendar
months, e.g. 3 months from 2026-07-24 → 2026-10-24) and writes it into the same
`expiryBefore` state the date input already controls — so it drives table filtering, CSV
export, and (per part 3 below) bulk-send scope exactly like manually typing a date does
today. A "Clear" affordance (or re-clicking the active preset) resets it to no filter.
This is purely a frontend addition — `get_clients_page`'s existing `expiry_before` param
handles the rest unchanged.

## 3. Filtered bulk send

### Backend

- `get_clients_page`'s existing filter logic (`status`, `cert_type`, `expiry_before`
  WHERE clauses) is extracted from `db.py` into a shared helper,
  `_client_where_clause(status, cert_type, expiry_before)`, reused by three call sites:
  `get_clients_page`, a new `get_eligible_count`, and the bulk-send functions below. The
  "currently filtered view" scope mirrors *all three* filters the table supports — not
  just cert type and expiry window — so the count shown in the confirm modal always
  matches what's actually visible on screen. (If `status="ACTIVE"` is part of the active
  filter, the filtered count is correctly 0, since ACTIVE is never alert-eligible — this
  is expected, not a bug.)
- **New:** `db.get_eligible_count(db_path, today, channel, status=None, cert_type=None,
  expiry_before=None) -> int` — counts alert-eligible, not-yet-sent-today (for
  `channel="whatsapp"`) or not-yet-emailed-today (for `channel="email"`) clients matching
  the optional filters. `status`, when given, further narrows within the alert-eligible
  set (e.g. `status="CRITICAL"` counts only Critical-tier eligible clients) rather than
  replacing the alert-eligibility check.
- **New endpoint:** `GET /api/eligible-count?status=&cert_type=&expiry_before=` →
  `{"whatsapp": N, "email": M}`. Called by the frontend when a send-all confirm modal
  opens, using whatever filters are currently active in the table.
- `/api/send-all` and `/api/send-all-emails` both gain optional `status`, `cert_type`,
  and `expiry_before` query params. When present, the job only processes clients matching
  those filters (same WHERE clause as above); when absent, behavior is unchanged
  (all eligible clients system-wide) — so existing tests and existing automation/cron
  usage keep working with no params supplied.

### Frontend

- `SendAllConfirmModal` gains a scope choice, shown before the existing confirm step:
  two radio-style options, "All eligible clients (N)" and "Currently filtered view (M)",
  where N and M come from `/api/eligible-count` (N with no filters, M with the table's
  current `status`/`cert_type`/`expiry_before`). Picking "Currently filtered view" when M
  is 0 disables the confirm action (nothing to send).
- `App.jsx`'s `handleConfirmSendAll` / `handleConfirmSendAllEmails` pass the chosen
  scope's filters (or none, for "all eligible") through to `sendAllAlerts` /
  `sendAllEmailAlerts`, which add them as query params.
- If the table's filters change *after* the modal opens but before confirming, the shown
  counts become stale; this is acceptable since the modal is closed and reopened for each
  send action; no live-refresh needed.

## Testing

- Backend: `import_helpers.py` functions get moved (not rewritten) — existing
  `import_bis_isi_data` tests continue to pass unchanged, pointed at the new import
  location. New tests for the `IMPORT_FORMATS` registry loop in `main.py` (both
  endpoints still resolve BIS ISI files correctly through the registry). New tests for
  `get_eligible_count` (with/without each of `status`/`cert_type`/`expiry_before`, both
  channels, including the `status="ACTIVE"` → 0 case) and for `/api/eligible-count`. New
  tests for `/api/send-all` and `/api/send-all-emails` with `status`/`cert_type`/
  `expiry_before` params, confirming filtered vs. unfiltered scope.
- Frontend: new tests for the duration preset buttons (each sets the expected date,
  clearing works). New tests for `SendAllConfirmModal`'s scope choice (shows both counts,
  confirm disabled when filtered count is 0, correct filters passed through on confirm).
