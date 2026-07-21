"""FastAPI backend for the Absolute Veritas React dashboard."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import base64  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import threading  # noqa: E402

import openpyxl  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, HTTPException, File, Query, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

from datetime import datetime  # noqa: E402

from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, read_clients, load_sent_log, save_sent_log,
    is_already_sent,
)
from whatsapp_renewal_alerts import (  # noqa: E402
    ALERT_STATUSES, dedup_key, filter_alertable, normalize_phone,
    send_one_alert, run,
)
from email_template import build_email_html  # noqa: E402
from import_bis_isi_data import (  # noqa: E402
    looks_like_bis_isi_workbook, import_bis_isi_workbook, RowCollector,
    OUTPUT_HEADERS as BIS_OUTPUT_HEADERS,
)

load_dotenv(REPO_ROOT / ".env")

EMAIL_DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")

LOGO_PATH = REPO_ROOT / "dashboard-app" / "frontend" / "public" / "company-logo.png"


def _logo_data_uri() -> str:
    if not LOGO_PATH.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _parse_expiry(value) -> datetime:
    if isinstance(value, datetime):
        return value
    for fmt in EMAIL_DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value!r}")


app = FastAPI(title="Absolute Veritas Renewal Dashboard API")

_send_lock = threading.Lock()
_pending_sends: set[str] = set()

_bulk_in_progress = False

REQUIRED_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]

# Mirrors the hardcoded day cutoffs in cert_automation.py (CRITICAL <= 7 days,
# URGENT <= 30 days). That script is intentionally untouched by this project,
# so these are documented here for display only, not read live from it.
CERT_STATUS_THRESHOLDS = {
    "critical_days": 7,
    "urgent_days": 30,
}

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
def get_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    status: str = "ALL", cert_type: str = "ALL",
    expiry_before: str = "", search: str = "", sort_key: str = "", sort_dir: str = "asc",
):
    today = _today_str()
    rows, total = get_clients_page(
        DEFAULT_DB_PATH, page=page, page_size=page_size,
        status=status, cert_type=cert_type, expiry_before=expiry_before or None,
        search=search or None, sort_key=sort_key or None, sort_dir=sort_dir.lower(),
    )
    result = []
    for rec in rows:
        if rec["status"] in ALERT_STATUSES:
            alert_sent_today = is_already_sent(DEFAULT_DB_PATH, rec["client_id"], rec["status"], today)
        else:
            alert_sent_today = None
        result.append({**rec, "alert_sent_today": alert_sent_today})
    return {"rows": result, "total": total, "page": page, "page_size": page_size}


@app.get("/api/stats")
def stats():
    return get_stats(DEFAULT_DB_PATH, _today_str())


def _csv_escape(value) -> str:
    text = str(value if value is not None else "")
    if any(c in text for c in ('"', ",", "\n")):
        return '"' + text.replace('"', '""') + '"'
    return text


@app.get("/api/clients/export")
def export_clients(status: str = "ALL", cert_type: str = "ALL", expiry_before: str = "", search: str = ""):
    def generate():
        yield ",".join(_csv_escape(h) for h in REQUIRED_HEADERS) + "\n"
        for rec in export_clients_rows(
            DEFAULT_DB_PATH, status=status, cert_type=cert_type,
            expiry_before=expiry_before or None, search=search or None,
        ):
            values = [
                rec["client_id"], rec["name"], rec["company"], rec["email"], rec["phone"],
                rec["cert_name"], rec["cert_id"], rec["issue_date"], rec["expiry_date"],
                rec["renewal_link"], rec["status"],
            ]
            yield ",".join(_csv_escape(v) for v in values) + "\n"

    return StreamingResponse(
        generate(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=clients_export.csv"},
    )


@app.get("/api/email-preview/{client_id}")
def email_preview(client_id: str):
    record = find_client_by_id(DEFAULT_EXCEL_PATH, client_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown client_id: {client_id}")

    expiry_dt = _parse_expiry(record["expiry_date"])
    days_left = (expiry_dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    rec = {
        **record,
        "days_left": days_left,
        "expiry_formatted": expiry_dt.strftime("%d %B %Y"),
    }
    html = build_email_html(
        rec,
        org_name="Absolute Veritas",
        org_website="",
        org_contact="",
        org_email="cs@absoluteveritas.com",
        logo_src=_logo_data_uri(),
    )
    subject = f"[Action Required] Renew {record['cert_name']} — {record['company']}"
    return {"subject": subject, "html": html}


@app.get("/api/settings-info")
def settings_info():
    return {
        "template_name": os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert"),
        "template_lang": os.environ.get("WHATSAPP_TEMPLATE_LANG", "en"),
        "phone_number_id": os.environ.get("PHONE_NUMBER_ID", ""),
        "scheduled_run_time": "09:30 (Asia/Kolkata)",
        "critical_days": CERT_STATUS_THRESHOLDS["critical_days"],
        "urgent_days": CERT_STATUS_THRESHOLDS["urgent_days"],
    }


@app.get("/api/message-log")
def message_log():
    sent_log = load_sent_log(DEFAULT_LOG_PATH)
    clients_by_id = {r["client_id"]: r for r in read_clients(DEFAULT_EXCEL_PATH)}
    entries = []
    for key, info in sent_log.items():
        client_id, status_tier, _date = key.split("|", 2)
        client = clients_by_id.get(client_id, {})
        entries.append({
            "client_id": client_id,
            "name": client.get("name", "Unknown"),
            "company": client.get("company", ""),
            "cert_name": client.get("cert_name", ""),
            "status_tier": status_tier,
            "phone": info.get("phone"),
            "message_id": info.get("message_id"),
            "sent_at": info.get("sent_at"),
        })
    entries.sort(key=lambda e: e["sent_at"] or "", reverse=True)
    return entries


@app.post("/api/send/{client_id}")
def send_alert(client_id: str):
    today = _today_str()
    record = find_client_by_id(DEFAULT_EXCEL_PATH, client_id)
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
        if _bulk_in_progress:
            raise HTTPException(
                status_code=409,
                detail="A bulk send is in progress; try again after it completes",
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


@app.post("/api/send-all")
def send_all_alerts():
    global _bulk_in_progress
    with _send_lock:
        if _bulk_in_progress:
            raise HTTPException(status_code=409, detail="A bulk send is already in progress")
        if _pending_sends:
            raise HTTPException(
                status_code=409,
                detail="One or more per-client sends are in progress; try again shortly",
            )
        _bulk_in_progress = True

    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        return run(
            DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH, token, phone_number_id,
            template_name, template_lang, dry_run=False, test_number=test_number,
        )
    finally:
        with _send_lock:
            _bulk_in_progress = False


@app.get("/api/client-template")
def client_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(REQUIRED_HEADERS)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=clients_certifications_template.xlsx"},
    )


@app.post("/api/upload-clients")
async def upload_clients(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    contents = await file.read()
    tmp_path = DEFAULT_EXCEL_PATH.parent / "_upload_tmp.xlsx"
    tmp_path.write_bytes(contents)

    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        active_title = wb.active.title
        try:
            header_row = next(wb.active.iter_rows(values_only=True))
        except StopIteration:
            header_row = None
    except HTTPException:
        raise
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded file as a valid .xlsx spreadsheet",
        )

    actual_headers = list(header_row[: len(REQUIRED_HEADERS)]) if header_row else None

    if actual_headers == REQUIRED_HEADERS:
        wb.close()
        if DEFAULT_EXCEL_PATH.exists():
            backup_path = DEFAULT_EXCEL_PATH.parent / "clients_certifications.backup.xlsx"
            shutil.copyfile(DEFAULT_EXCEL_PATH, backup_path)
        shutil.move(str(tmp_path), str(DEFAULT_EXCEL_PATH))
        row_count = len(read_clients(DEFAULT_EXCEL_PATH))
        return {"status": "ok", "row_count": row_count, "format": "roster"}

    if looks_like_bis_isi_workbook(wb):
        out_wb = openpyxl.Workbook()
        out_ws = out_wb.active
        out_ws.append(BIS_OUTPUT_HEADERS)
        stats = import_bis_isi_workbook(wb, out_ws)
        wb.close()
        tmp_path.unlink(missing_ok=True)

        if stats["rows_written"] == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Recognized this as a BIS ISI licence file, but no rows had both a "
                    "licence number and a validity date to import."
                ),
            )

        if DEFAULT_EXCEL_PATH.exists():
            backup_path = DEFAULT_EXCEL_PATH.parent / "clients_certifications.backup.xlsx"
            shutil.copyfile(DEFAULT_EXCEL_PATH, backup_path)
        out_wb.save(DEFAULT_EXCEL_PATH)

        row_count = len(read_clients(DEFAULT_EXCEL_PATH))
        return {"status": "ok", "row_count": row_count, "format": "bis_isi", "stats": stats}

    wb.close()
    tmp_path.unlink(missing_ok=True)

    if header_row is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"The active sheet ('{active_title}') has no rows. If this file has "
                "multiple sheets, make sure the one with your client data is the sheet "
                "selected/visible when the file was last saved."
            ),
        )
    raise HTTPException(
        status_code=400,
        detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
    )


@app.post("/api/merge-clients")
async def merge_clients(file: UploadFile = File(...)):
    """Adds rows from the uploaded spreadsheet to the existing roster instead
    of replacing it. Client IDs already present in the roster are left
    untouched — only genuinely new Client IDs get appended."""
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    contents = await file.read()
    tmp_path = DEFAULT_EXCEL_PATH.parent / "_merge_upload_tmp.xlsx"
    tmp_path.write_bytes(contents)

    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        active_title = wb.active.title
        try:
            header_row = next(wb.active.iter_rows(values_only=True))
        except StopIteration:
            header_row = None
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded file as a valid .xlsx spreadsheet",
        )

    actual_headers = list(header_row[: len(REQUIRED_HEADERS)]) if header_row else None
    stats = None

    if actual_headers == REQUIRED_HEADERS:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)  # header
        new_rows = [row[:len(REQUIRED_HEADERS)] for row in rows_iter if row and row[0] is not None]
        wb.close()
        upload_format = "roster"
    elif looks_like_bis_isi_workbook(wb):
        collector = RowCollector()
        stats = import_bis_isi_workbook(wb, collector)
        new_rows = collector.rows
        wb.close()
        upload_format = "bis_isi"
        if stats["rows_written"] == 0:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=(
                    "Recognized this as a BIS ISI licence file, but no rows had both a "
                    "licence number and a validity date to import."
                ),
            )
    else:
        wb.close()
        tmp_path.unlink(missing_ok=True)
        if header_row is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The active sheet ('{active_title}') has no rows. If this file has "
                    "multiple sheets, make sure the one with your client data is the sheet "
                    "selected/visible when the file was last saved."
                ),
            )
        raise HTTPException(
            status_code=400,
            detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
        )

    tmp_path.unlink(missing_ok=True)

    existing_rows = []
    existing_ids = set()
    if DEFAULT_EXCEL_PATH.exists():
        existing_wb = openpyxl.load_workbook(DEFAULT_EXCEL_PATH, read_only=True, data_only=True)
        try:
            erows = existing_wb.active.iter_rows(values_only=True)
            next(erows)  # header
            for row in erows:
                if not row or row[0] is None:
                    continue
                existing_rows.append(row)
                existing_ids.add(str(row[0]).strip())
        finally:
            existing_wb.close()

    merged_rows = list(existing_rows)
    added = 0
    skipped_duplicates = 0
    for row in new_rows:
        client_id = str(row[0]).strip() if row[0] is not None else None
        if client_id and client_id in existing_ids:
            skipped_duplicates += 1
            continue
        merged_rows.append(row)
        if client_id:
            existing_ids.add(client_id)
        added += 1

    if DEFAULT_EXCEL_PATH.exists():
        backup_path = DEFAULT_EXCEL_PATH.parent / "clients_certifications.backup.xlsx"
        shutil.copyfile(DEFAULT_EXCEL_PATH, backup_path)

    out_wb = openpyxl.Workbook()
    out_ws = out_wb.active
    out_ws.append(REQUIRED_HEADERS)
    for row in merged_rows:
        out_ws.append(list(row))
    out_wb.save(DEFAULT_EXCEL_PATH)

    return {
        "status": "ok",
        "row_count": len(merged_rows),
        "added": added,
        "skipped_duplicates": skipped_duplicates,
        "format": upload_format,
        "stats": stats,
    }


from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_DIST = REPO_ROOT / "dashboard-app" / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    print(f"Frontend not built — run 'npm run build' in {FRONTEND_DIST.parent} before starting the server.")
