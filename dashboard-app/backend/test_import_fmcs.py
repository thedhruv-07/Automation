"""Tests for import_fmcs.py -- the BIS FMCS (Foreign Manufacturers
Certification Scheme) roster converter."""
import openpyxl

from import_fmcs import RowCollector, import_fmcs_workbook, looks_like_fmcs_workbook

HEADERS = [
    "S No", "Email ID", "CML No", "Name", "Address", "City", "Country",
    "Validity Date", "Standard No", "Status", "Product", "Brand Names",
    "Email Source", "Web Source URL",
]


def _workbook(sheet_title, headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for row in rows:
        ws.append(row)
    return wb


def test_looks_like_fmcs_workbook_detects_cml_no_and_name_columns():
    wb = _workbook("Sheet1", HEADERS, [
        [1, "a@x.com", "4100277486", "Ambey Bhawani Ply Board Udhyog", "Addr", "City", "Nepal",
         "2026-11-02", "IS 2202 (Part 1) : 2023", "Operative", "Product", "", "", ""],
    ])
    assert looks_like_fmcs_workbook(wb) is True


def test_looks_like_fmcs_workbook_rejects_an_unrelated_sheet():
    wb = _workbook("Sheet1", ["Name", "Amount"], [["x", 1]])
    assert looks_like_fmcs_workbook(wb) is False


def test_import_fmcs_workbook_converts_rows_to_roster_schema():
    wb = _workbook("Sheet1", HEADERS, [
        [1, "a@x.com", "4100277486", "Ambey Bhawani Ply Board Udhyog", "Addr", "City", "Nepal",
         "2026-11-02", "IS 2202 (Part 1) : 2023", "Operative", "Product", "", "", ""],
    ])
    collector = RowCollector()

    stats = import_fmcs_workbook(wb, collector)

    assert stats["rows_written"] == 1
    row = collector.rows[0]
    assert row[0] == "4100277486"  # Client ID
    assert row[1] == "Ambey Bhawani Ply Board Udhyog"  # Full Name
    assert row[2] == "Ambey Bhawani Ply Board Udhyog"  # Company
    assert row[3] == "a@x.com"  # Email
    assert row[4] is None  # Phone -- not in this source
    assert row[5] == "IS 2202 (Part 1) : 2023"  # Certification Name
    assert row[6] == "FMCS"  # Scheme
    assert row[7] == "4100277486"  # Certification ID
    assert row[8] is None  # Issue Date -- not in this source
    assert row[9] == "02-11-2026"  # Expiry Date
    assert row[10] is None  # Renewal Link
    assert row[11] in ("DUE SOON", "ACTIVE", "URGENT", "CRITICAL", "EXPIRED")  # recomputed, not "Operative"


def test_import_fmcs_workbook_skips_rows_missing_cml_no_or_validity_date():
    wb = _workbook("Sheet1", HEADERS, [
        [1, "a@x.com", "4100277486", "Firm A", "Addr", "City", "Nepal",
         None, "IS 2202", "Operative", "Product", "", "", ""],  # no validity date
        [2, "b@x.com", None, "Firm B", "Addr", "City", "Nepal",
         "2026-11-02", "IS 2202", "Operative", "Product", "", "", ""],  # no CML No
    ])
    collector = RowCollector()

    stats = import_fmcs_workbook(wb, collector)

    assert stats["rows_written"] == 0
    assert stats["rows_skipped_missing_key"] == 2


def test_import_fmcs_workbook_skips_rows_missing_standard_no():
    wb = _workbook("Sheet1", HEADERS, [
        [1, "a@x.com", "4100277486", "Firm A", "Addr", "City", "Nepal",
         "2026-11-02", None, "Operative", "Product", "", "", ""],
    ])
    collector = RowCollector()

    stats = import_fmcs_workbook(wb, collector)

    assert stats["rows_written"] == 0
    assert stats["rows_skipped_missing_key"] == 1


def test_import_fmcs_workbook_dedups_same_cml_no_across_different_standards():
    wb = _workbook("Sheet1", HEADERS, [
        [1, "a@x.com", "SAME123", "Firm A", "Addr", "City", "Nepal",
         "2026-11-02", "IS 2202", "Operative", "Product", "", "", ""],
        [2, "a@x.com", "SAME123", "Firm A", "Addr", "City", "Nepal",
         "2027-01-15", "IS 303", "Operative", "Product", "", "", ""],
    ])
    collector = RowCollector()

    stats = import_fmcs_workbook(wb, collector)

    assert stats["rows_written"] == 2
    client_ids = {row[0] for row in collector.rows}
    assert client_ids == {"SAME123", "SAME123-IS 303"}


def test_import_fmcs_workbook_recomputes_status_ignoring_source_status_column():
    wb = _workbook("Sheet1", HEADERS, [
        [1, "a@x.com", "4100277486", "Firm A", "Addr", "City", "Nepal",
         "2020-01-01", "IS 2202", "Operative", "Product", "", "", ""],
    ])
    collector = RowCollector()

    import datetime
    stats = import_fmcs_workbook(wb, collector, today=datetime.datetime(2026, 10, 13))

    assert collector.rows[0][11] == "EXPIRED"
