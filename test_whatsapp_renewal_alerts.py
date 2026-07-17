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


def test_load_sent_log_missing_file_returns_empty_dict(tmp_path):
    assert load_sent_log(tmp_path / "missing.json") == {}


def test_save_and_load_sent_log_round_trip(tmp_path):
    path = tmp_path / "sent_log.json"
    save_sent_log(path, {"CLT001|CRITICAL|2026-07-17": {"message_id": "wamid.ABC"}})
    result = load_sent_log(path)
    assert result == {"CLT001|CRITICAL|2026-07-17": {"message_id": "wamid.ABC"}}


import openpyxl
from whatsapp_renewal_alerts import read_clients, filter_alertable

HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date",
    "Expiry Date", "Renewal Link", "Status",
]


def _write_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_read_clients_and_filter_alertable(tmp_path):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=OSHA-1", "URGENT"],
        ["CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919898765432",
         "GMP", "GMP-1", "01-01-2025", "10-09-2026",
         "https://x/renew?id=GMP-1", "DUE SOON"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026",
         "https://x/renew?id=ISO27-1", "ACTIVE"],
        ["CLT005", "Rajesh Nair", "Logistics Plus", "raj@x.com", "919654321098",
         "HACCP", "HACCP-1", "01-01-2025", "12-07-2026",
         "https://x/renew?id=HACCP-1", "EXPIRED"],
    ])

    records = read_clients(xlsx_path)
    assert len(records) == 5
    assert records[0]["client_id"] == "CLT001"
    assert records[0]["cert_id"] == "ISO-1"
    assert records[0]["status"] == "CRITICAL"

    alertable = filter_alertable(records)
    assert [r["client_id"] for r in alertable] == ["CLT001", "CLT002", "CLT003"]


def test_read_clients_skips_blank_rows(tmp_path):
    xlsx_path = tmp_path / "test.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Name", "Co", "e@x.com", "919876543210", "Cert", "C-1",
         "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        [None, None, None, None, None, None, None, None, None, None, None],
        ["CLT002", "Name2", "Co2", "e2@x.com", "919876543211", "Cert2", "C-2",
         "01-01-2025", "24-07-2026", "https://x", "URGENT"],
    ])
    records = read_clients(xlsx_path)
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

    body_params = payload["template"]["components"][0]["parameters"]
    assert body_params[0] == {"type": "text", "text": "Rahul Sharma"}
    assert body_params[1] == {"type": "text", "text": "TechCorp India Pvt Ltd"}
    assert body_params[2] == {"type": "text", "text": "ISO-2021-4521"}
    assert body_params[3] == {"type": "text", "text": "ISO 9001:2015 Quality Management"}
    assert body_params[4] == {"type": "text", "text": "24 July 2026"}

    button = payload["template"]["components"][1]
    assert button["type"] == "button"
    assert button["sub_type"] == "url"
    assert button["parameters"] == [{"type": "text", "text": "ISO-2021-4521"}]


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
