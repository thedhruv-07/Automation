"""FastAPI backend for the Absolute Veritas React dashboard."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import os  # noqa: E402
import threading  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from datetime import datetime  # noqa: E402

from whatsapp_renewal_alerts import (  # noqa: E402
    read_clients, ALERT_STATUSES, dedup_key, load_sent_log, save_sent_log,
    send_one_alert, DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH,
)

load_dotenv(REPO_ROOT / ".env")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


app = FastAPI(title="Absolute Veritas Renewal Dashboard API")

_send_lock = threading.Lock()
_pending_sends: set[str] = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/clients")
def get_clients():
    today = _today_str()
    records = read_clients(DEFAULT_EXCEL_PATH)
    sent_log = load_sent_log(DEFAULT_LOG_PATH)
    result = []
    for rec in records:
        if rec["status"] in ALERT_STATUSES:
            key = dedup_key(rec["client_id"], rec["status"], today)
            alert_sent_today = key in sent_log
        else:
            alert_sent_today = None
        result.append({**rec, "alert_sent_today": alert_sent_today})
    return result


@app.post("/api/send/{client_id}")
def send_alert(client_id: str):
    today = _today_str()
    records = read_clients(DEFAULT_EXCEL_PATH)
    record = next((r for r in records if r["client_id"] == client_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown client_id: {client_id}")
    if record["status"] not in ALERT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Status {record['status']} is not alert-eligible",
        )

    sent_log = load_sent_log(DEFAULT_LOG_PATH)
    key = dedup_key(record["client_id"], record["status"], today)
    if key in sent_log:
        raise HTTPException(
            status_code=409,
            detail="Alert already sent today for this client/status",
        )

    with _send_lock:
        if client_id in _pending_sends:
            raise HTTPException(
                status_code=409,
                detail="A send for this client is already in progress",
            )
        _pending_sends.add(client_id)

    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        result = send_one_alert(
            record, sent_log, today, token, phone_number_id,
            template_name, template_lang, to_phone_override=test_number,
        )

        if result["action"] == "sent":
            if not test_number:
                save_sent_log(DEFAULT_LOG_PATH, sent_log)
            return {"status": "sent", "message_id": result["message_id"]}
        if result["action"] == "skipped_duplicate":
            raise HTTPException(
                status_code=409,
                detail="Alert already sent today for this client/status",
            )
        raise HTTPException(status_code=502, detail=result.get("error", "Unknown error"))
    finally:
        with _send_lock:
            _pending_sends.discard(client_id)


from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_DIST = REPO_ROOT / "dashboard-app" / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
