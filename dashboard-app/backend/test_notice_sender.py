"""Tests for notice_sender.py's send orchestration."""
from unittest.mock import Mock, patch

from db import upsert_clients, record_notice_sent
from notice_sender import send_notice_whatsapp, send_notice_email, send_adhoc_whatsapp_notice

CRS_ROW = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
           "OSHA", "CRS", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
CRS_ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                     "ISO 9001", "CRS", "ISO-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")


def test_send_notice_whatsapp_skips_when_no_template_configured(tmp_path, monkeypatch, mongo_db):
    monkeypatch.delenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", raising=False)
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock()

    results = send_notice_whatsapp(
        db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()


def test_send_notice_whatsapp_sends_and_records_permanently(tmp_path, monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_notice_whatsapp(
        db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "sent"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "meity_series_guidelines_2026", "whatsapp") is True


def test_send_notice_whatsapp_skips_client_already_sent_to(tmp_path, monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    record_notice_sent(db_path, "CLT001", "meity_series_guidelines_2026", "whatsapp", "wamid.OLD", "2026-07-20T10:00:00")
    send_fn = Mock()

    results = send_notice_whatsapp(
        db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_notice_whatsapp_test_number_does_not_persist_dedup(tmp_path, monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.TEST"}))

    results = send_notice_whatsapp(
        db_path, "meity_series_guidelines_2026", "tok", "pid",
        send_fn=send_fn, scheme="CRS", test_number="919999999999",
    )

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "meity_series_guidelines_2026", "whatsapp") is False


def test_send_notice_whatsapp_respects_limit(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    row_b = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
             "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    upsert_clients(db_path, [CRS_ROW, row_b], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_notice_whatsapp(
        db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS", limit=1,
    )

    assert len(results) == 1
    assert send_fn.call_count == 1
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT002", "meity_series_guidelines_2026", "whatsapp") is False


def test_send_notice_whatsapp_paces_between_sends(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    row_b = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
             "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    upsert_clients(db_path, [CRS_ROW, row_b], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    with patch("notice_sender.time.sleep") as mock_sleep:
        send_notice_whatsapp(
            db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS", pace_seconds=1.5,
        )

    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(1.5)


def test_send_notice_email_skips_when_no_email_on_file(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW_NO_EMAIL], mode="replace")
    send_fn = Mock()

    results = send_notice_email(
        db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_notice_email_sends_and_records_permanently(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = send_notice_email(
        db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "sent"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "meity_series_guidelines_2026", "email") is True


def test_send_notice_email_skips_client_already_sent_to(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    record_notice_sent(db_path, "CLT001", "meity_series_guidelines_2026", "email", "brevo-old", "2026-07-20T10:00:00")
    send_fn = Mock()

    results = send_notice_email(
        db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_notice_email_respects_limit_and_leaves_the_rest_unattempted(tmp_path, mongo_db):
    """Brevo's send API returns a normal success response even once the
    account is over its real daily quota -- there's no synchronous
    rejection to detect. limit is the only thing standing between us and
    silently recording hundreds of false "sent" results, so once it's hit
    the remaining eligible clients must be left completely untouched (not
    attempted, not marked sent) rather than attempted and failing."""
    db_path = mongo_db
    row_b = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
             "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    row_c = ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919800000000",
             "OSHA", "CRS", "OSHA-2", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    upsert_clients(db_path, [CRS_ROW, row_b, row_c], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = send_notice_email(
        db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS", limit=1,
    )

    assert len(results) == 1
    assert results[0]["action"] == "sent"
    assert send_fn.call_count == 1
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "meity_series_guidelines_2026", "email") is True
    assert is_notice_already_sent(db_path, "CLT002", "meity_series_guidelines_2026", "email") is False
    assert is_notice_already_sent(db_path, "CLT003", "meity_series_guidelines_2026", "email") is False


def test_send_notice_email_test_send_counts_against_limit(tmp_path, mongo_db):
    """A test-email send still makes a real Brevo API call and consumes
    real quota, so it must count against the limit too."""
    db_path = mongo_db
    row_b = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
             "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    upsert_clients(db_path, [CRS_ROW, row_b], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-test"}))

    results = send_notice_email(
        db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS", limit=1, test_email="test@example.com",
    )

    assert len(results) == 1
    assert send_fn.call_count == 1


def test_send_notice_email_uses_the_notice_module_content(tmp_path, mongo_db):
    """Proves the email actually sent is the notice's own content (subject,
    URL), not the renewal-alert template -- the whole point of this feature
    is that a notice isn't about anyone's own certificate."""
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_notice_email(
            db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
            scheme="CRS",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == "Transitioning your BIS licence to IS/IEC 62368-1:2023"
    assert "is-62368-safety-rules-in-india" in payload["htmlContent"]


def test_send_notice_email_includes_logo_attachment_when_present(tmp_path, mongo_db):
    import base64
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    logo_path = tmp_path / "company-logo.png"
    logo_bytes = b"fake-png-bytes"
    logo_path.write_bytes(logo_bytes)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("notice_sender.LOGO_PATH", logo_path), \
         patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_notice_email(
            db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
            scheme="CRS",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["attachment"] == [
        {"name": "company-logo.png", "content": base64.b64encode(logo_bytes).decode("ascii")}
    ]
    assert 'src="cid:company-logo.png"' in payload["htmlContent"]


def test_send_notice_email_omits_logo_attachment_when_missing(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    missing_logo = tmp_path / "no-such-logo.png"
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("notice_sender.LOGO_PATH", missing_logo), \
         patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_notice_email(
            db_path, "meity_series_guidelines_2026", "api-key", "sender@x.com", "Absolute Veritas",
            scheme="CRS",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert "attachment" not in payload


def test_send_notice_whatsapp_raises_for_unknown_notice_id(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [CRS_ROW], mode="replace")

    import pytest
    with pytest.raises(ValueError):
        send_notice_whatsapp(db_path, "does_not_exist", "tok", "pid")


def _seed_adhoc_recipients(db, notice_id, phones):
    db["adhoc_recipients"].insert_many([
        {"_id": phone, "notice_id": notice_id, "source": "test"} for phone in phones
    ])


def test_send_adhoc_whatsapp_notice_skips_when_no_template_configured(monkeypatch, mongo_db):
    monkeypatch.delenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", raising=False)
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock()

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()


def test_send_adhoc_whatsapp_notice_sends_and_records_permanently(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    assert results[0]["action"] == "sent"
    assert results[0]["phone"] == "919876543210"
    from db import is_notice_already_sent
    assert is_notice_already_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp") is True


def test_send_adhoc_whatsapp_notice_skips_phone_already_sent_to(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    record_notice_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp", "wamid.OLD", "2026-08-01T10:00:00")
    send_fn = Mock()

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_adhoc_whatsapp_notice_builds_payload_with_no_personalization(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    payload = send_fn.call_args[0][0]
    assert payload["template"]["name"] == "independence_day_2026_offer"
    assert "components" not in payload["template"]


def test_send_adhoc_whatsapp_notice_respects_limit(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210", "919812345678", "919800000000"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn, limit=1)

    assert len(results) == 1
    assert send_fn.call_count == 1
    from db import is_notice_already_sent
    remaining_untouched = sum(
        1 for phone in ["919812345678", "919800000000"]
        if is_notice_already_sent(mongo_db, phone, "independence_day_2026", "whatsapp") is False
    )
    assert remaining_untouched == 2


def test_send_adhoc_whatsapp_notice_test_number_does_not_persist_dedup(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.TEST"}))

    results = send_adhoc_whatsapp_notice(
        mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn, test_number="919999999999",
    )

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    from db import is_notice_already_sent
    assert is_notice_already_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp") is False
