"""Tests for fix_bis_isi_cert_names.py's core logic (parsing the source file
and diffing it against the roster). apply_corrections()/main() are exercised
manually against the real database, not covered here, since they mutate a
real file by design."""
import openpyxl

from db import upsert_clients
from fix_bis_isi_cert_names import find_cert_name_corrections, load_correct_standards

ROW_A = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "1", "IS 12600", "ISI", "CLT001",
         "01-01-2025", "24-07-2026", "https://x", "ACTIVE")
ROW_B = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "2", "IS 12600", "ISI", "CLT002",
         "01-01-2025", "11-08-2026", "https://x", "ACTIVE")


def _write_source_xlsx(path, rows, sheet_title="Master Data"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(["S. No.", "Standard", "Licence No", "Firm Name", "Email", "Validity Date"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_load_correct_standards_maps_licence_no_to_standard(tmp_path):
    source_path = tmp_path / "master.xlsx"
    _write_source_xlsx(source_path, [
        [1, "IS 9825", "8200134406", "J.K.POLLUTION KILLER", "jk@x.com", "22-11-2026"],
        [2, "IS 4985", "5900008208", "Some Other Firm", "other@x.com", "30-11-2026"],
    ])

    mapping = load_correct_standards(source_path)

    assert mapping == {"8200134406": "IS 9825", "5900008208": "IS 4985"}


def test_load_correct_standards_skips_blank_licence_or_standard(tmp_path):
    source_path = tmp_path / "master.xlsx"
    _write_source_xlsx(source_path, [
        [1, "IS 9825", None, "No Licence Row", "a@x.com", "22-11-2026"],
        [2, None, "8200134406", "No Standard Row", "b@x.com", "22-11-2026"],
        [3, "IS 4985", "5900008208", "Valid Row", "c@x.com", "30-11-2026"],
    ])

    mapping = load_correct_standards(source_path)

    assert mapping == {"5900008208": "IS 4985"}


def test_load_correct_standards_returns_empty_when_no_matching_sheet(tmp_path):
    source_path = tmp_path / "master.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Some", "Other", "Columns"])
    ws.append(["a", "b", "c"])
    wb.save(source_path)

    assert load_correct_standards(source_path) == {}


def test_find_cert_name_corrections_flags_mismatches_only(mongo_db):
    upsert_clients(mongo_db, [ROW_A, ROW_B], mode="replace")

    corrections = find_cert_name_corrections(mongo_db, {
        "CLT001": "IS 9825",   # differs from stored "IS 12600" -- should be flagged
        "CLT002": "IS 12600",  # matches stored value -- should NOT be flagged
    })

    assert corrections == [("CLT001", "IS 12600", "IS 9825")]


def test_find_cert_name_corrections_ignores_client_ids_not_in_roster(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")

    corrections = find_cert_name_corrections(mongo_db, {"UNKNOWN-ID": "IS 9825"})

    assert corrections == []
