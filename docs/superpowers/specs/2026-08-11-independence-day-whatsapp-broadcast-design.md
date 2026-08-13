# Independence Day WhatsApp Broadcast — Design

> **Status (2026-08-12): implemented and merged to `master`.** The sections
> below are updated to match what actually shipped — a few details changed
> during implementation (env var naming, an added list endpoint, and a
> send-pacing fix; see inline notes). Still outstanding: the real 2,692-row
> import against production Mongo, and the actual broadcast send — both
> require direct sign-off, not automated. The Meta template
> (`independence_day_2026_offer`) is already APPROVED.

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
- `db.py` — **three** new small functions (one more than originally planned): `get_adhoc_recipients(db, notice_id) -> list[str]` (all phone numbers for a notice), `get_adhoc_recipient_count(db, notice_id)` (for the UI's "total recipients" display), and `get_adhoc_eligible_count(db, notice_id, channel)` (total minus already-sent, for the "X of Y haven't received this yet" display — added so the count endpoint doesn't have to compute that subtraction itself). All simple, direct queries against `adhoc_recipients`/`notice_sent_log` — no filtering, no pagination (2,692 is small enough to load in one shot, consistent with how the existing Notice Log page already loads everything in one shot).
- `notice_sender.py` — new `send_adhoc_whatsapp_notice(db_path, notice_id, token, phone_number_id, dry_run=False, test_number=None, send_fn=send_message, on_progress=None, limit=None, pace_seconds=0.0) -> list[dict]`. Loops `get_adhoc_recipients()`, checks `is_notice_already_sent` per phone number (reusing the existing function unchanged — it's already generic over `client_id`, which we're just feeding a phone number into), sends, records via `record_notice_sent` unchanged. Mirrors the shape of the existing `send_notice_whatsapp` closely enough to share the same dedup/logging/limit conventions, but doesn't call `get_broadcast_clients` at all. **`pace_seconds` was added mid-implementation** (see Rate Limiting note below) — it wasn't in the original design.
- `main.py` — **four** new endpoints (one more than originally planned), deliberately simpler than the roster-based notice endpoints (no filter query params at all, since there's nothing to filter):
  - `GET /api/adhoc-notices` → `[{"id": str, "label": str}, ...]` — lists registered ad-hoc notices, so the frontend doesn't hardcode which one(s) exist. Not in the original design; added for symmetry with the roster-based notices list and to keep the frontend generic.
  - `GET /api/adhoc-notices/{notice_id}/count` → `{"total": int, "not_yet_sent": int}`
  - `POST /api/adhoc-notices/{notice_id}/send-whatsapp` → starts a background job (same job-polling pattern as existing sends), capped at `limit` and paced by `pace_seconds` (see Rate Limiting note below — both are shared, env-overridable module constants, not ad-hoc-specific).
  - `GET /api/adhoc-notices/{notice_id}/send-whatsapp/status/{job_id}` → same job status shape as existing notice sends.

## Frontend

New minimal section — **as implemented, this is a card (`AdhocNoticeBroadcast.jsx`) rendered inside the existing `NoticesView.jsx`, below the existing roster-filtered notice UI, behind a `border-t` divider** (not a separate standalone page/view). Content: title, "X of Y haven't received this yet", one "Send via WhatsApp" button, reusing the existing `SendAllConfirmModal`/job-polling components since the confirm-modal-then-poll-progress pattern is identical to what already exists — no new modal/polling UI needed, just no filter bar above it (`SendAllConfirmModal`'s existing `singleScope` prop covers this — no filtered-vs-all scope choice, since there's nothing to filter).

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

Real sends require an env-var pair, set on **both** local `.env` and Render's environment, once Meta approves the template — **as implemented, the names are `WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME` / `_LANG`** (an `ADHOC` infix was added to disambiguate from the roster-based notices' env-var naming convention; this design doc originally specified `WHATSAPP_INDEPENDENCE_DAY_2026_NAME` without it — the `ADHOC` version is what actually shipped). Until set, `get_whatsapp_template()` returns `None` and the send button correctly reports everyone as `skipped_no_template`, exactly like the existing notice does before its template exists. **As of 2026-08-12, the template is APPROVED** (`independence_day_2026_offer`, category MARKETING, id `4474587969457169`) — so once the env vars are set, real sends are live immediately.

**Rate limiting — this section was superseded during implementation.** The original assumption (Meta's nominal 2,000/24h messaging tier is the number to cap at) turned out to be wrong: Meta's own `template_analytics` API showed the existing MeitY roster notice's unpaced, bursty `send_notice_whatsapp` had sent 3,436 requests that all returned a real, synchronous `message_id` (a genuine API success), but only 244 were actually counted as sent by Meta's own analytics — a ~93% silent loss, with no failure signal our code could have caught, caused by bursty sending tripping Meta's quality/abuse throttling well before the 2,000/day ceiling. Fixing this became its own task, applied to **both** the pre-existing roster-based `send_notice_whatsapp` and this feature's `send_adhoc_whatsapp_notice`:
- A `pace_seconds` sleep between each real send attempt (success or failure — pacing is about not bursting requests, not about outcome).
- A `limit` well below the nominal ceiling, left completely unattempted (not attempted-and-failed) once hit, so a later run resumes cleanly via the existing permanent dedup.
- Both are shared, env-overridable module constants in `main.py` — `WHATSAPP_NOTICE_DAILY_LIMIT` (default `200`) and `WHATSAPP_SEND_PACE_SECONDS` (default `1.5`) — reused by both senders rather than each having its own number with no real basis, since it's the same WhatsApp Business Account and the same demonstrated throttling behavior either way.
