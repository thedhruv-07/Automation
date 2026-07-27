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
