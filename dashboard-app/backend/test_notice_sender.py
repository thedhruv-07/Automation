"""Tests for notice_sender.py's send orchestration."""
from unittest.mock import Mock, patch

from db import upsert_clients, record_notice_sent
from notice_sender import send_notice_whatsapp, send_notice_email

CRS_ROW = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
           "OSHA", "CRS", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
CRS_ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                     "ISO 9001", "CRS", "ISO-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")


def test_send_notice_whatsapp_skips_when_no_template_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", raising=False)
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock()

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()


def test_send_notice_whatsapp_sends_and_records_permanently(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "sent"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp") is True


def test_send_notice_whatsapp_skips_client_already_sent_to(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.OLD", "2026-07-20T10:00:00")
    send_fn = Mock()

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_notice_whatsapp_test_number_does_not_persist_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.TEST"}))

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid",
        send_fn=send_fn, scheme="CRS", test_number="919999999999",
    )

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp") is False


def test_send_notice_email_skips_when_no_email_on_file(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW_NO_EMAIL], mode="replace")
    send_fn = Mock()

    results = send_notice_email(
        db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_notice_email_sends_and_records_permanently(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = send_notice_email(
        db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "sent"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "email") is True


def test_send_notice_email_skips_client_already_sent_to(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "email", "brevo-old", "2026-07-20T10:00:00")
    send_fn = Mock()

    results = send_notice_email(
        db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_notice_email_uses_the_notice_module_content(tmp_path):
    """Proves the email actually sent is the notice's own content (subject,
    URL), not the renewal-alert template -- the whole point of this feature
    is that a notice isn't about anyone's own certificate."""
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_notice_email(
            db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
            scheme="CRS",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == "Important: BIS Transition Facilitation Order, 2026 — What It Means for You"
    assert "transition-facilitation-quality-control-order-2026" in payload["htmlContent"]


def test_send_notice_whatsapp_raises_for_unknown_notice_id(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")

    import pytest
    with pytest.raises(ValueError):
        send_notice_whatsapp(db_path, "does_not_exist", "tok", "pid")
