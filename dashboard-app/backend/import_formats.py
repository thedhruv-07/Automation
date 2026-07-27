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
