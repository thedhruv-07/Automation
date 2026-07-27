# Broadcast Notices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable "Notices" feature — a registry of pre-built one-time broadcast announcements (email + WhatsApp), a dedicated Notices page to pick a notice, filter an audience, and send it, with permanent (not per-day) dedup — so any future notice is a small content file plus one registry line, not a new subsystem. The first notice is the Transition Facilitation Order 2026.

**Architecture:** A new `notice_sent_log` table (permanent dedup, unlike the per-day `sent_log`/`email_sent_log`), a `get_broadcast_clients()` query (every client matching filters, any status — unlike `get_eligible_clients()`'s `ALERT_STATUSES` restriction), a `notices.py` content registry with one flat file per notice, `notice_sender.py` orchestrating sends (mirrors `whatsapp_renewal_alerts.run()`/`email_alerts.run_email_alerts()`), new `main.py` endpoints mirroring the existing bulk-send job pattern, and a new `NoticesView.jsx` page reusing `ClientDataFilters` and a generalized `SendAllConfirmModal`.

**Tech Stack:** Python/FastAPI/SQLite (`dashboard-app/backend/`), React/Vite (`dashboard-app/frontend/`), pytest, Vitest + React Testing Library.

---

### Task 1: `db.py` — `notice_sent_log`, `get_broadcast_clients`, `get_notice_eligible_count`

**Files:**
- Modify: `dashboard-app/backend/db.py`
- Modify: `dashboard-app/backend/test_db.py`

- [ ] **Step 1: Add `notice_sent_log` to `SCHEMA`**

Current:

```python
CREATE TABLE IF NOT EXISTS email_sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    email       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);
"""
```

Replace with:

```python
CREATE TABLE IF NOT EXISTS email_sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    email       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);

CREATE TABLE IF NOT EXISTS notice_sent_log (
    client_id   TEXT NOT NULL,
    notice_id   TEXT NOT NULL,
    channel     TEXT NOT NULL,
    message_id  TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, notice_id, channel)
);
"""
```

(No `sent_date`/date column at all here — unlike `sent_log`/`email_sent_log`, a broadcast notice is permanently sent once, not eligible for a same-status resend the next day. `CREATE TABLE IF NOT EXISTS` self-heals this onto any pre-existing `clients.db` the same way every prior schema addition in this project has, via `init_db()`'s `executescript(SCHEMA)` — no migration branch needed since this is a wholly new table, not a new column on an existing one.)

- [ ] **Step 2: Add `is_notice_already_sent` / `record_notice_sent`**

Add after `save_email_sent_log` at the end of the file:

```python
def is_notice_already_sent(db_path, client_id, notice_id, channel) -> bool:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM notice_sent_log WHERE client_id = ? AND notice_id = ? AND channel = ?",
            (client_id, notice_id, channel),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_notice_sent(db_path, client_id, notice_id, channel, message_id, sent_at) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO notice_sent_log (client_id, notice_id, channel, message_id, sent_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (client_id, notice_id, channel, message_id, sent_at),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 3: Add `get_broadcast_clients`**

Add after `get_eligible_clients`:

```python
def get_broadcast_clients(
    db_path, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    """Every client matching the given filters, regardless of alert status --
    used for one-time broadcast notices (see notices.py), which aren't about
    any individual client's own renewal state, unlike get_eligible_clients.
    _client_filters_where already treats `status` as an optional exact-match
    filter on its own -- the ALERT_STATUSES restriction is something
    get_eligible_clients adds on top of it, not something this function
    needs. ORDER BY rowid pins insertion order the same way
    get_eligible_clients does."""
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"SELECT {', '.join(RECORD_FIELDS)} FROM clients {where_clause} ORDER BY rowid",
            params,
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 4: Add `get_notice_eligible_count`**

Add after `get_eligible_count`:

```python
def get_notice_eligible_count(
    db_path, notice_id: str, channel: str, status: str | None = None,
    cert_type: str | None = None, expiry_before: str | None = None,
    search: str | None = None, scheme: str | None = None,
) -> int:
    """Counts clients matching the given filters (any status -- see
    get_broadcast_clients) who haven't already received this notice via this
    channel, per notice_sent_log -- used to show a live count for the
    Notices page's audience before anything is sent."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
        where.append(
            "NOT EXISTS (SELECT 1 FROM notice_sent_log n "
            "WHERE n.client_id = clients.client_id AND n.notice_id = ? AND n.channel = ?)"
        )
        params = params + [notice_id, channel]
        count = conn.execute(
            f"SELECT COUNT(*) FROM clients WHERE {' AND '.join(where)}", params,
        ).fetchone()[0]
        return count
    finally:
        conn.close()
```

- [ ] **Step 5: Write the failing tests**

Add to `dashboard-app/backend/test_db.py`:

```python
def test_init_db_creates_notice_sent_log_table(tmp_path):
    db_path = tmp_path / "clients.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "notice_sent_log" in tables


def test_record_and_check_notice_sent(tmp_path):
    db_path = tmp_path / "clients.db"
    init_db(db_path)

    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp") is False

    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp") is True
    # A different channel for the same client/notice is tracked independently.
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "email") is False
    # A different notice_id for the same client/channel is tracked independently.
    assert is_notice_already_sent(db_path, "CLT001", "some_other_notice", "whatsapp") is False


def test_get_broadcast_clients_returns_every_status(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")

    records = get_broadcast_clients(db_path)

    assert {r["client_id"] for r in records} == {"CLT001", "CLT002"}


def test_get_broadcast_clients_honors_scheme_filter(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")

    records = get_broadcast_clients(db_path, scheme="CRS")

    assert {r["client_id"] for r in records} == {"CLT002"}


def test_get_notice_eligible_count_excludes_already_sent(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    count = get_notice_eligible_count(db_path, "transition_facilitation_2026", "whatsapp", scheme="CRS")

    assert count == 1


def test_get_notice_eligible_count_is_independent_per_notice_and_channel(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    # Already sent via whatsapp for this notice -- excluded.
    assert get_notice_eligible_count(db_path, "transition_facilitation_2026", "whatsapp") == 0
    # Not yet sent via email for this same notice -- still counted.
    assert get_notice_eligible_count(db_path, "transition_facilitation_2026", "email") == 1
    # Not yet sent (via any channel) for a different notice -- still counted.
    assert get_notice_eligible_count(db_path, "some_other_notice", "whatsapp") == 1
```

Also add `is_notice_already_sent, record_notice_sent, get_broadcast_clients, get_notice_eligible_count` to `test_db.py`'s existing top-of-file imports from `db` (find the existing `from db import (...)` line(s) and add these four names — read the file first to see its current exact import list, since it's grown across several prior tasks).

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: FAIL — none of these six functions/behaviors exist yet.

- [ ] **Step 7: Apply Steps 1-4 above, then run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: all passed.

- [ ] **Step 8: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed, zero regressions.

- [ ] **Step 9: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/test_db.py
git commit -m "feat: add notice_sent_log, get_broadcast_clients, get_notice_eligible_count"
```

---

### Task 2: Content layer — `notices.py`, `notice_transition_facilitation_2026.py`

**Files:**
- Create: `dashboard-app/backend/notice_transition_facilitation_2026.py`
- Create: `dashboard-app/backend/notices.py`
- Create: `dashboard-app/backend/test_notice_transition_facilitation_2026.py`
- Create: `dashboard-app/backend/test_notices.py`

- [ ] **Step 1: Write the failing tests for the notice content module**

Create `dashboard-app/backend/test_notice_transition_facilitation_2026.py`:

```python
"""Tests for notice_transition_facilitation_2026.py's content."""
import notice_transition_facilitation_2026 as notice


def _rec(**overrides):
    rec = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "email": "r@x.com", "phone": "919876543210",
    }
    rec.update(overrides)
    return rec


def test_build_email_html_includes_name_company_and_notice_url():
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert "Rahul Sharma" in html
    assert "TechCorp" in html
    assert notice.NOTICE_URL in html
    assert "Absolute Veritas" in html


def test_email_subject_mentions_the_order():
    assert "Transition Facilitation" in notice.EMAIL_SUBJECT
    assert "2026" in notice.EMAIL_SUBJECT


def test_get_whatsapp_template_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", raising=False)

    assert notice.get_whatsapp_template() is None


def test_get_whatsapp_template_returns_configured_pair(monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")

    assert notice.get_whatsapp_template() == ("transition_notice_2026", "en")


def test_build_whatsapp_payload_structure():
    payload = notice.build_whatsapp_payload(_rec(), "919876543210", "transition_notice_2026", "en")

    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "919876543210"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "transition_notice_2026"
    assert payload["template"]["language"] == {"code": "en"}
    params = payload["template"]["components"][0]["parameters"]
    assert params[0] == {"type": "text", "text": "Rahul Sharma"}
    assert params[1] == {"type": "text", "text": "TechCorp"}
    assert params[2] == {"type": "text", "text": notice.NOTICE_URL}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_notice_transition_facilitation_2026.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'notice_transition_facilitation_2026'`.

- [ ] **Step 3: Create `notice_transition_facilitation_2026.py`**

Create `dashboard-app/backend/notice_transition_facilitation_2026.py`:

```python
"""Content for the "Transition Facilitation Order 2026" one-time broadcast
notice. Summarizes DPIIT's Transition Facilitation (Quality Control) Order,
2026 (S.O. 3417(E), effective 25 June 2026) -- see
https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/
for the full article this summarizes. Unlike the per-scheme renewal alert
content in scheme_templates.py, this isn't about any individual client's own
certificate -- it's a general compliance-awareness announcement."""

NOTICE_URL = "https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/"

EMAIL_SUBJECT = "Important: BIS Transition Facilitation Order, 2026 — What It Means for You"


def build_email_html(rec: dict, org_name: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f9f9f7;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9f9f7;padding:30px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e1e0d9;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(11,11,11,0.10);">
        <tr><td style="background:#2a78d6;padding:28px 30px;text-align:center;">
          <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700;">{org_name}</h1>
          <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;">
            BIS Compliance Notice
          </p>
        </td></tr>
        <tr><td style="padding:32px 40px;">
          <p style="color:#0b0b0b;font-size:16px;margin:0 0 18px;">Dear <strong>{rec['name']}</strong> ({rec['company']}),</p>
          <p style="color:#52514e;font-size:14px;line-height:1.7;margin:0 0 18px;">
            DPIIT's new <strong>Transition Facilitation (Quality Control) Order, 2026</strong>
            (effective 25 June 2026) lets eligible companies source BIS Scheme-II
            certified product while their own ISI Mark certification is still in
            process — covering ten notified Quality Control Orders including toys,
            footwear, air conditioners, water heaters, washing machines, hinges,
            furniture, and household electrical appliances.
          </p>
          <p style="color:#52514e;font-size:14px;line-height:1.7;margin:0 0 26px;">
            The application window is <strong>24 months from 25 June 2026</strong>.
            If your business handles products under any of these categories, or is
            currently working through ISI Mark certification, this is worth
            building into your compliance planning now.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:4px 0 26px;">
              <a href="{NOTICE_URL}"
                 style="background:#2a78d6;color:#fff;padding:15px 42px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                Read the Full Breakdown
              </a>
            </td></tr>
          </table>
          <p style="color:#52514e;font-size:13px;line-height:1.7;margin:0;">
            Want help assessing your eligibility or compiling documentation?
            Reach out to {org_name} — we support BIS Certification, QCO
            compliance, and regulatory coordination across India.
          </p>
        </td></tr>
        <tr><td style="background:#0b0b0b;padding:18px;text-align:center;">
          <p style="color:rgba(255,255,255,0.6);font-size:11px;margin:0;">
            {org_name} — This is an automated notification.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def get_whatsapp_template() -> tuple[str, str] | None:
    import os
    name = os.environ.get("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME")
    lang = os.environ.get("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG")
    if name and lang:
        return name, lang
    return None


def build_whatsapp_payload(rec: dict, to_phone: str, template_name: str, template_lang: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": rec["name"]},
                        {"type": "text", "text": rec["company"]},
                        {"type": "text", "text": NOTICE_URL},
                    ],
                },
            ],
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_notice_transition_facilitation_2026.py -v`
Expected: 5 passed.

- [ ] **Step 5: Write the failing tests for the registry**

Create `dashboard-app/backend/test_notices.py`:

```python
"""Tests for notices.py's notice registry."""
import notice_transition_facilitation_2026
from notices import get_notice_module, list_notices


def test_list_notices_includes_transition_facilitation_2026():
    notices = list_notices()
    ids = {n["id"] for n in notices}
    assert "transition_facilitation_2026" in ids
    entry = next(n for n in notices if n["id"] == "transition_facilitation_2026")
    assert entry["label"] == "Transition Facilitation Order 2026"


def test_get_notice_module_returns_the_content_module():
    assert get_notice_module("transition_facilitation_2026") is notice_transition_facilitation_2026


def test_get_notice_module_returns_none_for_unknown_id():
    assert get_notice_module("does_not_exist") is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_notices.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'notices'`.

- [ ] **Step 7: Create `notices.py`**

Create `dashboard-app/backend/notices.py`:

```python
"""Registry of one-time broadcast notices (distinct from the per-scheme
renewal alert content in scheme_templates.py -- a notice isn't about any
individual client's own certificate, it's a general announcement sent once
to everyone matching a filter). Each entry names a module implementing:
  - EMAIL_SUBJECT: str
  - build_email_html(rec, org_name) -> str
  - get_whatsapp_template() -> (name, lang) | None
  - build_whatsapp_payload(rec, to_phone, template_name, template_lang) -> dict

To add a new notice: write notice_<id>.py implementing the above, then add
one line below plus a display label. No endpoint/frontend changes needed --
the Notices page and its endpoints already iterate this registry.
"""
import notice_transition_facilitation_2026

NOTICES = {
    "transition_facilitation_2026": {
        "label": "Transition Facilitation Order 2026",
        "module": notice_transition_facilitation_2026,
    },
}


def list_notices() -> list[dict]:
    return [{"id": notice_id, "label": entry["label"]} for notice_id, entry in NOTICES.items()]


def get_notice_module(notice_id: str):
    entry = NOTICES.get(notice_id)
    return entry["module"] if entry else None
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_notices.py -v`
Expected: 3 passed.

- [ ] **Step 9: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 10: Commit**

```bash
git add dashboard-app/backend/notice_transition_facilitation_2026.py dashboard-app/backend/notices.py dashboard-app/backend/test_notice_transition_facilitation_2026.py dashboard-app/backend/test_notices.py
git commit -m "feat: add the notice content registry and the Transition Facilitation 2026 notice"
```

---

### Task 3: `email_alerts.py` — extract `post_email_via_brevo`; new `notice_sender.py`

**Files:**
- Modify: `dashboard-app/backend/email_alerts.py`
- Modify: `dashboard-app/backend/test_email_alerts.py`
- Create: `dashboard-app/backend/notice_sender.py`
- Create: `dashboard-app/backend/test_notice_sender.py`

- [ ] **Step 1: Extract the low-level Brevo HTTP call out of `send_email_via_brevo`**

Both `email_alerts.py`'s renewal-alert emails and the new notice emails need to POST to Brevo's API and interpret the response identically — only the payload content differs (renewal content vs. notice content). Extracting this shared part avoids duplicating it in `notice_sender.py`.

Current (`dashboard-app/backend/email_alerts.py`):

```python
def send_email_via_brevo(rec: dict, brevo_api_key: str, email_sender: str, org_name: str, to_email: str):
    """Builds the HTML (same build_email_html() the preview endpoint uses) and
    sends via Brevo's transactional email API. Returns (success, info_dict)
    matching whatsapp_renewal_alerts.send_message()'s contract."""
    expiry_dt = _parse_expiry(rec["expiry_date"])
    days_left = (expiry_dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    template_rec = {
        **rec,
        "days_left": days_left,
        "expiry_formatted": expiry_dt.strftime("%d %B %Y"),
    }

    logo_exists = LOGO_PATH.exists()
    logo_src = f"cid:{LOGO_CID}" if logo_exists else ""
    subject_template, intro_text = get_email_content(rec["scheme"])
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src, intro_text=intro_text,
    )
    subject = subject_template.format(cert_name=rec["cert_name"], company=rec["company"])

    payload = {
        "sender": {"name": org_name, "email": email_sender},
        "to": [{"email": to_email, "name": rec["name"]}],
        "subject": subject,
        "htmlContent": html,
    }
    # Brevo's API doc doesn't guarantee an empty `attachment: []` is accepted,
    # so the key is only included when there's an actual attachment to send --
    # avoids relying on unverified behavior for the common case (no logo file
    # present, e.g. in dev/test environments).
    if logo_exists:
        logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        payload["attachment"] = [{"name": LOGO_CID, "content": logo_b64}]
    headers = {
        "api-key": brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=15,
        )
    except requests.RequestException as exc:
        return False, {"error": str(exc)}

    if response.status_code in (200, 201):
        try:
            data = response.json()
            return True, {"message_id": data.get("messageId")}
        except ValueError:
            return True, {"message_id": None}

    try:
        error_message = response.json().get("message", response.text)
    except ValueError:
        error_message = response.text
    return False, {"error": error_message}
```

Replace with:

```python
def post_email_via_brevo(payload: dict, brevo_api_key: str) -> tuple[bool, dict]:
    """Low-level Brevo transactional email API call, shared by
    send_email_via_brevo (renewal alerts) and notice_sender.py's notice
    email sending -- the two build very different payload content, but the
    HTTP call and response handling is identical. Returns (success,
    info_dict) matching whatsapp_renewal_alerts.send_message()'s contract."""
    headers = {
        "api-key": brevo_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email", json=payload, headers=headers, timeout=15,
        )
    except requests.RequestException as exc:
        return False, {"error": str(exc)}

    if response.status_code in (200, 201):
        try:
            data = response.json()
            return True, {"message_id": data.get("messageId")}
        except ValueError:
            return True, {"message_id": None}

    try:
        error_message = response.json().get("message", response.text)
    except ValueError:
        error_message = response.text
    return False, {"error": error_message}


def send_email_via_brevo(rec: dict, brevo_api_key: str, email_sender: str, org_name: str, to_email: str):
    """Builds the HTML (same build_email_html() the preview endpoint uses) and
    sends via Brevo's transactional email API. Returns (success, info_dict)
    matching whatsapp_renewal_alerts.send_message()'s contract."""
    expiry_dt = _parse_expiry(rec["expiry_date"])
    days_left = (expiry_dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    template_rec = {
        **rec,
        "days_left": days_left,
        "expiry_formatted": expiry_dt.strftime("%d %B %Y"),
    }

    logo_exists = LOGO_PATH.exists()
    logo_src = f"cid:{LOGO_CID}" if logo_exists else ""
    subject_template, intro_text = get_email_content(rec["scheme"])
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src, intro_text=intro_text,
    )
    subject = subject_template.format(cert_name=rec["cert_name"], company=rec["company"])

    payload = {
        "sender": {"name": org_name, "email": email_sender},
        "to": [{"email": to_email, "name": rec["name"]}],
        "subject": subject,
        "htmlContent": html,
    }
    # Brevo's API doc doesn't guarantee an empty `attachment: []` is accepted,
    # so the key is only included when there's an actual attachment to send --
    # avoids relying on unverified behavior for the common case (no logo file
    # present, e.g. in dev/test environments).
    if logo_exists:
        logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        payload["attachment"] = [{"name": LOGO_CID, "content": logo_b64}]
    return post_email_via_brevo(payload, brevo_api_key)
```

- [ ] **Step 2: Run tests to verify nothing broke**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all previously-existing tests pass unchanged — `send_email_via_brevo`'s external behavior is identical, only its internals were split.

- [ ] **Step 3: Add a direct test for the extracted function**

Add to `dashboard-app/backend/test_email_alerts.py`, after `test_send_email_via_brevo_network_error` (or wherever the existing `send_email_via_brevo` tests end — read the file to find the exact spot):

```python
def test_post_email_via_brevo_success():
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-9"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        ok, info = post_email_via_brevo({"subject": "Test"}, "api-key")

    assert ok is True
    assert info == {"message_id": "brevo-msg-9"}
    mock_post.assert_called_once()
```

Add `post_email_via_brevo` to the file's existing `from email_alerts import (...)` line.

- [ ] **Step 4: Run tests to verify it passes**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all passed.

- [ ] **Step 5: Write the failing tests for `notice_sender.py`**

Create `dashboard-app/backend/test_notice_sender.py`:

```python
"""Tests for notice_sender.py's send orchestration."""
from unittest.mock import Mock, patch

from db import upsert_clients, record_notice_sent
from notice_sender import send_notice_whatsapp, send_notice_email

CRS_ROW = ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
           "OSHA", "CRS", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL")
CRS_ROW_NO_EMAIL = ("CLT002", "Priya Mehta", "BuildRight", None, "919812345678",
                     "ISO 9001", "CRS", "ISO-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")


def test_send_notice_whatsapp_skips_when_no_template_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", raising=False)
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock()

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()


def test_send_notice_whatsapp_sends_and_records_permanently(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "sent"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp") is True


def test_send_notice_whatsapp_skips_client_already_sent_to(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.OLD", "2026-07-20T10:00:00")
    send_fn = Mock()

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid", send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_notice_whatsapp_test_number_does_not_persist_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.TEST"}))

    results = send_notice_whatsapp(
        db_path, "transition_facilitation_2026", "tok", "pid",
        send_fn=send_fn, scheme="CRS", test_number="919999999999",
    )

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp") is False


def test_send_notice_email_skips_when_no_email_on_file(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW_NO_EMAIL], mode="replace")
    send_fn = Mock()

    results = send_notice_email(
        db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_no_email"
    send_fn.assert_not_called()


def test_send_notice_email_sends_and_records_permanently(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "brevo-1"}))

    results = send_notice_email(
        db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "sent"
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT001", "transition_facilitation_2026", "email") is True


def test_send_notice_email_skips_client_already_sent_to(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "email", "brevo-old", "2026-07-20T10:00:00")
    send_fn = Mock()

    results = send_notice_email(
        db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
        send_fn=send_fn, scheme="CRS",
    )

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_notice_email_uses_the_notice_module_content(tmp_path):
    """Proves the email actually sent is the notice's own content (subject,
    URL), not the renewal-alert template -- the whole point of this feature
    is that a notice isn't about anyone's own certificate."""
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-1"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_notice_email(
            db_path, "transition_facilitation_2026", "api-key", "sender@x.com", "Absolute Veritas",
            scheme="CRS",
        )

    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == "Important: BIS Transition Facilitation Order, 2026 — What It Means for You"
    assert "transition-facilitation-quality-control-order-2026" in payload["htmlContent"]


def test_send_notice_whatsapp_raises_for_unknown_notice_id(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [CRS_ROW], mode="replace")

    import pytest
    with pytest.raises(ValueError):
        send_notice_whatsapp(db_path, "does_not_exist", "tok", "pid")
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_notice_sender.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'notice_sender'`.

- [ ] **Step 7: Create `notice_sender.py`**

Create `dashboard-app/backend/notice_sender.py`:

```python
"""Send orchestration for one-time broadcast notices (see notices.py for
the content registry). Mirrors whatsapp_renewal_alerts.run()/
email_alerts.run_email_alerts()'s shape, but targets get_broadcast_clients()
(every matching client regardless of alert status, not just ALERT_STATUSES)
and dedups against notice_sent_log (permanent, not per-day) instead of
sent_log/email_sent_log."""
from datetime import datetime

from db import get_broadcast_clients, is_notice_already_sent, record_notice_sent
from email_alerts import post_email_via_brevo
from notices import get_notice_module
from whatsapp_renewal_alerts import normalize_phone, send_message


def send_notice_whatsapp(
    db_path, notice_id: str, token: str, phone_number_id: str,
    dry_run: bool = False, test_number: str | None = None, send_fn=send_message,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
) -> list[dict]:
    module = get_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown notice_id: {notice_id!r}")

    template = module.get_whatsapp_template()
    records = get_broadcast_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    results = []

    for rec in records:
        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])

        if not test_number and is_notice_already_sent(db_path, rec["client_id"], notice_id, "whatsapp"):
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_duplicate", "to": to_phone,
            }
        elif template is None:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_no_template", "to": to_phone,
            }
        else:
            template_name, template_lang = template
            payload = module.build_whatsapp_payload(rec, to_phone, template_name, template_lang)
            if dry_run:
                result = {
                    "client_id": rec["client_id"], "name": rec["name"],
                    "action": "dry_run", "to": to_phone, "payload": payload,
                }
            else:
                try:
                    ok, info = send_fn(payload, token, phone_number_id)
                    if ok:
                        if not test_number:
                            record_notice_sent(
                                db_path, rec["client_id"], notice_id, "whatsapp",
                                info.get("message_id"), datetime.now().isoformat(),
                            )
                        result = {
                            "client_id": rec["client_id"], "name": rec["name"], "action": "sent",
                            "to": to_phone, "message_id": info.get("message_id"),
                        }
                    else:
                        result = {
                            "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                            "to": to_phone, "error": info.get("error"),
                        }
                except Exception as exc:
                    result = {
                        "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                        "to": to_phone, "error": str(exc),
                    }

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    return results


def send_notice_email(
    db_path, notice_id: str, brevo_api_key: str, email_sender: str, org_name: str,
    dry_run: bool = False, test_email: str | None = None, send_fn=post_email_via_brevo,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
) -> list[dict]:
    module = get_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown notice_id: {notice_id!r}")

    records = get_broadcast_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    results = []

    for rec in records:
        to_email = test_email or rec.get("email")

        if not to_email or "@" not in str(to_email):
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_no_email", "to": None,
            }
        elif not test_email and is_notice_already_sent(db_path, rec["client_id"], notice_id, "email"):
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "skipped_duplicate", "to": to_email,
            }
        elif dry_run:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "action": "dry_run", "to": to_email,
            }
        else:
            html = module.build_email_html(rec, org_name)
            payload = {
                "sender": {"name": org_name, "email": email_sender},
                "to": [{"email": to_email, "name": rec["name"]}],
                "subject": module.EMAIL_SUBJECT,
                "htmlContent": html,
            }
            try:
                ok, info = send_fn(payload, brevo_api_key)
                if ok:
                    if not test_email:
                        record_notice_sent(
                            db_path, rec["client_id"], notice_id, "email",
                            info.get("message_id"), datetime.now().isoformat(),
                        )
                    result = {
                        "client_id": rec["client_id"], "name": rec["name"], "action": "sent",
                        "to": to_email, "message_id": info.get("message_id"),
                    }
                else:
                    result = {
                        "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                        "to": to_email, "error": info.get("error"),
                    }
            except Exception as exc:
                result = {
                    "client_id": rec["client_id"], "name": rec["name"], "action": "failed",
                    "to": to_email, "error": str(exc),
                }

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    return results
```

Note: `test_send_notice_email_uses_the_notice_module_content` patches `email_alerts.requests.post`, not `notice_sender.requests.post` — `send_notice_email`'s default `send_fn=post_email_via_brevo` is a function *defined* in `email_alerts.py`, so its `requests.post(...)` call resolves against `email_alerts`'s own module-level `requests` import at call time, regardless of which module invokes the function. `notice_sender.py` itself has no `requests` import at all (it never calls `requests` directly — only through `post_email_via_brevo`/`send_message`, both imported from elsewhere), so there is nothing to patch there.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_notice_sender.py -v`
Expected: all passed.

- [ ] **Step 9: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 10: Commit**

```bash
git add dashboard-app/backend/email_alerts.py dashboard-app/backend/test_email_alerts.py dashboard-app/backend/notice_sender.py dashboard-app/backend/test_notice_sender.py
git commit -m "feat: extract post_email_via_brevo; add notice_sender.py send orchestration"
```

---

### Task 4: `main.py` — Notices API endpoints

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Add imports**

Current:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
    get_eligible_count,
)
```

Replace with:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
    get_eligible_count, get_notice_eligible_count,
)
```

Current:

```python
from scheme_templates import get_email_content  # noqa: E402
```

Replace with:

```python
from scheme_templates import get_email_content  # noqa: E402
from notices import list_notices, get_notice_module  # noqa: E402
from notice_sender import send_notice_whatsapp, send_notice_email  # noqa: E402
```

- [ ] **Step 2: Add the Notices endpoints**

Add immediately after the `/api/send-all-emails/status/{job_id}` endpoint (find `def send_all_emails_status(job_id: str):` and its `return job` line — add these new endpoints right after that function):

```python
@app.get("/api/notices", dependencies=[Depends(require_auth)])
def notices_list():
    return list_notices()


@app.get("/api/notices/{notice_id}/eligible-count", dependencies=[Depends(require_auth)])
def notice_eligible_count(
    notice_id: str, status: str = "", cert_type: str = "", expiry_before: str = "",
    search: str = "", scheme: str = "",
):
    if get_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown notice_id: {notice_id}")
    return {
        "whatsapp": get_notice_eligible_count(
            DEFAULT_DB_PATH, notice_id, "whatsapp",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
        "email": get_notice_eligible_count(
            DEFAULT_DB_PATH, notice_id, "email",
            status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
    }


_send_notice_jobs: dict[str, dict] = {}


def _run_send_notice_whatsapp_job(
    job_id, notice_id, token, phone_number_id, test_number,
    status=None, cert_type=None, expiry_before=None, search=None, scheme=None,
):
    def progress(result, total):
        job = _send_notice_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "skipped_no_template":
            job["skipped_no_template"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        send_notice_whatsapp(
            DEFAULT_DB_PATH, notice_id, token, phone_number_id,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
        )
    except Exception as exc:
        _send_notice_jobs[job_id]["error"] = str(exc)
    finally:
        _send_notice_jobs[job_id]["done"] = True


@app.post("/api/notices/{notice_id}/send-whatsapp", dependencies=[Depends(require_auth)])
def send_notice_whatsapp_endpoint(
    notice_id: str, status: str = "", cert_type: str = "", expiry_before: str = "",
    search: str = "", scheme: str = "",
):
    if get_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown notice_id: {notice_id}")
    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        job_id = str(uuid.uuid4())
        _send_notice_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "skipped_no_template": 0, "failed": 0,
            "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_notice_whatsapp_job,
            args=(
                job_id, notice_id, token, phone_number_id, test_number,
                status or None, cert_type or None, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        raise HTTPException(status_code=500, detail="Server is not configured to send WhatsApp messages")


@app.get("/api/notices/{notice_id}/send-whatsapp/status/{job_id}", dependencies=[Depends(require_auth)])
def send_notice_whatsapp_status(notice_id: str, job_id: str):
    job = _send_notice_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job


_send_notice_email_jobs: dict[str, dict] = {}


def _run_send_notice_email_job(
    job_id, notice_id, brevo_api_key, email_sender, test_email,
    status=None, cert_type=None, expiry_before=None, search=None, scheme=None,
):
    def progress(result, total):
        job = _send_notice_email_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "skipped_no_email":
            job["skipped_no_email"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        send_notice_email(
            DEFAULT_DB_PATH, notice_id, brevo_api_key, email_sender, "Absolute Veritas",
            dry_run=False, test_email=test_email, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
        )
    except Exception as exc:
        _send_notice_email_jobs[job_id]["error"] = str(exc)
    finally:
        _send_notice_email_jobs[job_id]["done"] = True


@app.post("/api/notices/{notice_id}/send-email", dependencies=[Depends(require_auth)])
def send_notice_email_endpoint(
    notice_id: str, status: str = "", cert_type: str = "", expiry_before: str = "",
    search: str = "", scheme: str = "",
):
    if get_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown notice_id: {notice_id}")
    try:
        brevo_api_key = os.environ["BREVO_API_KEY"]
        email_sender = os.environ["EMAIL_SENDER"]
        test_email = os.environ.get("DASHBOARD_TEST_EMAIL") or None

        job_id = str(uuid.uuid4())
        _send_notice_email_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "skipped_no_email": 0, "failed": 0,
            "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_notice_email_job,
            args=(
                job_id, notice_id, brevo_api_key, email_sender, test_email,
                status or None, cert_type or None, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        raise HTTPException(status_code=500, detail="Server is not configured to send emails")


@app.get("/api/notices/{notice_id}/send-email/status/{job_id}", dependencies=[Depends(require_auth)])
def send_notice_email_status(notice_id: str, job_id: str):
    job = _send_notice_email_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
```

- [ ] **Step 3: Write the failing tests**

Add to `dashboard-app/backend/test_main.py` (at the end of the file):

```python
def test_notices_list_includes_transition_facilitation_2026():
    response = client.get("/api/notices")
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()}
    assert "transition_facilitation_2026" in ids


def test_notice_eligible_count_unknown_notice_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", tmp_path / "clients.db")
    response = client.get("/api/notices/does_not_exist/eligible-count")
    assert response.status_code == 404


def test_notice_eligible_count_reflects_scheme_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    response = client.get("/api/notices/transition_facilitation_2026/eligible-count", params={"scheme": "CRS"})
    assert response.status_code == 200
    assert response.json() == {"whatsapp": 1, "email": 1}


def test_send_notice_whatsapp_unknown_notice_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", tmp_path / "clients.db")
    response = client.post("/api/notices/does_not_exist/send-whatsapp")
    assert response.status_code == 404


def test_send_notice_whatsapp_starts_job_and_reports_progress(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/notices/transition_facilitation_2026/send-whatsapp", params={"scheme": "CRS"})
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/notices/transition_facilitation_2026/send-whatsapp/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["sent"] == 1


def test_send_notice_whatsapp_status_returns_404_for_unknown_job():
    response = client.get("/api/notices/transition_facilitation_2026/send-whatsapp/status/does-not-exist")
    assert response.status_code == 404


def test_send_notice_email_starts_job_and_reports_progress(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "24-07-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("BREVO_API_KEY", "key")
    monkeypatch.setenv("EMAIL_SENDER", "sender@x.com")

    mock_response = type("Resp", (), {
        "status_code": 201,
        "json": lambda self: {"messageId": "brevo-1"},
    })()
    with patch("email_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/notices/transition_facilitation_2026/send-email", params={"scheme": "CRS"})
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/notices/transition_facilitation_2026/send-email/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["sent"] == 1


def test_send_notice_email_status_returns_404_for_unknown_job():
    response = client.get("/api/notices/transition_facilitation_2026/send-email/status/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: FAIL — none of these endpoints exist yet.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed, once Steps 1-2 above are applied.

- [ ] **Step 6: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add Notices API endpoints (list, eligible-count, send-whatsapp, send-email)"
```

---

### Task 5: Frontend `api.js` — Notices API functions

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/frontend/src/api.test.js` (at the end of the file, or grouped near the other bulk-send tests):

```javascript
describe("listNotices", () => {
  it("returns the notices list", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ([{ id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" }]),
    });
    const result = await listNotices();
    expect(result).toEqual([{ id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" }]);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices",
      { credentials: "include", headers: {} }
    );
  });
});

describe("getNoticeEligibleCount", () => {
  it("passes filters as query params", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 2, email: 3 }) });
    const result = await getNoticeEligibleCount("transition_facilitation_2026", { scheme: "CRS" });
    expect(result).toEqual({ whatsapp: 2, email: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/eligible-count?scheme=CRS",
      { credentials: "include", headers: {} }
    );
  });
});

describe("sendNotice", () => {
  it("posts to the channel-specific send endpoint with filters", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "job-1" }) });
    const result = await sendNotice("transition_facilitation_2026", "whatsapp", { scheme: "CRS" });
    expect(result).toEqual({ job_id: "job-1" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/send-whatsapp?scheme=CRS",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 404, json: async () => ({ detail: "Unknown notice_id: xyz" }),
    });
    await expect(sendNotice("xyz", "email", {})).rejects.toThrow("Unknown notice_id: xyz");
  });
});

describe("getNoticeSendStatus", () => {
  it("fetches the channel-specific job status", async () => {
    global.fetch.mockResolvedValue({
      ok: true, json: async () => ({ total: 2, sent: 1, skipped: 0, failed: 0, done: false }),
    });
    const result = await getNoticeSendStatus("transition_facilitation_2026", "whatsapp", "job-1");
    expect(result).toEqual({ total: 2, sent: 1, skipped: 0, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/send-whatsapp/status/job-1",
      { credentials: "include", headers: {} }
    );
  });
});
```

Add `listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus` to the file's existing top-of-file import from `./api`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: FAIL — none of these four functions exist in `api.js` yet.

- [ ] **Step 3: Add the functions to `api.js`**

Add at the end of `dashboard-app/frontend/src/api.js`:

```javascript
export async function listNotices() {
  const res = await fetch(`${API_BASE}/api/notices`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load notices: ${res.status}`);
  return res.json();
}

export async function getNoticeEligibleCount(noticeId, params = {}) {
  const qs = scopeQueryString(params);
  const url = `/api/notices/${noticeId}/eligible-count${qs ? `?${qs}` : ""}`;
  const res = await fetch(`${API_BASE}${url}`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load notice eligible count: ${res.status}`);
  return res.json();
}

export async function sendNotice(noticeId, channel, params = {}) {
  const qs = scopeQueryString(params);
  const url = `/api/notices/${noticeId}/send-${channel}${qs ? `?${qs}` : ""}`;
  const res = await fetch(`${API_BASE}${url}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send failed: ${res.status}`);
  }
  return data;
}

export async function getNoticeSendStatus(noticeId, channel, jobId) {
  const res = await fetch(`${API_BASE}/api/notices/${noticeId}/send-${channel}/status/${jobId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load notice send status: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: add Notices API client functions"
```

---

### Task 6: `SendAllConfirmModal.jsx` — generalize for single-scope notice sends

**Files:**
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx` (after the existing tests, inside the same `describe` block if there is one — read the file's current structure first):

```jsx
  it("shows the notice label in the title and body when noticeLabel is given", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} filteredCount={4} onConfirm={() => {}} onCancel={() => {}}
        noticeLabel="Transition Facilitation Order 2026" singleScope
      />
    );
    expect(screen.getByText('Send "Transition Facilitation Order 2026"?')).toBeInTheDocument();
    expect(screen.getByText(/Send "Transition Facilitation Order 2026" via WhatsApp/)).toBeInTheDocument();
  });

  it("hides the scope radio choice and shows a single count when singleScope is set", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} filteredCount={4} onConfirm={() => {}} onCancel={() => {}}
        noticeLabel="Transition Facilitation Order 2026" singleScope
      />
    );
    expect(screen.queryByText(/All eligible clients/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Currently filtered view/)).not.toBeInTheDocument();
    expect(screen.getByText(/4 clients matching your current filters/)).toBeInTheDocument();
  });

  it("calls onConfirm with no scope argument when singleScope is set", () => {
    const onConfirm = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} filteredCount={4} onConfirm={onConfirm} onCancel={() => {}}
        noticeLabel="Transition Facilitation Order 2026" singleScope
      />
    );
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("defaults to today's exact renewal-alert wording when noticeLabel is not given", () => {
    render(<SendAllConfirmModal open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("Send bulk renewal alerts?")).toBeInTheDocument();
    expect(screen.getByText(/Send a real WhatsApp renewal alert to:/)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: FAIL — `noticeLabel`/`singleScope` don't exist as props yet.

- [ ] **Step 3: Add the two new props**

Current (`dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`):

```jsx
export default function SendAllConfirmModal({
  open, eligibleCount, filteredCount = 0, channel = "whatsapp", onConfirm, onCancel, job = null,
}) {
```

Replace with:

```jsx
export default function SendAllConfirmModal({
  open, eligibleCount, filteredCount = 0, channel = "whatsapp", onConfirm, onCancel, job = null,
  noticeLabel = null, singleScope = false,
}) {
```

Current:

```jsx
  const selectedCount = scope === "filtered" ? filteredCount : eligibleCount;

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm(scope);
  }
```

Replace with:

```jsx
  const selectedCount = singleScope ? filteredCount : (scope === "filtered" ? filteredCount : eligibleCount);

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm(singleScope ? undefined : scope);
  }
```

Current:

```jsx
        <h3 id="send-all-confirm-title" className="text-lg font-bold text-ink-primary mb-2">
          Send bulk renewal alerts?
        </h3>
```

Replace with:

```jsx
        <h3 id="send-all-confirm-title" className="text-lg font-bold text-ink-primary mb-2">
          {noticeLabel ? `Send "${noticeLabel}"?` : "Send bulk renewal alerts?"}
        </h3>
```

Current:

```jsx
          <>
            <p className="text-sm text-ink-secondary mb-3">
              {channel === "email" ? "Send a renewal email" : "Send a real WhatsApp renewal alert"} to:
            </p>
            <div className="mb-6 space-y-2">
              <label className="flex items-center gap-2 text-sm text-ink-primary">
                <input
                  ref={scopeAllRadioRef}
                  type="radio"
                  name="send-all-scope"
                  checked={scope === "all"}
                  onChange={() => setScope("all")}
                />
                All eligible clients (<strong>{eligibleCount}</strong>)
              </label>
              <label className="flex items-center gap-2 text-sm text-ink-primary">
                <input
                  ref={scopeFilteredRadioRef}
                  type="radio"
                  name="send-all-scope"
                  checked={scope === "filtered"}
                  onChange={() => setScope("filtered")}
                />
                Currently filtered view (<strong>{filteredCount}</strong>)
              </label>
            </div>
            <div className="flex justify-end gap-3">
```

Replace with:

```jsx
          <>
            <p className="text-sm text-ink-secondary mb-3">
              {noticeLabel
                ? `Send "${noticeLabel}" via ${channel === "email" ? "email" : "WhatsApp"}`
                : (channel === "email" ? "Send a renewal email" : "Send a real WhatsApp renewal alert")} to:
            </p>
            {singleScope ? (
              <p className="text-sm text-ink-secondary mb-6">
                {`${filteredCount} client${filteredCount === 1 ? "" : "s"} matching your current filters.`}
              </p>
            ) : (
              <div className="mb-6 space-y-2">
                <label className="flex items-center gap-2 text-sm text-ink-primary">
                  <input
                    ref={scopeAllRadioRef}
                    type="radio"
                    name="send-all-scope"
                    checked={scope === "all"}
                    onChange={() => setScope("all")}
                  />
                  All eligible clients (<strong>{eligibleCount}</strong>)
                </label>
                <label className="flex items-center gap-2 text-sm text-ink-primary">
                  <input
                    ref={scopeFilteredRadioRef}
                    type="radio"
                    name="send-all-scope"
                    checked={scope === "filtered"}
                    onChange={() => setScope("filtered")}
                  />
                  Currently filtered view (<strong>{filteredCount}</strong>)
                </label>
              </div>
            )}
            <div className="flex justify-end gap-3">
```

(Leave the Tab-focus-handling `useEffect` untouched — when `singleScope` is set, `scopeAllRadioRef.current`/`scopeFilteredRadioRef.current` are simply never attached to a rendered element, so they're already `null` and the existing `.filter(Boolean)` in that effect naturally excludes them from the focusable set without needing any change there.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: all passed, including every pre-existing test (all of them omit `noticeLabel`/`singleScope`, which default to `null`/`false` and preserve today's exact rendering and `onConfirm(scope)` call shape).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/SendAllConfirmModal.jsx dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx
git commit -m "feat: generalize SendAllConfirmModal for single-scope notice sends"
```

---

### Task 7: `NoticesView.jsx` — the Notices page

**Files:**
- Create: `dashboard-app/frontend/src/components/NoticesView.jsx`
- Create: `dashboard-app/frontend/src/components/NoticesView.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/NoticesView.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NoticesView from "./NoticesView";

function setup(overrides = {}) {
  const props = {
    listNotices: vi.fn().mockResolvedValue([
      { id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" },
    ]),
    getNoticeEligibleCount: vi.fn().mockResolvedValue({ whatsapp: 3, email: 3 }),
    sendNotice: vi.fn().mockResolvedValue({ job_id: "job-1" }),
    getNoticeSendStatus: vi.fn().mockResolvedValue({
      total: 3, sent: 3, skipped: 0, failed: 0, done: true,
    }),
    ...overrides,
  };
  return { ...render(<NoticesView {...props} />), props };
}

describe("NoticesView", () => {
  it("loads and shows the notice options", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("Transition Facilitation Order 2026")).toBeInTheDocument());
  });

  it("fetches the eligible count once a notice is selected", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(props.getNoticeEligibleCount).toHaveBeenCalledWith(
      "transition_facilitation_2026", expect.objectContaining({ scheme: "ALL" })
    ));
  });

  it("keeps the send buttons disabled until a notice is selected", async () => {
    setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    expect(screen.getByText("Send via WhatsApp")).toBeDisabled();
    expect(screen.getByText("Send via Email")).toBeDisabled();
  });

  it("enables the send buttons once a notice is selected", async () => {
    setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(screen.getByText("Send via WhatsApp")).not.toBeDisabled());
  });

  it("sends the notice via WhatsApp and shows progress through to done", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(screen.getByText("Send via WhatsApp")).not.toBeDisabled());

    fireEvent.click(screen.getByText("Send via WhatsApp"));
    await waitFor(() => screen.getByText("Confirm Send All"));
    fireEvent.click(screen.getByText("Confirm Send All"));

    await waitFor(() => expect(props.sendNotice).toHaveBeenCalledWith(
      "transition_facilitation_2026", "whatsapp", expect.objectContaining({ scheme: "ALL" })
    ));
    await waitFor(() => expect(screen.getByText(/3 sent, 0 skipped, 0 failed/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/NoticesView.test.jsx`
Expected: FAIL — `NoticesView.jsx` doesn't exist yet.

- [ ] **Step 3: Create `NoticesView.jsx`**

Create `dashboard-app/frontend/src/components/NoticesView.jsx`:

```jsx
import { useEffect, useRef, useState } from "react";
import ClientDataFilters from "./ClientDataFilters";
import SendAllConfirmModal from "./SendAllConfirmModal";

const JOB_POLL_MS = 500;

export default function NoticesView({
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, schemeOptions = [],
}) {
  const [notices, setNotices] = useState([]);
  const [selectedNoticeId, setSelectedNoticeId] = useState("");
  const [certType, setCertType] = useState("ALL");
  const [scheme, setScheme] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
  const [eligibleCount, setEligibleCount] = useState({ whatsapp: 0, email: 0 });
  const [whatsappModalOpen, setWhatsappModalOpen] = useState(false);
  const [whatsappJob, setWhatsappJob] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailJob, setEmailJob] = useState(null);
  const [error, setError] = useState(null);
  const jobPollRef = useRef(null);

  useEffect(() => {
    listNotices().then(setNotices).catch((err) => setError(err.message));
  }, [listNotices]);

  useEffect(() => {
    if (!selectedNoticeId) return;
    getNoticeEligibleCount(selectedNoticeId, { status, certType, scheme, expiryBefore })
      .then(setEligibleCount)
      .catch(() => {});
  }, [selectedNoticeId, status, certType, scheme, expiryBefore, getNoticeEligibleCount]);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);

  const selectedNotice = notices.find((n) => n.id === selectedNoticeId) || null;

  function handleClearAllFilters() {
    setStatus("ALL");
    setCertType("ALL");
    setScheme("ALL");
    setExpiryBefore("");
  }

  function startSend(channel, setModalOpen, setJob) {
    return async function handleConfirm() {
      try {
        const { job_id: jobId } = await sendNotice(selectedNoticeId, channel, {
          status, certType, scheme, expiryBefore,
        });
        setJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
        jobPollRef.current = setInterval(async () => {
          try {
            const jobStatus = await getNoticeSendStatus(selectedNoticeId, channel, jobId);
            setJob(jobStatus);
            if (jobStatus.done) {
              clearInterval(jobPollRef.current);
            }
          } catch (err) {
            clearInterval(jobPollRef.current);
            setJob(null);
            setModalOpen(false);
            setError(err.message);
          }
        }, JOB_POLL_MS);
      } catch (err) {
        setModalOpen(false);
        setError(err.message);
      }
    };
  }

  function closeModal(setModalOpen, setJob) {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    setJob(null);
    setModalOpen(false);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-ink-primary">Notices</h2>
        <p className="text-ink-secondary text-sm mt-1">
          Send a one-time broadcast announcement to clients matching your filters.
        </p>
      </div>

      {error && (
        <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-2">
          Which notice?
        </label>
        <select
          value={selectedNoticeId}
          onChange={(e) => setSelectedNoticeId(e.target.value)}
          aria-label="Which notice?"
          className="min-w-[280px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="" disabled>-- Select a notice --</option>
          {notices.map((n) => (
            <option key={n.id} value={n.id}>{n.label}</option>
          ))}
        </select>
      </div>

      <ClientDataFilters
        certOptions={[]}
        certType={certType}
        onCertTypeChange={setCertType}
        schemeOptions={schemeOptions}
        scheme={scheme}
        onSchemeChange={setScheme}
        expiryBefore={expiryBefore}
        onExpiryBeforeChange={setExpiryBefore}
        onClearAll={handleClearAllFilters}
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setWhatsappModalOpen(true)}
          disabled={!selectedNoticeId || (whatsappJob !== null && !whatsappJob.done)}
          className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
        >
          Send via WhatsApp
        </button>
        <button
          type="button"
          onClick={() => setEmailModalOpen(true)}
          disabled={!selectedNoticeId || (emailJob !== null && !emailJob.done)}
          className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/10 transition-colors disabled:opacity-50"
        >
          Send via Email
        </button>
      </div>

      <SendAllConfirmModal
        open={whatsappModalOpen}
        eligibleCount={eligibleCount.whatsapp}
        filteredCount={eligibleCount.whatsapp}
        channel="whatsapp"
        job={whatsappJob}
        noticeLabel={selectedNotice?.label}
        singleScope
        onConfirm={startSend("whatsapp", setWhatsappModalOpen, setWhatsappJob)}
        onCancel={() => closeModal(setWhatsappModalOpen, setWhatsappJob)}
      />
      <SendAllConfirmModal
        open={emailModalOpen}
        eligibleCount={eligibleCount.email}
        filteredCount={eligibleCount.email}
        channel="email"
        job={emailJob}
        noticeLabel={selectedNotice?.label}
        singleScope
        onConfirm={startSend("email", setEmailModalOpen, setEmailJob)}
        onCancel={() => closeModal(setEmailModalOpen, setEmailJob)}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/NoticesView.test.jsx`
Expected: all passed. If a test fails because `ClientDataFilters` requires props this file doesn't pass (read `ClientDataFilters.jsx`'s current prop list first to confirm), adjust the props passed above to match its real current signature.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/NoticesView.jsx dashboard-app/frontend/src/components/NoticesView.test.jsx
git commit -m "feat: add the Notices page"
```

---

### Task 8: Sidebar nav entry + `App.jsx` wiring

**Files:**
- Modify: `dashboard-app/frontend/src/components/Sidebar.jsx`
- Modify: `dashboard-app/frontend/src/components/Sidebar.test.jsx`
- Modify: `dashboard-app/frontend/src/App.jsx`

- [ ] **Step 1: Write the failing test**

Add to `dashboard-app/frontend/src/components/Sidebar.test.jsx`, after the existing "calls onNavigate for WhatsApp Settings" test:

```jsx
  it("calls onNavigate for Notices", () => {
    const onNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Notices"));
    expect(onNavigate).toHaveBeenCalledWith("notices");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/frontend && npx vitest run src/components/Sidebar.test.jsx`
Expected: FAIL — there's no "Notices" nav item yet.

- [ ] **Step 3: Add the nav item**

Current (`dashboard-app/frontend/src/components/Sidebar.jsx`):

```javascript
const ICONS = {
  dashboard: (
    <path d="M3 3h8v8H3V3zm10 0h8v5h-8V3zM3 13h8v8H3v-8zm10 3h8v5h-8v-5z" />
  ),
  clients: (
    <path d="M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H5z" />
  ),
  sync: (
    <path d="M17 2l4 4-4 4M3 12a9 9 0 0115-6.7M7 22l-4-4 4-4M21 12a9 9 0 01-15 6.7" />
  ),
  whatsapp: (
    <path d="M12 2a10 10 0 00-8.6 15.1L2 22l4.9-1.3A10 10 0 1012 2z" />
  ),
  log: (
    <path d="M4 6h16M4 12h16M4 18h10" />
  ),
  logout: (
    <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
  ),
};

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: "dashboard", view: "dashboard" },
  { key: "clients", label: "Client Data", icon: "clients", view: "clientData" },
  { key: "sync", label: "Excel Sync", icon: "sync", view: "excelSync" },
  { key: "whatsapp", label: "WhatsApp Settings", icon: "whatsapp", view: "whatsappSettings" },
  { key: "log", label: "Message Log", icon: "log", view: "messageLog" },
];
```

Replace with:

```javascript
const ICONS = {
  dashboard: (
    <path d="M3 3h8v8H3V3zm10 0h8v5h-8V3zM3 13h8v8H3v-8zm10 3h8v5h-8v-5z" />
  ),
  clients: (
    <path d="M12 12a4 4 0 100-8 4 4 0 000 8zm-7 8a7 7 0 0114 0H5z" />
  ),
  sync: (
    <path d="M17 2l4 4-4 4M3 12a9 9 0 0115-6.7M7 22l-4-4 4-4M21 12a9 9 0 01-15 6.7" />
  ),
  whatsapp: (
    <path d="M12 2a10 10 0 00-8.6 15.1L2 22l4.9-1.3A10 10 0 1012 2z" />
  ),
  log: (
    <path d="M4 6h16M4 12h16M4 18h10" />
  ),
  notices: (
    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />
  ),
  logout: (
    <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
  ),
};

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", icon: "dashboard", view: "dashboard" },
  { key: "clients", label: "Client Data", icon: "clients", view: "clientData" },
  { key: "sync", label: "Excel Sync", icon: "sync", view: "excelSync" },
  { key: "whatsapp", label: "WhatsApp Settings", icon: "whatsapp", view: "whatsappSettings" },
  { key: "log", label: "Message Log", icon: "log", view: "messageLog" },
  { key: "notices", label: "Notices", icon: "notices", view: "notices" },
];
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard-app/frontend && npx vitest run src/components/Sidebar.test.jsx`
Expected: all passed.

- [ ] **Step 5: Wire `NoticesView` into `App.jsx`**

Current (`dashboard-app/frontend/src/App.jsx`):

```javascript
import ExcelSyncView from "./components/ExcelSyncView";
import MessageLogView from "./components/MessageLogView";
import WhatsAppSettingsView from "./components/WhatsAppSettingsView";
```

Replace with:

```javascript
import ExcelSyncView from "./components/ExcelSyncView";
import MessageLogView from "./components/MessageLogView";
import WhatsAppSettingsView from "./components/WhatsAppSettingsView";
import NoticesView from "./components/NoticesView";
```

Current:

```javascript
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
} from "./api";
```

Replace with:

```javascript
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus,
} from "./api";
```

Current:

```javascript
          {activeView === "whatsappSettings" && <WhatsAppSettingsView fetchInfo={getSettingsInfo} />}
        </main>
```

Replace with:

```javascript
          {activeView === "whatsappSettings" && <WhatsAppSettingsView fetchInfo={getSettingsInfo} />}

          {activeView === "notices" && (
            <NoticesView
              listNotices={listNotices}
              getNoticeEligibleCount={getNoticeEligibleCount}
              sendNotice={sendNotice}
              getNoticeSendStatus={getNoticeSendStatus}
              schemeOptions={schemeOptions}
            />
          )}
        </main>
```

(`schemeOptions` here is the same `stats?.schemes || []` variable `App.jsx` already computes for the Client Data page's own `ClientDataFilters` — reused as-is, not recomputed, so Notices only ever offers a scheme as an audience filter if real data for it actually exists.)

- [ ] **Step 6: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/frontend/src/components/Sidebar.jsx dashboard-app/frontend/src/components/Sidebar.test.jsx dashboard-app/frontend/src/App.jsx
git commit -m "feat: wire the Notices page into the sidebar nav"
```

---

### Task 9: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all tests pass, zero regressions, with roughly 30 new tests added across Tasks 1-4.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Manual smoke test against a real dev server**

Start the backend (`cd dashboard-app/backend && python -m uvicorn main:app --port 8040`) and frontend (`cd dashboard-app/frontend && npm run dev`) locally. In the browser:
1. Confirm "Notices" appears in the sidebar and navigates to a page with a notice dropdown, the same filter bar used on Client Data, and two "Send via WhatsApp"/"Send via Email" buttons.
2. Select "Transition Facilitation Order 2026" and set Scheme = CRS — confirm the send buttons enable and no console errors appear.
3. Click "Send via Email" (safe to test for real, unlike WhatsApp, since email doesn't need Meta approval) against a small real or test CRS client list — confirm the confirmation modal shows the notice's own title/wording (not "Send bulk renewal alerts?"), a single client count (not two radio options), and after confirming, the progress reaches "done" with a sensible sent count.
4. Check the sent email's actual content (if you have a test inbox configured via `DASHBOARD_TEST_EMAIL`) — confirm it shows the Transition Facilitation Order content, not a renewal-alert email.
5. Click "Send via Email" again for the same notice/filters — confirm the eligible count for email drops to 0 and nothing gets sent twice (permanent dedup working).
6. Confirm "Send via WhatsApp" is visibly present but will 400/report "no template" until `WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME`/`_LANG` are set (expected, since that template isn't Meta-approved yet).

Expected: no console errors other than the expected WhatsApp no-template case; every step matches the description above.
