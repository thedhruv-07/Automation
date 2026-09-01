# CRS Importer (`import_crs.py`)

## Problem

~1,800 CRS (Compulsory Registration Scheme) client rows need to enter the
dashboard's roster, but the raw BIS CRS export is a different format from
the BIS ISI license register `import_bis_isi_data.py` already converts:
different headers, no explicit expiry/validity column, and a multi-sheet
layout with a rollup "master" sheet alongside per-standard sheets.

## Scope

Add `import_crs.py`, following `import_bis_isi_data.py`'s exact template —
`import_helpers.py`'s own docstring already anticipates this file
(`"...and future ones like import_fmcs.py/import_crs.py"`). Register it in
`import_formats.py` so both `/api/upload-clients` and `/api/merge-clients`
pick it up automatically, no endpoint changes needed.

## 1. Source format

Raw CRS workbook structure (per the source screenshot):
- A `"BIS_CRS_Master"` sheet containing every client row across all
  standards combined.
- One sheet per Indian Standard (e.g. `"IS 13252"`), each containing the
  *same* rows as their slice of the Master sheet — i.e. Master is a
  duplicate rollup, not additional data.
- Header row per sheet: `Application No.`, `License No.`, `Organization
  Name`, `Country`, `Indian Standard`, `Product Name`, `Product Category`,
  `Grant Date`, `Status`, `E-mail`, `Phone No.`

There is no expiry/validity date column, and no column distinguishing an
initial registration from a renewal either. **Updated 2026-08-14**: a
first-time CRS registration is valid 2 years, but a renewal can be granted
for 2–5 years (confirmed against BIS's actual rules, not assumed) — since
the source data can't tell which a given row is, expiry is computed as
**Grant Date + 5 years** (the maximum real term) everywhere, a deliberate
overstatement for first-time registrations accepted in exchange for never
under-flagging a renewed license's real expiry. See `import_crs.py`'s
module docstring for the full reasoning.

## 2. Detection — `looks_like_crs_workbook(wb)`

True if any sheet's header row has both a `"license no"` and an
`"organization name"` column (case-insensitive, via the existing
`header_index_map` helper). Deliberately different spelling from BIS ISI's
own detector (`"licence no"` / `"firm name"`), so the two formats can never
be mistaken for each other — this doesn't need to exclude the Master sheet,
since Master has the same header shape and matching it too still correctly
identifies the workbook as CRS.

## 3. Import — `import_crs_workbook(wb, out_ws, today=None)`

Iterates every sheet **except** one whose name case-insensitively equals
`"bis_crs_master"` — that sheet duplicates every per-standard sheet's rows,
so importing it too would double-count every client.

For each data row in a per-standard sheet, columns map to roster fields as:

| Roster field | Source column | Notes |
|---|---|---|
| `client_id` / `cert_id` | License No. | e.g. `"R-7019869"`; same collision-suffix fallback as ISI (`f"{license_no}-{cert_name}"` if a license number repeats across sheets) |
| `name` / `company` | Organization Name | Same field for both — no separate contact-person column, matching ISI's `firm_name` pattern |
| `email` | E-mail | |
| `phone` | Phone No. | Used as-is; malformed international numbers fail at send-time the same way any bad phone number already does today — no per-country special-casing |
| `cert_name` | Indian Standard | Not combined with Product Category, per decision |
| `scheme` | — | Hardcoded `"CRS"` |
| `issue_date` | Grant Date | |
| `expiry_date` | Grant Date + 5 years (updated 2026-08-14, was +2) | Computed via a local `add_years()` helper |
| `renewal_link` | — | `None`, no source equivalent, same as ISI |
| `status` | — | Recomputed via `compute_status()`, not the source Status column (which just says "Register"/"Registered" — a different meaning, same reasoning ISI's own source Status column already documents) |

A row is skipped (and counted in `rows_skipped_missing_key`) if it has no
License No. or no Grant Date — without both, there's no identity or no way
to compute an expiry.

`add_years(dt, years)` is a small local helper (not added to the shared
`import_helpers.py`, since no other importer needs it yet):

```python
def add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # dt is Feb 29 and dt.year + years isn't a leap year.
        return dt.replace(year=dt.year + years, day=28)
```

Returned stats dict has the same shape as ISI's: `sheets_used`,
`sheets_empty`, `rows_written`, `rows_skipped_missing_key`. This means
`ExcelSyncView.jsx`'s existing result summary renders correctly for a CRS
upload with zero frontend changes — it already knows how to display these
same keys generically. One cosmetic gap: that summary's skip-count sentence
hardcodes the words "missing licence no / validity date" regardless of which
format was uploaded, so a CRS upload's skipped-row count will render with
ISI-flavored wording. Not fixed as part of this work — flagged as a known,
low-priority follow-up.

## 4. Registration — `import_formats.py`

```python
from import_bis_isi_data import looks_like_bis_isi_workbook, import_bis_isi_workbook
from import_crs import looks_like_crs_workbook, import_crs_workbook

IMPORT_FORMATS = [
    ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook),
    ("crs", looks_like_crs_workbook, import_crs_workbook),
]
```

## 5. CLI entrypoint

Mirrors `import_bis_isi_data.py`'s standalone usage exactly:

```
python import_crs.py "<path to source xlsx>"
```

Writes converted rows to `data/clients_certifications.xlsx` (same default
output path ISI's CLI entrypoint uses), printing the same
sheets-used/sheets-empty/rows-written/rows-skipped summary.

## Testing

- `looks_like_crs_workbook`: detects the per-standard sheet shape; does not
  false-positive on a BIS ISI workbook (different header spelling); does not
  false-positive on an unrelated workbook.
- `import_crs_workbook`:
  - Converts a well-formed per-standard sheet's rows correctly, including
    `scheme == "CRS"` and computed expiry = Grant Date + 5 years.
  - Skips the `"BIS_CRS_Master"` sheet entirely (proven by seeding Master and
    a per-standard sheet with the *same* license numbers and asserting each
    client appears exactly once in the output, not twice).
  - Skips rows missing License No. or Grant Date, counted in
    `rows_skipped_missing_key`.
  - Collision-suffixes `client_id` when the same License No. appears in two
    different per-standard sheets (a legitimate case here, since Master
    duplication is already excluded — this covers a client actually holding
    two different standards).
  - Handles a Feb 29 Grant Date whose +2-years target isn't a leap year
    (falls back to Feb 28) without raising.
- `import_formats.py`: `IMPORT_FORMATS` includes the new `"crs"` entry and
  `/api/upload-clients` correctly routes a CRS-shaped workbook to it (as an
  integration test, mirroring however the existing BIS ISI routing is
  tested in `test_main.py`).
