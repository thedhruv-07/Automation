# Broadcast Notices

## Problem

The dashboard can only alert a client about their *own* certification
renewal. There's no way to send a one-time, general-purpose announcement —
like DPIIT's Transition Facilitation (Quality Control) Order, 2026, which
CRS clients should hear about regardless of their own cert's status — to a
filtered group of clients. Today's alert infrastructure is built entirely
around per-client renewal state (`ALERT_STATUSES`, per-day dedup, expiry
countdown content) and doesn't fit a message that isn't about any
individual's own expiry date.

## Scope

Add a durable **Notices** feature: a registry of pre-built one-time
announcements (email + WhatsApp content each), a dedicated "Notices" page
in the sidebar to pick a notice, filter an audience, and send it, and
permanent (not per-day) dedup so a client never receives the same notice
twice. The first notice is the Transition Facilitation Order 2026,
targeting CRS clients — but the architecture is built so a *future* notice
is a small content file plus one registry line, not a new subsystem.

WhatsApp content is always pre-approved-template-based (Meta's hard
requirement, no exceptions) — there is no free-text composer for either
channel, so both stay symmetric: pick a pre-built notice, pick an audience,
send.

## 1. Content layer

**`notice_<id>.py`** (one flat file per notice, e.g.
`notice_transition_facilitation_2026.py` — mirrors how each import format
gets its own file registered in `import_formats.py`). Each implements:

```python
EMAIL_SUBJECT: str

def build_email_html(rec: dict, org_name: str) -> str: ...

def get_whatsapp_template() -> tuple[str, str] | None: ...
    # reads WHATSAPP_NOTICE_<ID>_NAME / WHATSAPP_NOTICE_<ID>_LANG env vars;
    # None until Meta approves the template and the env vars are set

def build_whatsapp_payload(rec: dict, to_phone: str, template_name: str, template_lang: str) -> dict: ...
```

**`notices.py`** (the registry, mirrors `import_formats.py`'s shape):

```python
NOTICES = {
    "transition_facilitation_2026": {
        "label": "Transition Facilitation Order 2026",
        "module": notice_transition_facilitation_2026,
    },
}

def list_notices() -> list[dict]: ...      # [{"id": ..., "label": ...}, ...]
def get_notice_module(notice_id: str): ...  # the module, or None if unknown
```

### First notice: `transition_facilitation_2026`

- **Email subject**: "Important: BIS Transition Facilitation Order, 2026 —
  What It Means for You"
- **Email body**: DPIIT's Transition Facilitation (Quality Control) Order,
  2026 (effective 25 June 2026) lets eligible companies source BIS
  Scheme-II certified product while their own ISI Mark certification is
  in process, covering 10 specific QCOs (toys, footwear, ACs, water
  heaters, washing machines, hinges, furniture, household electrical
  appliances). 24-month application window. CTA link to
  `https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/`
  for the full breakdown, plus an invitation to contact Absolute Veritas
  for eligibility help.
- **WhatsApp**: `"Hi {{1}}, DPIIT's new Transition Facilitation (QCO) Order
  2026 could open a faster BIS compliance path for {{2}}. See if it applies
  to you: {{3}}"` — `{{1}}`=name, `{{2}}`=company, `{{3}}`=the same URL.
  Needs its own Meta approval before it can send, same as every other
  WhatsApp template in this project.

## 2. Data layer — `db.py`

**New table**, added to `SCHEMA` (self-healing migration, same pattern as
every prior schema change in this project):

```sql
CREATE TABLE IF NOT EXISTS notice_sent_log (
    client_id  TEXT NOT NULL,
    notice_id  TEXT NOT NULL,
    channel    TEXT NOT NULL,
    sent_at    TEXT NOT NULL,
    message_id TEXT,
    PRIMARY KEY (client_id, notice_id, channel)
);
```

Deliberately a **new** table rather than reusing `sent_log`/
`email_sent_log`: those two are keyed by `client_id|status|date` because
renewal alerts are meant to *recur* (a CRITICAL client can be reminded
again tomorrow). A notice is the opposite — once sent, permanently sent,
no date component at all.

**New functions**: `is_notice_already_sent(db_path, client_id, notice_id,
channel) -> bool`, `record_notice_sent(db_path, client_id, notice_id,
channel, message_id, sent_at)` — mirror `is_already_sent`/`record_sent`'s
shape, just against the new table and without a date dimension.

**New client query**: `get_broadcast_clients(db_path, status=None,
cert_type=None, expiry_before=None, search=None, scheme=None) ->
list[dict]` — identical filter shape to `get_eligible_clients`, but without
the hardcoded `ALERT_STATUSES` restriction, so "no status filter" means
*every* client, not just alert-eligible ones. Built directly on the
existing `_client_filters_where` helper (which already treats `status` as
an optional exact-match filter on its own — the `ALERT_STATUSES`
restriction is something `get_eligible_clients` adds on top, not something
`_client_filters_where` itself imposes).

**New count**: `get_notice_eligible_count(db_path, notice_id, channel,
status=None, cert_type=None, expiry_before=None, search=None, scheme=None)
-> int` — clients matching the filters, minus whoever's already in
`notice_sent_log` for this `notice_id`/`channel`. Powers the Notices page's
live "N clients will receive this" count, mirroring `get_eligible_count`'s
role for renewal alerts.

## 3. Send orchestration — `notice_sender.py`

New file, parallel to `whatsapp_renewal_alerts.py`/`email_alerts.py` but
for notices: `send_notice_whatsapp(db_path, notice_id, token,
phone_number_id, dry_run=False, test_number=None, send_fn=send_message,
on_progress=None, status=None, cert_type=None, expiry_before=None,
search=None, scheme=None) -> list[dict]` and an analogous
`send_notice_email(...)`. Per record: skip if already in
`notice_sent_log` (`action: "skipped_duplicate"`), skip if the notice's
WhatsApp template isn't configured yet (`action: "skipped_no_template"`,
same reasoning as the per-scheme renewal templates), otherwise build the
payload via the notice module and send — recording success into
`notice_sent_log` (not `sent_log`).

## 4. API — new endpoints in `main.py`

- `GET /api/notices` → `list_notices()`'s result, for the page's dropdown.
- `GET /api/notices/{notice_id}/eligible-count?...filters` → `{"whatsapp":
  N, "email": M}`, calling `get_notice_eligible_count(...)` once per
  channel — mirrors `/api/eligible-count`'s existing shape for renewal
  alerts exactly, rather than requiring a separate `channel` param per call.
- `POST /api/notices/{notice_id}/send-whatsapp` / `POST
  /api/notices/{notice_id}/send-email` → background job, identical
  progress-polling shape to `/api/send-all`/`/api/send-all-emails`
  (`_send_notice_jobs`/`_send_notice_email_jobs` dicts, `GET
  .../status/{job_id}`).
- Both send endpoints accept the same filter query params
  (`status`/`cert_type`/`expiry_before`/`search`/`scheme`) as the existing
  bulk-send endpoints, applied via `get_broadcast_clients` instead of
  `get_eligible_clients`.

## 5. Frontend

- **New sidebar item**: "Notices", its own view (not folded into Client
  Data or Excel Sync).
- **`NoticesView.jsx`**: a "Which notice?" `<select>` (populated from
  `/api/notices`), the *same* `ClientDataFilters`-style filter controls
  already built (scheme/status/cert type/expiry/search) reused here for
  audience targeting, a live eligible-count display, and two buttons —
  `Send via WhatsApp` / `Send via Email` — reusing the existing
  `SendAllConfirmModal` pattern (confirm → background job → progress →
  done). `SendAllConfirmModal` currently hardcodes renewal-alert wording
  ("Send a real WhatsApp renewal alert to:", "Send a renewal email to:") —
  it gains a `confirmLabel` prop (defaulting to today's exact text, so
  existing renewal-alert call sites need no changes) that `NoticesView`
  overrides with the selected notice's own label, rather than forking a
  near-duplicate modal component.
- `api.js` gains `listNotices()`, `getNoticeEligibleCount(noticeId,
  params)`, `sendNotice(noticeId, channel, params)`,
  `getNoticeSendStatus(noticeId, channel, jobId)`.

## Testing

- `notices.py`: `list_notices()` returns the registered entries;
  `get_notice_module()` returns `None` for an unknown id.
- `notice_transition_facilitation_2026.py`: `build_email_html` includes the
  client's name/company and the notice URL; `get_whatsapp_template`
  returns `None` when unconfigured, the configured pair when env vars are
  set; `build_whatsapp_payload` produces the 3-variable structure.
- `db.py`: `notice_sent_log` migration is self-healing (mirrors the
  `scheme` column migration test shape); `get_broadcast_clients` returns
  clients of *every* status when unfiltered, and honors each filter
  independently; `get_notice_eligible_count` excludes clients already in
  `notice_sent_log` for that notice/channel but not for a *different*
  notice/channel (proving the dedup key is genuinely per-notice-per-channel,
  not global).
- `notice_sender.py`: a client already in `notice_sent_log` is skipped as
  `skipped_duplicate`; an unconfigured WhatsApp template produces
  `skipped_no_template`; a successful send records into `notice_sent_log`,
  not `sent_log`/`email_sent_log`.
- `main.py`: each new endpoint, mirroring the existing bulk-send endpoint
  test shapes (job starts, progress polls, unknown `notice_id` returns 404).
- Frontend: `NoticesView` renders the notice dropdown and filters, shows
  the live eligible count, and both send buttons drive the same
  confirm/progress/done flow already proven for `SendAllConfirmModal`.
