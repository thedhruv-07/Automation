import base64
from unittest.mock import patch

import pytest

import cert_automation


def make_rec(**overrides):
    rec = {
        "client_id": "CLT001",
        "name": "Rahul Sharma",
        "company": "TechCorp",
        "email": "rahul@techcorp.com",
        "cert_name": "ISO 9001",
        "cert_id": "ISO-1",
        "days_left": 5,
        "expiry_formatted": "24 July 2026",
        "renewal_link": "https://example.com/renew",
    }
    rec.update(overrides)
    return rec


def test_send_email_real_success_with_no_logo(tmp_path, monkeypatch):
    monkeypatch.setitem(cert_automation.CONFIG, "EMAIL_SENDER", "sender@absoluteveritas.com")
    monkeypatch.setitem(cert_automation.CONFIG, "BREVO_API_KEY", "test-api-key")
    monkeypatch.setattr(cert_automation, "LOGO_PATH", tmp_path / "no-logo-here.png")

    mock_response = type("Resp", (), {"status_code": 201, "text": "ok"})()
    with patch("cert_automation.requests.post", return_value=mock_response) as mock_post:
        cert_automation.send_email_real(make_rec(), "<html>body</html>")

    assert mock_post.call_args.args[0] == "https://api.brevo.com/v3/smtp/email"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["sender"]["email"] == "sender@absoluteveritas.com"
    assert payload["to"] == [{"email": "rahul@techcorp.com", "name": "Rahul Sharma"}]
    assert payload["subject"] == "[Action Required] Renew ISO 9001 — TechCorp"
    assert payload["htmlContent"] == "<html>body</html>"
    assert payload["attachment"] == []

    headers = mock_post.call_args.kwargs["headers"]
    assert headers["api-key"] == "test-api-key"


def test_send_email_real_attaches_only_logo_when_present(tmp_path, monkeypatch):
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(b"fake-logo-bytes")
    monkeypatch.setattr(cert_automation, "LOGO_PATH", logo_path)
    monkeypatch.setitem(cert_automation.CONFIG, "BREVO_API_KEY", "test-api-key")

    mock_response = type("Resp", (), {"status_code": 201, "text": "ok"})()
    with patch("cert_automation.requests.post", return_value=mock_response) as mock_post:
        cert_automation.send_email_real(make_rec(), "<html>body</html>")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["attachment"] == [
        {"name": cert_automation.LOGO_CID, "content": base64.b64encode(b"fake-logo-bytes").decode("ascii")},
    ]


def test_send_email_real_raises_on_api_error(tmp_path, monkeypatch):
    monkeypatch.setattr(cert_automation, "LOGO_PATH", tmp_path / "no-logo-here.png")
    monkeypatch.setitem(cert_automation.CONFIG, "BREVO_API_KEY", "test-api-key")

    mock_response = type("Resp", (), {"status_code": 400, "text": "Invalid sender"})()
    with patch("cert_automation.requests.post", return_value=mock_response):
        with pytest.raises(RuntimeError, match="Invalid sender"):
            cert_automation.send_email_real(make_rec(), "<html>body</html>")
