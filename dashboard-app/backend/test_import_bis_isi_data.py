"""Tests for import_bis_isi_data.py -- the BIS ISI licence register converter."""
import openpyxl

from import_bis_isi_data import RowCollector, import_bis_isi_workbook, looks_like_bis_isi_workbook

# The current "final" template: one sheet, every standard mixed together,
# distinguished by a per-row "Standard" column.
SINGLE_SHEET_HEADERS = [
    "S. No.", "Standard", "Licence No", "Firm Name", "Address", "District", "State",
    "PIN Code", "Email", "Validity Date", "Status", "Variety", "Brand Names",
]

# The older format: one sheet per standard, sheet title carries the standard,
# no "Standard" column at all. Must keep working for any old file still in use.
OLD_MULTI_SHEET_HEADERS = [
    "S. No.", "Licence No", "Firm Name", "Address", "District", "State",
    "PIN Code", "Email", "Validity Date", "Status", "Variety", "Brand Names",
]


def _workbook(sheet_title, headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(headers)
    for row in rows:
        ws.append(row)
    return wb


def test_looks_like_bis_isi_workbook_detects_the_new_single_sheet_format():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "4631257", "Prayagh Consumer Care Pvt. Unit II", "Addr", "Mahbubnagar",
         "Telangana", "509316", "info@prayagh.com", "2026-08-31", "Operative", "-", ""],
    ])
    assert looks_like_bis_isi_workbook(wb) is True


def test_single_sheet_uses_per_row_standard_column_as_cert_name():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "4631257", "Prayagh Consumer Care Pvt. Unit II", "Addr", "Mahbubnagar",
         "Telangana", "509316", "info@prayagh.com", "2026-08-31", "Operative", "-", ""],
        [2, "IS 10124 Part 2", "6298283", "Sudhakar PVC Products Private Limited", "Addr",
         "Suryapet", "Telangana", "508213", "sudhakar@x.com", "2026-12-31", "Operative", "Show Variety", ""],
    ])
    collector = RowCollector()

    stats = import_bis_isi_workbook(wb, collector)

    assert stats["rows_written"] == 2
    # row[6] is now scheme ("ISI" for every row here); the licence number
    # (what used to be at index 6) shifted to index 7.
    cert_name_by_licence = {row[7]: row[5] for row in collector.rows}
    assert cert_name_by_licence["4631257"] == "IS 1008"
    assert cert_name_by_licence["6298283"] == "IS 10124 Part 2"


def test_single_sheet_dedups_same_licence_no_across_different_standards():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "SAME123", "Firm A", "Addr", "Dist", "State", "12345",
         "a@x.com", "2026-08-31", "Operative", "-", ""],
        [2, "IS 1011", "SAME123", "Firm A", "Addr", "Dist", "State", "12345",
         "a@x.com", "2026-08-31", "Operative", "-", ""],
    ])
    collector = RowCollector()

    stats = import_bis_isi_workbook(wb, collector)

    assert stats["rows_written"] == 2
    client_ids = {row[0] for row in collector.rows}
    assert client_ids == {"SAME123", "SAME123-IS 1011"}


def test_row_with_blank_standard_falls_back_to_sheet_name():
    wb = _workbook("IS 999", SINGLE_SHEET_HEADERS, [
        [1, None, "7777777", "Firm B", "Addr", "Dist", "State", "12345",
         "b@x.com", "2026-08-31", "Operative", "-", ""],
    ])
    collector = RowCollector()

    import_bis_isi_workbook(wb, collector)

    assert collector.rows[0][5] == "IS 999"


def test_old_multi_sheet_format_without_standard_column_still_uses_sheet_name():
    wb = _workbook("IS 302 (Part 2 Sec 30)", OLD_MULTI_SHEET_HEADERS, [
        [1, "9512485121", "Creative Hitech Private Limited", "Addr", "JHAJJAR", "HARYANA",
         "124501", "hod@creativehitech.co.in", "24-07-2026", "Operative", "Fan", ""],
    ])
    collector = RowCollector()

    stats = import_bis_isi_workbook(wb, collector)

    assert stats["rows_written"] == 1
    assert collector.rows[0][5] == "IS 302 (Part 2 Sec 30)"


def test_produced_rows_are_tagged_with_isi_scheme():
    wb = _workbook("Master", SINGLE_SHEET_HEADERS, [
        [1, "IS 1008", "4631257", "Prayagh Consumer Care Pvt. Unit II", "Addr", "Mahbubnagar",
         "Telangana", "509316", "info@prayagh.com", "2026-08-31", "Operative", "-", ""],
    ])
    collector = RowCollector()

    import_bis_isi_workbook(wb, collector)

    assert collector.rows[0][6] == "ISI"
