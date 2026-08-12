# Independence Day WhatsApp Broadcast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new, WhatsApp-only "ad-hoc" notice type that broadcasts to a one-time imported list of 2,692 raw phone numbers (no roster/client record behind them), completely separate from the existing roster-filtered Notices feature. Also fixes a real, confirmed problem found while scoping this: WhatsApp's Graph API returns a genuine success response (a real message_id) for far more sends than it actually counts as sent in its own analytics — confirmed directly via Meta's `template_analytics` API showing 244 real sent messages against 3,436 our system recorded as "sent" for the existing MeitY notice, a ~93% gap with no synchronous failure signal our code could have caught.

**Architecture:** A new `adhoc_recipients` MongoDB collection holds the imported phone numbers, keyed by notice_id. A new `notice_independence_day_2026.py` content module holds only WhatsApp template wiring (no email, no personalization). A new `send_adhoc_whatsapp_notice()` in `notice_sender.py` loops the raw phone list (not `get_broadcast_clients()`), reusing the existing `is_notice_already_sent`/`record_notice_sent` dedup functions with the phone number standing in for `client_id`. New `main.py` endpoints (list/count/send/status) mirror the existing notice-send job-polling pattern. A new minimal frontend section (no filters — nothing to filter by) renders inside the existing Notices page. Both the new ad-hoc sender and the pre-existing roster-based `send_notice_whatsapp` get a pacing delay between individual sends and a conservative real-world daily cap (not the 2,000/day messaging-tier ceiling, which is a legal upper bound, not the actually-sustainable rate this account has just demonstrated) — the likely cause of the silent-drop problem is bursty, unpaced sending triggering Meta's quality/abuse throttling well before that ceiling.

**Tech Stack:** FastAPI, MongoDB, WhatsApp Cloud API, React, pytest/mongomock, Vitest.

---

### Task 1: `db.py` — adhoc recipient storage functions

**Files:**
- Modify: `dashboard-app/backend/db.py`
- Modify: `dashboard-app/backend/test_db.py`

- [ ] **Step 1: Add the three new functions**

Add to `dashboard-app/backend/db.py`, after `load_notice_sent_log` (end of file):

```python


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
```

- [ ] **Step 2: Add tests**

Add to `dashboard-app/backend/test_db.py`, after `test_load_notice_sent_log_returns_every_recorded_entry` (or any convenient spot near the other notice-related tests):

```python
def test_get_adhoc_recipients_returns_phone_numbers_for_the_notice(mongo_db):
    init_db(mongo_db)
    mongo_db["adhoc_recipients"].insert_many([
        {"_id": "919876543210", "notice_id": "independence_day_2026", "source": "test"},
        {"_id": "919812345678", "notice_id": "independence_day_2026", "source": "test"},
        {"_id": "919800000000", "notice_id": "some_other_adhoc_notice", "source": "test"},
    ])

    result = get_adhoc_recipients(mongo_db, "independence_day_2026")

    assert set(result) == {"919876543210", "919812345678"}


def test_get_adhoc_recipient_count(mongo_db):
    init_db(mongo_db)
    mongo_db["adhoc_recipients"].insert_many([
        {"_id": "919876543210", "notice_id": "independence_day_2026", "source": "test"},
        {"_id": "919812345678", "notice_id": "independence_day_2026", "source": "test"},
    ])

    assert get_adhoc_recipient_count(mongo_db, "independence_day_2026") == 2
    assert get_adhoc_recipient_count(mongo_db, "does_not_exist") == 0


def test_get_adhoc_eligible_count_excludes_already_sent(mongo_db):
    init_db(mongo_db)
    mongo_db["adhoc_recipients"].insert_many([
        {"_id": "919876543210", "notice_id": "independence_day_2026", "source": "test"},
        {"_id": "919812345678", "notice_id": "independence_day_2026", "source": "test"},
    ])
    record_notice_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp", "wamid.ABC", "2026-08-11T10:00:00")

    assert get_adhoc_eligible_count(mongo_db, "independence_day_2026", "whatsapp") == 1
    # a different channel isn't affected by the whatsapp send above
    assert get_adhoc_eligible_count(mongo_db, "independence_day_2026", "email") == 2
```

- [ ] **Step 3: Update the `db.py` import line in `test_db.py`**

Find the import block in `test_db.py` that includes `load_notice_sent_log` (from Task 1 of the earlier Notice Log plan) and add the three new names:

```python
from db import (
    is_notice_already_sent, record_notice_sent, get_broadcast_clients, get_notice_eligible_count,
    load_notice_sent_log, get_adhoc_recipients, get_adhoc_recipient_count, get_adhoc_eligible_count,
)
```

- [ ] **Step 4: Run the tests**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -q -k adhoc`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/test_db.py
git commit -m "feat: add db.py functions for ad-hoc (roster-free) notice recipients"
```

---

### Task 2: Notice content module + registry

**Files:**
- Create: `dashboard-app/backend/notice_independence_day_2026.py`
- Modify: `dashboard-app/backend/notices.py`
- Modify: `dashboard-app/backend/test_notices.py`

- [ ] **Step 1: Write the content module**

Create `dashboard-app/backend/notice_independence_day_2026.py`:

```python
"""Content for the "Independence Day Special Offer" one-time WhatsApp-only
broadcast, sent to a flat imported list of phone numbers with no
corresponding roster/client record (see adhoc_recipients in db.py, and
import_adhoc_recipients.py which populates it). Unlike the roster-based
notices in this file's sibling modules, there is no build_email_html (this
notice is WhatsApp-only) and the message is fully static -- no
per-recipient personalization, since the phone list has no name/company
data to personalize with. The approved Meta template itself must have zero
body variables to match."""
import os


def get_whatsapp_template() -> tuple[str, str] | None:
    name = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME")
    lang = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG")
    if name and lang:
        return name, lang
    return None


def build_whatsapp_payload(to_phone: str, template_name: str, template_lang: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
        },
    }
```

- [ ] **Step 2: Extend the registry**

In `dashboard-app/backend/notices.py`, the current full file reads:

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
import notice_meity_series_guidelines_2026

NOTICES = {
    "meity_series_guidelines_2026": {
        "label": "MeitY Series Guidelines — IS/IEC 62368-1:2023",
        "module": notice_meity_series_guidelines_2026,
    },
}


def list_notices() -> list[dict]:
    return [{"id": notice_id, "label": entry["label"]} for notice_id, entry in NOTICES.items()]


def get_notice_module(notice_id: str):
    entry = NOTICES.get(notice_id)
    return entry["module"] if entry else None
```

Replace it with:

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

ADHOC_NOTICES is a separate, smaller registry for notices that target a
flat imported phone list (db.py's adhoc_recipients) instead of the roster --
those modules only implement get_whatsapp_template() and a
build_whatsapp_payload(to_phone, template_name, template_lang) that takes a
bare phone number, not a roster rec dict, since there's no roster record
behind these recipients at all.
"""
import notice_meity_series_guidelines_2026
import notice_independence_day_2026

NOTICES = {
    "meity_series_guidelines_2026": {
        "label": "MeitY Series Guidelines — IS/IEC 62368-1:2023",
        "module": notice_meity_series_guidelines_2026,
    },
}

ADHOC_NOTICES = {
    "independence_day_2026": {
        "label": "Independence Day Special Offer 2026",
        "module": notice_independence_day_2026,
    },
}


def list_notices() -> list[dict]:
    return [{"id": notice_id, "label": entry["label"]} for notice_id, entry in NOTICES.items()]


def get_notice_module(notice_id: str):
    entry = NOTICES.get(notice_id)
    return entry["module"] if entry else None


def list_adhoc_notices() -> list[dict]:
    return [{"id": notice_id, "label": entry["label"]} for notice_id, entry in ADHOC_NOTICES.items()]


def get_adhoc_notice_module(notice_id: str):
    entry = ADHOC_NOTICES.get(notice_id)
    return entry["module"] if entry else None
```

- [ ] **Step 3: Add tests**

Add to `dashboard-app/backend/test_notices.py`:

```python
import notice_independence_day_2026
from notices import list_adhoc_notices, get_adhoc_notice_module


def test_list_adhoc_notices_includes_independence_day_2026():
    notices = list_adhoc_notices()
    ids = {n["id"] for n in notices}
    assert "independence_day_2026" in ids


def test_get_adhoc_notice_module_returns_the_content_module():
    assert get_adhoc_notice_module("independence_day_2026") is notice_independence_day_2026


def test_get_adhoc_notice_module_returns_none_for_unknown_id():
    assert get_adhoc_notice_module("does_not_exist") is None
```

- [ ] **Step 4: Run the tests**

Run: `cd dashboard-app/backend && python -m pytest test_notices.py -q`
Expected: all pass (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/notice_independence_day_2026.py dashboard-app/backend/notices.py dashboard-app/backend/test_notices.py
git commit -m "feat: add Independence Day notice content module and adhoc notice registry"
```

---

### Task 3: Fix WhatsApp send pacing and the real daily limit on the existing roster-based notice sender

**Files:**
- Modify: `dashboard-app/backend/notice_sender.py`
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_notice_sender.py`

**Why this is here, not just in the new ad-hoc code:** the existing `send_notice_whatsapp()` (the MeitY notice) has no send-to-send pacing and no daily cap at all — it just loops every eligible client as fast as `requests.post` allows. Confirmed via Meta's own `template_analytics` API: this sent 3,436 requests that all returned a real `message_id` (a genuine synchronous success from Meta's API), but only 244 were actually counted as sent by Meta's own analytics — a ~93% silent loss with no failure our code could see. The likely cause is that bursty, unpaced sending trips Meta's quality/abuse throttling well before the account's nominal 2,000/day messaging-tier ceiling. Fixing only the new ad-hoc sender and leaving this one broken would just let the same problem recur the next time the MeitY notice is resumed.

- [ ] **Step 1: Add a shared pacing delay to `send_notice_whatsapp`**

In `dashboard-app/backend/notice_sender.py`, add `time` to the imports:

```python
import base64
import time
from datetime import datetime
```

Change the `send_notice_whatsapp` signature and add a pacing sleep right after each real (non-dry-run, non-duplicate-skip, non-no-template) send attempt — whether it succeeded or failed, since either way a real HTTP request just went to Meta and pacing is about not bursting requests, not about outcome:

```python
def send_notice_whatsapp(
    db_path, notice_id: str, token: str, phone_number_id: str,
    dry_run: bool = False, test_number: str | None = None, send_fn=send_message,
    on_progress=None, status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None, scheme: str | None = None,
    limit: int | None = None, pace_seconds: float = 0.0,
) -> list[dict]:
```

(`limit` is also new here — this function had no cap at all before. Same convention as `send_notice_email`'s existing `limit`: once hit, remaining eligible records are left completely untouched.)

Inside the `for rec in records:` loop, add the limit check at the top (mirroring `send_notice_email`'s existing pattern) and the pacing sleep after a real send attempt. The full updated loop body:

```python
    results = []
    sent_count = 0

    for rec in records:
        if limit is not None and sent_count >= limit:
            break

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
                    if pace_seconds:
                        time.sleep(pace_seconds)
                    if ok:
                        sent_count += 1
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
                    if pace_seconds:
                        time.sleep(pace_seconds)
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
```

This replaces the function's existing body from `records = get_broadcast_clients(...)` onward through its `return results` — the `records = get_broadcast_clients(...)` line itself and everything above it in the function (the `module = get_notice_module(...)` / `template = module.get_whatsapp_template()` setup) stay unchanged.

- [ ] **Step 2: Wire `limit` and `pace_seconds` into `main.py`'s existing job runner**

In `dashboard-app/backend/main.py`, find `_run_send_notice_whatsapp_job` and its call to `send_notice_whatsapp`:

```python
    try:
        send_notice_whatsapp(
            DEFAULT_DB_PATH, notice_id, token, phone_number_id,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
        )
```

Change it to:

```python
    try:
        send_notice_whatsapp(
            DEFAULT_DB_PATH, notice_id, token, phone_number_id,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
            limit=WHATSAPP_NOTICE_DAILY_LIMIT, pace_seconds=WHATSAPP_SEND_PACE_SECONDS,
        )
```

Add the two new module-level constants near the top of `main.py`, right after the existing `CERT_STATUS_THRESHOLDS` dict (or any similarly-placed constants block):

```python
# Meta's 2,000/24h messaging-tier figure is a legal ceiling, not a
# demonstrated-safe rate -- confirmed via Meta's own template_analytics API
# that unpaced bursts get silently throttled (a genuine message_id returned
# synchronously, but the message never actually counted as sent) long before
# that ceiling. Both figures are env-overridable without a redeploy in case
# the account's real sustainable rate turns out to be different once this
# is observed over a few real runs.
WHATSAPP_NOTICE_DAILY_LIMIT = int(os.environ.get("WHATSAPP_NOTICE_DAILY_LIMIT", "200"))
WHATSAPP_SEND_PACE_SECONDS = float(os.environ.get("WHATSAPP_SEND_PACE_SECONDS", "1.5"))
```

- [ ] **Step 3: Update tests**

In `dashboard-app/backend/test_notice_sender.py`, the existing `test_send_notice_whatsapp_sends_and_records_permanently` and similar tests call `send_notice_whatsapp` without `limit`/`pace_seconds` — both now default to `None`/`0.0` respectively, so **no existing test needs to change**. Add two new tests, near the existing WhatsApp notice tests:

```python
def test_send_notice_whatsapp_respects_limit(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    row_b = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
             "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    upsert_clients(db_path, [CRS_ROW, row_b], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_notice_whatsapp(
        db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS", limit=1,
    )

    assert len(results) == 1
    assert send_fn.call_count == 1
    from db import is_notice_already_sent
    assert is_notice_already_sent(db_path, "CLT002", "meity_series_guidelines_2026", "whatsapp") is False


def test_send_notice_whatsapp_paces_between_sends(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026_tpl")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")
    db_path = mongo_db
    row_b = ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
             "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE")
    upsert_clients(db_path, [CRS_ROW, row_b], mode="replace")
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    import time
    with patch("notice_sender.time.sleep") as mock_sleep:
        send_notice_whatsapp(
            db_path, "meity_series_guidelines_2026", "tok", "pid", send_fn=send_fn, scheme="CRS", pace_seconds=1.5,
        )

    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(1.5)
```

- [ ] **Step 4: Run the tests**

Run: `cd dashboard-app/backend && python -m pytest test_notice_sender.py test_main.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/notice_sender.py dashboard-app/backend/main.py dashboard-app/backend/test_notice_sender.py
git commit -m "fix: pace WhatsApp notice sends and cap at a real sustainable daily rate

Meta's own template_analytics API confirms unpaced bursts get silently
throttled -- a real message_id returned synchronously, but the message
never actually counted as sent (3,436 recorded vs 244 real, for the
existing MeitY notice). Adds a pacing delay between individual sends and
a conservative daily cap, both env-overridable, to send_notice_whatsapp --
the same fix the new ad-hoc sender gets from the start in this branch."
```

---

### Task 4: `notice_sender.py` — ad-hoc WhatsApp send orchestration

**Files:**
- Modify: `dashboard-app/backend/notice_sender.py`
- Modify: `dashboard-app/backend/test_notice_sender.py`

- [ ] **Step 1: Add the import**

In `dashboard-app/backend/notice_sender.py`, change:

```python
from db import get_broadcast_clients, is_notice_already_sent, record_notice_sent
from email_alerts import post_email_via_brevo, LOGO_PATH, LOGO_CID
from notices import get_notice_module
from whatsapp_renewal_alerts import normalize_phone, send_message
```

to:

```python
from db import get_broadcast_clients, get_adhoc_recipients, is_notice_already_sent, record_notice_sent
from email_alerts import post_email_via_brevo, LOGO_PATH, LOGO_CID
from notices import get_notice_module, get_adhoc_notice_module
from whatsapp_renewal_alerts import normalize_phone, send_message
```

- [ ] **Step 2: Add `send_adhoc_whatsapp_notice`**

Add to the end of `dashboard-app/backend/notice_sender.py`:

```python


def send_adhoc_whatsapp_notice(
    db_path, notice_id: str, token: str, phone_number_id: str,
    dry_run: bool = False, test_number: str | None = None, send_fn=send_message,
    on_progress=None, limit: int | None = None, pace_seconds: float = 0.0,
) -> list[dict]:
    """Sends a fully static (no personalization) WhatsApp template to every
    phone number imported for this notice_id via adhoc_recipients. Unlike
    send_notice_whatsapp, there's no roster client behind these numbers --
    just a bare phone number, no name/company to build a payload around --
    so this doesn't call get_broadcast_clients or module.build_whatsapp_payload(rec, ...)
    the way the roster-based sender does.

    limit caps real sends per call -- once hit, remaining recipients are
    left completely untouched (not attempted). pace_seconds sleeps between
    each real send attempt. Both exist because Meta's own template_analytics
    API confirmed unpaced bursts get silently throttled (a genuine
    message_id returned synchronously, but never actually counted as sent)
    well before this account's nominal 2,000/24h messaging-tier ceiling --
    see send_notice_whatsapp's docstring for the full finding."""
    module = get_adhoc_notice_module(notice_id)
    if module is None:
        raise ValueError(f"Unknown adhoc notice_id: {notice_id!r}")

    template = module.get_whatsapp_template()
    phone_numbers = get_adhoc_recipients(db_path, notice_id)
    results = []
    sent_count = 0

    for phone in phone_numbers:
        if limit is not None and sent_count >= limit:
            break

        to_phone = normalize_phone(test_number) if test_number else phone

        if not test_number and is_notice_already_sent(db_path, phone, notice_id, "whatsapp"):
            result = {"phone": phone, "action": "skipped_duplicate", "to": to_phone}
        elif template is None:
            result = {"phone": phone, "action": "skipped_no_template", "to": to_phone}
        else:
            template_name, template_lang = template
            payload = module.build_whatsapp_payload(to_phone, template_name, template_lang)
            if dry_run:
                result = {"phone": phone, "action": "dry_run", "to": to_phone, "payload": payload}
            else:
                try:
                    ok, info = send_fn(payload, token, phone_number_id)
                    if pace_seconds:
                        time.sleep(pace_seconds)
                    if ok:
                        sent_count += 1
                        if not test_number:
                            record_notice_sent(
                                db_path, phone, notice_id, "whatsapp",
                                info.get("message_id"), datetime.now().isoformat(),
                            )
                        result = {
                            "phone": phone, "action": "sent",
                            "to": to_phone, "message_id": info.get("message_id"),
                        }
                    else:
                        result = {
                            "phone": phone, "action": "failed",
                            "to": to_phone, "error": info.get("error"),
                        }
                except Exception as exc:
                    if pace_seconds:
                        time.sleep(pace_seconds)
                    result = {"phone": phone, "action": "failed", "to": to_phone, "error": str(exc)}

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(phone_numbers))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    return results
```

- [ ] **Step 3: Add tests**

`test_notice_sender.py`'s existing top-of-file imports already include `record_notice_sent` (line 4: `from db import upsert_clients, record_notice_sent`) — no change needed there. Change line 5 from:

```python
from notice_sender import send_notice_whatsapp, send_notice_email
```

to:

```python
from notice_sender import send_notice_whatsapp, send_notice_email, send_adhoc_whatsapp_notice
```

Then add the following to `dashboard-app/backend/test_notice_sender.py`, anywhere after the imports (e.g. at the end of the file):

```python
def _seed_adhoc_recipients(db, notice_id, phones):
    db["adhoc_recipients"].insert_many([
        {"_id": phone, "notice_id": notice_id, "source": "test"} for phone in phones
    ])


def test_send_adhoc_whatsapp_notice_skips_when_no_template_configured(monkeypatch, mongo_db):
    monkeypatch.delenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", raising=False)
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock()

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()


def test_send_adhoc_whatsapp_notice_sends_and_records_permanently(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    assert results[0]["action"] == "sent"
    assert results[0]["phone"] == "919876543210"
    from db import is_notice_already_sent
    assert is_notice_already_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp") is True


def test_send_adhoc_whatsapp_notice_skips_phone_already_sent_to(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    record_notice_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp", "wamid.OLD", "2026-08-01T10:00:00")
    send_fn = Mock()

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    assert results[0]["action"] == "skipped_duplicate"
    send_fn.assert_not_called()


def test_send_adhoc_whatsapp_notice_builds_payload_with_no_personalization(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn)

    payload = send_fn.call_args[0][0]
    assert payload["template"]["name"] == "independence_day_2026_offer"
    assert "components" not in payload["template"]


def test_send_adhoc_whatsapp_notice_respects_limit(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210", "919812345678", "919800000000"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = send_adhoc_whatsapp_notice(mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn, limit=1)

    assert len(results) == 1
    assert send_fn.call_count == 1
    from db import is_notice_already_sent
    remaining_untouched = sum(
        1 for phone in ["919812345678", "919800000000"]
        if is_notice_already_sent(mongo_db, phone, "independence_day_2026", "whatsapp") is False
    )
    assert remaining_untouched == 2


def test_send_adhoc_whatsapp_notice_test_number_does_not_persist_dedup(monkeypatch, mongo_db):
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME", "independence_day_2026_offer")
    monkeypatch.setenv("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG", "en")
    _seed_adhoc_recipients(mongo_db, "independence_day_2026", ["919876543210"])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.TEST"}))

    results = send_adhoc_whatsapp_notice(
        mongo_db, "independence_day_2026", "tok", "pid", send_fn=send_fn, test_number="919999999999",
    )

    assert results[0]["action"] == "sent"
    assert results[0]["to"] == "919999999999"
    from db import is_notice_already_sent
    assert is_notice_already_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp") is False
```

Remove the throwaway `_unused_import_check` line above once you've confirmed the file's existing imports already include `record_notice_sent` (they do, per the file's current top-of-file import from `db`) — it was only a placeholder note for whoever executes this task, not something to actually leave in the file.

- [ ] **Step 4: Run the tests**

Run: `cd dashboard-app/backend && python -m pytest test_notice_sender.py -q`
Expected: all pass (existing 13 + 6 new = 19).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/notice_sender.py dashboard-app/backend/test_notice_sender.py
git commit -m "feat: add send_adhoc_whatsapp_notice for phone-list-only broadcasts"
```

---

### Task 5: `main.py` — endpoints

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Update imports**

Change:

```python
from notices import list_notices, get_notice_module  # noqa: E402
from notice_sender import send_notice_whatsapp, send_notice_email  # noqa: E402
```

to:

```python
from notices import list_notices, get_notice_module, list_adhoc_notices, get_adhoc_notice_module  # noqa: E402
from notice_sender import send_notice_whatsapp, send_notice_email, send_adhoc_whatsapp_notice  # noqa: E402
```

Also change the existing `from db import (...)` block's last import line from:

```python
    load_notice_sent_log, find_clients_by_ids,
)
```

to:

```python
    load_notice_sent_log, find_clients_by_ids, get_adhoc_recipient_count, get_adhoc_eligible_count,
)
```

- [ ] **Step 2: Add the endpoints**

Add to `dashboard-app/backend/main.py`, immediately after `send_notice_email_status` and before `@app.get("/api/client-template")`:

```python


_send_adhoc_notice_jobs: dict[str, dict] = {}


def _run_send_adhoc_whatsapp_job(job_id, notice_id, lock_key, token, phone_number_id, test_number, limit, pace_seconds):
    def progress(result, total):
        job = _send_adhoc_notice_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "skipped_no_template":
            job["skipped_no_template"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1
            print(f"⚠ send failed for {result['phone']} ({result.get('to')}): {result.get('error')}")

    try:
        send_adhoc_whatsapp_notice(
            DEFAULT_DB_PATH, notice_id, token, phone_number_id,
            dry_run=False, test_number=test_number, on_progress=progress,
            limit=limit, pace_seconds=pace_seconds,
        )
    except Exception as exc:
        _send_adhoc_notice_jobs[job_id]["error"] = str(exc)
    finally:
        _send_adhoc_notice_jobs[job_id]["done"] = True
        with _notice_send_lock:
            _notice_sends_in_progress.discard(lock_key)


@app.get("/api/adhoc-notices")
def adhoc_notices_list():
    return list_adhoc_notices()


@app.get("/api/adhoc-notices/{notice_id}/count")
def adhoc_notice_count(notice_id: str):
    if get_adhoc_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown adhoc notice_id: {notice_id}")
    return {
        "total": get_adhoc_recipient_count(DEFAULT_DB_PATH, notice_id),
        "not_yet_sent": get_adhoc_eligible_count(DEFAULT_DB_PATH, notice_id, "whatsapp"),
    }


@app.post("/api/adhoc-notices/{notice_id}/send-whatsapp")
def send_adhoc_notice_whatsapp_endpoint(notice_id: str):
    if get_adhoc_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown adhoc notice_id: {notice_id}")

    lock_key = f"adhoc:{notice_id}:whatsapp"
    with _notice_send_lock:
        if lock_key in _notice_sends_in_progress:
            raise HTTPException(status_code=409, detail="A send for this notice is already in progress")
        _notice_sends_in_progress.add(lock_key)

    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        job_id = str(uuid.uuid4())
        _send_adhoc_notice_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "skipped_no_template": 0, "failed": 0,
            "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_adhoc_whatsapp_job,
            args=(
                job_id, notice_id, lock_key, token, phone_number_id, test_number,
                WHATSAPP_NOTICE_DAILY_LIMIT, WHATSAPP_SEND_PACE_SECONDS,
            ),
            daemon=True,
        )
        thread.start()
        return {"job_id": job_id}
    except Exception:
        with _notice_send_lock:
            _notice_sends_in_progress.discard(lock_key)
        raise HTTPException(status_code=500, detail="Server is not configured to send WhatsApp messages")


@app.get("/api/adhoc-notices/{notice_id}/send-whatsapp/status/{job_id}")
def send_adhoc_notice_whatsapp_status(notice_id: str, job_id: str):
    job = _send_adhoc_notice_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job
```

Reuses `WHATSAPP_NOTICE_DAILY_LIMIT`/`WHATSAPP_SEND_PACE_SECONDS` (added to `main.py` in Task 3, Step 2) rather than a separate ad-hoc-specific limit — it's the same WhatsApp Business Account and the same demonstrated throttling behavior regardless of which notice is sending, so one shared, env-overridable pair of constants is more honest than inventing a second number with no real basis.

- [ ] **Step 3: Add tests**

Add to `dashboard-app/backend/test_main.py`:

```python
def test_adhoc_notices_list_includes_independence_day_2026():
    response = client.get("/api/adhoc-notices")
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()}
    assert "independence_day_2026" in ids


def test_adhoc_notice_count_unknown_notice_returns_404():
    response = client.get("/api/adhoc-notices/does_not_exist/count")
    assert response.status_code == 404


def test_adhoc_notice_count_returns_total_and_not_yet_sent(tmp_path, monkeypatch, mongo_db):
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", mongo_db)
    mongo_db["adhoc_recipients"].insert_many([
        {"_id": "919876543210", "notice_id": "independence_day_2026", "source": "test"},
        {"_id": "919812345678", "notice_id": "independence_day_2026", "source": "test"},
    ])
    from db import record_notice_sent
    record_notice_sent(mongo_db, "919876543210", "independence_day_2026", "whatsapp", "wamid.ABC", "2026-08-11T10:00:00")

    response = client.get("/api/adhoc-notices/independence_day_2026/count")
    assert response.status_code == 200
    assert response.json() == {"total": 2, "not_yet_sent": 1}


def test_send_adhoc_notice_whatsapp_unknown_notice_returns_404(tmp_path, monkeypatch, mongo_db):
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", mongo_db)
    response = client.post("/api/adhoc-notices/does_not_exist/send-whatsapp")
    assert response.status_code == 404


def test_send_adhoc_notice_whatsapp_status_unknown_job_returns_404():
    response = client.get("/api/adhoc-notices/independence_day_2026/send-whatsapp/status/does-not-exist")
    assert response.status_code == 404
```

- [ ] **Step 4: Run the tests**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -q -k adhoc`
Expected: all pass.

- [ ] **Step 5: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add /api/adhoc-notices endpoints for phone-list broadcasts"
```

---

### Task 6: One-time data import script

**Files:**
- Create: `dashboard-app/backend/import_adhoc_recipients.py`

- [ ] **Step 1: Write the script**

Create `dashboard-app/backend/import_adhoc_recipients.py`:

```python
"""One-time import: loads a flat phone-number list into the adhoc_recipients
collection for a given ad-hoc notice_id. Not part of any app code path --
run once by hand, per docs/superpowers/specs/2026-08-11-independence-day-whatsapp-broadcast-design.md.

Usage: python import_adhoc_recipients.py "<path to xlsx>" <notice_id>

Expects a sheet named "Numbers" with a "Digits Only" column (matches
Numbers_Only_Deduplicated.xlsx's actual format) and a "Source" column.
Any other sheet (e.g. "Needs Review") is ignored -- this only reads the
"Numbers" sheet."""
import sys

import openpyxl

from db import DEFAULT_DB_PATH
from whatsapp_renewal_alerts import normalize_phone


def import_adhoc_recipients(source_path: str, notice_id: str) -> dict:
    wb = openpyxl.load_workbook(source_path, read_only=True, data_only=True)
    ws = wb["Numbers"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    index_map = {str(h).strip().lower(): i for i, h in enumerate(header) if h is not None}

    digits_idx = index_map["digits only"]
    source_idx = index_map.get("source")

    docs = []
    seen = set()
    skipped_blank = 0
    for row in rows:
        raw = row[digits_idx]
        if not raw:
            skipped_blank += 1
            continue
        phone = normalize_phone(raw)
        if not phone or phone in seen:
            continue
        seen.add(phone)
        docs.append({
            "_id": phone,
            "notice_id": notice_id,
            "source": row[source_idx] if source_idx is not None else None,
        })

    wb.close()

    db = DEFAULT_DB_PATH
    if docs:
        db["adhoc_recipients"].delete_many({"notice_id": notice_id})
        db["adhoc_recipients"].insert_many(docs)

    return {"imported": len(docs), "skipped_blank": skipped_blank}


def demo():
    """Self-check: import logic against an in-memory mongomock database and
    a tiny in-memory workbook, no real file or real database needed."""
    import mongomock
    import db as db_module

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Numbers"
    ws.append(["S.No", "Name", "Phone Number", "Digits Only", "Source"])
    ws.append([1, None, "919876543210", "919876543210", "WhatsApp broadcast list"])
    ws.append([2, None, "0091 98123 45678", "009198123 45678", "WhatsApp broadcast list"])  # exercises the 00-prefix strip
    ws.append([3, None, None, None, "WhatsApp broadcast list"])  # blank row, must be skipped
    wb.save("_demo_adhoc_import.xlsx")

    original_db_path = db_module.DEFAULT_DB_PATH
    db_module.DEFAULT_DB_PATH = mongomock.MongoClient()["demo"]
    try:
        result = import_adhoc_recipients("_demo_adhoc_import.xlsx", "demo_notice")
        assert result == {"imported": 2, "skipped_blank": 1}, result
        stored = list(db_module.DEFAULT_DB_PATH["adhoc_recipients"].find({"notice_id": "demo_notice"}))
        ids = {d["_id"] for d in stored}
        assert ids == {"919876543210", "9198123 45678".replace(" ", "")}, ids
        print("demo() self-check passed:", result)
    finally:
        db_module.DEFAULT_DB_PATH = original_db_path
        import os
        os.remove("_demo_adhoc_import.xlsx")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        demo()
    elif len(sys.argv) == 3:
        source, notice_id = sys.argv[1], sys.argv[2]
        result = import_adhoc_recipients(source, notice_id)
        print(f"Imported {result['imported']} recipients for notice_id={notice_id!r} "
              f"(skipped {result['skipped_blank']} blank rows).")
    else:
        print("Usage: python import_adhoc_recipients.py \"<path to xlsx>\" <notice_id>")
        print("       python import_adhoc_recipients.py   (no args runs the self-check demo)")
        sys.exit(1)
```

- [ ] **Step 2: Run the self-check**

Run: `cd dashboard-app/backend && python import_adhoc_recipients.py`
Expected: prints `demo() self-check passed: {'imported': 2, 'skipped_blank': 1}` and exits 0.

- [ ] **Step 3: Run the real import**

Run: `cd dashboard-app/backend && python import_adhoc_recipients.py "C:\Users\dhruv\OneDrive\Desktop\Numbers_Only_Deduplicated.xlsx" independence_day_2026`
Expected: prints `Imported 2692 recipients for notice_id='independence_day_2026' (skipped 0 blank rows).` — if the count differs from 2692, stop and check why before proceeding (e.g. confirm you're not accidentally re-running against a file with a different row count than the one inspected during design).

- [ ] **Step 4: Verify directly against the real database**

Run: `cd dashboard-app/backend && python3 -c "from db import DEFAULT_DB_PATH; print(DEFAULT_DB_PATH['adhoc_recipients'].count_documents({'notice_id': 'independence_day_2026'}))"`
Expected: `2692`.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/import_adhoc_recipients.py
git commit -m "feat: add one-time import script for the Independence Day phone list"
```

(This commits the script, not the imported data itself — the data lives only in MongoDB, same as every other client record in this app.)

---

### Task 7: Frontend — minimal send UI

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`
- Create: `dashboard-app/frontend/src/components/AdhocNoticeBroadcast.jsx`
- Create: `dashboard-app/frontend/src/components/AdhocNoticeBroadcast.test.jsx`
- Modify: `dashboard-app/frontend/src/components/NoticesView.jsx`
- Modify: `dashboard-app/frontend/src/App.jsx`

- [ ] **Step 1: Add API functions**

Add to `dashboard-app/frontend/src/api.js`, after `getNoticeSendStatus` (end of file):

```js

export async function listAdhocNotices() {
  const res = await fetch(`${API_BASE}/api/adhoc-notices`, { credentials: "include", headers: {} });
  if (!res.ok) throw new Error(`Failed to load adhoc notices: ${res.status}`);
  return res.json();
}

export async function getAdhocNoticeCount(noticeId) {
  const res = await fetch(`${API_BASE}/api/adhoc-notices/${noticeId}/count`, {
    credentials: "include", headers: {},
  });
  if (!res.ok) throw new Error(`Failed to load adhoc notice count: ${res.status}`);
  return res.json();
}

export async function sendAdhocNotice(noticeId) {
  const res = await fetch(`${API_BASE}/api/adhoc-notices/${noticeId}/send-whatsapp`, {
    method: "POST", credentials: "include", headers: {},
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send failed: ${res.status}`);
  }
  return data;
}

export async function getAdhocNoticeSendStatus(noticeId, jobId) {
  const res = await fetch(`${API_BASE}/api/adhoc-notices/${noticeId}/send-whatsapp/status/${jobId}`, {
    credentials: "include", headers: {},
  });
  if (!res.ok) throw new Error(`Failed to load adhoc notice send status: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Add API tests**

Add to `dashboard-app/frontend/src/api.test.js`:

```js
describe("listAdhocNotices", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true, json: async () => [{ id: "independence_day_2026", label: "Independence Day Special Offer 2026" }],
    });
    const notices = await listAdhocNotices();
    expect(notices).toEqual([{ id: "independence_day_2026", label: "Independence Day Special Offer 2026" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/adhoc-notices", { credentials: "include", headers: {} });
  });
});

describe("getAdhocNoticeCount", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ total: 2692, not_yet_sent: 2692 }) });
    const count = await getAdhocNoticeCount("independence_day_2026");
    expect(count).toEqual({ total: 2692, not_yet_sent: 2692 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/adhoc-notices/independence_day_2026/count", { credentials: "include", headers: {} }
    );
  });
});

describe("sendAdhocNotice", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "job-1" }) });
    const result = await sendAdhocNotice("independence_day_2026");
    expect(result).toEqual({ job_id: "job-1" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/adhoc-notices/independence_day_2026/send-whatsapp",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: "already in progress" }) });
    await expect(sendAdhocNotice("independence_day_2026")).rejects.toThrow("already in progress");
  });
});

describe("getAdhocNoticeSendStatus", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true, json: async () => ({ total: 2692, sent: 300, skipped: 0, skipped_no_template: 0, failed: 0, done: false }),
    });
    const status = await getAdhocNoticeSendStatus("independence_day_2026", "job-1");
    expect(status.sent).toBe(300);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/adhoc-notices/independence_day_2026/send-whatsapp/status/job-1",
      { credentials: "include", headers: {} }
    );
  });
});
```

Also add the 4 new function names to the existing `import { ... } from "./api";` block at the top of `api.test.js`.

- [ ] **Step 3: Run the API tests**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all pass.

- [ ] **Step 4: Write the `AdhocNoticeBroadcast` component**

Create `dashboard-app/frontend/src/components/AdhocNoticeBroadcast.jsx`:

```jsx
import { useEffect, useRef, useState } from "react";
import SendAllConfirmModal from "./SendAllConfirmModal";

const JOB_POLL_MS = 500;

export default function AdhocNoticeBroadcast({
  listAdhocNotices, getAdhocNoticeCount, sendAdhocNotice, getAdhocNoticeSendStatus,
}) {
  const [notices, setNotices] = useState([]);
  const [counts, setCounts] = useState({});
  const [error, setError] = useState(null);
  const [modalNoticeId, setModalNoticeId] = useState(null);
  const [job, setJob] = useState(null);
  const jobPollRef = useRef(null);

  function loadCounts(noticeList) {
    noticeList.forEach((n) => {
      getAdhocNoticeCount(n.id)
        .then((count) => setCounts((prev) => ({ ...prev, [n.id]: count })))
        .catch(() => {});
    });
  }

  useEffect(() => {
    listAdhocNotices()
      .then((data) => {
        setNotices(data);
        loadCounts(data);
      })
      .catch((err) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listAdhocNotices]);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);

  function openModal(noticeId) {
    setModalNoticeId(noticeId);
  }

  function closeModal() {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    setJob(null);
    setModalNoticeId(null);
    if (modalNoticeId) {
      getAdhocNoticeCount(modalNoticeId)
        .then((count) => setCounts((prev) => ({ ...prev, [modalNoticeId]: count })))
        .catch(() => {});
    }
  }

  async function handleConfirm() {
    try {
      const { job_id: jobId } = await sendAdhocNotice(modalNoticeId);
      setJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
      jobPollRef.current = setInterval(async () => {
        try {
          const jobStatus = await getAdhocNoticeSendStatus(modalNoticeId, jobId);
          setJob(jobStatus);
          if (jobStatus.done) {
            clearInterval(jobPollRef.current);
          }
        } catch (err) {
          clearInterval(jobPollRef.current);
          setJob(null);
          setModalNoticeId(null);
          setError(err.message);
        }
      }, JOB_POLL_MS);
    } catch (err) {
      setModalNoticeId(null);
      setError(err.message);
    }
  }

  if (notices.length === 0 && !error) return null;

  const activeNotice = notices.find((n) => n.id === modalNoticeId);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-bold text-ink-primary">Ad-Hoc WhatsApp Broadcasts</h3>
        <p className="text-ink-secondary text-sm mt-1">
          One-time sends to an imported phone list — no roster filtering, since these numbers have no client record.
        </p>
      </div>

      {error && (
        <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {notices.map((n) => {
        const count = counts[n.id];
        return (
          <div key={n.id} className="bg-surface border border-line rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="font-semibold text-ink-primary">{n.label}</p>
              {count && (
                <p className="text-sm text-ink-secondary mt-1">
                  {count.not_yet_sent} of {count.total} haven't received this yet
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => openModal(n.id)}
              disabled={!count || count.not_yet_sent === 0}
              className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
            >
              Send via WhatsApp
            </button>
          </div>
        );
      })}

      <SendAllConfirmModal
        open={modalNoticeId !== null}
        eligibleCount={counts[modalNoticeId]?.not_yet_sent || 0}
        filteredCount={counts[modalNoticeId]?.not_yet_sent || 0}
        channel="whatsapp"
        job={job}
        noticeLabel={activeNotice?.label}
        singleScope
        onConfirm={handleConfirm}
        onCancel={closeModal}
      />
    </div>
  );
}
```

- [ ] **Step 5: Write the component's tests**

Create `dashboard-app/frontend/src/components/AdhocNoticeBroadcast.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AdhocNoticeBroadcast from "./AdhocNoticeBroadcast";

function setup(overrides = {}) {
  const props = {
    listAdhocNotices: vi.fn().mockResolvedValue([
      { id: "independence_day_2026", label: "Independence Day Special Offer 2026" },
    ]),
    getAdhocNoticeCount: vi.fn().mockResolvedValue({ total: 2692, not_yet_sent: 2692 }),
    sendAdhocNotice: vi.fn().mockResolvedValue({ job_id: "job-1" }),
    getAdhocNoticeSendStatus: vi.fn().mockResolvedValue({
      total: 2692, sent: 2692, skipped: 0, failed: 0, done: true,
    }),
    ...overrides,
  };
  return { ...render(<AdhocNoticeBroadcast {...props} />), props };
}

describe("AdhocNoticeBroadcast", () => {
  it("shows the notice label and recipient counts", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("Independence Day Special Offer 2026")).toBeInTheDocument());
    expect(screen.getByText("2692 of 2692 haven't received this yet")).toBeInTheDocument();
  });

  it("renders nothing when there are no ad-hoc notices", async () => {
    const { container } = setup({ listAdhocNotices: vi.fn().mockResolvedValue([]) });
    await waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("opens the confirm modal and starts a send on confirm", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByText("Send via WhatsApp"));
    fireEvent.click(screen.getByText("Send via WhatsApp"));
    await waitFor(() => screen.getByText(/Independence Day Special Offer 2026/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(props.sendAdhocNotice).toHaveBeenCalledWith("independence_day_2026"));
    await waitFor(() => expect(screen.getByText(/2692 sent/)).toBeInTheDocument());
  });

  it("disables the send button when nothing is left to send", async () => {
    setup({ getAdhocNoticeCount: vi.fn().mockResolvedValue({ total: 2692, not_yet_sent: 0 }) });
    await waitFor(() => screen.getByText("Send via WhatsApp"));
    expect(screen.getByText("Send via WhatsApp")).toBeDisabled();
  });
});
```

- [ ] **Step 6: Wire into `NoticesView.jsx`**

In `dashboard-app/frontend/src/components/NoticesView.jsx`, add the import:

```jsx
import AdhocNoticeBroadcast from "./AdhocNoticeBroadcast";
```

Add 4 new props to the component signature:

```jsx
export default function NoticesView({
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  getNoticeClients,
  listAdhocNotices, getAdhocNoticeCount, sendAdhocNotice, getAdhocNoticeSendStatus,
  schemeOptions = [], certOptions = [],
}) {
```

Render the new section at the end of the returned JSX, right before the closing `</div>` of the outermost `<div className="space-y-6">` (after the existing `SendAllConfirmModal` pair for the roster-based notice, i.e. as the very last thing in the component):

```jsx
      <div className="pt-4 border-t border-line">
        <AdhocNoticeBroadcast
          listAdhocNotices={listAdhocNotices}
          getAdhocNoticeCount={getAdhocNoticeCount}
          sendAdhocNotice={sendAdhocNotice}
          getAdhocNoticeSendStatus={getAdhocNoticeSendStatus}
        />
      </div>
```

- [ ] **Step 7: Wire into `App.jsx`**

Update the import block:

```js
import {
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getNoticeLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  getNoticeClients, listAdhocNotices, getAdhocNoticeCount, sendAdhocNotice, getAdhocNoticeSendStatus,
} from "./api";
```

Update the `<NoticesView>` render call:

```jsx
          {activeView === "notices" && (

<NoticesView
              listNotices={listNotices}
              getNoticeEligibleCount={getNoticeEligibleCount}
              sendNotice={sendNotice}
              getNoticeSendStatus={getNoticeSendStatus}
              getNoticePreview={getNoticePreview}
              getNoticeClients={getNoticeClients}
              listAdhocNotices={listAdhocNotices}
              getAdhocNoticeCount={getAdhocNoticeCount}
              sendAdhocNotice={sendAdhocNotice}
              getAdhocNoticeSendStatus={getAdhocNoticeSendStatus}
              schemeOptions={schemeOptions}
              certOptions={certOptions}
            />
          )}
```

- [ ] **Step 8: Update existing `NoticesView.test.jsx`'s `setup()` helper**

Its `setup(overrides)` helper builds a `props` object and spreads `...overrides` last, so it already tolerates new required-in-practice-but-optional-in-tests props being absent (React just renders `AdhocNoticeBroadcast` with `undefined` fetch functions) — **but** `AdhocNoticeBroadcast` will then call `listAdhocNotices()` as a function and throw, since `undefined` isn't callable. Add the 4 new no-op mocks to the existing `setup()` helper's default `props` object in `dashboard-app/frontend/src/components/NoticesView.test.jsx`:

```js
    listAdhocNotices: vi.fn().mockResolvedValue([]),
    getAdhocNoticeCount: vi.fn().mockResolvedValue({ total: 0, not_yet_sent: 0 }),
    sendAdhocNotice: vi.fn().mockResolvedValue({ job_id: "adhoc-job-1" }),
    getAdhocNoticeSendStatus: vi.fn().mockResolvedValue({ total: 0, sent: 0, skipped: 0, failed: 0, done: true }),
```

(Returning an empty list from `listAdhocNotices` keeps `AdhocNoticeBroadcast` rendering `null` for all of `NoticesView.test.jsx`'s existing tests, which know nothing about this new section and shouldn't need to.)

- [ ] **Step 9: Run the frontend test suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js \
  dashboard-app/frontend/src/components/AdhocNoticeBroadcast.jsx \
  dashboard-app/frontend/src/components/AdhocNoticeBroadcast.test.jsx \
  dashboard-app/frontend/src/components/NoticesView.jsx \
  dashboard-app/frontend/src/components/NoticesView.test.jsx \
  dashboard-app/frontend/src/App.jsx
git commit -m "feat: add minimal Ad-Hoc WhatsApp Broadcast UI to the Notices page"
```

---

### Task 8: Final verification

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all pass.

- [ ] **Step 3: Manual smoke test against local dev**

The template is already approved (confirmed directly via Meta's Graph API: `independence_day_2026_offer`, `status: APPROVED`, `category: MARKETING`, id `4474587969457169`) — so unlike a typical first run, real sends are possible as soon as the env vars are set. Be deliberate about that.

With both local dev servers running and the real import (Task 6) already done against the real database:
1. Open the Notices page — confirm a new "Ad-Hoc WhatsApp Broadcasts" section appears below the existing MeitY notice UI, showing "Independence Day Special Offer 2026" with a real recipient count (should read close to "2692 of 2692 haven't received this yet" if this is the first time).
2. Set `WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME=independence_day_2026_offer` and `WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG=en` in local `.env` (matching the approved template exactly).
3. Set `DASHBOARD_TEST_NUMBER` in local `.env` to a real number you control, if not already set — this redirects every send to that number instead of the real list, same safeguard used throughout this project.
4. Restart the local backend so the new env vars take effect, then click "Send via WhatsApp" → confirm the modal shows the real count and notice label → confirm the send. Verify the test number actually receives the message.
5. Check the job's final counts in the modal — confirm `sent` is 1 (capped correctly at whatever's really eligible for a single test) and nothing looks like the earlier silent-drop pattern.
6. **Do not remove `DASHBOARD_TEST_NUMBER` and send to the real 2,692-number list from local dev.** Real sends to the full list should happen deliberately, from the live deployment, once you're ready — not as a side effect of this smoke test.
7. Set the same env vars on Render (without `DASHBOARD_TEST_NUMBER`, or with it removed once ready for a real send) when actually launching the real broadcast.

Report back: pass/fail on each step, the exact recipient count shown, and confirmation the test-number message actually arrived.
