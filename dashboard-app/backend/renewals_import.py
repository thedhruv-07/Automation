"""Uses a BIS Manak Online "List of Licences" report to find clients who have
renewed: a client whose licence now shows a later validity date than the one
we hold gets that date, and its status is recomputed (so it drops to ACTIVE
and out of renewal emails/follow-ups).

The report is parsed straight from the xlsx XML rather than with openpyxl --
the file Manak Online exports has a stylesheet openpyxl refuses to load."""
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from db import init_db, to_iso_date
from import_helpers import compute_status

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")
_SAMPLE_LIMIT = 20


def _column_index(ref: str) -> int:
    index = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _sheet_rows(data: bytes) -> list[list]:
    """Rows of the first worksheet as lists of strings (None for blanks).
    Raises zipfile.BadZipFile if data isn't an xlsx at all."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(_NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))
        sheets = sorted(
            (n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
            key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)),
        )
        if not sheets:
            raise ValueError("The spreadsheet has no worksheet.")
        root = ET.fromstring(z.read(sheets[0]))

    rows = []
    for row in root.iter(_NS + "row"):
        cells = {}
        for c in row.findall(_NS + "c"):
            kind, v = c.get("t"), c.find(_NS + "v")
            if kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(_NS + "t"))
            elif kind == "s" and v is not None:
                value = shared[int(v.text)]
            else:
                value = v.text if v is not None else None
            cells[_column_index(c.get("r"))] = value
        rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
    return rows


def _licence_no(value) -> str | None:
    """10-digit licence number, restoring zeros Excel drops when it stores the
    number as a number. None if it isn't numeric at all."""
    text = re.sub(r"\.0+$", "", str(value).strip()) if value is not None else ""
    return text.zfill(10) if text.isdigit() else None


def _validity_iso(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    if re.fullmatch(r"\d+(\.\d+)?", text):  # an Excel date serial
        return (datetime(1899, 12, 30) + timedelta(days=float(text))).strftime("%Y-%m-%d")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_report(data: bytes) -> tuple[list[dict], int]:
    """(rows, unreadable): one {licence_no, validity_iso, bis_status} per usable
    row, and how many rows had no readable licence number or validity date.
    Columns are found by header name, so their order doesn't matter."""
    table = _sheet_rows(data)
    for header_at, row in enumerate(table):
        names = {str(v).strip().lower(): i for i, v in enumerate(row) if v is not None}
        if "licence no" in names and "validity date" in names:
            break
    else:
        raise ValueError(
            "This doesn't look like a Manak Online 'List of Licences' report -- "
            "expected 'Licence No' and 'Validity Date' columns."
        )

    def cell(row, name):
        i = names.get(name)
        return row[i] if i is not None and i < len(row) else None

    rows, unreadable = [], 0
    for row in table[header_at + 1:]:
        if not any(v not in (None, "") for v in row):
            continue
        licence, validity = _licence_no(cell(row, "licence no")), _validity_iso(cell(row, "validity date"))
        if licence is None or validity is None:
            unreadable += 1
            continue
        status = cell(row, "status")
        rows.append({"licence_no": licence, "validity_iso": validity, "bis_status": status.strip() if status else None})
    return rows, unreadable


def parse_reports(files: list[tuple[str, bytes]]) -> tuple[list[dict], int]:
    """parse_report over several files (e.g. one Manak download per state) as
    one combined list. A licence in more than one file keeps its latest
    validity. A file that can't be read fails the whole call, naming the file,
    so nothing is half-imported."""
    latest, unreadable_total = {}, 0
    for name, data in files:
        try:
            rows, unreadable = parse_report(data)
        except zipfile.BadZipFile:
            raise ValueError(f"{name}: could not be read as a valid .xlsx spreadsheet")
        except ValueError as exc:
            raise ValueError(f"{name}: {exc}")
        unreadable_total += unreadable
        for row in rows:
            known = latest.get(row["licence_no"])
            if known is None or row["validity_iso"] > known["validity_iso"]:
                latest[row["licence_no"]] = row
    return list(latest.values()), unreadable_total


def apply_report(db, rows: list[dict], unreadable: int, apply: bool, today: datetime | None = None) -> dict:
    """Matches report rows to clients by licence number (cert_id). Where the
    report's validity is later than the client's expiry, the client is renewed:
    apply=True writes the new expiry date and recomputed status, apply=False
    only reports what would change. Never moves an expiry backwards."""
    init_db(db)
    by_licence = {r["licence_no"]: r for r in rows}
    lookups = list(by_licence) + [k.lstrip("0") for k in by_licence]
    clients = list(db["clients"].find({"cert_id": {"$in": lookups}}))

    matched_licences, renewed, already_current, sample = set(), 0, 0, []
    for doc in clients:
        licence = _licence_no(doc.get("cert_id"))
        report = by_licence.get(licence)
        if report is None:
            continue
        matched_licences.add(licence)
        current_iso = doc.get("expiry_date_iso") or to_iso_date(doc.get("expiry_date"))
        if current_iso and report["validity_iso"] <= current_iso:
            already_current += 1
            continue
        new_dt = datetime.strptime(report["validity_iso"], "%Y-%m-%d")
        new_expiry, new_status = new_dt.strftime("%d-%m-%Y"), compute_status(new_dt, today)
        renewed += 1
        if len(sample) < _SAMPLE_LIMIT:
            sample.append({
                "client_id": doc["client_id"], "name": doc.get("name"), "company": doc.get("company"),
                "cert_id": doc.get("cert_id"), "old_expiry": doc.get("expiry_date"),
                "new_expiry": new_expiry, "new_status": new_status,
            })
        if apply:
            db["clients"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"expiry_date": new_expiry, "expiry_date_iso": report["validity_iso"], "status": new_status}},
            )

    return {
        "applied": apply, "report_rows": len(rows) + unreadable, "unreadable": unreadable,
        "matched": renewed + already_current, "renewed": renewed, "already_current": already_current,
        "not_found": len(by_licence) - len(matched_licences), "renewed_sample": sample,
    }
