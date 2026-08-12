"""MongoDB-backed client roster storage. Replaces the SQLite backend --
pagination, filtering, and single-client lookups work the same way, just
against MongoDB collections instead of tables.

expiry_date is stored as the original DD-MM-YYYY display string (unchanged
from the roster format the frontend already expects); expiry_date_iso is a
YYYY-MM-DD copy used for correct sorting/filtering, since plain string
comparison of DD-MM-YYYY does not sort chronologically.
"""
import os
import weakref
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

# Entry points (main.py, whatsapp_renewal_alerts.py, etc.) import this module
# before calling load_dotenv() themselves, so MONGODB_URI wouldn't be in
# os.environ yet when DEFAULT_DB_PATH below resolves it. Load .env here so
# db.py is self-sufficient regardless of caller import order.
load_dotenv(Path(__file__).parent.parent.parent / ".env")


def get_client(mongodb_uri: str | None = None) -> MongoClient:
    uri = mongodb_uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    return MongoClient(uri)


def _resolve_default_db() -> Database:
    return get_client()["cert_dashboard"]


DEFAULT_DB_PATH = _resolve_default_db()

RECORD_FIELDS = [
    "client_id", "name", "company", "email", "phone", "cert_name", "scheme",
    "cert_id", "issue_date", "expiry_date", "renewal_link", "status",
]

DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y")

_SORTABLE_COLUMNS = {
    "client_id", "name", "company", "cert_name", "scheme", "cert_id", "status",
}

ALERT_STATUSES = ("CRITICAL", "URGENT", "DUE SOON", "EXPIRED")
REMINDER_INTERVAL_DAYS = 20


_initialized_dbs: "weakref.WeakSet" = weakref.WeakSet()


def init_db(db: Database) -> None:
    """Creates the app's indexes. Nearly every function in this module calls
    this at the top, so it's cached per Database instance (a WeakSet, not a
    plain id() set, so it can't collide with a garbage-collected object's
    reused memory address) -- otherwise every read and write would pay for
    7 create_index round-trips to MongoDB on every single call, which is
    pure waste once the indexes already exist."""
    if db in _initialized_dbs:
        return
    db["clients"].create_index("status")
    db["clients"].create_index("expiry_date_iso")
    db["clients"].create_index("cert_name")
    db["clients"].create_index("_seq")
    db["sent_log"].create_index([("client_id", 1), ("status", 1)])
    db["email_sent_log"].create_index([("client_id", 1), ("status", 1)])
    db["notice_sent_log"].create_index(
        [("client_id", 1), ("notice_id", 1), ("channel", 1)], unique=True,
    )
    _initialized_dbs.add(db)


def to_iso_date(value) -> str | None:
    """Converts a DD-MM-YYYY/YYYY-MM-DD/DD/MM/YYYY value (or datetime) to
    YYYY-MM-DD for sorting/filtering. Returns None if unparseable/blank."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _doc_to_dict(doc: dict) -> dict:
    return {field: doc.get(field) for field in RECORD_FIELDS}


def read_clients(db: Database) -> list[dict]:
    return [_doc_to_dict(doc) for doc in db["clients"].find()]


def find_client_by_id(db: Database, client_id: str) -> dict | None:
    doc = db["clients"].find_one({"_id": client_id})
    return _doc_to_dict(doc) if doc else None


def find_clients_by_ids(db: Database, client_ids: list[str]) -> dict[str, dict]:
    """Bulk lookup: {client_id: record} for every id found, in one round
    trip. Callers that would otherwise call find_client_by_id in a loop
    (e.g. joining a log of hundreds/thousands of entries against the
    roster) should use this instead -- one query beats one-per-entry."""
    if not client_ids:
        return {}
    docs = db["clients"].find({"_id": {"$in": list(set(client_ids))}})
    return {doc["_id"]: _doc_to_dict(doc) for doc in docs}


def upsert_clients(db: Database, rows: list[tuple], mode: str) -> dict:
    """rows: list of tuples in RECORD_FIELDS order (client_id first, scheme
    right after cert_name).
    mode="replace": backs up the current clients collection to
    clients_backup, then clears clients and inserts all rows.
    mode="merge": inserts only rows whose client_id isn't already present.

    Rows with a blank/None client_id are dropped before insertion in either
    mode. Every remaining row must have a non-empty name -- checked across
    the whole batch before any insert happens, so a single bad row rejects
    the entire call rather than partially applying it.
    """
    if mode not in ("replace", "merge"):
        raise ValueError(f"Unknown mode: {mode!r}")

    init_db(db)

    rows = [row for row in rows if row[0] is not None and str(row[0]).strip() != ""]

    for row in rows:
        if not row[1]:
            raise ValueError(f"Client {row[0]!r} is missing a required name")

    if mode == "replace":
        existing = list(db["clients"].find())
        if existing:
            db["clients_backup"].delete_many({})
            db["clients_backup"].insert_many(existing)
        db["clients"].delete_many({})
        docs = []
        for i, row in enumerate(rows):
            doc = dict(zip(RECORD_FIELDS, row))
            doc["_id"] = doc["client_id"]
            doc["expiry_date_iso"] = to_iso_date(row[9])
            doc["_seq"] = i
            docs.append(doc)
        if docs:
            db["clients"].insert_many(docs)
        row_count = db["clients"].count_documents({})
        return {"row_count": row_count, "added": row_count, "skipped_duplicates": 0}

    last = db["clients"].find_one(sort=[("_seq", -1)])
    next_seq = (last["_seq"] + 1) if last else 0
    existing_ids = set(db["clients"].distinct("_id"))

    docs = []
    skipped = 0
    for row in rows:
        client_id = row[0]
        if client_id in existing_ids:
            skipped += 1
            continue
        doc = dict(zip(RECORD_FIELDS, row))
        doc["_id"] = client_id
        doc["expiry_date_iso"] = to_iso_date(row[9])
        doc["_seq"] = next_seq + len(docs)
        docs.append(doc)
        existing_ids.add(client_id)  # a later row in this same file could repeat a client_id

    if docs:
        db["clients"].insert_many(docs)
    row_count = db["clients"].count_documents({})
    return {"row_count": row_count, "added": len(docs), "skipped_duplicates": skipped}


def _client_filters_query(
    status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> dict:
    """Builds the MongoDB filter dict shared by get_clients_page,
    export_clients_rows, get_eligible_clients, get_broadcast_clients, and
    the eligible-count functions -- so "currently filtered view" always
    means the same thing everywhere it's used."""
    query: dict = {}
    if status and status != "ALL":
        query["status"] = status
    # Defensive: a stale client or a direct API call could still send the
    # old single-value sentinel ("ALL") or blank strings inside the list --
    # both must mean "no filter", not a literal cert_name match.
    cert_type = [c for c in (cert_type or []) if c and c != "ALL"]
    if cert_type:
        query["cert_name"] = {"$in": cert_type}
    if scheme and scheme != "ALL":
        query["scheme"] = scheme
    if expiry_before:
        query["expiry_date_iso"] = {"$lte": expiry_before}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
        ]
    return query


def _and_query(*parts: dict) -> dict:
    """Combines filter dicts with explicit $and so a caller-supplied
    `status` key (from _client_filters_query) never silently overwrites a
    separately-required status constraint (e.g. the ALERT_STATUSES $in
    check) via dict key collision."""
    parts = [p for p in parts if p]
    if not parts:
        return {}
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


def get_clients_page(
    db: Database, page: int = 1, page_size: int = 50, status: str | None = None,
    cert_type: list[str] | None = None, expiry_before: str | None = None,
    search: str | None = None, sort_key: str | None = None, sort_dir: str = "asc",
    scheme: str | None = None,
) -> tuple[list[dict], int]:
    query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    total = db["clients"].count_documents(query)

    if sort_key in ("expiry_date", "days_left"):
        order_field = "expiry_date_iso"
    elif sort_key in _SORTABLE_COLUMNS:
        order_field = sort_key
    else:
        order_field = "client_id"
    direction = -1 if sort_dir == "desc" else 1

    offset = (page - 1) * page_size
    cursor = db["clients"].find(query).sort(order_field, direction).skip(offset).limit(page_size)
    return [_doc_to_dict(doc) for doc in cursor], total


def _reminder_cutoff_date(today: str) -> str:
    cutoff = datetime.strptime(today, "%Y-%m-%d") - timedelta(days=REMINDER_INTERVAL_DAYS)
    return cutoff.strftime("%Y-%m-%d")


def _count_eligible_excluding_recent(
    db: Database, log_collection: str, today: str, extra_query: dict | None = None,
) -> int:
    """Counts clients in ALERT_STATUSES (optionally further narrowed by
    extra_query) whose most recent log_collection entry for their own
    (client_id, status) pair is NOT within REMINDER_INTERVAL_DAYS of today --
    mirrors send_one_alert/send_one_email_alert's own dedup check exactly,
    including that a status change (no prior entry under the new status)
    always counts as eligible regardless of how recently the client was
    contacted under a previous status."""
    cutoff = _reminder_cutoff_date(today)
    recent_pairs = {
        (doc["client_id"], doc["status"])
        for doc in db[log_collection].find(
            {"sent_date": {"$gt": cutoff}}, {"client_id": 1, "status": 1},
        )
    }
    query = _and_query({"status": {"$in": list(ALERT_STATUSES)}}, extra_query or {})
    count = 0
    for doc in db["clients"].find(query, {"client_id": 1, "status": 1}):
        if (doc["client_id"], doc["status"]) not in recent_pairs:
            count += 1
    return count


def get_stats(db: Database, today: str) -> dict:
    init_db(db)
    total = db["clients"].count_documents({})
    status_counts = {"total": total}
    for status in ("CRITICAL", "URGENT", "DUE SOON", "ACTIVE", "EXPIRED"):
        status_counts[status] = db["clients"].count_documents({"status": status})

    eligible_not_sent = _count_eligible_excluding_recent(db, "sent_log", today)
    eligible_not_emailed = _count_eligible_excluding_recent(db, "email_sent_log", today)

    cert_types = sorted(db["clients"].distinct("cert_name", {"cert_name": {"$ne": None}}))
    schemes = sorted(db["clients"].distinct("scheme", {"scheme": {"$ne": None}}))

    monthly_counts: dict[str, int] = {}
    for doc in db["clients"].find({"expiry_date_iso": {"$ne": None}}, {"expiry_date_iso": 1}):
        ym = doc["expiry_date_iso"][:7]
        monthly_counts[ym] = monthly_counts.get(ym, 0) + 1
    renewals_by_month = [
        {"year_month": ym, "count": cnt} for ym, cnt in sorted(monthly_counts.items())
    ]

    return {
        "status_counts": status_counts,
        "eligible_not_sent_today": eligible_not_sent,
        "eligible_not_emailed_today": eligible_not_emailed,
        "cert_types": cert_types,
        "schemes": schemes,
        "renewals_by_month": renewals_by_month,
    }


def export_clients_rows(
    db: Database, status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
):
    """Yields a dict per matching client, no pagination -- for CSV export."""
    query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    for doc in db["clients"].find(query):
        yield _doc_to_dict(doc)


def get_eligible_clients(
    db: Database, status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    """Alert-eligible (status in ALERT_STATUSES) client records, optionally
    further narrowed by the same filters get_clients_page's table view
    supports. Sorted by _seq (insertion order) so callers that depend on
    result order see the same order read_clients() always gave them."""
    extra_query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    query = _and_query({"status": {"$in": list(ALERT_STATUSES)}}, extra_query)
    cursor = db["clients"].find(query).sort("_seq", 1)
    return [_doc_to_dict(doc) for doc in cursor]


def get_broadcast_clients(
    db: Database, status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    """Every client matching the given filters, regardless of alert status --
    used for one-time broadcast notices (see notices.py), which aren't about
    any individual client's own renewal state, unlike get_eligible_clients."""
    query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    cursor = db["clients"].find(query).sort("_seq", 1)
    return [_doc_to_dict(doc) for doc in cursor]


def get_broadcast_clients_page(
    db: Database, notice_id: str, page: int = 1, page_size: int = 50,
    status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> tuple[list[dict], int]:
    """Paginated sibling to get_broadcast_clients, each row additionally
    annotated with notice_sent_whatsapp/notice_sent_email booleans -- powers
    the Notices page's client list."""
    query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    total = db["clients"].count_documents(query)

    offset = (page - 1) * page_size
    docs = list(db["clients"].find(query).sort("_seq", 1).skip(offset).limit(page_size))
    page_ids = [d["client_id"] for d in docs]

    sent_pairs = {
        (d["client_id"], d["channel"])
        for d in db["notice_sent_log"].find(
            {"client_id": {"$in": page_ids}, "notice_id": notice_id},
            {"client_id": 1, "channel": 1},
        )
    }

    result = []
    for doc in docs:
        rec = _doc_to_dict(doc)
        rec["notice_sent_whatsapp"] = (doc["client_id"], "whatsapp") in sent_pairs
        rec["notice_sent_email"] = (doc["client_id"], "email") in sent_pairs
        result.append(rec)
    return result, total


def get_eligible_count(
    db: Database, today: str, channel: str, status: str | None = None,
    cert_type: list[str] | None = None, expiry_before: str | None = None,
    search: str | None = None, scheme: str | None = None,
) -> int:
    """Counts alert-eligible clients not yet sent via the given channel
    ('whatsapp' -> sent_log, 'email' -> email_sent_log) within the last
    REMINDER_INTERVAL_DAYS, optionally narrowed by status/cert_type/
    expiry_before/search/scheme."""
    if channel not in ("whatsapp", "email"):
        raise ValueError(f"Unknown channel: {channel!r}")
    log_collection = "sent_log" if channel == "whatsapp" else "email_sent_log"
    init_db(db)
    extra_query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    return _count_eligible_excluding_recent(db, log_collection, today, extra_query)


def get_notice_eligible_count(
    db: Database, notice_id: str, channel: str, status: str | None = None,
    cert_type: list[str] | None = None, expiry_before: str | None = None,
    search: str | None = None, scheme: str | None = None,
) -> int:
    """Counts clients matching the given filters (any status -- see
    get_broadcast_clients) who haven't already received this notice via this
    channel, per notice_sent_log."""
    init_db(db)
    already_sent_ids = set(
        db["notice_sent_log"].distinct("client_id", {"notice_id": notice_id, "channel": channel}),
    )
    query = _client_filters_query(status, cert_type, expiry_before, search, scheme)
    count = 0
    for doc in db["clients"].find(query, {"client_id": 1}):
        if doc["client_id"] not in already_sent_ids:
            count += 1
    return count


def record_sent(db: Database, client_id, status, sent_date, message_id, phone, sent_at) -> None:
    init_db(db)
    db["sent_log"].update_one(
        {"client_id": client_id, "status": status, "sent_date": sent_date},
        {"$set": {"message_id": message_id, "phone": phone, "sent_at": sent_at}},
        upsert=True,
    )


def is_already_sent(db: Database, client_id, status, sent_date) -> bool:
    return db["sent_log"].find_one(
        {"client_id": client_id, "status": status, "sent_date": sent_date},
    ) is not None


def load_sent_log(db: Database) -> dict:
    init_db(db)
    log = {}
    for doc in db["sent_log"].find():
        key = f"{doc['client_id']}|{doc['status']}|{doc['sent_date']}"
        log[key] = {"sent_at": doc["sent_at"], "message_id": doc["message_id"], "phone": doc["phone"]}
    return log


def save_sent_log(db: Database, log: dict) -> None:
    for key, info in log.items():
        client_id, status, sent_date = key.split("|", 2)
        record_sent(
            db, client_id, status, sent_date,
            info.get("message_id"), info.get("phone"), info.get("sent_at"),
        )


def record_email_sent(db: Database, client_id, status, sent_date, message_id, email, sent_at) -> None:
    init_db(db)
    db["email_sent_log"].update_one(
        {"client_id": client_id, "status": status, "sent_date": sent_date},
        {"$set": {"message_id": message_id, "email": email, "sent_at": sent_at}},
        upsert=True,
    )


def is_email_already_sent(db: Database, client_id, status, sent_date) -> bool:
    init_db(db)
    return db["email_sent_log"].find_one(
        {"client_id": client_id, "status": status, "sent_date": sent_date},
    ) is not None


def load_email_sent_log(db: Database) -> dict:
    init_db(db)
    log = {}
    for doc in db["email_sent_log"].find():
        key = f"{doc['client_id']}|{doc['status']}|{doc['sent_date']}"
        log[key] = {"sent_at": doc["sent_at"], "message_id": doc["message_id"], "email": doc["email"]}
    return log


def save_email_sent_log(db: Database, log: dict) -> None:
    for key, info in log.items():
        client_id, status, sent_date = key.split("|", 2)
        record_email_sent(
            db, client_id, status, sent_date,
            info.get("message_id"), info.get("email"), info.get("sent_at"),
        )


def is_notice_already_sent(db: Database, client_id, notice_id, channel) -> bool:
    init_db(db)
    return db["notice_sent_log"].find_one(
        {"client_id": client_id, "notice_id": notice_id, "channel": channel},
    ) is not None


def record_notice_sent(db: Database, client_id, notice_id, channel, message_id, sent_at) -> None:
    init_db(db)
    db["notice_sent_log"].update_one(
        {"client_id": client_id, "notice_id": notice_id, "channel": channel},
        {"$set": {"message_id": message_id, "sent_at": sent_at}},
        upsert=True,
    )


def load_notice_sent_log(db: Database) -> list[dict]:
    """Every notice_sent_log entry across every notice/channel, newest first
    isn't guaranteed here -- callers sort as needed (main.py's /api/notice-log
    sorts by sent_at)."""
    init_db(db)
    return [
        {
            "client_id": doc["client_id"],
            "notice_id": doc["notice_id"],
            "channel": doc["channel"],
            "message_id": doc.get("message_id"),
            "sent_at": doc.get("sent_at"),
        }
        for doc in db["notice_sent_log"].find()
    ]


def get_adhoc_recipients(db: Database, notice_id: str) -> list[str]:
    """Every phone number imported for this ad-hoc notice_id -- see
    adhoc_recipients, populated once by import_adhoc_recipients.py, not by
    any app code path. Unlike the roster-based get_broadcast_clients, there
    are no per-recipient fields (name/company/etc.) at all, just the number
    itself."""
    init_db(db)
    return [doc["_id"] for doc in db["adhoc_recipients"].find({"notice_id": notice_id}, {"_id": 1})]


def get_adhoc_recipient_count(db: Database, notice_id: str) -> int:
    init_db(db)
    return db["adhoc_recipients"].count_documents({"notice_id": notice_id})


def get_adhoc_eligible_count(db: Database, notice_id: str, channel: str) -> int:
    """Recipients who haven't been sent this notice+channel yet -- mirrors
    get_notice_eligible_count's purpose for the roster-based notices, but
    against adhoc_recipients instead of the client roster."""
    init_db(db)
    total = get_adhoc_recipient_count(db, notice_id)
    already_sent = db["notice_sent_log"].count_documents({"notice_id": notice_id, "channel": channel})
    return max(0, total - already_sent)
