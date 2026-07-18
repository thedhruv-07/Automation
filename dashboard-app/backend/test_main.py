import json
import openpyxl
import main as main_module
from fastapi.testclient import TestClient
from main import app

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
