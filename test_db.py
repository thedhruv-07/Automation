# test_db.py
import sqlite3
import pytest
from db import (
    init_db, read_clients, find_client_by_id, upsert_clients, RECORD_FIELDS,
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


def test_upsert_replace_inserts_all_rows_and_reports_counts(tmp_path):
    db_path = tmp_path / "clients.db"
    rows = [ROW_A, ROW_B]
    stats = upsert_clients(db_path, rows, mode="replace")
    assert stats == {"row_count": 2, "added": 2, "skipped_duplicates": 0}
    assert len(read_clients(db_path)) == 2


def test_upsert_replace_clears_previous_data(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")
    stats = upsert_clients(db_path, [ROW_B], mode="replace")
    assert stats["row_count"] == 1
    records = read_clients(db_path)
    assert [r["client_id"] for r in records] == ["CLT002"]


def test_upsert_replace_backs_up_existing_db(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")
    upsert_clients(db_path, [ROW_B], mode="replace")
    backup_path = tmp_path / "clients.backup.db"
    assert backup_path.exists()


def test_upsert_merge_adds_new_and_skips_existing_ids(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")

    updated_row_a = ("CLT001", "SHOULD NOT OVERWRITE", "TechCorp", "r@x.com",
                       "919876543210", "ISO 9001", "ISO-1", "01-01-2025",
                       "24-07-2026", "https://x", "CRITICAL")
    stats = upsert_clients(db_path, [updated_row_a, ROW_B], mode="merge")

    assert stats == {"row_count": 2, "added": 1, "skipped_duplicates": 1}
    record = find_client_by_id(db_path, "CLT001")
    assert record["name"] == "Rahul Sharma"  # kept, not overwritten


def test_upsert_computes_expiry_date_iso_for_sorting(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")
    conn = sqlite3.connect(str(db_path))
    iso = conn.execute("SELECT expiry_date_iso FROM clients WHERE client_id = 'CLT001'").fetchone()[0]
    conn.close()
    assert iso == "2026-07-24"


def test_upsert_merge_drops_rows_with_blank_or_none_client_id(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")

    blank_id_row = ("", "No ID Person", "Acme", "n@x.com", "919999999999",
                     "ISO 9001", "ISO-2", "01-01-2025", "01-01-2027", "https://x", "OK")
    none_id_row = (None, "Also No ID", "Acme", "n2@x.com", "919999999998",
                    "ISO 9001", "ISO-3", "01-01-2025", "01-01-2027", "https://x", "OK")

    stats = upsert_clients(db_path, [blank_id_row, none_id_row, ROW_B], mode="merge")

    # Only ROW_B (a genuinely new, valid client_id) should be added; the
    # blank/None client_id rows are dropped and never reach the table.
    assert stats == {"row_count": 2, "added": 1, "skipped_duplicates": 0}
    records = read_clients(db_path)
    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}


def test_upsert_merge_raises_on_constraint_violation_not_miscounted_as_duplicate(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")

    # A brand-new client_id (not a duplicate of CLT001) but with a NULL name,
    # which violates the `name TEXT NOT NULL` constraint.
    invalid_row = (
        "CLT099", None, "TechCorp", "r@x.com", "919876543210",
        "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL",
    )

    with pytest.raises(sqlite3.IntegrityError):
        upsert_clients(db_path, [invalid_row], mode="merge")

    # Must not have been silently dropped-and-counted as a duplicate skip:
    # it was never inserted, and the pre-check confirms it wasn't treated
    # as a duplicate of any existing row.
    assert find_client_by_id(db_path, "CLT099") is None
