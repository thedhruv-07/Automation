import io
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


def test_email_preview_returns_subject_and_html(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)

    response = client.get("/api/email-preview/CLT001")
    assert response.status_code == 200
    data = response.json()
    assert data["subject"] == "[Action Required] Renew ISO 9001 — TechCorp"
    assert "Rahul Sharma" in data["html"]
    assert "Absolute Veritas" in data["html"]
    assert "24 July 2026" in data["html"]


def test_email_preview_unknown_client_returns_404(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [])
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)

    response = client.get("/api/email-preview/NOPE")
    assert response.status_code == 404


def test_settings_info_reflects_env_and_never_exposes_token(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TOKEN", "super-secret-token")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en")

    response = client.get("/api/settings-info")
    assert response.status_code == 200
    data = response.json()
    assert data["template_name"] == "cert_renewal_alert"
    assert data["template_lang"] == "en"
    assert data["phone_number_id"] == "pid123"
    assert data["critical_days"] == 7
    assert data["urgent_days"] == 30
    assert "super-secret-token" not in response.text
    assert "token" not in data


def test_message_log_returns_entries_joined_with_client_data(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text(json.dumps({
        "CLT001|CRITICAL|2026-07-18": {
            "sent_at": "2026-07-18T10:00:00", "message_id": "wamid.OLD", "phone": "919876543210",
        },
        "CLT001|CRITICAL|2026-07-19": {
            "sent_at": "2026-07-19T10:00:00", "message_id": "wamid.NEW", "phone": "919876543210",
        },
    }))
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)

    response = client.get("/api/message-log")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # newest first
    assert data[0]["message_id"] == "wamid.NEW"
    assert data[0]["name"] == "Rahul Sharma"
    assert data[0]["company"] == "TechCorp"
    assert data[0]["status_tier"] == "CRITICAL"
    assert data[0]["phone"] == "919876543210"


def test_message_log_handles_client_no_longer_in_roster(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text(json.dumps({
        "CLT999|CRITICAL|2026-07-18": {
            "sent_at": "2026-07-18T10:00:00", "message_id": "wamid.OLD", "phone": "919999999999",
        },
    }))
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)

    response = client.get("/api/message-log")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["name"] == "Unknown"


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
    _setup_one_client(tmp_path, monkeypatch)
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


def test_send_alert_with_test_number_does_not_persist_dedup_log(tmp_path, monkeypatch):
    """Bug 1: a send redirected to DASHBOARD_TEST_NUMBER must NOT write the
    real client's dedup key to sent_log.json, or the real 9:30 AM CLI run
    (and future dashboard sends) would wrongly believe the client was already
    alerted today."""
    log_path = _setup_one_client(tmp_path, monkeypatch)
    original_log_contents = log_path.read_text()
    monkeypatch.setenv("DASHBOARD_TEST_NUMBER", "919000000000")
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.TEST"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send/CLT001")
    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message_id": "wamid.TEST"}

    # The log file on disk must be untouched: no dedup key was persisted.
    assert log_path.read_text() == original_log_contents
    on_disk_log = json.loads(log_path.read_text())
    assert "CLT001|CRITICAL|2026-07-18" not in on_disk_log


def test_send_alert_concurrent_send_in_progress_returns_409(tmp_path, monkeypatch):
    """Bug 3: if a send for this client_id is already marked in-progress
    (e.g. an overlapping request got there first), a second request must be
    rejected with 409 rather than double-sending."""
    _setup_one_client(tmp_path, monkeypatch)
    main_module._pending_sends.add("CLT001")
    try:
        response = client.post("/api/send/CLT001")
    finally:
        main_module._pending_sends.discard("CLT001")
    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_send_alert_skipped_duplicate_from_send_one_alert_returns_409(tmp_path, monkeypatch):
    """Bug 2: if send_one_alert() itself reports skipped_duplicate (e.g. its
    internal dedup logic diverges from the endpoint's own pre-check in the
    future), the endpoint must still surface a 409, not a bogus 502."""
    _setup_one_client(tmp_path, monkeypatch)

    def fake_send_one_alert(*args, **kwargs):
        return {"action": "skipped_duplicate"}

    monkeypatch.setattr(main_module, "send_one_alert", fake_send_one_alert)
    response = client.post("/api/send/CLT001")
    assert response.status_code == 409
    assert "already sent today" in response.json()["detail"]


def test_send_all_alerts_success(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en")
    monkeypatch.delenv("DASHBOARD_TEST_NUMBER", raising=False)

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # only CRITICAL/URGENT are alertable; ACTIVE excluded
    actions = {r["client_id"]: r["action"] for r in data}
    assert actions == {"CLT001": "sent", "CLT002": "sent"}


def test_send_all_alerts_uses_test_number_override(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("DASHBOARD_TEST_NUMBER", "919000000000")
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.TEST"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response) as mock_post:
        response = client.post("/api/send-all")
    assert response.status_code == 200
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["to"] == "919000000000"


def test_send_all_alerts_blocks_concurrent_calls(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_bulk_in_progress", True)
    response = client.post("/api/send-all")
    assert response.status_code == 409


def test_send_alert_blocked_while_bulk_in_progress(tmp_path, monkeypatch):
    _setup_one_client(tmp_path, monkeypatch)
    monkeypatch.setattr(main_module, "_bulk_in_progress", True)
    response = client.post("/api/send/CLT001")
    assert response.status_code == 409


def test_send_all_alerts_blocked_while_per_client_send_in_progress(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    main_module._pending_sends.add("CLT999")
    try:
        response = client.post("/api/send-all")
        assert response.status_code == 409
    finally:
        main_module._pending_sends.discard("CLT999")


def test_client_template_returns_header_only_xlsx():
    response = client.get("/api/client-template")
    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows == [tuple(HEADERS)]


def test_upload_clients_success(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)

    upload_path = tmp_path / "upload.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "row_count": 1}
    assert excel_path.exists()


def test_upload_clients_rejects_non_xlsx_extension(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)
    response = client.post(
        "/api/upload-clients",
        files={"file": ("clients.csv", b"not,a,real,xlsx", "text/csv")},
    )
    assert response.status_code == 400


def test_upload_clients_rejects_wrong_headers(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)

    upload_path = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Wrong", "Headers", "Here"])
    ws.append(["a", "b", "c"])
    wb.save(upload_path)

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("bad.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 400
    assert not excel_path.exists()


def test_upload_clients_backs_up_existing_file(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    _write_xlsx(excel_path, [
        ["CLT999", "Old Client", "OldCo", "o@x.com", "919999999999",
         "Old Cert", "OLD-1", "01-01-2025", "01-01-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)

    upload_path = tmp_path / "new.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200

    backup_path = excel_path.parent / "clients_certifications.backup.xlsx"
    assert backup_path.exists()
