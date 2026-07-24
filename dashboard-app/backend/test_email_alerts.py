"""Tests for email_alerts.py."""
from unittest.mock import Mock

from db import upsert_clients, save_email_sent_log
from email_alerts import send_one_email_alert, run_email_alerts

ROW_WITH_EMAIL = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
                    "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                 "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
ROW_INVALID_EMAIL = ("CLT003", "Amit Verma", "HealthFirst", "not-an-email", "919800000000",
                       "ISO 9001", "ISO27-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON")


def _record_dict(row):
    from db import RECORD_FIELDS
    return dict(zip(RECORD_FIELDS, row))


def test_send_one_email_alert_sends_and_updates_log():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "sent"
    assert result["message_id"] == "brevo-1"
    key = "CLT001|CRITICAL|2026-07-17"
    assert key in sent_log
    send_fn.assert_called_once()


def test_send_one_email_alert_skips_duplicate():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {"CLT001|CRITICAL|2026-07-17": {"sent_at": "x", "message_id": "y", "email": "r@x.com"}}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_one_email_alert_skips_when_no_email():
    record = _record_dict(ROW_NO_EMAIL)
    sent_log = {}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_one_email_alert_skips_when_email_missing_at_sign():
    record = _record_dict(ROW_INVALID_EMAIL)
    sent_log = {}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_one_email_alert_reports_failure():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(False, {"error": "Brevo rejected the request"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )

    assert result["action"] == "failed"
    assert result["error"] == "Brevo rejected the request"
    assert sent_log == {}


def test_send_one_email_alert_test_email_override_redirects_recipient():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas",
        to_email_override="test-inbox@x.com", send_fn=send_fn,
    )

    call_kwargs = send_fn.call_args
    assert call_kwargs.kwargs.get("to_email") == "test-inbox@x.com" or "test-inbox@x.com" in call_kwargs.args


def test_run_email_alerts_processes_all_alert_eligible_clients(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_WITH_EMAIL, ROW_NO_EMAIL, ROW_INVALID_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn,
    )

    actions = {r["client_id"]: r["action"] for r in results}
    assert actions["CLT001"] == "sent"
    assert actions["CLT002"] == "skipped_no_email"
    assert actions["CLT003"] == "skipped_no_email"
    assert send_fn.call_count == 1


def test_run_email_alerts_calls_on_progress_for_each_record(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [ROW_WITH_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))
    progress_calls = []

    run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )

    assert progress_calls == [("sent", 1)]
