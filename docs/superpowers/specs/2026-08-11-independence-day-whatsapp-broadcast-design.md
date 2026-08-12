# Independence Day WhatsApp Broadcast — Design

## Problem

The existing "Notices" feature only targets clients already in the roster, filtered by scheme/cert-type/status/expiry. There's now a need to send a one-time WhatsApp promotional message (an Independence Day service discount) to a separate list of 2,692 phone numbers that have no corresponding roster/client record at all — just raw numbers, no name or company data. The existing roster-filtered notice system doesn't fit this shape of send.

## Scope

- A new, WhatsApp-only notice type that targets an imported flat list of phone numbers instead of the client roster.
- One-time import of the given Excel file (`Numbers_Only_Deduplicated.xlsx`, sheet `Numbers`, column `Digits Only`, 2,692 rows) into MongoDB. The `Needs Review` sheet (120 rows flagged as malformed) is excluded.
- No email component — WhatsApp only.
- No per-recipient personalization — the message body is fully static, matching the pasted content exactly (no name/company placeholders, since none exist for this list).
- A minimal, dedicated UI section (not the roster-filter-heavy existing Notices page) — just: notice name, total recipients, how many haven't received it yet, a Send button.

## Message Content (for Meta template submission)

```
🇮🇳 Independence Day Special Offer!
Get 15% OFF on Service Fees for:
🔹 Testing
🔹 Inspection
🔹 Certifications
🔹 IT Compliances
🎁 FREE Compliance Assessment
📅 Valid till 31 August 2026

Absolute Veritas
Effortless Global Trade with Smart Solutions
☎️: 01294001010
📞: 7303215033
📧: cs@absoluteveritas.com
🧑‍💻: www.absoluteveritas.com
```

This is a **Marketing**-category template (promotional discount + CTA-free), submitted to Meta Business Manager with **zero body variables** — the same static text goes to every recipient, no `{{1}}`/`{{2}}` placeholders. Template name suggestion: `independence_day_2026_offer`, language `en`. **This still needs to be submitted and approved in Meta Business Manager before any real send can happen** — same ~24h+ review process seen earlier this session for other templates. Sending code will be built now so it's ready the moment approval lands; nothing will actually send before then (the template lookup returns `None` until the env vars for an approved template are set, exactly like the existing MeitY notice's `skipped_no_template` behavior).

## Data Model

New collection: `adhoc_recipients`

```
{
  "_id": "<digits-only phone number>",   # itself the natural unique key
  "notice_id": "independence_day_2026",
  "source": "WhatsApp broadcast list",   # carried over from the sheet's Source column, for traceability
}
```

Imported once via a standalone script (`import_adhoc_recipients.py`), not a reusable upload UI — matches the "one-time import" decision. If a future ad-hoc list is needed, this script (or a copy of it) gets pointed at a new file and `notice_id`; building a general-purpose upload UI is explicitly out of scope for now (YAGNI — no second use case yet).

Each `Digits Only` value is run through the existing `normalize_phone()` (from `whatsapp_renewal_alerts.py`, already fixed this session to strip a leading "00" international trunk prefix) before being stored as `_id` — a cheap safety net in case any value still carries that prefix despite the sheet labeling it "digits only," and keeps this list normalized the same way every other WhatsApp send in the app already is.

Dedup/send tracking reuses the **existing** `notice_sent_log` collection and its permanent-dedup semantics (`{client_id, notice_id, channel}`), with the phone number itself standing in for `client_id`. This keeps it consistent with the existing notice system's proven safe-resume behavior (already fixed for the Brevo false-positive issue this session; WhatsApp doesn't have that specific problem since Meta's Graph API does synchronously reject over-limit sends with a real error code, unlike Brevo).

## Backend

- `notice_independence_day_2026.py` — new notice module. Unlike the existing MeitY module, this one has **no `build_email_html`** (WhatsApp-only) and its `build_whatsapp_payload` takes a bare phone number (not a roster `rec` dict) and returns a template payload with an empty parameter list (static content, no variables).
- `db.py` — two new small functions: `get_adhoc_recipients(db, notice_id) -> list[str]` (all phone numbers for a notice) and `get_adhoc_recipient_count(db, notice_id)` (for the UI's "total recipients" display). Both simple, direct queries against `adhoc_recipients` — no filtering, no pagination (2,692 is small enough to load in one shot, consistent with how the existing Notice Log page already loads everything in one shot).
- `notice_sender.py` — new `send_adhoc_whatsapp_notice(db_path, notice_id, token, phone_number_id, dry_run=False, test_number=None, send_fn=send_message, on_progress=None, limit=None) -> list[dict]`. Loops `get_adhoc_recipients()`, checks `is_notice_already_sent` per phone number (reusing the existing function unchanged — it's already generic over `client_id`, which we're just feeding a phone number into), sends, records via `record_notice_sent` unchanged. Mirrors the shape of the existing `send_notice_whatsapp` closely enough to share the same dedup/logging/limit conventions, but doesn't call `get_broadcast_clients` at all.
- `main.py` — three new endpoints, deliberately simpler than the roster-based notice endpoints (no filter query params at all, since there's nothing to filter):
  - `GET /api/adhoc-notices/{notice_id}/count` → `{"total": int, "not_yet_sent": int}`
  - `POST /api/adhoc-notices/{notice_id}/send-whatsapp` → starts a background job (same job-polling pattern as existing sends), capped at a WhatsApp messaging-tier-safe `limit` (see Testing/Deployment note below on what value).
  - `GET /api/adhoc-notices/{notice_id}/send-whatsapp/status/{job_id}` → same job status shape as existing notice sends.

## Frontend

New minimal section — not a new full page, just a card added to the existing Notices page (below the existing roster-filtered notice UI, clearly visually separated), or a small standalone view — **exact placement to be finalized during implementation planning**, but the content is fixed: title, "X of Y clients haven't received this yet", one "Send via WhatsApp" button, reusing the existing `SendAllConfirmModal`/job-polling components since the confirm-modal-then-poll-progress pattern is identical to what already exists — no new modal/polling UI needed, just no filter bar above it.

## What Does Not Change

- The existing roster-filtered Notices page/feature (MeitY notice) — completely untouched, this is additive.
- `notice_sent_log`'s schema and dedup semantics — reused as-is.
- No new Excel-upload UI — the import is a one-time script, run once by an engineer, not a repeatable admin action.

## Testing Strategy

- Backend: `test_notice_sender.py`-style tests for `send_adhoc_whatsapp_notice` (sends, skips duplicates, respects `limit`, dry-run) using the same `mongomock`-based fixture pattern as the rest of the suite.
- `db.py` tests for `get_adhoc_recipients`/`get_adhoc_recipient_count`.
- Frontend: a test for the new minimal send-card component, mirroring the existing `SendAllConfirmModal` usage tests elsewhere.
- The import script itself gets a `demo()`/`__main__` self-check (per this session's lazy-but-checked convention) rather than a full pytest suite, since it's a one-time operational script, not app logic — but the parsing/filtering logic it shares with `db.py`'s new functions (if any) stays covered by real tests.

## Deployment Note

Real sends require the same env-var pattern as the existing MeitY notice: `WHATSAPP_INDEPENDENCE_DAY_2026_NAME` / `_LANG`, set on **both** local `.env` and Render's environment — once Meta approves the template. Until then, `get_whatsapp_template()` returns `None` and the send button correctly reports everyone as `skipped_no_template`, exactly like the existing notice does before its template exists.

**Rate limiting**: given today's real-world lesson (Brevo silently over-committing past quota), before a real send at 2,692 recipients, confirm the WhatsApp Business Account's actual current messaging tier (checked once already this session: 2,000/24h) and pass that as `limit` — unlike Brevo, Meta's Graph API does synchronously reject over-limit sends with a real HTTP error, so the same "our system falsely marks as sent" failure mode is not expected here, but capping proactively avoids wasting time on guaranteed-to-fail attempts anyway.
