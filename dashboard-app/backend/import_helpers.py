"""Generic helpers shared by every per-scheme importer (import_bis_isi_data.py
and future ones like import_fmcs.py/import_crs.py) -- none of this is specific
to any one certification scheme's raw export format."""
from datetime import datetime


class RowCollector:
    """Drop-in stand-in for an openpyxl worksheet's .append() -- lets an
    importer collect rows into a plain list instead of writing to a real
    worksheet, for callers that want the converted rows in memory (e.g. to
    merge with existing data) rather than a saved file."""

    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(tuple(row))


SOURCE_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y")


def parse_validity_date(value):
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    for fmt in SOURCE_DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def compute_status(expiry_dt, today=None):
    today = today or datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    days_left = (expiry_dt - today).days
    if days_left < 0:
        return "EXPIRED"
    if days_left <= 7:
        return "CRITICAL"
    if days_left <= 30:
        return "URGENT"
    if days_left <= 60:
        return "DUE SOON"
    return "ACTIVE"


def header_index_map(header_row):
    index_by_name = {}
    for i, name in enumerate(header_row):
        if name is None:
            continue
        index_by_name[str(name).strip().lower()] = i
    return index_by_name


def get(row, index_map, *names):
    for name in names:
        idx = index_map.get(name.lower())
        if idx is not None and idx < len(row):
            return row[idx]
    return None
