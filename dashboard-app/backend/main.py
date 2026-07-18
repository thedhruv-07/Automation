"""FastAPI backend for the Absolute Veritas React dashboard."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from datetime import datetime  # noqa: E402

from whatsapp_renewal_alerts import (  # noqa: E402
    read_clients, ALERT_STATUSES, dedup_key, load_sent_log,
    DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH,
)


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


app = FastAPI(title="Absolute Veritas Renewal Dashboard API")

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
