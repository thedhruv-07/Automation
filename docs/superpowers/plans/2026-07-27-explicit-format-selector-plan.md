# Explicit Import Format Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace auto-detection-by-cascade with an explicit, required format selector (`Roster` / `BIS ISI` / `CRS`, with `FMCS` shown disabled) on the Excel Sync upload/merge flow, so a mismatch between the selected format and the actual file produces a targeted error naming what that format needed, instead of one generic message.

**Architecture:** `REQUIRED_HEADERS` moves from `main.py` into `import_helpers.py` (removing a circular-import risk), a new `import_roster.py` gives the roster format the same `(detector, importer)` interface every raw format already has, and `IMPORT_FORMATS` entries grow a 4th field (a short description of expected columns for targeted error messages). Both `/api/upload-clients` and `/api/merge-clients` gain a required `import_format` form field and look up their `(detector, importer, expected_columns)` triple directly by name instead of cascading through every registered format. The frontend gains a required dropdown that must be set (alongside a file) before the Upload/Merge buttons enable.

**Tech Stack:** Python/FastAPI (`dashboard-app/backend/`), React/Vite (`dashboard-app/frontend/`), pytest, Vitest + React Testing Library.

---

### Task 1: `import_helpers.py` gains `REQUIRED_HEADERS`; new `import_roster.py`

**Files:**
- Modify: `dashboard-app/backend/import_helpers.py`
- Create: `dashboard-app/backend/import_roster.py`
- Create: `dashboard-app/backend/test_import_roster.py`

- [ ] **Step 1: Move `REQUIRED_HEADERS` into `import_helpers.py`**

Current (`dashboard-app/backend/import_helpers.py`):

```python
"""Generic helpers shared by every per-scheme importer (import_bis_isi_data.py
and future ones like import_fmcs.py/import_crs.py) -- none of this is specific
to any one certification scheme's raw export format."""
from datetime import datetime
```

Replace with:

```python
"""Generic helpers shared by every per-scheme importer (import_bis_isi_data.py
and future ones like import_fmcs.py/import_crs.py) -- none of this is specific
to any one certification scheme's raw export format."""
from datetime import datetime

REQUIRED_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Scheme", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

(This lives here rather than in `main.py` so `import_roster.py` -- Step 3 below -- can use it without an import cycle back into `main.py`.)

- [ ] **Step 2: Write the failing tests for `import_roster.py`**

Create `dashboard-app/backend/test_import_roster.py`:

```python
"""Tests for import_roster.py -- the passthrough "importer" for the
dashboard's own roster template, unified into the same detector/importer
interface every raw-format importer already has."""
import openpyxl

from import_helpers import REQUIRED_HEADERS
from import_roster import RowCollector, import_roster_workbook, looks_like_roster_workbook


def _workbook(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    return wb


def test_looks_like_roster_workbook_matches_exact_headers():
    wb = _workbook(REQUIRED_HEADERS, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    assert looks_like_roster_workbook(wb) is True


def test_looks_like_roster_workbook_rejects_wrong_headers():
    wb = _workbook(["Wrong", "Headers", "Here"], [["a", "b", "c"]])
    assert looks_like_roster_workbook(wb) is False


def test_looks_like_roster_workbook_rejects_empty_sheet():
    wb = openpyxl.Workbook()
    assert looks_like_roster_workbook(wb) is False


def test_import_roster_workbook_passes_rows_through_unchanged():
    row = ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
           "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"]
    wb = _workbook(REQUIRED_HEADERS, [row])
    collector = RowCollector()

    stats = import_roster_workbook(wb, collector)

    assert stats["rows_written"] == 1
    assert list(collector.rows[0]) == row


def test_import_roster_workbook_skips_blank_rows():
    good_row = ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
                "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"]
    blank_row = [None] * 12
    wb = _workbook(REQUIRED_HEADERS, [good_row, blank_row])
    collector = RowCollector()

    stats = import_roster_workbook(wb, collector)

    assert stats["rows_written"] == 1
    assert len(collector.rows) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_import_roster.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'import_roster'`.

- [ ] **Step 4: Create `import_roster.py`**

Create `dashboard-app/backend/import_roster.py`:

```python
"""Passthrough "importer" for the dashboard's own roster template -- the
Excel Sync upload/merge format whose rows are already shaped exactly like
RECORD_FIELDS (see db.py), needing no field-by-field conversion. Registered
in import_formats.py alongside the raw per-scheme importers so all formats
share one dispatch mechanism instead of the roster case being special-cased
separately in main.py.
"""
from import_helpers import RowCollector, REQUIRED_HEADERS  # noqa: F401 (RowCollector re-exported for tests)


def looks_like_roster_workbook(wb) -> bool:
    """True if the active sheet's header row exactly matches REQUIRED_HEADERS."""
    try:
        header_row = next(wb.active.iter_rows(values_only=True))
    except StopIteration:
        return False
    return list(header_row[:len(REQUIRED_HEADERS)]) == REQUIRED_HEADERS


def import_roster_workbook(wb, out_ws, today=None):
    """Passes already-roster-shaped rows through unchanged. `today` is
    accepted only to match every other importer's (wb, out_ws, today=None)
    interface -- roster rows already carry their own Expiry Date, nothing
    to compute."""
    rows_iter = wb.active.iter_rows(values_only=True)
    next(rows_iter)  # header row
    rows_written = 0
    for row in rows_iter:
        if not row or row[0] is None:
            continue
        out_ws.append(list(row[:len(REQUIRED_HEADERS)]))
        rows_written += 1
    return {"rows_written": rows_written}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_import_roster.py -v`
Expected: 5 passed.

- [ ] **Step 6: Run the full backend suite to confirm nothing else broke from the `REQUIRED_HEADERS` move**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all previously-passing tests still pass -- `main.py` still defines its own `REQUIRED_HEADERS` at this point (Task 3 removes it), so nothing else is affected yet.

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/import_helpers.py dashboard-app/backend/import_roster.py dashboard-app/backend/test_import_roster.py
git commit -m "feat: add import_roster.py, unifying the roster format into the importer interface"
```

---

### Task 2: `import_formats.py` — 4th field, roster entry, display names

**Files:**
- Modify: `dashboard-app/backend/import_formats.py`

- [ ] **Step 1: Add the roster entry, the expected-columns field, and a display-name map**

Current (`dashboard-app/backend/import_formats.py`):

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
from import_crs import looks_like_crs_workbook, import_crs_workbook

IMPORT_FORMATS = [
    ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook),
    ("crs", looks_like_crs_workbook, import_crs_workbook),
]
```

Replace with:

```python
"""Registry of import formats, looked up by name (the "import_format" form
field on /api/upload-clients and /api/merge-clients -- see main.py) rather
than sniffed by cascading through every entry. Each entry is
(format_name, detector, importer, expected_columns_hint):
  - detector(wb) -> bool: sniffs an already-open openpyxl Workbook; used to
    confirm a file actually matches its explicitly-selected format, not to
    guess the format itself.
  - importer(wb, out_ws, today=None) -> dict: appends converted roster rows
    to out_ws (a real worksheet or an import_helpers.RowCollector) and
    returns a stats dict that must include a "rows_written" key.
  - expected_columns_hint: a short human-readable description of the
    columns this format's detector looks for, used to build a specific
    error message when a file explicitly selected as this format doesn't
    actually match it.

To add a new scheme (e.g. FMCS): write import_fmcs.py with
looks_like_fmcs_workbook()/import_fmcs_workbook() following
import_bis_isi_data.py as a template, then add one line below plus an entry
in FORMAT_DISPLAY_NAMES. No endpoint changes needed -- both
/api/upload-clients and /api/merge-clients look up this list by name
already.
"""
from import_bis_isi_data import looks_like_bis_isi_workbook, import_bis_isi_workbook
from import_crs import looks_like_crs_workbook, import_crs_workbook
from import_roster import looks_like_roster_workbook, import_roster_workbook

IMPORT_FORMATS = [
    ("roster", looks_like_roster_workbook, import_roster_workbook,
     "the exact roster template headers (Client ID, Full Name, Company, ...)"),
    ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook,
     "a Licence No. and Firm Name column"),
    ("crs", looks_like_crs_workbook, import_crs_workbook,
     "a License No. and Organization Name column"),
]

FORMAT_DISPLAY_NAMES = {
    "roster": "roster",
    "bis_isi": "BIS ISI",
    "crs": "CRS",
}
```

- [ ] **Step 2: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all previously-passing tests still pass -- `main.py` still unpacks `IMPORT_FORMATS` as 3-tuples at this point (`for format_name, detector, importer in IMPORT_FORMATS`), which will now raise `ValueError: too many values to unpack` the moment those loops execute. This is expected and is exactly what Task 3 fixes; if you see failures here, confirm they're all `ValueError: too many values to unpack (expected 3)` from `main.py`'s upload/merge endpoints specifically, not something else.

- [ ] **Step 3: Commit**

```bash
git add dashboard-app/backend/import_formats.py
git commit -m "feat: unify roster into IMPORT_FORMATS with a 4th expected-columns field"
```

---

### Task 3: `main.py` — explicit `import_format`, targeted errors; `test_main.py` fixture updates

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Update imports**

Current:

```python
from fastapi import Depends, FastAPI, HTTPException, File, Query, UploadFile, status
```

Replace with:

```python
from fastapi import Depends, FastAPI, Form, HTTPException, File, Query, UploadFile, status
```

Current:

```python
from import_helpers import RowCollector  # noqa: E402
from import_formats import IMPORT_FORMATS  # noqa: E402
```

Replace with:

```python
from import_helpers import RowCollector, REQUIRED_HEADERS  # noqa: E402
from import_formats import IMPORT_FORMATS, FORMAT_DISPLAY_NAMES  # noqa: E402
```

- [ ] **Step 2: Remove `main.py`'s own `REQUIRED_HEADERS` definition (now imported instead)**

Current:

```python
REQUIRED_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Scheme", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]

# Mirrors the hardcoded day cutoffs in cert_automation.py (CRITICAL <= 7 days,
# URGENT <= 30 days). That script is intentionally untouched by this project,
# so these are documented here for display only, not read live from it.
CERT_STATUS_THRESHOLDS = {
    "critical_days": 7,
    "urgent_days": 30,
}
```

Replace with:

```python
# Mirrors the hardcoded day cutoffs in cert_automation.py (CRITICAL <= 7 days,
# URGENT <= 30 days). That script is intentionally untouched by this project,
# so these are documented here for display only, not read live from it.
CERT_STATUS_THRESHOLDS = {
    "critical_days": 7,
    "urgent_days": 30,
}
```

- [ ] **Step 3: Rewrite `upload_clients`**

Current:

```python
@app.post("/api/upload-clients", dependencies=[Depends(require_auth)])
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
        stats = _upsert_clients_or_400(rows, mode="replace")
        return {"status": "ok", "row_count": stats["row_count"], "format": "roster"}

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
```

Replace with:

```python
@app.post("/api/upload-clients", dependencies=[Depends(require_auth)])
async def upload_clients(file: UploadFile = File(...), import_format: str = Form(...)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    format_entry = next((f for f in IMPORT_FORMATS if f[0] == import_format), None)
    if format_entry is None:
        raise HTTPException(status_code=400, detail=f"Unknown format {import_format!r}.")
    _, detector, importer, expected_columns = format_entry

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

    if header_row is None:
        wb.close()
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=(
                f"The active sheet ('{active_title}') has no rows. If this file has "
                "multiple sheets, make sure the one with your client data is the sheet "
                "selected/visible when the file was last saved."
            ),
        )

    if not detector(wb):
        wb.close()
        tmp_path.unlink(missing_ok=True)
        display_name = FORMAT_DISPLAY_NAMES.get(import_format, import_format)
        raise HTTPException(
            status_code=400,
            detail=f"This doesn't look like a valid {display_name} export — expected {expected_columns}.",
        )

    collector = RowCollector()
    format_stats = importer(wb, collector)
    wb.close()
    tmp_path.unlink(missing_ok=True)

    if format_stats["rows_written"] == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Recognized this as a {import_format} file, but no rows had both a "
                "required identifier and a validity date to import."
            ),
        )

    stats = _upsert_clients_or_400(collector.rows, mode="replace")
    return {"status": "ok", "row_count": stats["row_count"], "format": import_format, "stats": format_stats}
```

- [ ] **Step 4: Rewrite `merge_clients`**

Current:

```python
@app.post("/api/merge-clients", dependencies=[Depends(require_auth)])
async def merge_clients(file: UploadFile = File(...)):
    """Adds rows from the uploaded spreadsheet to the existing roster instead
    of replacing it. Client IDs already present in the roster are left
    untouched — only genuinely new Client IDs get appended."""
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

Replace with:

```python
@app.post("/api/merge-clients", dependencies=[Depends(require_auth)])
async def merge_clients(file: UploadFile = File(...), import_format: str = Form(...)):
    """Adds rows from the uploaded spreadsheet to the existing roster instead
    of replacing it. Client IDs already present in the roster are left
    untouched — only genuinely new Client IDs get appended."""
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    format_entry = next((f for f in IMPORT_FORMATS if f[0] == import_format), None)
    if format_entry is None:
        raise HTTPException(status_code=400, detail=f"Unknown format {import_format!r}.")
    _, detector, importer, expected_columns = format_entry

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

    if header_row is None:
        wb.close()
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=(
                f"The active sheet ('{active_title}') has no rows. If this file has "
                "multiple sheets, make sure the one with your client data is the sheet "
                "selected/visible when the file was last saved."
            ),
        )

    if not detector(wb):
        wb.close()
        tmp_path.unlink(missing_ok=True)
        display_name = FORMAT_DISPLAY_NAMES.get(import_format, import_format)
        raise HTTPException(
            status_code=400,
            detail=f"This doesn't look like a valid {display_name} export — expected {expected_columns}.",
        )

    collector = RowCollector()
    format_stats = importer(wb, collector)
    wb.close()
    tmp_path.unlink(missing_ok=True)

    if format_stats["rows_written"] == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Recognized this as a {import_format} file, but no rows had both a "
                "required identifier and a validity date to import."
            ),
        )

    stats = _upsert_clients_or_400(collector.rows, mode="merge")
    return {
        "status": "ok", "row_count": stats["row_count"], "added": stats["added"],
        "skipped_duplicates": stats["skipped_duplicates"], "format": import_format, "stats": format_stats,
    }
```

- [ ] **Step 5: Run the full backend suite and confirm the expected failures**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: every existing `client.post("/api/upload-clients", ...)` / `client.post("/api/merge-clients", ...)` call in `test_main.py` that doesn't send an `import_format` form field now gets a `422 Unprocessable Entity` (FastAPI's own required-field validation) instead of whatever it expected before. This is expected — Step 6 fixes every one of these 16 call sites.

- [ ] **Step 6: Add `data={"import_format": ...}` to every existing upload/merge test**

Each fix below adds a `data={"import_format": "..."}` argument to an existing `client.post(...)` call in `dashboard-app/backend/test_main.py`. None of these change any other line in their test.

`test_upload_clients_success`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "row_count": 1, "format": "roster"}
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "row_count": 1, "format": "roster"}
```

`test_upload_clients_rejects_non_xlsx_extension`. Current:

```python
    response = client.post(
        "/api/upload-clients",
        files={"file": ("clients.csv", b"not,a,real,xlsx", "text/csv")},
    )
    assert response.status_code == 400
```

Replace with:

```python
    response = client.post(
        "/api/upload-clients",
        files={"file": ("clients.csv", b"not,a,real,xlsx", "text/csv")},
        data={"import_format": "roster"},
    )
    assert response.status_code == 400
```

`test_upload_clients_rejects_wrong_headers`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("bad.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 400
    assert not db_path.exists()
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("bad.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 400
    assert not db_path.exists()
```

`test_upload_clients_rejects_empty_active_sheet_with_clear_message`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("multi_sheet.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 400
    assert "EmptyActive" in response.json()["detail"]
    assert not db_path.exists()
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("multi_sheet.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 400
    assert "EmptyActive" in response.json()["detail"]
    assert not db_path.exists()
```

`test_upload_clients_converts_raw_bis_isi_workbook`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("BIS ISI Data.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "bis_isi"
    assert body["row_count"] == 1
    assert body["stats"]["rows_written"] == 1
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("BIS ISI Data.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "bis_isi"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "bis_isi"
    assert body["row_count"] == 1
    assert body["stats"]["rows_written"] == 1
```

`test_upload_clients_converts_single_sheet_bis_isi_workbook_with_standard_column`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("BIS_Final_Edited_Master_File.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "bis_isi"
    assert body["row_count"] == 2
    assert body["stats"]["rows_written"] == 2
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("BIS_Final_Edited_Master_File.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "bis_isi"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "bis_isi"
    assert body["row_count"] == 2
    assert body["stats"]["rows_written"] == 2
```

`test_upload_clients_converts_raw_crs_workbook`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("CRS Data.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "crs"
    assert body["row_count"] == 1
    assert body["stats"]["rows_written"] == 1
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("CRS Data.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "crs"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["format"] == "crs"
    assert body["row_count"] == 1
    assert body["stats"]["rows_written"] == 1
```

`test_upload_clients_backs_up_existing_file`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200

    backup_path = db_path.parent / "clients.backup.db"
    assert backup_path.exists()
```

There are two tests with this exact block (`test_upload_clients_backs_up_existing_file` and, later, `test_merge_clients_backs_up_existing_file` posts to a different URL so is NOT caught by this — do not use `replace_all` here, fix each individually as shown). For `test_upload_clients_backs_up_existing_file`, replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 200

    backup_path = db_path.parent / "clients.backup.db"
    assert backup_path.exists()
```

`test_upload_clients_rejects_blank_name_with_400_not_500`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("blank_name.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()

    # The pre-existing roster must survive untouched -- not wiped by the
    # DELETE that mode="replace" issues before the failed insert.
    rows = read_clients(db_path)
    assert {r["client_id"] for r in rows} == {"CLT999"}
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("blank_name.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()

    # The pre-existing roster must survive untouched -- not wiped by the
    # DELETE that mode="replace" issues before the failed insert.
    rows = read_clients(db_path)
    assert {r["client_id"] for r in rows} == {"CLT999"}
```

`test_merge_clients_adds_new_and_keeps_existing`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok", "row_count": 2, "added": 1, "skipped_duplicates": 0,
        "format": "roster", "stats": None,
    }
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok", "row_count": 2, "added": 1, "skipped_duplicates": 0,
        "format": "roster", "stats": None,
    }
```

`test_merge_clients_skips_duplicate_client_ids`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 2
    assert body["added"] == 1
    assert body["skipped_duplicates"] == 1
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 2
    assert body["added"] == 1
    assert body["skipped_duplicates"] == 1
```

`test_merge_clients_converts_and_merges_raw_bis_isi_workbook`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("BIS ISI Data.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "bis_isi"
    assert body["added"] == 1
    assert body["skipped_duplicates"] == 1
    assert body["row_count"] == 2
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("BIS ISI Data.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "bis_isi"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["format"] == "bis_isi"
    assert body["added"] == 1
    assert body["skipped_duplicates"] == 1
    assert body["row_count"] == 2
```

`test_merge_clients_into_empty_roster`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 1
    assert body["added"] == 1
    assert body["skipped_duplicates"] == 0
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 1
    assert body["added"] == 1
    assert body["skipped_duplicates"] == 0
```

`test_merge_clients_rejects_blank_name_with_400_and_rolls_back_batch`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()

    # CLT001 (valid, ordered before the bad row) must NOT have been
    # partially merged in -- only the pre-existing CLT999 remains.
    rows = read_clients(db_path)
    assert {r["client_id"] for r in rows} == {"CLT999"}
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()

    # CLT001 (valid, ordered before the bad row) must NOT have been
    # partially merged in -- only the pre-existing CLT999 remains.
    rows = read_clients(db_path)
    assert {r["client_id"] for r in rows} == {"CLT999"}
```

`test_merge_clients_rejects_non_xlsx_extension`. Current:

```python
    response = client.post(
        "/api/merge-clients",
        files={"file": ("data.csv", b"not,a,spreadsheet", "text/csv")},
    )
    assert response.status_code == 400
```

Replace with:

```python
    response = client.post(
        "/api/merge-clients",
        files={"file": ("data.csv", b"not,a,spreadsheet", "text/csv")},
        data={"import_format": "roster"},
    )
    assert response.status_code == 400
```

`test_merge_clients_backs_up_existing_file`. Current:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200

    backup_path = db_path.parent / "clients.backup.db"
    assert backup_path.exists()
```

Replace with:

```python
    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "roster"},
        )
    assert response.status_code == 200

    backup_path = db_path.parent / "clients.backup.db"
    assert backup_path.exists()
```

- [ ] **Step 7: Run tests to verify the existing suite passes again**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all previously-existing tests pass. If a test still fails with a 422, you missed one of the 16 call sites above -- search `test_main.py` for `client.post(\n        "/api/upload-clients"` and `client.post(\n        "/api/merge-clients"` (and their 12-space-indented variants inside `with open(...)` blocks) to find any straggler.

- [ ] **Step 8: Add new tests for the explicit-selection behavior**

Add after `test_upload_clients_rejects_empty_active_sheet_with_clear_message`:

```python
def test_upload_clients_rejects_unknown_format(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    upload_path = tmp_path / "clients.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "fmcs"},
        )
    assert response.status_code == 400
    assert "fmcs" in response.json()["detail"].lower()


def test_upload_clients_missing_format_returns_422(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    upload_path = tmp_path / "clients.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 422


def test_upload_clients_selected_crs_but_file_is_roster_gives_targeted_error(tmp_path, monkeypatch):
    """Selecting the wrong format for a real file must name what the
    selected format actually needed, not the old generic
    "doesn't match any format" message -- proves the new per-format
    dispatch replaced the old cascade rather than just adding to it."""
    db_path = tmp_path / "clients.db"
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    upload_path = tmp_path / "clients.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "crs"},
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "CRS" in detail
    assert "License No." in detail
    assert not db_path.exists()
```

Add after `test_merge_clients_rejects_non_xlsx_extension`:

```python
def test_merge_clients_selected_bis_isi_but_file_is_roster_gives_targeted_error(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    upload_path = tmp_path / "clients.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/merge-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"import_format": "bis_isi"},
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "BIS ISI" in detail
    assert "Firm Name" in detail
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed.

- [ ] **Step 10: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 11: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: require an explicit import_format on upload/merge, replacing detector cascading"
```

---

### Task 4: Frontend `api.js` — `import_format` on upload/merge

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Current (`dashboard-app/frontend/src/api.test.js`):

```javascript
describe("uploadClientsFile", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 3 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await uploadClientsFile(file);
    expect(result).toEqual({ status: "ok", row_count: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/upload-clients",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Column headers don't match the expected format" }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(uploadClientsFile(file)).rejects.toThrow(
      "Column headers don't match the expected format"
    );
  });
});
```

Replace with:

```javascript
describe("uploadClientsFile", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 3 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await uploadClientsFile(file, "roster");
    expect(result).toEqual({ status: "ok", row_count: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/upload-clients",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });

  it("includes import_format in the request body", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ status: "ok", row_count: 1 }) });
    const file = new File(["dummy"], "clients.xlsx");
    await uploadClientsFile(file, "crs");
    const body = global.fetch.mock.calls[0][1].body;
    expect(body.get("import_format")).toBe("crs");
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Column headers don't match the expected format" }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(uploadClientsFile(file, "roster")).rejects.toThrow(
      "Column headers don't match the expected format"
    );
  });
});

describe("mergeClientsFile", () => {
  it("returns parsed JSON on success and includes import_format in the request body", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 5, added: 2, skipped_duplicates: 0 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await mergeClientsFile(file, "bis_isi");
    expect(result).toEqual({ status: "ok", row_count: 5, added: 2, skipped_duplicates: 0 });
    const body = global.fetch.mock.calls[0][1].body;
    expect(body.get("import_format")).toBe("bis_isi");
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Unknown format 'xyz'." }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(mergeClientsFile(file, "xyz")).rejects.toThrow("Unknown format 'xyz'.");
  });
});
```

Also update the import at the top of the file to include `mergeClientsFile`:

Current:

```javascript
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus, verifyCredentials,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
} from "./api";
```

Replace with:

```javascript
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, mergeClientsFile,
  getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus, verifyCredentials,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
} from "./api";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: FAIL — `uploadClientsFile`/`mergeClientsFile` don't send `import_format` yet, so `body.get("import_format")` is `null`, not the expected string.

- [ ] **Step 3: Update `api.js`**

Current:

```javascript
export async function uploadClientsFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Upload failed: ${res.status}`);
  }
  return data;
}

export async function mergeClientsFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/merge-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Merge failed: ${res.status}`);
  }
  return data;
}
```

Replace with:

```javascript
export async function uploadClientsFile(file, importFormat) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("import_format", importFormat);
  const res = await fetch(`${API_BASE}/api/upload-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Upload failed: ${res.status}`);
  }
  return data;
}

export async function mergeClientsFile(file, importFormat) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("import_format", importFormat);
  const res = await fetch(`${API_BASE}/api/merge-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Merge failed: ${res.status}`);
  }
  return data;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: send import_format alongside the file on upload/merge requests"
```

---

### Task 5: Frontend `ExcelSyncView.jsx` — required format dropdown; `App.jsx` wiring

**Files:**
- Modify: `dashboard-app/frontend/src/components/ExcelSyncView.jsx`
- Modify: `dashboard-app/frontend/src/components/ExcelSyncView.test.jsx`
- Modify: `dashboard-app/frontend/src/App.jsx`

- [ ] **Step 1: Write the failing tests**

Current (`dashboard-app/frontend/src/components/ExcelSyncView.test.jsx`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ExcelSyncView from "./ExcelSyncView";

function makeFile(name = "clients.xlsx") {
  return new File(["dummy"], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

describe("ExcelSyncView", () => {
  it("shows the selected file name after choosing a file", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile("renewals.xlsx")] } });
    expect(screen.getByText("renewals.xlsx")).toBeInTheDocument();
  });

  it("does not show an Upload button until a file is chosen", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    expect(screen.queryByText("Upload and Replace Client Data")).not.toBeInTheDocument();
  });

  it("calls onUpload with the chosen file and shows a success result", async () => {
    const onUpload = vi.fn().mockResolvedValue({ status: "ok", row_count: 4 });
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(file));
    await waitFor(() => expect(screen.getByText(/Import succeeded — 4 rows loaded/)).toBeInTheDocument());
  });

  it("shows an inline error message when the upload fails", async () => {
    const onUpload = vi.fn().mockRejectedValue(new Error("Column headers don't match"));
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: Column headers don't match")).toBeInTheDocument()
    );
  });

  it("calls onMerge with the chosen file and shows an added/skipped summary", async () => {
    const onMerge = vi.fn().mockResolvedValue({
      status: "ok", row_count: 5, added: 2, skipped_duplicates: 3, format: "roster", stats: null,
    });
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() => expect(onMerge).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(screen.getByText(/added 2 new clients, skipped 3 already on file \(5 total now\)/)).toBeInTheDocument()
    );
  });

  it("shows an inline error message when the merge fails", async () => {
    const onMerge = vi.fn().mockRejectedValue(new Error("File must be an .xlsx spreadsheet"));
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: File must be an .xlsx spreadsheet")).toBeInTheDocument()
    );
  });
});
```

Replace with:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ExcelSyncView from "./ExcelSyncView";

function makeFile(name = "clients.xlsx") {
  return new File(["dummy"], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

function selectFormat(value) {
  fireEvent.change(screen.getByLabelText("Import format"), { target: { value } });
}

describe("ExcelSyncView", () => {
  it("shows the selected file name after choosing a file", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile("renewals.xlsx")] } });
    expect(screen.getByText("renewals.xlsx")).toBeInTheDocument();
  });

  it("does not show an Upload button until a file is chosen", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    expect(screen.queryByText("Upload and Replace Client Data")).not.toBeInTheDocument();
  });

  it("lists Roster, BIS ISI, and CRS as selectable, and FMCS as disabled", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const select = screen.getByLabelText("Import format");
    const options = Array.from(select.querySelectorAll("option"));
    const fmcsOption = options.find((o) => o.value === "fmcs");
    expect(options.map((o) => o.value)).toEqual(expect.arrayContaining(["roster", "bis_isi", "crs", "fmcs"]));
    expect(fmcsOption.disabled).toBe(true);
  });

  it("keeps the Upload button disabled until both a file and a format are set", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    expect(screen.getByText("Upload and Replace Client Data")).toBeDisabled();
    selectFormat("roster");
    expect(screen.getByText("Upload and Replace Client Data")).not.toBeDisabled();
  });

  it("calls onUpload with the chosen file and format, and shows a success result", async () => {
    const onUpload = vi.fn().mockResolvedValue({ status: "ok", row_count: 4, format: "roster" });
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(file, "roster"));
    await waitFor(() => expect(screen.getByText(/Import succeeded — 4 rows loaded/)).toBeInTheDocument());
  });

  it("shows the converted-export summary for a CRS upload", async () => {
    const onUpload = vi.fn().mockResolvedValue({
      status: "ok", row_count: 2, format: "crs",
      stats: { sheets_used: 1, sheets_empty: 0, rows_written: 2, rows_skipped_missing_key: 0 },
    });
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    selectFormat("crs");
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() =>
      expect(screen.getByText(/Converted CRS registration export — 2 rows loaded from 1 sheet/)).toBeInTheDocument()
    );
  });

  it("shows an inline error message when the upload fails", async () => {
    const onUpload = vi.fn().mockRejectedValue(new Error("Column headers don't match"));
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: Column headers don't match")).toBeInTheDocument()
    );
  });

  it("calls onMerge with the chosen file and format, and shows an added/skipped summary", async () => {
    const onMerge = vi.fn().mockResolvedValue({
      status: "ok", row_count: 5, added: 2, skipped_duplicates: 3, format: "roster", stats: null,
    });
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() => expect(onMerge).toHaveBeenCalledWith(file, "roster"));
    await waitFor(() =>
      expect(screen.getByText(/added 2 new clients, skipped 3 already on file \(5 total now\)/)).toBeInTheDocument()
    );
  });

  it("shows an inline error message when the merge fails", async () => {
    const onMerge = vi.fn().mockRejectedValue(new Error("File must be an .xlsx spreadsheet"));
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: File must be an .xlsx spreadsheet")).toBeInTheDocument()
    );
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ExcelSyncView.test.jsx`
Expected: FAIL — there's no "Import format" `<select>` yet, and the Upload/Merge buttons aren't disabled based on format.

- [ ] **Step 3: Rewrite `ExcelSyncView.jsx`**

Current (`dashboard-app/frontend/src/components/ExcelSyncView.jsx`):

```jsx
import { useRef, useState } from "react";
import { downloadClientTemplate } from "../api";

export default function ExcelSyncView({ onUpload, onMerge }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [runningAction, setRunningAction] = useState(null); // "replace" | "merge" | null
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  function pickFile(file) {
    if (!file) return;
    setSelectedFile(file);
    setResult(null);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragActive(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function handleUploadClick() {
    if (!selectedFile) return;
    setRunningAction("replace");
    try {
      const res = await onUpload(selectedFile);
      setResult({ type: "success", mode: "replace", rowCount: res.row_count, format: res.format, stats: res.stats });
      setSelectedFile(null);
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setRunningAction(null);
    }
  }

  async function handleMergeClick() {
    if (!selectedFile) return;
    setRunningAction("merge");
    try {
      const res = await onMerge(selectedFile);
      setResult({
        type: "success", mode: "merge", rowCount: res.row_count, format: res.format,
        stats: res.stats, added: res.added, skippedDuplicates: res.skipped_duplicates,
      });
      setSelectedFile(null);
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setRunningAction(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink-primary">Excel Sync</h2>
          <p className="text-ink-secondary text-sm mt-1">
            Replace the client roster, or merge in new clients from an updated spreadsheet.
          </p>
        </div>
        <button
          type="button"
          onClick={downloadClientTemplate}
          className="px-4 py-2 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
        >
          Download Template
        </button>
      </div>

      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`bg-surface border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
          dragActive ? "border-accent bg-accent/5" : "border-line"
        }`}
      >
        <svg
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" className="h-12 w-12 text-accent mb-4" aria-hidden="true"
        >
          <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5-5 5 5M12 5v12" />
        </svg>
        <p className="font-semibold text-ink-primary mb-1">
          {selectedFile ? selectedFile.name : "Drag and drop your .xlsx file here, or click to browse"}
        </p>
        <p className="text-xs text-ink-muted">
          Accepts either the roster template above, or a raw BIS ISI licence export
          (one sheet per IS standard, with Licence No / Firm Name / Email / Validity Date columns) —
          it's converted automatically.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx"
          aria-label="Upload client spreadsheet"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
      </div>

      {selectedFile && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={runningAction !== null}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
          >
            {runningAction === "replace" ? "Uploading…" : "Upload and Replace Client Data"}
          </button>
          <button
            type="button"
            onClick={handleMergeClick}
            disabled={runningAction !== null}
            className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/5 transition-colors disabled:opacity-50"
          >
            {runningAction === "merge" ? "Merging…" : "Upload and Merge with Existing Data"}
          </button>
        </div>
      )}

      {result?.type === "success" && (
        <div className="bg-status-good/10 border border-status-good/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          {result.mode === "merge" ? (
            <>
              Merged{result.format === "bis_isi" ? " (converted BIS ISI licence export)" : ""} —{" "}
              added {result.added} new client{result.added === 1 ? "" : "s"}, skipped{" "}
              {result.skippedDuplicates} already on file ({result.rowCount} total now).
            </>
          ) : result.format === "bis_isi" ? (
            <>
              Converted BIS ISI licence export — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded
              from {result.stats?.sheets_used} sheet{result.stats?.sheets_used === 1 ? "" : "s"}
              {result.stats?.sheets_empty ? `, ${result.stats.sheets_empty} sheet(s) skipped (empty)` : ""}
              {result.stats?.rows_skipped_missing_key
                ? `, ${result.stats.rows_skipped_missing_key} row(s) skipped (missing licence no / validity date)`
                : ""}.
            </>
          ) : (
            <>Import succeeded — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded.</>
          )}
        </div>
      )}
      {result?.type === "error" && (
        <div className="bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          Import failed: {result.message}
        </div>
      )}
    </div>
  );
}
```

Replace with:

```jsx
import { useRef, useState } from "react";
import { downloadClientTemplate } from "../api";

const FORMAT_LABELS = { bis_isi: "BIS ISI licence", crs: "CRS registration" };

export default function ExcelSyncView({ onUpload, onMerge }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [importFormat, setImportFormat] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [runningAction, setRunningAction] = useState(null); // "replace" | "merge" | null
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  function pickFile(file) {
    if (!file) return;
    setSelectedFile(file);
    setResult(null);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragActive(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function handleUploadClick() {
    if (!selectedFile || !importFormat) return;
    setRunningAction("replace");
    try {
      const res = await onUpload(selectedFile, importFormat);
      setResult({ type: "success", mode: "replace", rowCount: res.row_count, format: res.format, stats: res.stats });
      setSelectedFile(null);
      setImportFormat("");
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setRunningAction(null);
    }
  }

  async function handleMergeClick() {
    if (!selectedFile || !importFormat) return;
    setRunningAction("merge");
    try {
      const res = await onMerge(selectedFile, importFormat);
      setResult({
        type: "success", mode: "merge", rowCount: res.row_count, format: res.format,
        stats: res.stats, added: res.added, skippedDuplicates: res.skipped_duplicates,
      });
      setSelectedFile(null);
      setImportFormat("");
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setRunningAction(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink-primary">Excel Sync</h2>
          <p className="text-ink-secondary text-sm mt-1">
            Replace the client roster, or merge in new clients from an updated spreadsheet.
          </p>
        </div>
        <button
          type="button"
          onClick={downloadClientTemplate}
          className="px-4 py-2 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
        >
          Download Template
        </button>
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-2">
          File format
        </label>
        <select
          value={importFormat}
          onChange={(e) => setImportFormat(e.target.value)}
          aria-label="Import format"
          className="min-w-[220px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="" disabled>-- Select format --</option>
          <option value="roster">Roster (dashboard template)</option>
          <option value="bis_isi">BIS ISI (raw government export)</option>
          <option value="crs">CRS (raw government export)</option>
          <option value="fmcs" disabled>FMCS (coming soon)</option>
        </select>
      </div>

      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`bg-surface border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
          dragActive ? "border-accent bg-accent/5" : "border-line"
        }`}
      >
        <svg
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" className="h-12 w-12 text-accent mb-4" aria-hidden="true"
        >
          <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5-5 5 5M12 5v12" />
        </svg>
        <p className="font-semibold text-ink-primary mb-1">
          {selectedFile ? selectedFile.name : "Drag and drop your .xlsx file here, or click to browse"}
        </p>
        <p className="text-xs text-ink-muted">
          Select the file's format above, then drop it here or click to browse.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx"
          aria-label="Upload client spreadsheet"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
      </div>

      {selectedFile && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={runningAction !== null || !importFormat}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
          >
            {runningAction === "replace" ? "Uploading…" : "Upload and Replace Client Data"}
          </button>
          <button
            type="button"
            onClick={handleMergeClick}
            disabled={runningAction !== null || !importFormat}
            className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/5 transition-colors disabled:opacity-50"
          >
            {runningAction === "merge" ? "Merging…" : "Upload and Merge with Existing Data"}
          </button>
        </div>
      )}

      {result?.type === "success" && (
        <div className="bg-status-good/10 border border-status-good/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          {result.mode === "merge" ? (
            <>
              Merged{FORMAT_LABELS[result.format] ? ` (converted ${FORMAT_LABELS[result.format]} export)` : ""} —{" "}
              added {result.added} new client{result.added === 1 ? "" : "s"}, skipped{" "}
              {result.skippedDuplicates} already on file ({result.rowCount} total now).
            </>
          ) : FORMAT_LABELS[result.format] ? (
            <>
              Converted {FORMAT_LABELS[result.format]} export — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded
              from {result.stats?.sheets_used} sheet{result.stats?.sheets_used === 1 ? "" : "s"}
              {result.stats?.sheets_empty ? `, ${result.stats.sheets_empty} sheet(s) skipped (empty)` : ""}
              {result.stats?.rows_skipped_missing_key
                ? `, ${result.stats.rows_skipped_missing_key} row(s) skipped (missing required identifier / date)`
                : ""}.
            </>
          ) : (
            <>Import succeeded — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded.</>
          )}
        </div>
      )}
      {result?.type === "error" && (
        <div className="bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          Import failed: {result.message}
        </div>
      )}
    </div>
  );
}
```

(This also fixes a pre-existing gap flagged during the CRS importer's own design: the old message only special-cased `"bis_isi"`, so a CRS upload used to silently fall through to the generic "Import succeeded" line despite having the same stats available. The `FORMAT_LABELS` map now covers both, and the missing-key wording is generalized since ISI and CRS name that field differently ("licence no / validity date" vs. "license no / grant date").)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ExcelSyncView.test.jsx`
Expected: all passed.

- [ ] **Step 5: Update `App.jsx`'s upload/merge handlers to thread the format through**

Current (`dashboard-app/frontend/src/App.jsx`):

```javascript
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

Replace with:

```javascript
  async function handleUploadClients(file, importFormat) {
    try {
      const result = await uploadClientsFile(file, importFormat);
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

  async function handleMergeClients(file, importFormat) {
    try {
      const result = await mergeClientsFile(file, importFormat);
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

- [ ] **Step 6: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed, including `App.test.jsx` (its Excel Sync tests, if any, call `handleUploadClients`/`handleMergeClients` indirectly through the same component props and shouldn't need changes since neither function's *external* calling contract from `App.jsx`'s own perspective changed shape -- only check for this if something unexpectedly fails).

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/frontend/src/components/ExcelSyncView.jsx dashboard-app/frontend/src/components/ExcelSyncView.test.jsx dashboard-app/frontend/src/App.jsx
git commit -m "feat: add a required import format dropdown to Excel Sync"
```

---

### Task 6: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all tests pass, zero regressions, with roughly 15 new tests added across Tasks 1-3.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Manual smoke test against a real dev server**

Start the backend (`cd dashboard-app/backend && python -m uvicorn main:app --port 8040`) and frontend (`cd dashboard-app/frontend && npm run dev`) locally. On the Excel Sync page:
1. Confirm a "File format" dropdown appears above the drop zone, defaulting to "-- Select format --", with Roster/BIS ISI/CRS selectable and FMCS visibly present but greyed out/unselectable.
2. Pick a file without selecting a format — confirm both Upload and Merge buttons stay disabled.
3. Select "Roster (dashboard template)", then upload your real roster export — confirm it still succeeds exactly as before.
4. If you have a raw BIS ISI or CRS file handy, select the matching format and upload it — confirm it converts correctly and the success message names the right export type.
5. Deliberately select the *wrong* format for a file you have (e.g. select "CRS" for a roster file) — confirm you get a clear, specific error naming what CRS needed, not a generic "doesn't match any format" message.

Expected: no console errors; every step matches the description above.
