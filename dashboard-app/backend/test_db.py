# test_db.py
from unittest.mock import patch, MagicMock

import mongomock
import pytest
from db import (
    init_db, read_clients, find_client_by_id, upsert_clients, RECORD_FIELDS,
    get_broadcast_clients_page,
)


@pytest.fixture
def mongo_db():
    return mongomock.MongoClient()["cert_dashboard_test"]


ROW_A = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
          "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_B = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
          "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")


def _insert_raw(db, rows):
    from db import to_iso_date
    init_db(db)
    for row in rows:
        doc = dict(zip(RECORD_FIELDS, row))
        doc["_id"] = doc["client_id"]
        doc["expiry_date_iso"] = to_iso_date(row[9])
        doc["_seq"] = 0
        db["clients"].insert_one(doc)


def test_init_db_is_idempotent(mongo_db):
    init_db(mongo_db)
    init_db(mongo_db)  # must not raise on second call
    assert mongo_db["clients"].index_information() is not None
    assert mongo_db["notice_sent_log"].index_information() is not None


def test_get_client_uses_env_mongodb_uri(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "mongodb://custom-host:27017/mydb")
    import db
    with patch("db.MongoClient", return_value=MagicMock()) as mock_client:
        db.get_client()
    mock_client.assert_called_once_with("mongodb://custom-host:27017/mydb")


def test_get_client_falls_back_to_localhost_default(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    import db
    with patch("db.MongoClient", return_value=MagicMock()) as mock_client:
        db.get_client()
    mock_client.assert_called_once_with("mongodb://localhost:27017")


def test_read_clients_returns_all_rows(mongo_db):
    _insert_raw(mongo_db, [ROW_A, ROW_B])
    records = read_clients(mongo_db)
    assert len(records) == 2
    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}
    assert records[0]["expiry_date"] in ("24-07-2026", "11-08-2026")  # original display format preserved


def test_find_client_by_id_returns_matching_record(mongo_db):
    _insert_raw(mongo_db, [ROW_A, ROW_B])
    record = find_client_by_id(mongo_db, "CLT002")
    assert record["name"] == "Priya Mehta"
    assert record["status"] == "URGENT"


def test_find_client_by_id_returns_none_for_unknown_id(mongo_db):
    init_db(mongo_db)
    assert find_client_by_id(mongo_db, "NOPE") is None


def test_upsert_replace_inserts_all_rows_and_reports_counts(mongo_db):
    rows = [ROW_A, ROW_B]
    stats = upsert_clients(mongo_db, rows, mode="replace")
    assert stats == {"row_count": 2, "added": 2, "skipped_duplicates": 0}
    assert len(read_clients(mongo_db)) == 2


def test_upsert_replace_clears_previous_data(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")
    stats = upsert_clients(mongo_db, [ROW_B], mode="replace")
    assert stats["row_count"] == 1
    records = read_clients(mongo_db)
    assert [r["client_id"] for r in records] == ["CLT002"]


def test_upsert_replace_backs_up_existing_data(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")
    upsert_clients(mongo_db, [ROW_B], mode="replace")
    backed_up = list(mongo_db["clients_backup"].find())
    assert [d["client_id"] for d in backed_up] == ["CLT001"]


def test_upsert_merge_adds_new_and_skips_existing_ids(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")

    updated_row_a = ("CLT001", "SHOULD NOT OVERWRITE", "TechCorp", "r@x.com",
                       "919876543210", "ISO 9001", "ISI", "ISO-1", "01-01-2025",
                       "24-07-2026", "https://x", "CRITICAL")
    stats = upsert_clients(mongo_db, [updated_row_a, ROW_B], mode="merge")

    assert stats == {"row_count": 2, "added": 1, "skipped_duplicates": 1}
    record = find_client_by_id(mongo_db, "CLT001")
    assert record["name"] == "Rahul Sharma"  # kept, not overwritten


def test_upsert_computes_expiry_date_iso_for_sorting(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")
    doc = mongo_db["clients"].find_one({"_id": "CLT001"})
    assert doc["expiry_date_iso"] == "2026-07-24"


def test_upsert_merge_drops_rows_with_blank_or_none_client_id(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")

    blank_id_row = ("", "No ID Person", "Acme", "n@x.com", "919999999999",
                     "ISO 9001", "ISI", "ISO-2", "01-01-2025", "01-01-2027", "https://x", "OK")
    none_id_row = (None, "Also No ID", "Acme", "n2@x.com", "919999999998",
                    "ISO 9001", "ISI", "ISO-3", "01-01-2025", "01-01-2027", "https://x", "OK")

    stats = upsert_clients(mongo_db, [blank_id_row, none_id_row, ROW_B], mode="merge")

    # Only ROW_B (a genuinely new, valid client_id) should be added; the
    # blank/None client_id rows are dropped and never reach the collection.
    assert stats == {"row_count": 2, "added": 1, "skipped_duplicates": 0}
    records = read_clients(mongo_db)
    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}


def test_upsert_merge_raises_on_missing_name_not_miscounted_as_duplicate(mongo_db):
    upsert_clients(mongo_db, [ROW_A], mode="replace")

    # A brand-new client_id (not a duplicate of CLT001) but with no name.
    invalid_row = (
        "CLT099", None, "TechCorp", "r@x.com", "919876543210",
        "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL",
    )

    with pytest.raises(ValueError):
        upsert_clients(mongo_db, [invalid_row], mode="merge")

    # Must not have been silently dropped-and-counted as a duplicate skip:
    # it was never inserted.
    assert find_client_by_id(mongo_db, "CLT099") is None


def test_upsert_merge_rejects_whole_batch_on_missing_name(mongo_db):
    """A batch containing one genuinely-new, valid row followed by one row
    with no name must not partially apply: the valid row must also not be
    inserted, since the whole batch is validated before any insert."""
    upsert_clients(mongo_db, [ROW_A], mode="replace")

    valid_new_row = ROW_B  # CLT002, new and valid
    invalid_row = (
        "CLT099", None, "TechCorp", "r@x.com", "919876543210",
        "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL",
    )

    with pytest.raises(ValueError):
        upsert_clients(mongo_db, [valid_new_row, invalid_row], mode="merge")

    # Neither CLT002 (valid) nor CLT099 (invalid) should have been inserted --
    # only the pre-existing CLT001 remains.
    records = read_clients(mongo_db)
    assert {r["client_id"] for r in records} == {"CLT001"}


from db import get_clients_page

FIVE_ROWS = [
    ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "1", "ISO 9001", "ISI", "ISO-1",
     "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "2", "OSHA", "ISI", "OSHA-1",
     "01-01-2025", "11-08-2026", "https://x", "URGENT"),
    ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "3", "ISO 9001", "ISI", "ISO27-1",
     "01-01-2025", "10-09-2026", "https://x", "DUE SOON"),
    ("CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "4", "GMP", "FMCS", "GMP-1",
     "01-01-2025", "15-10-2026", "https://x", "ACTIVE"),
    ("CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "5", "HACCP", "ISI", "HACCP-1",
     "01-01-2025", "12-01-2026", "https://x", "EXPIRED"),
]


def _seeded_db(mongo_db):
    upsert_clients(mongo_db, FIVE_ROWS, mode="replace")
    return mongo_db


def test_get_clients_page_returns_page_and_total(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=2)
    assert total == 5
    assert len(rows) == 2


def test_get_clients_page_second_page_has_remaining_rows(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=3, page_size=2)
    assert total == 5
    assert len(rows) == 1


def test_get_clients_page_filters_by_status(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, status="URGENT")
    assert total == 1
    assert rows[0]["client_id"] == "CLT002"


def test_get_clients_page_filters_by_cert_type(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, cert_type="ISO 9001")
    assert total == 2
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


def test_get_clients_page_filters_by_search_matches_name_or_company(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, search="tech")
    # "TechCorp" (CLT001 company) and "EduTech" (CLT004 company) both contain "tech" as a substring
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT004"}


def test_get_clients_page_filters_by_expiry_before(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, expiry_before="2026-08-01")
    # CLT001 expiry_date_iso 2026-07-24, CLT005 expiry_date_iso 2026-01-12, both <= 2026-08-01
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT005"}


def test_get_clients_page_sorts_by_expiry_date_chronologically_not_lexically(mongo_db):
    _seeded_db(mongo_db)
    rows, _ = get_clients_page(mongo_db, page=1, page_size=50, sort_key="expiry_date", sort_dir="asc")
    # Chronological order by actual date, NOT lexical DD-MM-YYYY string order:
    # CLT005 2026-01-12, CLT001 2026-07-24, CLT002 2026-08-11, CLT003 2026-09-10, CLT004 2026-10-15
    assert [r["client_id"] for r in rows] == ["CLT005", "CLT001", "CLT002", "CLT003", "CLT004"]


def test_get_clients_page_sorts_descending_by_name(mongo_db):
    _seeded_db(mongo_db)
    rows, _ = get_clients_page(mongo_db, page=1, page_size=50, sort_key="name", sort_dir="desc")
    # Names: Rahul Sharma, Priya Mehta, Amit Verma, Sneha Kapoor, Rajesh Nair
    # Descending alphabetical: Sneha Kapoor, Rajesh Nair, Rahul Sharma, Priya Mehta, Amit Verma
    assert rows[0]["client_id"] == "CLT004"
    assert rows[-1]["client_id"] == "CLT003"


def test_get_clients_page_defaults_to_client_id_order_when_no_sort_key(mongo_db):
    _seeded_db(mongo_db)
    rows, _ = get_clients_page(mongo_db, page=1, page_size=50)
    assert [r["client_id"] for r in rows] == ["CLT001", "CLT002", "CLT003", "CLT004", "CLT005"]


from db import get_stats, export_clients_rows, record_sent


def test_get_stats_counts_by_status_and_total(mongo_db):
    _seeded_db(mongo_db)
    stats = get_stats(mongo_db, today="2026-07-21")
    assert stats["status_counts"]["total"] == 5
    assert stats["status_counts"]["CRITICAL"] == 1
    assert stats["status_counts"]["URGENT"] == 1
    assert stats["status_counts"]["ACTIVE"] == 1
    assert stats["status_counts"]["EXPIRED"] == 1


def test_get_stats_cert_types_are_distinct_and_sorted(mongo_db):
    _seeded_db(mongo_db)
    stats = get_stats(mongo_db, today="2026-07-21")
    assert stats["cert_types"] == ["GMP", "HACCP", "ISO 9001", "OSHA"]


def test_get_stats_renewals_by_month_groups_by_year_month(mongo_db):
    _seeded_db(mongo_db)
    stats = get_stats(mongo_db, today="2026-07-21")
    by_month = {r["year_month"]: r["count"] for r in stats["renewals_by_month"]}
    assert by_month["2026-07"] == 1
    assert by_month["2026-08"] == 1


def test_get_stats_eligible_not_sent_today_excludes_already_sent(mongo_db):
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    stats = get_stats(mongo_db, today="2026-07-21")
    # CRITICAL, URGENT, DUE SOON, EXPIRED = 4 alert-eligible rows; CLT001 already sent today
    assert stats["eligible_not_sent_today"] == 3


def test_get_stats_eligible_not_sent_today_excludes_within_reminder_interval(mongo_db):
    """A client sent 5 days ago is still inside the 20-day reminder window,
    same as get_eligible_count -- the stat tile must agree with the send
    endpoint's actual dedup logic, not just exact-same-day sends."""
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-16", "wamid.ABC", "1", "2026-07-16T10:00:00")
    stats = get_stats(mongo_db, today="2026-07-21")
    assert stats["eligible_not_sent_today"] == 3


def test_export_clients_rows_yields_all_matching_rows_no_pagination(mongo_db):
    _seeded_db(mongo_db)
    rows = list(export_clients_rows(mongo_db, cert_type="ISO 9001"))
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


from db import is_already_sent, load_sent_log, save_sent_log


def test_is_already_sent_false_then_true_after_record_sent(mongo_db):
    _seeded_db(mongo_db)
    assert is_already_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21") is False
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    assert is_already_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21") is True


def test_save_sent_log_then_load_sent_log_round_trips_exactly(mongo_db):
    _seeded_db(mongo_db)
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
    save_sent_log(mongo_db, original)
    loaded = load_sent_log(mongo_db)
    assert loaded == original


from db import record_email_sent, is_email_already_sent, load_email_sent_log, save_email_sent_log


def test_is_email_already_sent_false_then_true_after_record_email_sent(mongo_db):
    _seeded_db(mongo_db)
    assert is_email_already_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21") is False
    record_email_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "brevo-msg-1", "r@x.com", "2026-07-21T10:00:00")
    assert is_email_already_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21") is True


def test_email_dedup_is_independent_of_whatsapp_dedup(mongo_db):
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "919876543210", "2026-07-21T10:00:00")
    # WhatsApp was sent, but email for the same client/status/day should still be unsent
    assert is_already_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21") is True
    assert is_email_already_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21") is False


def test_save_email_sent_log_then_load_email_sent_log_round_trips_exactly(mongo_db):
    _seeded_db(mongo_db)
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
    save_email_sent_log(mongo_db, original)
    loaded = load_email_sent_log(mongo_db)
    assert loaded == original


def test_get_stats_eligible_not_emailed_today_excludes_already_emailed(mongo_db):
    _seeded_db(mongo_db)
    record_email_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "brevo-msg-1", "r@x.com", "2026-07-21T10:00:00")
    stats = get_stats(mongo_db, today="2026-07-21")
    # CRITICAL, URGENT, DUE SOON, EXPIRED = 4 alert-eligible rows; CLT001 already emailed today
    assert stats["eligible_not_emailed_today"] == 3
    # WhatsApp's own count is untouched by the email send
    assert stats["eligible_not_sent_today"] == 4


from db import get_eligible_clients, get_eligible_count
from db import (
    is_notice_already_sent, record_notice_sent, get_broadcast_clients, get_notice_eligible_count,
)


def test_get_eligible_clients_excludes_active_by_default(mongo_db):
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db)
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT002", "CLT003", "CLT005"}


def test_get_eligible_clients_preserves_insertion_order(mongo_db):
    """run()/run_email_alerts() depend on this order matching read_clients()'s
    order exactly -- see whatsapp_renewal_alerts.py's order-sensitive tests."""
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db)
    assert [r["client_id"] for r in rows] == ["CLT001", "CLT002", "CLT003", "CLT005"]


def test_get_eligible_clients_filters_by_cert_type(mongo_db):
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db, cert_type="ISO 9001")
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT003"}


def test_get_eligible_clients_filters_by_expiry_before(mongo_db):
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db, expiry_before="2026-08-01")
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT005"}


def test_get_eligible_clients_status_filter_narrows_within_alert_eligible_set(mongo_db):
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db, status="CRITICAL")
    assert {r["client_id"] for r in rows} == {"CLT001"}


def test_get_eligible_clients_status_active_returns_empty(mongo_db):
    """ACTIVE is never alert-eligible, so filtering to it must yield nothing --
    the alert-eligibility restriction and the status filter are AND'ed
    together, not one replacing the other."""
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db, status="ACTIVE")
    assert rows == []


def test_get_eligible_clients_filters_by_search(mongo_db):
    """CLT004 (EduTech, "tech" match) is ACTIVE and thus excluded from the
    alert-eligible set regardless of the search term, so only CLT001
    (TechCorp) should match."""
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db, search="tech")
    assert {r["client_id"] for r in rows} == {"CLT001"}


def test_get_eligible_count_counts_all_eligible_not_sent_today(mongo_db):
    _seeded_db(mongo_db)
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp") == 4


def test_get_eligible_count_excludes_already_sent_today(mongo_db):
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp") == 3


def test_get_eligible_count_excludes_sent_within_reminder_interval(mongo_db):
    """A client sent 5 days ago is still inside the 20-day reminder window --
    it must not count as eligible again, even though it wasn't sent today."""
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-16", "wamid.ABC", "1", "2026-07-16T10:00:00")
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp") == 3


def test_get_eligible_count_includes_sent_after_reminder_interval_elapses(mongo_db):
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-01", "wamid.ABC", "1", "2026-07-01T10:00:00")
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp") == 4


def test_get_eligible_count_email_channel_is_independent_of_whatsapp(mongo_db):
    _seeded_db(mongo_db)
    record_sent(mongo_db, "CLT001", "CRITICAL", "2026-07-21", "wamid.ABC", "1", "2026-07-21T10:00:00")
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp") == 3
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="email") == 4


def test_get_eligible_count_filters_by_cert_type(mongo_db):
    _seeded_db(mongo_db)
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp", cert_type="ISO 9001") == 2


def test_get_eligible_count_filters_by_search(mongo_db):
    """CLT004 (EduTech, "tech" match) is ACTIVE and thus excluded from the
    alert-eligible set regardless of the search term, so only CLT001
    (TechCorp) should be counted."""
    _seeded_db(mongo_db)
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp", search="tech") == 1


def test_get_eligible_count_status_active_returns_zero(mongo_db):
    _seeded_db(mongo_db)
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp", status="ACTIVE") == 0


def test_get_eligible_count_rejects_unknown_channel(mongo_db):
    _seeded_db(mongo_db)
    with pytest.raises(ValueError):
        get_eligible_count(mongo_db, today="2026-07-21", channel="carrier-pigeon")


def test_get_clients_page_filters_by_scheme(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, scheme="FMCS")
    assert total == 1
    assert rows[0]["client_id"] == "CLT004"


def test_export_clients_rows_filters_by_scheme(mongo_db):
    _seeded_db(mongo_db)
    rows = list(export_clients_rows(mongo_db, scheme="FMCS"))
    assert {r["client_id"] for r in rows} == {"CLT004"}


def test_get_stats_schemes_are_distinct_and_sorted(mongo_db):
    _seeded_db(mongo_db)
    stats = get_stats(mongo_db, today="2026-07-21")
    assert stats["schemes"] == ["FMCS", "ISI"]


def test_get_eligible_clients_filters_by_scheme(mongo_db):
    _seeded_db(mongo_db)
    rows = get_eligible_clients(mongo_db, scheme="ISI")
    # CLT004 is scheme FMCS but also ACTIVE (not alert-eligible) -- this
    # confirms the scheme filter and alert-eligibility both apply, not
    # either alone.
    assert {r["client_id"] for r in rows} == {"CLT001", "CLT002", "CLT003", "CLT005"}
    # The only FMCS row (CLT004) is ACTIVE and thus never alert-eligible
    # regardless of scheme, so filtering to scheme="FMCS" must yield nothing.
    assert get_eligible_clients(mongo_db, scheme="FMCS") == []


def test_get_eligible_count_filters_by_scheme(mongo_db):
    _seeded_db(mongo_db)
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp", scheme="FMCS") == 0
    assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp", scheme="ISI") == 4


def test_record_and_check_notice_sent(mongo_db):
    init_db(mongo_db)

    assert is_notice_already_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "whatsapp") is False

    record_notice_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    assert is_notice_already_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "whatsapp") is True
    # A different channel for the same client/notice is tracked independently.
    assert is_notice_already_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "email") is False
    # A different notice_id for the same client/channel is tracked independently.
    assert is_notice_already_sent(mongo_db, "CLT001", "some_other_notice", "whatsapp") is False


def test_get_broadcast_clients_returns_every_status(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")

    records = get_broadcast_clients(mongo_db)

    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}


def test_get_broadcast_clients_honors_scheme_filter(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")

    records = get_broadcast_clients(mongo_db, scheme="CRS")

    assert {r["client_id"] for r in records} == {"CLT002"}


def test_get_notice_eligible_count_excludes_already_sent(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")
    record_notice_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    count = get_notice_eligible_count(mongo_db, "meity_series_guidelines_2026", "whatsapp", scheme="CRS")

    assert count == 1


def test_get_notice_eligible_count_is_independent_per_notice_and_channel(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ], mode="replace")
    record_notice_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    # Already sent via whatsapp for this notice -- excluded.
    assert get_notice_eligible_count(mongo_db, "meity_series_guidelines_2026", "whatsapp") == 0
    # Not yet sent via email for this same notice -- still counted.
    assert get_notice_eligible_count(mongo_db, "meity_series_guidelines_2026", "email") == 1
    # Not yet sent (via any channel) for a different notice -- still counted.
    assert get_notice_eligible_count(mongo_db, "some_other_notice", "whatsapp") == 1


def test_get_broadcast_clients_page_paginates_and_totals(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
        ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919898765432",
         "GMP", "CRS", "GMP-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON"),
    ], mode="replace")

    rows, total = get_broadcast_clients_page(mongo_db, "meity_series_guidelines_2026", page=1, page_size=2)

    assert total == 3
    assert len(rows) == 2
    assert [r["client_id"] for r in rows] == ["CLT001", "CLT002"]

    rows_page2, total2 = get_broadcast_clients_page(mongo_db, "meity_series_guidelines_2026", page=2, page_size=2)
    assert total2 == 3
    assert [r["client_id"] for r in rows_page2] == ["CLT003"]


def test_get_broadcast_clients_page_honors_filters(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")

    rows, total = get_broadcast_clients_page(mongo_db, "meity_series_guidelines_2026", scheme="CRS")

    assert total == 1
    assert rows[0]["client_id"] == "CLT002"


def test_get_broadcast_clients_page_reports_per_channel_notice_status(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")
    record_notice_sent(mongo_db, "CLT001", "meity_series_guidelines_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    rows, _ = get_broadcast_clients_page(mongo_db, "meity_series_guidelines_2026")
    by_id = {r["client_id"]: r for r in rows}

    assert by_id["CLT001"]["notice_sent_whatsapp"] is True
    assert by_id["CLT001"]["notice_sent_email"] is False
    assert by_id["CLT002"]["notice_sent_whatsapp"] is False
    assert by_id["CLT002"]["notice_sent_email"] is False


def test_get_broadcast_clients_page_notice_status_is_independent_per_notice(mongo_db):
    upsert_clients(mongo_db, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ], mode="replace")
    record_notice_sent(mongo_db, "CLT001", "some_other_notice", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    rows, _ = get_broadcast_clients_page(mongo_db, "meity_series_guidelines_2026")

    assert rows[0]["notice_sent_whatsapp"] is False
