"""SQLite-backed client roster storage. Replaces xlsx-as-database for
clients_certifications.xlsx so pagination, filtering, and single-client
lookups stay fast regardless of dataset size.

expiry_date is stored as the original DD-MM-YYYY display string (unchanged
from the roster format the frontend already expects); expiry_date_iso is a
YYYY-MM-DD copy used for correct sorting/filtering, since plain string
comparison of DD-MM-YYYY does not sort chronologically.
"""
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
