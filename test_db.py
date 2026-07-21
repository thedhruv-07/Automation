# test_db.py
import sqlite3
from db import (
    init_db, read_clients, find_client_by_id, RECORD_FIELDS,
)

ROW_A = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
          "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_B = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
          "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")


def _insert_raw(db_path, rows):
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    for row in rows:
        expiry_iso = _ddmmyyyy_to_iso(row[8])
        conn.execute(
            f"INSERT INTO clients ({', '.join(RECORD_FIELDS)}, expiry_date_iso) "
            f"VALUES ({', '.join(['?'] * (len(RECORD_FIELDS) + 1))})",
            row + (expiry_iso,),
        )
    conn.commit()
    conn.close()


def _ddmmyyyy_to_iso(value):
    d, m, y = value.split("-")
    return f"{y}-{m}-{d}"


def test_init_db_creates_tables_and_is_idempotent(tmp_path):
    db_path = tmp_path / "clients.db"
    init_db(db_path)
    init_db(db_path)  # must not raise on second call
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "clients" in tables
    assert "sent_log" in tables


def test_read_clients_returns_all_rows(tmp_path):
    db_path = tmp_path / "clients.db"
    _insert_raw(db_path, [ROW_A, ROW_B])
    records = read_clients(db_path)
    assert len(records) == 2
    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}
    assert records[0]["expiry_date"] in ("24-07-2026", "11-08-2026")  # original display format preserved


def test_find_client_by_id_returns_matching_record(tmp_path):
    db_path = tmp_path / "clients.db"
    _insert_raw(db_path, [ROW_A, ROW_B])
    record = find_client_by_id(db_path, "CLT002")
    assert record["name"] == "Priya Mehta"
    assert record["status"] == "URGENT"


def test_find_client_by_id_returns_none_for_unknown_id(tmp_path):
    db_path = tmp_path / "clients.db"
    init_db(db_path)
    assert find_client_by_id(db_path, "NOPE") is None
