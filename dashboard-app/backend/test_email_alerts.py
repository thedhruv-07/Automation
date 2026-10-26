"""Tests for email_alerts.py."""
from unittest.mock import Mock, patch

import requests

from db import upsert_clients, save_email_sent_log
from email_alerts import send_one_email_alert, run_email_alerts, send_email_via_brevo, post_email_via_brevo

ROW_WITH_EMAIL = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
                    "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                 "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
ROW_INVALID_EMAIL = ("CLT003", "Amit Verma", "HealthFirst", "not-an-email", "919800000000",
                       "ISO 9001", "ISI", "ISO27-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON")
ROW_FMCS = ("CLT005", "Li Wei", "Lotte Chemical Titan", "l@x.com", None,
             "IS 7328 : 2020", "FMCS", "4100106459", None, "03-11-2026", "https://x", "URGENT",
             "Polyethylene Moulding & Extrusion Material")


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


def test_send_one_email_alert_skips_reminder_before_interval_elapses():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {"CLT001|CRITICAL|2026-07-01": {"sent_at": "x", "message_id": "y", "email": "r@x.com"}}
    send_fn = Mock()

    result = send_one_email_alert(
        record, sent_log, "2026-07-20", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )  # 19 days after the last send for this same status

    assert result["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_one_email_alert_sends_reminder_once_interval_elapses():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {"CLT001|CRITICAL|2026-07-01": {"sent_at": "x", "message_id": "y", "email": "r@x.com"}}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-2"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-21", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )  # 20 days after the last send for this same status

    assert result["action"] == "sent"
    send_fn.assert_called_once()


def test_send_one_email_alert_sends_immediately_on_status_change():
    """ROW_WITH_EMAIL is status CRITICAL; a very recent send under a
    different status (DUE SOON) must not block it -- the reminder interval
    is scoped per client+status, not per client."""
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {"CLT001|DUE SOON|2026-07-16": {"sent_at": "x", "message_id": "y", "email": "r@x.com"}}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-3"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn,
    )  # 1 day after a DUE SOON send, but this record's status is CRITICAL

    assert result["action"] == "sent"
    send_fn.assert_called_once()


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

    assert send_fn.call_args.kwargs["to_email"] == "test-inbox@x.com"


def test_run_email_alerts_processes_all_alert_eligible_clients(tmp_path, mongo_db):
    db_path = mongo_db
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


def test_run_email_alerts_only_persists_new_entries_not_the_whole_history(tmp_path, mongo_db):
    """save_email_sent_log previously received the FULL loaded sent_log
    (every historical entry, loaded by load_email_sent_log) and rewrote
    every single one via a separate record_email_sent() round-trip per
    entry -- harmless when the log was small, but as it grows over months
    of real daily sends, every bulk-send job gets slower, eventually taking
    long enough to look like a hung job (this is what was actually
    happening in production, not a true hang). It must only persist the
    entries this run actually added."""
    from db import record_email_sent
    db_path = mongo_db
    # A large-ish pre-existing history unrelated to this run's client --
    # rewriting these on every save is exactly the bug being fixed.
    for i in range(50):
        record_email_sent(db_path, f"OLD{i:03d}", "CRITICAL", "2026-01-01", "m", "x@x.com", "2026-01-01T09:00:00")
    upsert_clients(db_path, [ROW_WITH_EMAIL], mode="merge")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    with patch("email_alerts.save_email_sent_log") as mock_save:
        run_email_alerts(db_path, "api-key", "sender@x.com", "Absolute Veritas", today="2026-07-17", send_fn=send_fn)

    mock_save.assert_called_once()
    saved_log = mock_save.call_args.args[1]
    assert list(saved_log.keys()) == ["CLT001|CRITICAL|2026-07-17"]


def test_run_email_alerts_stops_after_limit_sends(tmp_path, mongo_db):
    row2 = ("CLT004", "Sana Iqbal", "GreenBuild", "s@x.com", "919800000001",
            "ISO 9001", "ISI", "ISO-2", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
    db_path = mongo_db
    upsert_clients(db_path, [ROW_WITH_EMAIL, row2], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn, limit=1,
    )

    assert len(results) == 1
    assert results[0]["action"] == "sent"
    assert send_fn.call_count == 1


def test_run_email_alerts_filters_by_cert_type(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [ROW_WITH_EMAIL, ROW_NO_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn, cert_type=["OSHA"],
    )

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"
    assert results[0]["action"] == "skipped_no_email"  # ROW_NO_EMAIL has no email on file


def test_run_email_alerts_filters_by_search(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [ROW_WITH_EMAIL, ROW_NO_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn, search="BuildRight",
    )

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT002"
    assert results[0]["action"] == "skipped_no_email"  # ROW_NO_EMAIL has no email on file


def test_run_email_alerts_filters_by_scheme(tmp_path, mongo_db):
    db_path = mongo_db
    fmcs_row = ("CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
                "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
    upsert_clients(db_path, [ROW_WITH_EMAIL, fmcs_row], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn, scheme="FMCS",
    )

    assert len(results) == 1
    assert results[0]["client_id"] == "CLT004"


def test_send_email_via_brevo_success():
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        ok, info = send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    assert ok is True
    assert info == {"message_id": "brevo-msg-1"}
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://api.brevo.com/v3/smtp/email"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["to"] == [{"email": "r@x.com", "name": "Rahul Sharma"}]
    # ISI has its own dedicated subject/layout (see scheme_html_overrides) --
    # this fixture's scheme is ISI, so it gets the BIS-specific subject, not
    # the generic "Renew {cert_name} — {company}" template.
    assert payload["subject"] == "Absolute Veritas — BIS ISI Licence Renewal — TechCorp — ISO-1 — Expiry 24 July 2026"


def test_send_email_via_brevo_splits_multiple_semicolon_joined_addresses():
    """Many FMCS prospect records carry a source email field like
    "a@x.com;b@x.com" (a primary + backup inbox) -- Brevo's API rejects
    that whole string as a single invalid "to" address ("email is not
    valid in to"), which was silently failing most of a real campaign.
    Each address must become its own recipient entry."""
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(
            record, "api-key", "sender@x.com", "Absolute Veritas",
            to_email="primary@x.com;backup@x.com",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["to"] == [
        {"email": "primary@x.com", "name": "Rahul Sharma"},
        {"email": "backup@x.com", "name": "Rahul Sharma"},
    ]


def test_send_email_via_brevo_splits_comma_joined_addresses_and_trims_whitespace():
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(
            record, "api-key", "sender@x.com", "Absolute Veritas",
            to_email=" primary@x.com , backup@x.com ",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["to"] == [
        {"email": "primary@x.com", "name": "Rahul Sharma"},
        {"email": "backup@x.com", "name": "Rahul Sharma"},
    ]


def test_send_email_via_brevo_includes_whatsapp_qr_when_present(tmp_path):
    record = _record_dict(ROW_WITH_EMAIL)
    qr_path = tmp_path / "whatsapp-qr.png"
    qr_path.write_bytes(b"fake-png-bytes")
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.QR_PATH", qr_path), \
         patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert 'src="https://automation-q3hp.onrender.com/whatsapp-qr.png"' in html
    assert "WHATSAPP" in html
    assert "WECHAT" not in html
    assert html.index("Book an Appointment") < html.index("whatsapp-qr.png")


def test_send_email_via_brevo_omits_qr_section_when_missing(tmp_path):
    record = _record_dict(ROW_WITH_EMAIL)
    missing_qr = tmp_path / "no-such-qr.png"
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.QR_PATH", missing_qr), \
         patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert "whatsapp-qr.png" not in html
    assert "WECHAT" not in html


def test_send_email_via_brevo_isi_uses_bis_specific_layout():
    """ISI clients get the BIS-specific Certification Details table
    (Manufacturer, Product Certification, Indian Standard, BIS Licence No.,
    Current Validity), the "Proceed with Renewal" CTA label, the "BIS
    License Expiry date:" label, and the full signature block -- not the
    generic 2-row table/plain contact line other schemes get."""
    record = _record_dict(ROW_WITH_EMAIL)  # scheme="ISI", cert_name="ISO 9001", cert_id="ISO-1"
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert "Manufacturer</td>" in html
    assert "Company / Manufacturer" not in html
    assert "TechCorp" in html
    assert "Product Certification</td>" in html
    assert "Indian Standard</td>" in html
    assert "ISO 9001" in html
    assert "BIS Licence No.</td>" in html
    assert "ISO-1" in html
    assert "ISI Certification" in html
    assert "Upto <span" in html
    assert "Proceed with Renewal" in html
    assert "BIS License Expiry date:" in html
    assert "Inspection, Testing &amp; Certifications" in html
    assert "www.absoluteveritas.com" in html
    assert "Certificate ID</td>" not in html
    assert 'href="https://absoluteveritas.com/bis-isi-renewal-and-amc-services-2026/"' in html
    assert "For more info" in html


def test_send_email_via_brevo_fmcs_uses_bis_specific_layout_and_subject():
    """FMCS clients get the dedicated Manufacturer/Certificate Number/Indian
    Standard Number/Name of Product table and the FMCS-specific subject line
    -- not the generic 2-row Certification/Certificate ID table."""
    record = _record_dict(ROW_FMCS)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="l@x.com")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == (
        "India BIS FMCS Certification Renewal | Lotte Chemical Titan | "
        "CM/L-4100106459 | Expiry: 03 November 2026 | Absolute Veritas"
    )
    html = payload["htmlContent"]
    assert "Name of Manufacturer</td>" in html
    assert "M/s Lotte Chemical Titan" in html
    assert "Certificate Number</td>" in html
    assert "4100106459" in html
    assert "Indian Standard Number</td>" in html
    assert "IS 7328 : 2020" in html
    assert "Name of Product</td>" in html
    assert "Polyethylene Moulding &amp; Extrusion Material" in html or "Polyethylene Moulding & Extrusion Material" in html
    assert "Certification</td>" not in html
    assert "Certificate ID</td>" not in html


def test_send_email_via_brevo_fmcs_includes_more_info_link_and_signature_block():
    record = _record_dict(ROW_FMCS)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="l@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert 'href="https://absoluteveritas.com/foreign-manufacturer-certification-services/"' in html
    assert "For more info" in html
    assert "Testing, Inspection &amp; Certifications" in html
    assert "Mobile/Whatsapp: +91-7303215033" in html
    assert "Tel: +91-129-4001010" in html
    assert "Email: cs@absoluteveritas.com" in html
    assert "Website: https://absoluteveritas.com/" in html
    # signature_html replaces the plain org_email contact line, same as ISI
    assert html.count("cs@absoluteveritas.com") == 1


def test_send_email_via_brevo_fmcs_shows_placeholder_when_product_name_missing():
    """Older FMCS rows imported before the Product Name field existed have
    no value for it -- the email should show a placeholder dash, not crash
    or render a blank/None cell."""
    row_without_product = ROW_FMCS[:12]  # no 13th (Product Name) element
    record = _record_dict(row_without_product)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="l@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert "Name of Product</td>" in html
    assert ">—</td>" in html  # placeholder dash, not "None"
    assert ">None<" not in html


def test_send_email_via_brevo_isi_colors_current_validity_red_when_expired():
    """ROW_WITH_EMAIL expires 24-07-2026, already in the past relative to
    today -- the "Current Validity" row's date must be colored red."""
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert '<span style="color:#d03b3b;">24 July 2026</span>' in html


def test_send_email_via_brevo_non_isi_scheme_keeps_generic_layout():
    crs_row = ("CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
               "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
    record = _record_dict(crs_row)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-2"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="d@x.com")

    html = mock_post.call_args.kwargs["json"]["htmlContent"]
    assert "Certificate ID</td>" in html
    assert "Proceed with Renewal" not in html
    assert "Inspection, Testing" not in html


def test_send_email_via_brevo_uses_scheme_specific_subject_and_intro(monkeypatch):
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal: {cert_name}")
    monkeypatch.setenv("EMAIL_INTRO_TEXT_CRS", "Your CRS registration for <strong>{company}</strong> needs renewal.")
    crs_row = ("CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
               "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
    record = _record_dict(crs_row)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-2"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="d@x.com")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == "Registration renewal: CRS-Cert"
    assert "Your CRS registration for <strong>M/s FreshFoods</strong> needs renewal." in payload["htmlContent"]


def test_send_email_via_brevo_api_error():
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=400)
    mock_response.json.return_value = {"message": "Invalid sender email"}

    with patch("email_alerts.requests.post", return_value=mock_response):
        ok, info = send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    assert ok is False
    assert info == {"error": "Invalid sender email"}


def test_send_email_via_brevo_network_error():
    record = _record_dict(ROW_WITH_EMAIL)

    with patch("email_alerts.requests.post", side_effect=requests.exceptions.ConnectionError("boom")):
        ok, info = send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    assert ok is False
    assert "boom" in info["error"]


def test_post_email_via_brevo_success():
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-9"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        ok, info = post_email_via_brevo({"subject": "Test"}, "api-key")

    assert ok is True
    assert info == {"message_id": "brevo-msg-9"}
    mock_post.assert_called_once()


def test_send_email_via_brevo_success_status_with_malformed_body_still_reports_sent():
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=200)
    mock_response.json.side_effect = ValueError("not JSON")

    with patch("email_alerts.requests.post", return_value=mock_response):
        ok, info = send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    assert ok is True
    assert info == {"message_id": None}


def test_send_email_via_brevo_never_sends_a_separate_logo_attachment(tmp_path):
    """Brevo's transactional API doesn't support inline CID images -- its
    `attachment` field only produces a real, visible/downloadable attachment
    with no rendering in the body -- so the logo must never be sent via
    `attachment` at all, regardless of whether the logo file exists."""
    record = _record_dict(ROW_WITH_EMAIL)
    logo_path = tmp_path / "company-logo.png"
    logo_path.write_bytes(b"fake-png-bytes")
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.LOGO_PATH", logo_path), \
         patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    payload = mock_post.call_args.kwargs["json"]
    assert "attachment" not in payload


def test_send_email_via_brevo_never_includes_a_logo_image(tmp_path):
    """The email is plain text-style now (see build_email_html's rewrite) --
    no logo image is sent regardless of whether the logo file exists,
    matching feedback that renewal emails should read like plain email
    text, not a designed graphic."""
    record = _record_dict(ROW_WITH_EMAIL)
    logo_path = tmp_path / "company-logo.png"
    logo_path.write_bytes(b"fake-png-bytes")
    missing_qr = tmp_path / "no-such-qr.png"
    mock_response = Mock(status_code=200)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.LOGO_PATH", logo_path), \
         patch("email_alerts.QR_PATH", missing_qr), \
         patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    payload = mock_post.call_args.kwargs["json"]
    assert "company-logo.png" not in payload["htmlContent"]
    assert "<img" not in payload["htmlContent"]


def test_run_email_alerts_calls_on_progress_for_each_record(tmp_path, mongo_db):
    db_path = mongo_db
    upsert_clients(db_path, [ROW_WITH_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))
    progress_calls = []

    run_email_alerts(
        db_path, "api-key", "sender@x.com", "Absolute Veritas",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )

    assert progress_calls == [("sent", 1)]


from email_alerts import run_followups, send_followup_via_brevo
from db import record_email_sent, get_followup_eligible_clients, count_followups_sent_today


def test_send_followup_via_brevo_uses_follow_up_subject_and_wording():
    record = _record_dict(ROW_WITH_EMAIL)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-fu-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        ok, info = send_followup_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="r@x.com")

    assert ok is True
    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == "Follow-up: Absolute Veritas — BIS ISI Licence Renewal — TechCorp — ISO-1 — Expiry 24 July 2026"
    assert "follow-up" in payload["htmlContent"].lower()


def _seed_emailed(mongo_db, rows, emailed):
    upsert_clients(mongo_db, rows, mode="replace")
    for cid, status, date in emailed:
        record_email_sent(mongo_db, cid, status, date, "m", "x@x.com", f"{date}T10:00:00")


def test_run_followups_sends_and_records_each_eligible_client(mongo_db):
    _seed_emailed(mongo_db, [ROW_WITH_EMAIL], [("CLT001", "CRITICAL", "2026-07-10")])
    send_fn = Mock(return_value=(True, {"message_id": "fu-1"}))

    results = run_followups(mongo_db, "api-key", "sender@x.com", "Absolute Veritas", today="2026-07-21", send_fn=send_fn)

    assert [r["action"] for r in results] == ["sent"]
    send_fn.assert_called_once()
    assert count_followups_sent_today(mongo_db, "2026-07-21") == 1
    assert get_followup_eligible_clients(mongo_db, "2026-07-21") == []


def test_run_followups_uses_fmcs_sender_for_fmcs_clients_only(mongo_db):
    """fmcs_sender routes an FMCS follow-up's "from" address separately
    from everyone else's, by the record's OWN scheme -- same pattern as
    run_email_alerts' per-record fmcs_credentials dispatch."""
    _seed_emailed(
        mongo_db, [ROW_WITH_EMAIL, ROW_FMCS],
        [("CLT001", "CRITICAL", "2026-07-10"), ("CLT005", "URGENT", "2026-07-10")],
    )
    send_fn = Mock(return_value=(True, {"message_id": "fu-1"}))

    results = run_followups(
        mongo_db, "api-key", "main@x.com", "Absolute Veritas", today="2026-07-21", send_fn=send_fn,
        fmcs_sender="marketing@absoluteveritas.com",
    )

    assert {r["client_id"]: r["action"] for r in results} == {"CLT001": "sent", "CLT005": "sent"}
    senders_by_client = {c.args[0]["client_id"]: c.args[2] for c in send_fn.call_args_list}
    assert senders_by_client == {"CLT001": "main@x.com", "CLT005": "marketing@absoluteveritas.com"}


def test_run_followups_skips_clients_without_a_valid_email(mongo_db):
    _seed_emailed(mongo_db, [ROW_NO_EMAIL], [("CLT002", "URGENT", "2026-07-10")])
    send_fn = Mock()

    results = run_followups(mongo_db, "api-key", "sender@x.com", "Absolute Veritas", today="2026-07-21", send_fn=send_fn)

    assert [r["action"] for r in results] == ["skipped_no_email"]
    send_fn.assert_not_called()
    assert count_followups_sent_today(mongo_db, "2026-07-21") == 0


def test_run_followups_failed_send_is_not_recorded_so_it_can_be_retried(mongo_db):
    _seed_emailed(mongo_db, [ROW_WITH_EMAIL], [("CLT001", "CRITICAL", "2026-07-10")])
    send_fn = Mock(return_value=(False, {"error": "boom"}))

    results = run_followups(mongo_db, "api-key", "sender@x.com", "Absolute Veritas", today="2026-07-21", send_fn=send_fn)

    assert [r["action"] for r in results] == ["failed"]
    assert results[0]["error"] == "boom"
    assert len(get_followup_eligible_clients(mongo_db, "2026-07-21")) == 1


def test_run_followups_stops_at_the_limit(mongo_db):
    row_b = ("CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
             "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
    _seed_emailed(mongo_db, [ROW_WITH_EMAIL, row_b],
                  [("CLT001", "CRITICAL", "2026-07-10"), ("CLT004", "URGENT", "2026-07-10")])
    send_fn = Mock(return_value=(True, {"message_id": "fu"}))

    results = run_followups(mongo_db, "api-key", "sender@x.com", "Absolute Veritas",
                            today="2026-07-21", send_fn=send_fn, limit=1)

    assert [r["action"] for r in results] == ["sent"]
    assert send_fn.call_count == 1


def test_run_followups_calls_on_progress_for_each_client(mongo_db):
    _seed_emailed(mongo_db, [ROW_WITH_EMAIL], [("CLT001", "CRITICAL", "2026-07-10")])
    on_progress = Mock()

    run_followups(mongo_db, "api-key", "sender@x.com", "Absolute Veritas", today="2026-07-21",
                  send_fn=Mock(return_value=(True, {"message_id": "fu"})), on_progress=on_progress)

    on_progress.assert_called_once()
    assert on_progress.call_args.args[1] == 1


def test_run_followups_with_test_email_redirects_and_does_not_record(mongo_db):
    _seed_emailed(mongo_db, [ROW_WITH_EMAIL], [("CLT001", "CRITICAL", "2026-07-10")])
    send_fn = Mock(return_value=(True, {"message_id": "fu"}))

    results = run_followups(mongo_db, "api-key", "sender@x.com", "Absolute Veritas", today="2026-07-21",
                            send_fn=send_fn, test_email="me@x.com")

    assert send_fn.call_args.kwargs["to_email"] == "me@x.com"
    assert results[0]["to"] == "me@x.com"
    assert count_followups_sent_today(mongo_db, "2026-07-21") == 0


def test_send_one_email_alert_tags_sent_log_entry_with_account():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    result = send_one_email_alert(
        record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, account="followup",
    )

    assert result["action"] == "sent"
    key = "CLT001|CRITICAL|2026-07-17"
    assert sent_log[key]["account"] == "followup"


def test_send_one_email_alert_defaults_account_to_main():
    record = _record_dict(ROW_WITH_EMAIL)
    sent_log = {}
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    send_one_email_alert(record, sent_log, "2026-07-17", "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn)

    assert sent_log["CLT001|CRITICAL|2026-07-17"]["account"] == "main"


def test_run_email_alerts_persists_the_given_account_tag(mongo_db):
    upsert_clients(mongo_db, [ROW_WITH_EMAIL], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    run_email_alerts(mongo_db, "api-key", "sender@x.com", "Absolute Veritas", send_fn=send_fn, account="followup")

    from db import count_overflow_sent_today, count_emails_sent_today
    today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    assert count_overflow_sent_today(mongo_db, today) == 1
    assert count_emails_sent_today(mongo_db, today) == 0
