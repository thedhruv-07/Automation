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
