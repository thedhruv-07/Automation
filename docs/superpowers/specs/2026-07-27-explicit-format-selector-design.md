# Explicit Import Format Selector

## Problem

Upload format is currently auto-detected: `/api/upload-clients` and
`/api/merge-clients` first check for an exact roster-header match, then
iterate `IMPORT_FORMATS` trying each raw-format detector in turn. If a raw
file's headers don't precisely match a detector's strict check (a header
spelled slightly differently, an export variant), the upload is rejected
with a single generic "Column headers don't match the expected format"
message that doesn't say *which* format was being attempted, or what that
format actually needed. As more raw formats are added (CRS just landed,
FMCS planned), this guessing-and-cascading approach also risks two formats'
loose detectors someday colliding.

## Scope

Add a required format selector to the Excel Sync upload flow (`Roster`,
`BIS ISI`, `CRS`, and a disabled `FMCS (coming soon)` placeholder). The
selection drives dispatch directly — no more cascading through every
registered format hoping one matches — and a mismatch between the selected
format and the actual file produces a targeted, specific error naming what
that format needed, instead of one generic message.

## 1. Unify "roster" into `IMPORT_FORMATS`

Today, `main.py`'s upload/merge endpoints special-case the roster format
(exact match against `REQUIRED_HEADERS`) separately from the
`IMPORT_FORMATS` loop used for raw formats. This round adds a
`looks_like_roster_workbook(wb)` / `import_roster_workbook(wb, out_ws,
today=None)` pair with the same interface every other registry entry
already has — `import_roster_workbook` passes rows through unchanged, since
they're already roster-shaped. `IMPORT_FORMATS` becomes:

```python
IMPORT_FORMATS = [
    ("roster", looks_like_roster_workbook, import_roster_workbook,
     "the exact roster template headers (Client ID, Full Name, Company, ...)"),
    ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook,
     "a Licence No. and Firm Name column"),
    ("crs", looks_like_crs_workbook, import_crs_workbook,
     "a License No. and Organization Name column"),
]
```

The new 4th field is a short human-readable description of what that
format's detector looks for, used to build a targeted error message.

## 2. Backend endpoint dispatch

`/api/upload-clients` and `/api/merge-clients` both gain a required
`format: str = Form(...)` field, sent alongside the file in the same
multipart request. Endpoint logic changes from "cascade through every
registered format" to a direct lookup:

1. Find the `IMPORT_FORMATS` entry whose `format_name` matches the request's
   `format` value. An unrecognized value is a 400 ("Unknown format
   'xyz'.").
2. Run *only* that entry's detector against the uploaded workbook. If it
   returns `False`, respond 400 with:
   `f"This doesn't look like a valid {display_name} export — expected {expected_columns}."`
   (`display_name` from a small `{"roster": "roster", "bis_isi": "BIS ISI",
   "crs": "CRS"}` label map; `expected_columns` from the registry's 4th
   field.)
3. If the detector passes, run that entry's importer and proceed exactly as
   today (upsert, or merge-specific duplicate handling).

No more silently trying a different format than the one the user actually
selected, and a genuine mismatch gets a message that names the specific
columns expected — actionable rather than generic.

## 3. Frontend — `ExcelSyncView.jsx`

- New required `<select>` above the drop zone: a disabled placeholder
  (`"-- Select format --"`, selected by default), then `Roster (dashboard
  template)` / `BIS ISI (raw government export)` / `CRS (raw government
  export)`, plus a disabled `FMCS (coming soon)` option (no importer exists
  yet — listed so the UI communicates what's planned, per earlier
  decision).
- The existing Upload/Merge buttons (shown once a file is picked) become
  disabled unless a real format is *also* selected — both conditions
  required, not just a file.
- `onUpload`/`onMerge` props gain a second argument: `onUpload(file,
  format)` / `onMerge(file, format)`.
- Result-banner generalization: today's success message only shows the
  "Converted BIS ISI licence export — N rows loaded from M sheets..."
  detail when `result.format === "bis_isi"` (checked via a hardcoded
  string), with anything else (including CRS today) silently falling
  through to a generic "Import succeeded" line despite having the same
  stats available. Since format is now explicit rather than inferred, this
  becomes a small `{bis_isi: "BIS ISI licence", crs: "CRS registration"}`
  label map so both raw formats get the full stats sentence with the
  correct wording, and only genuine `"roster"` uploads get the plain
  message.

## 4. `api.js`

`uploadClientsFile(file, format)` / `mergeClientsFile(file, format)` both
gain a `format` parameter, appended to the `FormData` alongside `"file"`.

## 5. `App.jsx`

Wherever `onUpload={...}`/`onMerge={...}` are passed to `<ExcelSyncView>`,
the handlers gain a `format` parameter and pass it straight through to
`uploadClientsFile`/`mergeClientsFile`. No new state needed here — the
selected format lives inside `ExcelSyncView`'s own local state, matching
where `selectedFile` already lives today.

## Testing

- Backend: `looks_like_roster_workbook`/`import_roster_workbook` unit
  tests (exact-header match, pass-through row shape). Endpoint tests: each
  of the three formats succeeds when selected against its own matching
  file; each produces the new targeted mismatch error when selected against
  a file that isn't actually that format; an unrecognized `format` value is
  a 400; omitting `format` entirely is a 422 (FastAPI's own required-field
  validation).
- Every existing upload/merge test in `test_main.py` needs a
  `data={"format": "roster"}` (or `"bis_isi"`/`"crs"` for the raw-format
  conversion tests) added to its `client.post(...)` call, now that the
  field is required — mechanical, one line per test, but touches roughly a
  dozen existing tests.
- Frontend: `api.test.js` — `uploadClientsFile`/`mergeClientsFile` tests
  updated to pass and assert on the `format` FormData field.
  `ExcelSyncView.test.jsx` — new tests for the format dropdown (options
  present, FMCS disabled, upload/merge buttons stay disabled until both
  file and format are set), and updated existing tests to select a format
  before triggering upload/merge (since the buttons are now conditionally
  disabled).
