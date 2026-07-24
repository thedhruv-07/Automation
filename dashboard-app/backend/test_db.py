# test_db.py
import sqlite3
from pathlib import Path

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


def test_upsert_merge_rolls_back_whole_batch_on_constraint_violation(tmp_path):
    """A batch containing one genuinely-new, valid row followed by one row
    that violates the NOT NULL constraint on name must not partially commit:
    the valid row processed before the failing one must also be rolled back,
    so the caller's "this whole operation failed" story matches reality."""
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_A], mode="replace")

    valid_new_row = ROW_B  # CLT002, new and valid
    invalid_row = (
        "CLT099", None, "TechCorp", "r@x.com", "919876543210",
        "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL",
    )

    with pytest.raises(sqlite3.IntegrityError):
        upsert_clients(db_path, [valid_new_row, invalid_row], mode="merge")

    # Neither CLT002 (valid, processed first) nor CLT099 (invalid) should
    # have been committed -- only the pre-existing CLT001 remains.
    records = read_clients(db_path)
    assert {r["client_id"] for r in records} == {"CLT001"}


from db import get_clients_page

FIVE_ROWS = [
    ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "1", "ISO 9001", "ISO-1",
     "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "2", "OSHA", "OSHA-1",
     "01-01-2025", "11-08-2026", "https://x", "URGENT"),
    ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "3", "ISO 9001", "ISO27-1",
     "01-01-2025", "10-09-2026", "https://x", "DUE SOON"),
    ("CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "4", "GMP", "GMP-1",
     "01-01-2025", "15-10-2026", "https://x", "ACTIVE"),
    ("CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "5", "HACCP", "HACCP-1",
     "01-01-2025", "12-01-2026", "https://x", "EXPIRED"),
]


def _seeded_db(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, FIVE_ROWS, mode="replace")
    return db_path


def test_get_clients_page_returns_page_and_total(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=2)
    assert total == 5
    assert len(rows) == 2


def test_get_clients_page_second_page_has_remaining_rows(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=3, page_size=2)
    assert total == 5
    assert len(rows) == 1


def test_get_clients_page_filters_by_status(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, status="URGENT")
    assert total == 1
    assert rows[0]["client_id"] == "CLT002"


def test_get_clients_page_filters_by_cert_type(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, cert_type="ISO 9001")
    assert total == 2
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


def test_get_clients_page_filters_by_search_matches_name_or_company(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, search="tech")
    # "TechCorp" (CLT001 company) and "EduTech" (CLT004 company) both contain "tech" as a substring
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT004"}


def test_get_clients_page_filters_by_expiry_before(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, total = get_clients_page(db_path, page=1, page_size=50, expiry_before="2026-08-01")
    # CLT001 expiry_date_iso 2026-07-24, CLT005 expiry_date_iso 2026-01-12, both <= 2026-08-01
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT005"}


def test_get_clients_page_sorts_by_expiry_date_chronologically_not_lexically(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, _ = get_clients_page(db_path, page=1, page_size=50, sort_key="expiry_date", sort_dir="asc")
    # Chronological order by actual date, NOT lexical DD-MM-YYYY string order:
    # CLT005 2026-01-12, CLT001 2026-07-24, CLT002 2026-08-11, CLT003 2026-09-10, CLT004 2026-10-15
    assert [r["client_id"] for r in rows] == ["CLT005", "CLT001", "CLT002", "CLT003", "CLT004"]


def test_get_clients_page_sorts_descending_by_name(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, _ = get_clients_page(db_path, page=1, page_size=50, sort_key="name", sort_dir="desc")
    # Names: Rahul Sharma, Priya Mehta, Amit Verma, Sneha Kapoor, Rajesh Nair
    # Descending alphabetical: Sneha Kapoor, Rajesh Nair, Rahul Sharma, Priya Mehta, Amit Verma
    # (verified with sorted(names, reverse=True) in plain Python - "Rahul" < "Rajesh"
    # lexically since 'h' < 'j' at the 3rd char, so Amit Verma, not Rahul Sharma, is last)
    assert rows[0]["client_id"] == "CLT004"
    assert rows[-1]["client_id"] == "CLT003"


def test_get_clients_page_defaults_to_client_id_order_when_no_sort_key(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows, _ = get_clients_page(db_path, page=1, page_size=50)
    assert [r["client_id"] for r in rows] == ["CLT001", "CLT002", "CLT003", "CLT004", "CLT005"]


from db import get_stats, export_clients_rows, record_sent


def test_get_stats_counts_by_status_and_total(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    assert stats["status_counts"]["total"] == 5
    assert stats["status_counts"]["CRITICAL"] == 1
    assert stats["status_counts"]["URGENT"] == 1
    assert stats["status_counts"]["ACTIVE"] == 1
    assert stats["status_counts"]["EXPIRED"] == 1


def test_get_stats_cert_types_are_distinct_and_sorted(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    assert stats["cert_types"] == ["GMP", "HACCP", "ISO 9001", "OSHA"]


def test_get_stats_renewals_by_month_groups_by_year_month(tmp_path):
    db_path = _seeded_db(tmp_path)
    stats = get_stats(db_path, today="2026-07-21")
    by_month = {r["year_month"]: r["count"] for r in stats["renewals_by_month"]}
    assert by_month["2026-07"] == 1
    assert by_month["2026-08"] == 1


def test_get_stats_eligible_not_sent_today_excludes_already_sent(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    stats = get_stats(db_path, today="2026-07-21")
    # CRITICAL, URGENT, DUE SOON, EXPIRED = 4 alert-eligible rows; CLT001 already sent today
    assert stats["eligible_not_sent_today"] == 3


def test_export_clients_rows_yields_all_matching_rows_no_pagination(tmp_path):
    db_path = _seeded_db(tmp_path)
    rows = list(export_clients_rows(db_path, cert_type="ISO 9001"))
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


from db import is_already_sent, load_sent_log, save_sent_log


def test_is_already_sent_false_then_true_after_record_sent(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert is_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is False
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    assert is_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is True


def test_save_sent_log_then_load_sent_log_round_trips_exactly(tmp_path):
    db_path = _seeded_db(tmp_path)
    original = {
        "CLT001|CRITICAL|2026-07-21": {
            "sent_at": "2026-07-21T10:00:00",
            "message_id": "wamid.ABC",
            "phone": "919876543210",
        },
        "CLT002|URGENT|2026-07-21": {
            "sent_at": "2026-07-21T10:05:00",
            "message_id": "wamid.DEF",
            "phone": "919812345678",
        },
    }
    save_sent_log(db_path, original)
    loaded = load_sent_log(db_path)
    assert loaded == original


def test_resolve_default_db_path_uses_env_override(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", "/tmp/custom-dir/clients.db")
    from db import _resolve_default_db_path
    assert _resolve_default_db_path() == Path("/tmp/custom-dir/clients.db")


def test_resolve_default_db_path_falls_back_to_repo_data_dir(monkeypatch):
    monkeypatch.delenv("DASHBOARD_DB_PATH", raising=False)
    from db import _resolve_default_db_path, REPO_ROOT
    assert _resolve_default_db_path() == REPO_ROOT / "data" / "clients.db"


from db import (
    record_email_sent, is_email_already_sent, load_email_sent_log, save_email_sent_log,
)


def test_is_email_already_sent_false_then_true_after_record_email_sent(tmp_path):
    db_path = _seeded_db(tmp_path)
    assert is_email_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is False
    record_email_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "brevo-msg-1", "r@x.com", "2026-07-21T10:00:00")
    assert is_email_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is True


def test_email_dedup_is_independent_of_whatsapp_dedup(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "919876543210", "2026-07-21T10:00:00")
    # WhatsApp was sent, but email for the same client/status/day should still be unsent
    assert is_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is True
    assert is_email_already_sent(db_path, "CLT001", "CRITICAL", "2026-07-21") is False


def test_save_email_sent_log_then_load_email_sent_log_round_trips_exactly(tmp_path):
    db_path = _seeded_db(tmp_path)
    original = {
        "CLT001|CRITICAL|2026-07-21": {
            "sent_at": "2026-07-21T10:00:00",
            "message_id": "brevo-msg-1",
            "email": "r@x.com",
        },
        "CLT002|URGENT|2026-07-21": {
            "sent_at": "2026-07-21T10:05:00",
            "message_id": "brevo-msg-2",
            "email": "p@x.com",
        },
    }
    save_email_sent_log(db_path, original)
    loaded = load_email_sent_log(db_path)
    assert loaded == original


def test_get_stats_eligible_not_emailed_today_excludes_already_emailed(tmp_path):
    db_path = _seeded_db(tmp_path)
    record_email_sent(db_path, "CLT001", "CRITICAL", "2026-07-21", "brevo-msg-1", "r@x.com", "2026-07-21T10:00:00")
    stats = get_stats(db_path, today="2026-07-21")
    # CRITICAL, URGENT, DUE SOON, EXPIRED = 4 alert-eligible rows; CLT001 already emailed today
    assert stats["eligible_not_emailed_today"] == 3
    # WhatsApp's own count is untouched by the email send
    assert stats["eligible_not_sent_today"] == 4
