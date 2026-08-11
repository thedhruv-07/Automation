from datetime import datetime
from whatsapp_renewal_alerts import normalize_phone, format_expiry


def test_normalize_phone_strips_plus_sign():
    assert normalize_phone("+919876543210") == "919876543210"


def test_normalize_phone_handles_bare_digits():
    assert normalize_phone("919876543210") == "919876543210"


def test_normalize_phone_handles_int_input():
    assert normalize_phone(919876543210) == "919876543210"


def test_normalize_phone_strips_spaces_and_hyphens():
    assert normalize_phone("+91 98765-43210") == "919876543210"


def test_normalize_phone_strips_00_international_trunk_prefix():
    """Some contact data uses "00" as the international access code instead
    of "+" -- WhatsApp's API expects country_code+number with neither."""
    assert normalize_phone("0091 98765 43210") == "919876543210"


def test_normalize_phone_strips_00_prefix_even_when_result_is_still_malformed():
    """The function only strips the trunk prefix -- it doesn't validate
    whether what's left is a real deliverable number (e.g. a landline).
    That validation happens on Meta's side, not here."""
    assert normalize_phone("(0086)-0755-86360200") == "86075586360200"


def test_format_expiry_from_ddmmyyyy_string():
    assert format_expiry("24-07-2026") == "24 July 2026"


def test_format_expiry_from_datetime_object():
    assert format_expiry(datetime(2026, 7, 24)) == "24 July 2026"


def test_format_expiry_raises_on_unparseable_value():
    import pytest as pytest_mod
    with pytest_mod.raises(ValueError):
        format_expiry("not-a-date")


def test_format_expiry_from_yyyymmdd_string():
    assert format_expiry("2026-07-24") == "24 July 2026"


def test_format_expiry_from_ddmmyyyy_slash_string():
    assert format_expiry("24/07/2026") == "24 July 2026"


def test_format_expiry_strips_whitespace():
    assert format_expiry("  24-07-2026  ") == "24 July 2026"


from whatsapp_renewal_alerts import dedup_key, load_sent_log, save_sent_log


def test_dedup_key_format():
    assert dedup_key("CLT001", "CRITICAL", "2026-07-17") == "CLT001|CRITICAL|2026-07-17"


def test_load_sent_log_missing_file_returns_empty_dict(mongo_db):
    assert load_sent_log(mongo_db) == {}


def test_save_and_load_sent_log_round_trip(mongo_db):
    entry = {"message_id": "wamid.ABC", "phone": "919876543210", "sent_at": "2026-07-17T10:00:00"}
    save_sent_log(mongo_db, {"CLT001|CRITICAL|2026-07-17": entry})
    result = load_sent_log(mongo_db)
    assert result == {"CLT001|CRITICAL|2026-07-17": entry}


from whatsapp_renewal_alerts import read_clients, filter_alertable
from db import upsert_clients


def _write_db(path, rows):
    upsert_clients(path, rows, mode="replace")


def test_read_clients_and_filter_alertable(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
        ["CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919898765432",
         "GMP", "ISI", "GMP-1", "01-01-2025", "10-09-2026",
         "https://x/renew?id=GMP-1", "DUE SOON"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISI", "ISO27-1", "01-01-2025", "15-10-2026",
         "https://x/renew?id=ISO27-1", "ACTIVE"],
        ["CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "919654321098",
         "HACCP", "ISI", "HACCP-1", "01-01-2025", "12-07-2026",
         "https://x/renew?id=HACCP-1", "EXPIRED"],
    ])

    records = read_clients(db_path)
    assert len(records) == 5
    assert records[0]["client_id"] == "CLT001"
    assert records[0]["cert_id"] == "ISO-1"
    assert records[0]["status"] == "CRITICAL"

    alertable = filter_alertable(records)
    assert [r["client_id"] for r in alertable] == ["CLT001", "CLT002", "CLT003", "CLT005"]


def test_read_clients_skips_blank_rows(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Name", "Co", "e@x.com", "919876543210", "Cert", "ISI", "C-1",
         "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        [None, None, None, None, None, None, None, None, None, None, None, None],
        ["CLT002", "Name2", "Co2", "e2@x.com", "919876543211", "Cert2", "ISI", "C-2",
         "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
    records = read_clients(db_path)
    assert len(records) == 2
    assert [r["client_id"] for r in records] == ["CLT001", "CLT002"]


from whatsapp_renewal_alerts import build_payload


def test_build_payload_structure_and_placeholder_order():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp India Pvt Ltd",
        "cert_name": "ISO 9001:2015 Quality Management", "cert_id": "ISO-2021-4521",
        "expiry_date": "24-07-2026", "status": "CRITICAL",
    }

    payload = build_payload(record, "919876543210", "cert_renewal_alert", "en_US")

    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "919876543210"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "cert_renewal_alert"
    assert payload["template"]["language"] == {"code": "en_US"}

    assert len(payload["template"]["components"]) == 1

    body_params = payload["template"]["components"][0]["parameters"]
    assert body_params[0] == {"type": "text", "text": "Rahul Sharma"}
    assert body_params[1] == {"type": "text", "text": "TechCorp India Pvt Ltd"}
    assert body_params[2] == {"type": "text", "text": "ISO-2021-4521"}
    assert body_params[3] == {"type": "text", "text": "ISO 9001:2015 Quality Management"}
    assert body_params[4] == {"type": "text", "text": "24 July 2026"}


def test_build_payload_includes_header_image_when_image_id_given():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp India Pvt Ltd",
        "cert_name": "ISO 9001:2015 Quality Management", "cert_id": "ISO-2021-4521",
        "expiry_date": "24-07-2026", "status": "CRITICAL",
    }

    payload = build_payload(record, "919876543210", "cert_renewal_alert", "en_US", "1791756442005243")

    components = payload["template"]["components"]
    assert len(components) == 2
    assert components[0] == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "1791756442005243"}}],
    }
    assert components[1]["type"] == "body"


from unittest.mock import patch, Mock
import requests
from whatsapp_renewal_alerts import send_message


def test_send_message_success():
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"messages": [{"id": "wamid.ABC"}]}
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response) as mock_post:
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is True
    assert info == {"message_id": "wamid.ABC"}
    mock_post.assert_called_once()
    called_url = mock_post.call_args.args[0]
    assert called_url == "https://graph.facebook.com/v23.0/pid123/messages"


def test_send_message_api_error():
    mock_response = Mock(status_code=400)
    mock_response.json.return_value = {"error": {"message": "Invalid parameter"}}
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is False
    assert info == {"error": "Invalid parameter"}


def test_send_message_network_error():
    with patch("whatsapp_renewal_alerts.requests.post", side_effect=requests.exceptions.ConnectionError("boom")):
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is False
    assert "boom" in info["error"]


def test_send_message_success_status_with_malformed_body_returns_failure():
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {}
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        ok, info = send_message({"to": "919876543210"}, "tok", "pid123")

    assert ok is False
    assert info == {"error": "Invalid response structure from API"}


from whatsapp_renewal_alerts import run

ONE_CRITICAL_ROW = [
    ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
     "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
     "https://x/renew?id=ISO-1", "CRITICAL"],
]


def test_run_dry_run_makes_no_calls_and_no_log_writes(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, ONE_CRITICAL_ROW)
    send_fn = Mock()

    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )

    assert len(results) == 1
    assert results[0]["action"] == "dry_run"
    send_fn.assert_not_called()
    assert load_sent_log(db_path) == {}


def test_run_dry_run_honors_dedup_log_for_already_sent_client(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Already Sent", "Co1", "a@x.com", "919111111111",
         "Cert1", "ISI", "C-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-1", "CRITICAL"],
        ["CLT002", "Not Sent Yet", "Co2", "b@x.com", "919222222222",
         "Cert2", "ISI", "C-2", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-2", "URGENT"],
    ])
    save_sent_log(db_path, {"CLT001|CRITICAL|2026-07-17": {
        "message_id": "wamid.OLD", "phone": "919111111111", "sent_at": "2026-07-16T10:00:00",
    }})
    send_fn = Mock()

    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )

    assert results[0]["action"] == "skipped_duplicate"
    assert results[1]["action"] == "dry_run"
    send_fn.assert_not_called()


def test_run_live_sends_and_dedups_on_second_call(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, ONE_CRITICAL_ROW)
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    first = run(db_path=db_path, token="tok", phone_number_id="pid",
                today="2026-07-17", send_fn=send_fn)
    assert first[0]["action"] == "sent"
    assert send_fn.call_count == 1
    assert "CLT001|CRITICAL|2026-07-17" in load_sent_log(db_path)

    second = run(db_path=db_path, token="tok", phone_number_id="pid",
                 today="2026-07-17", send_fn=send_fn)
    assert second[0]["action"] == "skipped_duplicate"
    assert send_fn.call_count == 1


def test_run_test_number_overrides_phone_and_skips_log_write(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, ONE_CRITICAL_ROW)
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  test_number="+919999999999", today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    assert load_sent_log(db_path) == {}


def test_run_failed_send_does_not_write_log(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, ONE_CRITICAL_ROW)
    send_fn = Mock(return_value=(False, {"error": "Invalid parameter"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "failed"
    assert results[0]["error"] == "Invalid parameter"
    assert load_sent_log(db_path) == {}


def test_run_mixed_outcomes_in_single_call_preserves_earlier_successes(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Already Sent", "Co1", "a@x.com", "919111111111",
         "Cert1", "ISI", "C-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-1", "CRITICAL"],
        ["CLT002", "New Success", "Co2", "b@x.com", "919222222222",
         "Cert2", "ISI", "C-2", "01-01-2025", "24-07-2026",
         "https://x/renew?id=C-2", "URGENT"],
        ["CLT003", "Bad Date", "Co3", "c@x.com", "919333333333",
         "Cert3", "ISI", "C-3", "01-01-2025", "not-a-date",
         "https://x/renew?id=C-3", "DUE SOON"],
    ])
    save_sent_log(db_path, {"CLT001|CRITICAL|2026-07-17": {
        "message_id": "wamid.OLD", "phone": "919111111111", "sent_at": "2026-07-16T10:00:00",
    }})
    send_fn = Mock(return_value=(True, {"message_id": "wamid.NEW"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "skipped_duplicate"
    assert results[1]["action"] == "sent"
    assert results[2]["action"] == "failed"
    assert send_fn.call_count == 1

    saved = load_sent_log(db_path)
    assert "CLT001|CRITICAL|2026-07-17" in saved
    assert "CLT002|URGENT|2026-07-17" in saved


def test_run_filters_by_cert_type(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn, cert_type=["OSHA"])

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"


def test_run_filters_by_search(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn, search="BuildRight")

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"


def test_run_filters_by_scheme(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=FMCS-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn, scheme="FMCS")

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"


def test_run_calls_on_progress_for_each_record(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))
    progress_calls = []

    run(
        db_path=db_path, token="tok", phone_number_id="pid",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )

    assert progress_calls == [("sent", 2), ("sent", 2)]


def test_run_survives_raising_on_progress_and_still_persists_sent_log(tmp_path, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    def flaky_on_progress(result, total):
        raise RuntimeError("boom: broken progress callback")

    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        today="2026-07-17", send_fn=send_fn,
        on_progress=flaky_on_progress,
    )

    assert len(results) == 2
    assert [r["action"] for r in results] == ["sent", "sent"]
    assert send_fn.call_count == 2

    saved = load_sent_log(db_path)
    assert "CLT001|CRITICAL|2026-07-17" in saved
    assert "CLT002|URGENT|2026-07-17" in saved


from whatsapp_renewal_alerts import send_one_alert


def test_send_one_alert_success_updates_log_in_place():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return True, {"message_id": "wamid.ABC"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "sent", "to": "919876543210", "message_id": "wamid.ABC",
    }
    assert "CLT001|CRITICAL|2026-07-18" in sent_log
    assert sent_log["CLT001|CRITICAL|2026-07-18"]["message_id"] == "wamid.ABC"


def test_send_one_alert_skips_when_already_in_log():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.OLD"}}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called when already sent")

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "skipped_duplicate", "to": "919876543210",
    }


def test_send_one_alert_skips_reminder_before_interval_elapses():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|CRITICAL|2026-07-01": {"message_id": "wamid.OLD"}}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called before the interval elapses")

    result = send_one_alert(
        record, sent_log, "2026-07-20", "tok", "pid123", send_fn=fake_send,
    )  # 19 days after the last send for this same status

    assert result["action"] == "skipped_duplicate"


def test_send_one_alert_sends_reminder_once_interval_elapses():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|CRITICAL|2026-07-01": {"message_id": "wamid.OLD"}}
    send_fn = Mock(return_value=(True, {"message_id": "wamid.NEW"}))

    result = send_one_alert(
        record, sent_log, "2026-07-21", "tok", "pid123", send_fn=send_fn,
    )  # 20 days after the last send for this same status

    assert result["action"] == "sent"
    send_fn.assert_called_once()


def test_send_one_alert_sends_immediately_on_status_change():
    """A very recent send under a different status (DUE SOON) must not
    block a send for this record's status (CRITICAL) -- the reminder
    interval is scoped per client+status, not per client."""
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|DUE SOON|2026-07-16": {"message_id": "wamid.OLD"}}
    send_fn = Mock(return_value=(True, {"message_id": "wamid.NEW"}))

    result = send_one_alert(
        record, sent_log, "2026-07-17", "tok", "pid123", send_fn=send_fn,
    )  # 1 day after a DUE SOON send, but this record's status is CRITICAL

    assert result["action"] == "sent"
    send_fn.assert_called_once()


def test_send_one_alert_uses_override_phone_and_reports_failure():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return False, {"error": "Invalid parameter"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        to_phone_override="919000000000", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "failed", "to": "919000000000", "error": "Invalid parameter",
    }
    assert sent_log == {}


def test_run_resolves_template_per_record_in_mixed_scheme_batch(tmp_path, monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_CRS", "crs_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_CRS", "en")
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=CRS-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)

    assert [r["action"] for r in results] == ["sent", "sent"]
    isi_payload, crs_payload = (call.args[0] for call in send_fn.call_args_list)
    assert isi_payload["template"]["name"] == "cert_renewal_alert"
    assert crs_payload["template"]["name"] == "crs_renewal_alert"


def test_run_skips_records_when_scheme_has_no_configured_template(tmp_path, monkeypatch, mongo_db):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=CRS-1", "URGENT"],
    ])
    send_fn = Mock()

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()
    assert load_sent_log(db_path) == {}


def test_send_one_alert_skips_when_scheme_has_no_configured_template(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)
    record = {
        "client_id": "CLT002", "name": "Priya Mehta", "company": "BuildRight",
        "cert_name": "CRS-Cert", "cert_id": "CRS-1", "scheme": "CRS",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919812345678",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called when scheme has no configured template")

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT002", "name": "Priya Mehta", "status": "CRITICAL",
        "action": "skipped_no_template", "to": "919812345678",
    }


from whatsapp_renewal_alerts import parse_args


def test_parse_args_defaults():
    args = parse_args([])
    assert args.dry_run is False
    assert args.test_number is None


def test_parse_args_dry_run_and_test_number():
    args = parse_args(["--dry-run", "--test-number", "919999999999"])
    assert args.dry_run is True
    assert args.test_number == "919999999999"


from whatsapp_renewal_alerts import format_result_line, append_text_log


def test_format_result_line_sent():
    result = {"action": "sent", "client_id": "CLT001", "name": "Rahul Sharma",
              "status": "CRITICAL", "message_id": "wamid.ABC"}
    assert format_result_line(result) == "✅ SENT | CLT001 Rahul Sharma | CRITICAL | msg_id=wamid.ABC"


def test_format_result_line_failed():
    result = {"action": "failed", "client_id": "CLT001", "name": "Rahul Sharma",
              "status": "CRITICAL", "error": "Invalid parameter"}
    assert format_result_line(result) == "❌ FAIL | CLT001 Rahul Sharma | CRITICAL | Invalid parameter"


def test_format_result_line_skipped():
    result = {"action": "skipped_duplicate", "client_id": "CLT001",
              "name": "Rahul Sharma", "status": "CRITICAL"}
    assert format_result_line(result) == "⏭ SKIP | CLT001 Rahul Sharma | CRITICAL"


def test_format_result_line_skipped_no_template():
    result = {"action": "skipped_no_template", "client_id": "CLT001",
              "name": "Rahul Sharma", "status": "CRITICAL"}
    assert format_result_line(result) == "⏭ SKIP (no template) | CLT001 Rahul Sharma | CRITICAL"


def test_append_text_log_writes_lines(tmp_path):
    log_path = tmp_path / "log.txt"
    append_text_log(log_path, ["✅ SENT | CLT001 Rahul Sharma | CRITICAL | msg_id=wamid.ABC"])
    content = log_path.read_text(encoding="utf-8")
    assert "✅ SENT | CLT001 Rahul Sharma | CRITICAL | msg_id=wamid.ABC" in content


def test_format_result_line_dry_run():
    payload = {
        "template": {
            "components": [
                {"type": "body", "parameters": [
                    {"type": "text", "text": "Rahul Sharma"},
                    {"type": "text", "text": "TechCorp India Pvt Ltd"},
                    {"type": "text", "text": "ISO-2021-4521"},
                    {"type": "text", "text": "ISO 9001:2015 Quality Management"},
                    {"type": "text", "text": "24 July 2026"},
                ]},
            ]
        }
    }
    result = {"action": "dry_run", "client_id": "CLT001", "name": "Rahul Sharma",
              "status": "CRITICAL", "to": "919876543210", "payload": payload}
    line = format_result_line(result)
    assert line == (
        "🧪 DRY-RUN | CLT001 Rahul Sharma | CRITICAL | to=919876543210 | "
        "body=[Rahul Sharma | TechCorp India Pvt Ltd | ISO-2021-4521 | "
        "ISO 9001:2015 Quality Management | 24 July 2026]"
    )
