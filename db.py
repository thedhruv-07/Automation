"""SQLite-backed client roster storage. Replaces xlsx-as-database for
clients_certifications.xlsx so pagination, filtering, and single-client
lookups stay fast regardless of dataset size.

expiry_date is stored as the original DD-MM-YYYY display string (unchanged
from the roster format the frontend already expects); expiry_date_iso is a
YYYY-MM-DD copy used for correct sorting/filtering, since plain string
comparison of DD-MM-YYYY does not sort chronologically.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB_PATH = SCRIPT_DIR / "clients.db"

RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]

DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    company         TEXT,
    email           TEXT,
    phone           TEXT,
    cert_name       TEXT,
    cert_id         TEXT,
    issue_date      TEXT,
    expiry_date     TEXT,
    expiry_date_iso TEXT,
    renewal_link    TEXT,
    status          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_expiry ON clients(expiry_date_iso);

CREATE TABLE IF NOT EXISTS sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    phone       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);
"""


def get_connection(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def to_iso_date(value) -> str | None:
    """Converts a DD-MM-YYYY/YYYY-MM-DD/DD/MM/YYYY value (or datetime) to
    YYYY-MM-DD for sorting/filtering. Returns None if unparseable/blank."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {field: row[field] for field in RECORD_FIELDS}


def read_clients(db_path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(f"SELECT {', '.join(RECORD_FIELDS)} FROM clients").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def find_client_by_id(db_path, client_id: str) -> dict | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            f"SELECT {', '.join(RECORD_FIELDS)} FROM clients WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def upsert_clients(db_path, rows: list[tuple], mode: str) -> dict:
    """rows: list of tuples in RECORD_FIELDS order (client_id first).
    mode="replace": clears the table and inserts all rows.
    mode="merge": inserts only rows whose client_id isn't already present.

    Rows with a blank/None client_id are dropped before insertion in either
    mode: SQLite allows multiple NULLs in a non-INTEGER PRIMARY KEY column, so
    such rows would never collide with each other and can't be treated as
    valid client records regardless of mode.
    """
    if mode not in ("replace", "merge"):
        raise ValueError(f"Unknown mode: {mode!r}")

    init_db(db_path)
    db_path = Path(db_path)
    if db_path.exists():
        backup_path = db_path.parent / "clients.backup.db"
        shutil.copyfile(db_path, backup_path)

    rows = [row for row in rows if row[0] is not None and str(row[0]).strip() != ""]

    columns = RECORD_FIELDS + ["expiry_date_iso"]
    placeholders = ", ".join(["?"] * len(columns))
    insert_sql = f"INSERT INTO clients ({', '.join(columns)}) VALUES ({placeholders})"
    prepared_rows = [tuple(row) + (to_iso_date(row[8]),) for row in rows]

    conn = get_connection(db_path)
    try:
        if mode == "replace":
            conn.execute("DELETE FROM clients")
            conn.executemany(insert_sql, prepared_rows)
            conn.commit()
            row_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            return {"row_count": row_count, "added": row_count, "skipped_duplicates": 0}

        added = 0
        skipped = 0
        try:
            for row in prepared_rows:
                client_id = row[0]
                # Check for a genuine duplicate explicitly, rather than relying
                # on INSERT OR IGNORE: that would also silently swallow (and
                # miscount as "duplicate") a row that fails for an unrelated
                # reason, e.g. a NOT NULL violation on name.
                exists = conn.execute(
                    "SELECT 1 FROM clients WHERE client_id = ?", (client_id,)
                ).fetchone()
                if exists:
                    skipped += 1
                    continue
                # Not a duplicate: attempt a plain insert so a real constraint
                # violation raises instead of being folded into the duplicate
                # count. Rows added before a failing row are still committed
                # below (in `finally`) so a bad row doesn't discard prior work.
                conn.execute(insert_sql, row)
                added += 1
        finally:
            conn.commit()
        row_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        return {"row_count": row_count, "added": added, "skipped_duplicates": skipped}
    finally:
        conn.close()
