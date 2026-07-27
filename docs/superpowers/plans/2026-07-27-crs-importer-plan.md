# CRS Importer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `import_crs.py` so a raw BIS CRS registration export auto-detects and converts into the roster schema (`scheme="CRS"`), the same way `import_bis_isi_data.py` already does for BIS ISI, with expiry computed as Grant Date + 2 years since the source has no expiry column.

**Architecture:** `import_crs.py` mirrors `import_bis_isi_data.py`'s exact template: a `looks_like_crs_workbook(wb)` detector, an `import_crs_workbook(wb, out_ws, today=None)` converter, and a CLI entrypoint. It's registered in `import_formats.py`'s `IMPORT_FORMATS` list, which both `/api/upload-clients` and `/api/merge-clients` already loop over — no endpoint changes needed. The source workbook's `"BIS_CRS_Master"` sheet is explicitly skipped during conversion since it duplicates every per-standard sheet's rows.

**Tech Stack:** Python (`dashboard-app/backend/`), openpyxl, pytest.

---

### Task 1: `import_crs.py` — detector, converter, CLI entrypoint

**Files:**
- Create: `dashboard-app/backend/import_crs.py`
- Create: `dashboard-app/backend/test_import_crs.py`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/backend/test_import_crs.py`:

```python
"""Tests for import_crs.py -- the BIS CRS registration export converter."""
import openpyxl

from import_crs import RowCollector, import_crs_workbook, looks_like_crs_workbook

PER_STANDARD_HEADERS = [
    "Application No.", "License No.", "Organization Name", "Country", "Indian Standard",
    "Product Name", "Product Category", "Grant Date", "Status", "E-mail", "Phone No.",
]


def _workbook(sheet_title, headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for row in rows:
        ws.append(row)
    return wb


def _multi_sheet_workbook(sheets):
    """sheets: list of (title, headers, rows) tuples -> one workbook with a
    sheet per tuple."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title)
        ws.append(headers)
        for row in rows:
            ws.append(row)
    return wb


def test_looks_like_crs_workbook_detects_the_format():
    wb = _workbook("IS 13252", PER_STANDARD_HEADERS, [
        ["0846", "R-7019869", "Panache Digilife Limited", "India",
         "Is 13252(Part 1):2010/ Iec 60950-1: 2005", "Notebook", "Laptop/Notebook/Tablet",
         "2024-01-15", "Register", "jitendra.d@vardhamantechnology.com", "913322634755"],
    ])
    assert looks_like_crs_workbook(wb) is True


def test_looks_like_crs_workbook_does_not_match_bis_isi_headers():
    isi_headers = ["S. No.", "Licence No", "Firm Name", "Address", "District", "State",
                    "PIN Code", "Email", "Validity Date", "Status", "Variety", "Brand Names"]
    wb = _workbook("IS 999", isi_headers, [
        [1, "7777777", "Firm B", "Addr", "Dist", "State", "12345",
         "b@x.com", "2026-08-31", "Operative", "-", ""],
    ])
    assert looks_like_crs_workbook(wb) is False


def test_looks_like_crs_workbook_does_not_match_unrelated_workbook():
    wb = _workbook("Sheet1", ["Some", "Other", "Columns"], [["a", "b", "c"]])
    assert looks_like_crs_workbook(wb) is False


def test_import_crs_workbook_converts_rows_and_computes_expiry():
    wb = _workbook("IS 13252", PER_STANDARD_HEADERS, [
        ["0846", "R-7019869", "Panache Digilife Limited", "India",
         "Is 13252(Part 1):2010/ Iec 60950-1: 2005", "Notebook", "Laptop/Notebook/Tablet",
         "2024-01-15", "Register", "jitendra.d@vardhamantechnology.com", "913322634755"],
    ])
    collector = RowCollector()

    stats = import_crs_workbook(wb, collector)

    assert stats["rows_written"] == 1
    row = collector.rows[0]
    assert row[0] == "R-7019869"                                   # client_id
    assert row[1] == "Panache Digilife Limited"                    # name
    assert row[2] == "Panache Digilife Limited"                    # company
    assert row[3] == "jitendra.d@vardhamantechnology.com"          # email
    assert row[4] == "913322634755"                                # phone
    assert row[5] == "Is 13252(Part 1):2010/ Iec 60950-1: 2005"    # cert_name
    assert row[6] == "CRS"                                         # scheme
    assert row[7] == "R-7019869"                                   # cert_id
    assert row[8] == "15-01-2024"                                  # issue_date (Grant Date)
    assert row[9] == "15-01-2026"                                  # expiry_date (Grant Date + 2y)
    assert row[10] is None                                         # renewal_link
    assert row[11] in {"CRITICAL", "URGENT", "DUE SOON", "ACTIVE", "EXPIRED"}


def test_import_crs_workbook_skips_the_master_sheet():
    same_row = ["0846", "R-7019869", "Panache Digilife Limited", "India",
                "Is 13252(Part 1):2010/ Iec 60950-1: 2005", "Notebook", "Laptop/Notebook/Tablet",
                "2024-01-15", "Register", "jitendra.d@vardhamantechnology.com", "913322634755"]
    wb = _multi_sheet_workbook([
        ("BIS_CRS_Master", PER_STANDARD_HEADERS, [same_row]),
        ("IS 13252", PER_STANDARD_HEADERS, [same_row]),
    ])
    collector = RowCollector()

    stats = import_crs_workbook(wb, collector)

    assert stats["rows_written"] == 1
    assert len(collector.rows) == 1


def test_import_crs_workbook_master_sheet_name_match_is_case_insensitive():
    same_row = ["0846", "R-7019869", "Panache Digilife Limited", "India",
                "Is 13252(Part 1):2010/ Iec 60950-1: 2005", "Notebook", "Laptop/Notebook/Tablet",
                "2024-01-15", "Register", "jitendra.d@vardhamantechnology.com", "913322634755"]
    wb = _multi_sheet_workbook([
        ("bis_crs_master", PER_STANDARD_HEADERS, [same_row]),
        ("IS 13252", PER_STANDARD_HEADERS, [same_row]),
    ])
    collector = RowCollector()

    stats = import_crs_workbook(wb, collector)

    assert stats["rows_written"] == 1


def test_import_crs_workbook_skips_rows_missing_license_no_or_grant_date():
    wb = _workbook("IS 13252", PER_STANDARD_HEADERS, [
        [1, None, "No License Row", "India", "IS 13252", "Notebook", "Laptop", None,
         "Register", "a@x.com", "919000000000"],
        [2, "R-1111111", "No Grant Date Row", "India", "IS 13252", "Notebook", "Laptop", None,
         "Register", "b@x.com", "919000000001"],
    ])
    collector = RowCollector()

    stats = import_crs_workbook(wb, collector)

    assert stats["rows_written"] == 0
    assert stats["rows_skipped_missing_key"] == 2


def test_import_crs_workbook_dedups_same_license_no_across_different_standard_sheets():
    wb = _multi_sheet_workbook([
        ("IS 13252", PER_STANDARD_HEADERS, [
            ["1", "SAME123", "Firm A", "India", "IS 13252", "Notebook", "Laptop",
             "2024-01-15", "Register", "a@x.com", "919000000000"],
        ]),
        ("IS 616", PER_STANDARD_HEADERS, [
            ["2", "SAME123", "Firm A", "India", "IS 616", "Audio", "Speaker",
             "2024-01-15", "Register", "a@x.com", "919000000000"],
        ]),
    ])
    collector = RowCollector()

    stats = import_crs_workbook(wb, collector)

    assert stats["rows_written"] == 2
    client_ids = {row[0] for row in collector.rows}
    assert client_ids == {"SAME123", "SAME123-IS 616"}


def test_import_crs_workbook_handles_feb_29_grant_date_in_non_leap_target_year():
    wb = _workbook("IS 13252", PER_STANDARD_HEADERS, [
        ["1", "R-2222222", "Firm C", "India", "IS 13252", "Notebook", "Laptop",
         "2024-02-29", "Register", "c@x.com", "919000000002"],
    ])
    collector = RowCollector()

    import_crs_workbook(wb, collector)

    assert collector.rows[0][9] == "28-02-2026"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_import_crs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'import_crs'` — the module doesn't exist yet.

- [ ] **Step 3: Create `import_crs.py`**

Create `dashboard-app/backend/import_crs.py`:

```python
"""One-off importer: converts a BIS CRS (Compulsory Registration Scheme)
export into clients_certifications.xlsx's single-sheet client roster schema.

Source workbook has one sheet per Indian Standard (e.g. "IS 13252") plus a
"BIS_CRS_Master" sheet that duplicates every per-standard sheet's rows
combined -- the Master sheet is skipped during import to avoid double-
counting every client. There's no expiry/validity date column in this
source format; a CRS registration is valid for a fixed 2 years from its
Grant Date, so Expiry Date is computed here rather than read. License No.
is used for both Client ID and Certification ID, since it's the natural
unique key in this dataset (mirrors import_bis_isi_data.py's use of its own
licence number). Status is recomputed from the computed expiry using this
project's own urgency thresholds -- the source "Status" column
(Register/Registered/etc.) means something different and is not used.

Usage: python import_crs.py "<path to source xlsx>"
"""
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

from import_helpers import RowCollector, parse_validity_date, compute_status, header_index_map, get

OUTPUT_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Scheme", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]

MASTER_SHEET_NAME = "bis_crs_master"


def add_years(dt: datetime, years: int) -> datetime:
    """dt with `years` added, falling back to Feb 28 if dt is a Feb 29 whose
    shifted year isn't a leap year."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        return dt.replace(year=dt.year + years, day=28)


def looks_like_crs_workbook(wb) -> bool:
    """True if any sheet's header row has both a license-no and
    organization-name column. Deliberately different spelling from BIS
    ISI's own detector ("licence no" / "firm name"), so the two formats
    can never be mistaken for each other."""
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        try:
            header_row = next(ws.iter_rows(values_only=True))
        except StopIteration:
            continue
        index_map = header_index_map(header_row)
        if "license no" in index_map and "organization name" in index_map:
            return True
    return False


def import_crs_workbook(wb, out_ws, today=None):
    """Appends converted roster rows from an already-open CRS workbook into
    out_ws. Skips the "BIS_CRS_Master" rollup sheet, which duplicates every
    per-standard sheet's rows combined -- importing it too would count
    every client twice."""
    today = today or datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    seen_client_ids = set()
    stats = {"sheets_used": 0, "sheets_empty": 0, "rows_written": 0, "rows_skipped_missing_key": 0}

    for sheet_name in wb.sheetnames:
        if sheet_name.strip().lower() == MASTER_SHEET_NAME:
            continue

        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            stats["sheets_empty"] += 1
            continue

        index_map = header_index_map(header_row)
        sheet_had_rows = False

        for row in rows_iter:
            if not row or row[0] is None:
                continue
            license_no = get(row, index_map, "license no")
            org_name = get(row, index_map, "organization name")
            email = get(row, index_map, "e-mail", "email")
            phone = get(row, index_map, "phone no.", "phone no", "phone")
            grant_date_raw = get(row, index_map, "grant date")
            cert_name = get(row, index_map, "indian standard")

            if not license_no or not grant_date_raw:
                stats["rows_skipped_missing_key"] += 1
                continue

            grant_dt = parse_validity_date(grant_date_raw)
            if grant_dt is None:
                stats["rows_skipped_missing_key"] += 1
                continue
            expiry_dt = add_years(grant_dt, 2)

            client_id = str(license_no).strip()
            if client_id in seen_client_ids:
                client_id = f"{client_id}-{cert_name}"
            seen_client_ids.add(client_id)

            out_ws.append([
                client_id,
                org_name,
                org_name,
                email,
                phone,
                cert_name,
                "CRS",
                str(license_no).strip(),
                grant_dt.strftime("%d-%m-%Y"),
                expiry_dt.strftime("%d-%m-%Y"),
                None,
                compute_status(expiry_dt, today),
            ])
            stats["rows_written"] += 1
            sheet_had_rows = True

        if sheet_had_rows:
            stats["sheets_used"] += 1
        else:
            stats["sheets_empty"] += 1

    return stats


def import_crs(source_path: str, output_path: str):
    wb = openpyxl.load_workbook(source_path, read_only=True, data_only=True)

    out_wb = openpyxl.Workbook()
    out_ws = out_wb.active
    out_ws.append(OUTPUT_HEADERS)

    stats = import_crs_workbook(wb, out_ws)

    wb.close()
    out_wb.save(output_path)
    return stats


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python import_crs.py \"<path to source xlsx>\"")
        sys.exit(1)

    source = sys.argv[1]
    output = str(Path(__file__).parent.parent.parent / "data" / "clients_certifications.xlsx")
    result = import_crs(source, output)
    print("Sheets with data used:", result["sheets_used"])
    print("Sheets empty/skipped:", result["sheets_empty"])
    print("Rows written:", result["rows_written"])
    print("Rows skipped (missing license no / grant date):", result["rows_skipped_missing_key"])
    print("Saved to:", output)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_import_crs.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/import_crs.py dashboard-app/backend/test_import_crs.py
git commit -m "feat: add import_crs.py to convert BIS CRS exports into the roster schema"
```

---

### Task 2: Register in `import_formats.py` + upload integration test

**Files:**
- Modify: `dashboard-app/backend/import_formats.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing integration test**

Add to `dashboard-app/backend/test_main.py`, immediately after
`test_upload_clients_converts_single_sheet_bis_isi_workbook_with_standard_column`'s
closing lines (before the next test function):

```python
def test_upload_clients_converts_raw_crs_workbook(tmp_path, monkeypatch):
    """A raw BIS CRS registration export (govt column names, one sheet per
    Indian Standard, no Client ID/Company columns) should be auto-detected
    and converted into the roster schema, not rejected as a header mismatch."""
    db_path = tmp_path / "clients.db"
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    upload_path = tmp_path / "CRS Data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "IS 13252"
    ws.append(["Application No.", "License No.", "Organization Name", "Country", "Indian Standard",
               "Product Name", "Product Category", "Grant Date", "Status", "E-mail", "Phone No."])
    ws.append(["0846", "R-7019869", "Panache Digilife Limited", "India",
               "Is 13252(Part 1):2010/ Iec 60950-1: 2005", "Notebook", "Laptop/Notebook/Tablet",
               "2024-01-15", "Register", "jitendra.d@vardhamantechnology.com", "913322634755"])
    wb.save(upload_path)

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

    rows = read_clients(db_path)
    assert rows[0]["client_id"] == "R-7019869"
    assert rows[0]["name"] == "Panache Digilife Limited"
    assert rows[0]["scheme"] == "CRS"
    assert rows[0]["cert_name"] == "Is 13252(Part 1):2010/ Iec 60950-1: 2005"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/backend && python -m pytest test_main.py::test_upload_clients_converts_raw_crs_workbook -v`
Expected: FAIL — with only `"bis_isi"` registered in `IMPORT_FORMATS`, the CRS-shaped upload matches neither the roster header check nor the BIS ISI detector, so it's rejected with a 400 "Column headers don't match the expected format" response instead of being converted.

- [ ] **Step 3: Register the new format**

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

IMPORT_FORMATS = [
    ("bis_isi", looks_like_bis_isi_workbook, import_bis_isi_workbook),
]
```

Replace with:

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed, including the new `test_upload_clients_converts_raw_crs_workbook`.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/import_formats.py dashboard-app/backend/test_main.py
git commit -m "feat: register the CRS importer in IMPORT_FORMATS"
```

---

### Task 3: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all tests pass, zero regressions, with 10 new tests added across Tasks 1-2.

- [ ] **Step 2: The merge path already picks up the new format — no separate test needed**

`dashboard-app/backend/main.py`'s `merge_clients` function (the `/api/merge-clients` endpoint) already contains its own `for format_name, detector, importer in IMPORT_FORMATS:` loop, structurally identical to `upload_clients`'s. Since Task 2 added the CRS entry to that same shared `IMPORT_FORMATS` list, both endpoints pick it up automatically — nothing further to change or test here.

- [ ] **Step 3: If you have the real CRS source file, dry-run the CLI against it**

```bash
cd dashboard-app/backend
python import_crs.py "<path to your real CRS export xlsx>"
```

Expected output: non-zero `Rows written`, a `Sheets empty/skipped` count that should be exactly 1 (only the "BIS_CRS_Master" sheet, if present, being skipped — check the printed count against how many per-standard sheets the real file has to confirm Master was excluded and nothing else was unexpectedly skipped), and a small or zero `Rows skipped (missing license no / grant date)` count. Inspect the saved `data/clients_certifications.xlsx` to spot-check a few converted rows against the source.

If anything looks off (unexpected skip counts, wrong cert_name values, garbled phone numbers), stop and report back rather than uploading it to production — this step is a safety check before real data ever reaches the dashboard.
