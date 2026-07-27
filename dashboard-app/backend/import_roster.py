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
