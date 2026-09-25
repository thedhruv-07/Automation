"""Tests for renewals_import.py -- reading a BIS Manak Online "List of
Licences" report and using it to move renewed clients' expiry dates forward."""
import io
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

import openpyxl
import pytest

from db import upsert_clients, find_client_by_id
from renewals_import import parse_report, parse_reports, apply_report

HEADER = ["S. No.", "Licence No", "Firm Name & Address", "District", "State", "Validity Date", "Status", "Variety", "Brand Names"]


def _manak_xlsx(rows, header=HEADER):
    """Mimics the file Manak Online exports: inline strings, no
    sharedStrings.xml and a stylesheet openpyxl can't parse."""
    def cell(ref, value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
    body = ""
    for r, row in enumerate([header] + rows, start=1):
        cells = "".join(cell(f"{chr(65 + c)}{r}", v) for c, v in enumerate(row) if v is not None)
        body += f'<row r="{r}">{cells}</row>'
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{body}</sheetData></worksheet>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def _excel_xlsx(rows, header=HEADER):
    """A normal Excel-saved file (shared strings, real numbers/dates)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _row(licence="0009156278", validity="2031/08/31", status="Operative"):
    return ["1", licence, "Some Firm", "UNNAO", "UTTAR PRADESH", validity, status, "Show Variety", None]


def test_parse_reads_licence_validity_and_status_from_a_manak_export():
    rows, unreadable = parse_report(_manak_xlsx([_row()]))
    assert unreadable == 0
    assert rows == [{"licence_no": "0009156278", "validity_iso": "2031-08-31", "bis_status": "Operative"}]


def test_parse_reads_a_normal_excel_file_with_shared_strings():
    rows, _ = parse_report(_excel_xlsx([_row(validity="2027/02/07", status="Under Stop Marking")]))
    assert rows == [{"licence_no": "0009156278", "validity_iso": "2027-02-07", "bis_status": "Under Stop Marking"}]


def test_parse_restores_leading_zeros_lost_when_excel_stores_the_licence_as_a_number():
    rows, _ = parse_report(_excel_xlsx([_row(licence=9156278)]))
    assert rows[0]["licence_no"] == "0009156278"


def test_parse_accepts_dates_excel_converted_to_real_dates():
    rows, _ = parse_report(_excel_xlsx([_row(validity=datetime(2029, 3, 15))]))
    assert rows[0]["validity_iso"] == "2029-03-15"


@pytest.mark.parametrize("value,expected", [
    ("2031/08/31", "2031-08-31"), ("2031-08-31", "2031-08-31"),
    ("31-08-2031", "2031-08-31"), ("31/08/2031", "2031-08-31"),
])
def test_parse_accepts_the_common_date_formats(value, expected):
    rows, _ = parse_report(_manak_xlsx([_row(validity=value)]))
    assert rows[0]["validity_iso"] == expected


def test_parse_counts_rows_it_cannot_read_instead_of_failing():
    rows, unreadable = parse_report(_manak_xlsx([
        _row(), _row(licence="not-a-number"), _row(validity="soon"), _row(licence=None),
    ]))
    assert len(rows) == 1
    assert unreadable == 3


def test_parse_finds_columns_by_name_not_position_and_ignores_case():
    header = ["Firm", "validity date ", "STATE", " LICENCE NO"]
    rows, _ = parse_report(_manak_xlsx([["X", "2031/08/31", "UP", "0009156278"]], header=header))
    assert rows == [{"licence_no": "0009156278", "validity_iso": "2031-08-31", "bis_status": None}]


def test_parse_rejects_a_file_without_the_expected_columns():
    with pytest.raises(ValueError, match="Licence No"):
        parse_report(_manak_xlsx([["a", "b"]], header=["Name", "Amount"]))


def test_parse_rejects_something_that_is_not_an_xlsx():
    with pytest.raises(zipfile.BadZipFile):
        parse_report(b"definitely not a spreadsheet")


CLIENT = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
          "IS 4250:2015", "ISI", "0009156278", "01-01-2021", "24-07-2026", "https://x", "EXPIRED")


def _report(licence="0009156278", validity="2031-08-31", bis_status="Operative"):
    return {"licence_no": licence, "validity_iso": validity, "bis_status": bis_status}


TODAY = datetime(2026, 9, 25)


def test_apply_moves_a_renewed_clients_expiry_forward_and_recomputes_status(mongo_db):
    upsert_clients(mongo_db, [CLIENT], mode="replace")

    summary = apply_report(mongo_db, [_report()], 0, apply=True, today=TODAY)

    client = find_client_by_id(mongo_db, "CLT001")
    assert client["expiry_date"] == "31-08-2031"
    assert client["status"] == "ACTIVE"
    assert mongo_db["clients"].find_one({"_id": "CLT001"})["expiry_date_iso"] == "2031-08-31"
    assert summary["renewed"] == 1
    assert summary["applied"] is True


def test_preview_reports_the_same_counts_but_changes_nothing(mongo_db):
    upsert_clients(mongo_db, [CLIENT], mode="replace")

    summary = apply_report(mongo_db, [_report()], 0, apply=False, today=TODAY)

    assert summary["renewed"] == 1
    assert summary["applied"] is False
    assert find_client_by_id(mongo_db, "CLT001")["expiry_date"] == "24-07-2026"
    assert find_client_by_id(mongo_db, "CLT001")["status"] == "EXPIRED"


def test_apply_lists_what_changed_for_the_preview(mongo_db):
    upsert_clients(mongo_db, [CLIENT], mode="replace")

    summary = apply_report(mongo_db, [_report()], 0, apply=False, today=TODAY)

    assert summary["renewed_sample"] == [{
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp", "cert_id": "0009156278",
        "old_expiry": "24-07-2026", "new_expiry": "31-08-2031", "new_status": "ACTIVE",
    }]


def test_apply_never_moves_an_expiry_backwards_or_sideways(mongo_db):
    upsert_clients(mongo_db, [CLIENT], mode="replace")

    for validity in ("2026-07-24", "2026-01-01"):
        summary = apply_report(mongo_db, [_report(validity=validity)], 0, apply=True, today=TODAY)
        assert summary["renewed"] == 0
        assert summary["already_current"] == 1
    assert find_client_by_id(mongo_db, "CLT001")["expiry_date"] == "24-07-2026"


def test_apply_counts_licences_that_are_not_in_the_roster(mongo_db):
    upsert_clients(mongo_db, [CLIENT], mode="replace")

    summary = apply_report(mongo_db, [_report(), _report(licence="0000000001")], 2, apply=False, today=TODAY)

    assert summary["report_rows"] == 4  # 2 usable + 2 unreadable
    assert summary["not_found"] == 1
    assert summary["unreadable"] == 2


def test_apply_matches_a_roster_licence_stored_without_leading_zeros(mongo_db):
    stripped = CLIENT[:7] + ("9156278",) + CLIENT[8:]
    upsert_clients(mongo_db, [stripped], mode="replace")

    summary = apply_report(mongo_db, [_report()], 0, apply=True, today=TODAY)

    assert summary["renewed"] == 1
    assert find_client_by_id(mongo_db, "CLT001")["expiry_date"] == "31-08-2031"


def test_apply_updates_every_client_that_shares_a_licence(mongo_db):
    second = ("CLT002", "Priya Mehta", "TechCorp", "p@x.com", "919812345678") + CLIENT[5:]
    upsert_clients(mongo_db, [CLIENT, second], mode="replace")

    summary = apply_report(mongo_db, [_report()], 0, apply=True, today=TODAY)

    assert summary["renewed"] == 2
    assert find_client_by_id(mongo_db, "CLT002")["status"] == "ACTIVE"


def test_apply_renews_a_client_with_no_expiry_on_file(mongo_db):
    no_expiry = CLIENT[:9] + ("",) + CLIENT[10:]
    upsert_clients(mongo_db, [no_expiry], mode="replace")

    summary = apply_report(mongo_db, [_report()], 0, apply=True, today=TODAY)

    assert summary["renewed"] == 1


def test_parse_reports_combines_the_rows_of_every_file():
    rows, unreadable = parse_reports([
        ("gujarat.xlsx", _manak_xlsx([_row(licence="0000000001")])),
        ("haryana.xlsx", _manak_xlsx([_row(licence="0000000002"), _row(licence="bad")])),
    ])
    assert sorted(r["licence_no"] for r in rows) == ["0000000001", "0000000002"]
    assert unreadable == 1


def test_parse_reports_keeps_the_latest_validity_when_a_licence_is_in_two_files():
    rows, _ = parse_reports([
        ("a.xlsx", _manak_xlsx([_row(validity="2028/01/01")])),
        ("b.xlsx", _manak_xlsx([_row(validity="2031/08/31")])),
        ("c.xlsx", _manak_xlsx([_row(validity="2029/05/05")])),
    ])
    assert rows == [{"licence_no": "0009156278", "validity_iso": "2031-08-31", "bis_status": "Operative"}]


def test_parse_reports_names_the_file_that_is_not_a_spreadsheet():
    with pytest.raises(ValueError, match=r"haryana\.xlsx.*valid \.xlsx"):
        parse_reports([("gujarat.xlsx", _manak_xlsx([_row()])), ("haryana.xlsx", b"garbage")])


def test_parse_reports_names_the_file_with_the_wrong_columns():
    with pytest.raises(ValueError, match=r"punjab\.xlsx.*Licence No"):
        parse_reports([("punjab.xlsx", _manak_xlsx([["a", "b"]], header=["Name", "Amount"]))])
