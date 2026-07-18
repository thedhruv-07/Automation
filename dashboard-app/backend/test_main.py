import json
import openpyxl
import main as main_module
from fastapi.testclient import TestClient
from main import app
from unittest.mock import patch

client = TestClient(app)

HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]


def _write_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_clients_merges_alert_sent_today(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text(json.dumps({"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.ABC"}}))

    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    critical = next(r for r in data if r["client_id"] == "CLT001")
    assert critical["alert_sent_today"] is True

    active = next(r for r in data if r["client_id"] == "CLT004")
    assert active["alert_sent_today"] is None


def test_get_clients_alert_eligible_not_yet_sent(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")

    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    response = client.get("/api/clients")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["alert_sent_today"] is False


def _setup_one_client(tmp_path, monkeypatch, status="CRITICAL"):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", status],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en")
    monkeypatch.delenv("DASHBOARD_TEST_NUMBER", raising=False)
    return log_path


def test_send_alert_success(tmp_path, monkeypatch):
    log_path = _setup_one_client(tmp_path, monkeypatch)
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send/CLT001")
    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message_id": "wamid.ABC"}
    assert "CLT001|CRITICAL|2026-07-18" in json.loads(log_path.read_text())


def test_send_alert_unknown_client_returns_404(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch)
    response = client.post("/api/send/NOPE")
    assert response.status_code == 404


def test_send_alert_ineligible_status_returns_400(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch, status="ACTIVE")
    response = client.post("/api/send/CLT001")
    assert response.status_code == 400


def test_send_alert_duplicate_returns_409(tmp_path, monkeypatch):
    log_path = _setup_one_client(tmp_path, monkeypatch)
    log_path.write_text(json.dumps({"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.OLD"}}))
    response = client.post("/api/send/CLT001")
    assert response.status_code == 409


def test_send_alert_api_failure_returns_502(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch)
    mock_response = type("Resp", (), {
        "status_code": 400,
        "json": lambda self: {"error": {"message": "Invalid parameter"}},
        "text": "Invalid parameter",
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send/CLT001")
    assert response.status_code == 502
    assert "Invalid parameter" in response.json()["detail"]


def test_send_alert_uses_dashboard_test_number_override(tmp_path, monkeypatch):
    log_path = _setup_one_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DASHBOARD_TEST_NUMBER", "919000000000")
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.TEST"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response) as mock_post:
        response = client.post("/api/send/CLT001")
    assert response.status_code == 200
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["to"] == "919000000000"
