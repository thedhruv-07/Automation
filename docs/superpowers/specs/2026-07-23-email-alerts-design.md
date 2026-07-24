# Email Renewal Alerts (Dashboard Send + Bulk Send)

**Status:** Approved

## Problem

The dashboard can preview a renewal email (`/api/email-preview/{client_id}` + "Preview Email" link) but has no way to actually send it. The only code that sends email via Brevo lives in the legacy standalone `cert_automation.py` CLI script, not the dashboard.

This matters now specifically because the WhatsApp channel — the dashboard's only working send mechanism — is non-functional for the current roster: **0 of 66,745 clients have a phone number** (the BIS ISI government licensing data this roster is now mostly built from never included one). Email, by contrast, is viable for nearly everyone: only 8 of 11,122 alert-eligible clients (0.07%) have a missing/invalid email address.

## Goals

1. A "Send Email" action per client, next to the existing "Preview Email" link.
2. A "Send All Emails" bulk action, mirroring "Send All Eligible" (WhatsApp)'s job-based progress UI.
3. Per-day dedup (a client already emailed today for a given status isn't emailed again), tracked **independently** of WhatsApp's dedup — a client can receive both channels the same day without either blocking the other.
4. Clients with no/invalid email are skipped (not attempted, not counted as failures) in bulk send, and their per-client button is disabled.
5. A test-recipient override (`DASHBOARD_TEST_EMAIL`), mirroring `DASHBOARD_TEST_NUMBER`, so this can be verified without emailing real clients.
6. Reuse existing, already-correct pieces without modification: `email_template.build_email_html()` (same function the preview already uses), the Brevo API call shape already proven in `cert_automation.py`'s `send_email_real()`.

## Design

### 1. New `email_sent_log` table (`db.py`)

```sql
CREATE TABLE IF NOT EXISTS email_sent_log (
    client_id   TEXT NOT NULL,
    status      TEXT NOT NULL,
    sent_date   TEXT NOT NULL,
    message_id  TEXT,
    email       TEXT,
    sent_at     TEXT NOT NULL,
    PRIMARY KEY (client_id, status, sent_date)
);
```

Structurally identical to the existing `sent_log` table (WhatsApp's), but a separate table rather than a shared one with a `channel` column — this avoids any migration of the existing, already-working WhatsApp table, and keeps the two channels' dedup logic fully independent by construction (no shared code path that could accidentally couple them). `db.py` gains parallel functions: `record_email_sent()`, `is_email_already_sent()`, `load_email_sent_log()`, `save_email_sent_log()` — direct mirrors of the existing WhatsApp-facing `record_sent()`/`is_already_sent()`/`load_sent_log()`/`save_sent_log()`, same signatures with `email` replacing `phone`.

### 2. New module `email_alerts.py` (mirrors `whatsapp_renewal_alerts.py`)

- `send_one_email_alert(record, sent_log, today, brevo_api_key, email_sender, org_name, to_email_override=None, send_fn=send_email_via_brevo) -> dict` — same shape as `send_one_alert`: checks dedup, builds the email via `build_email_html()` (imported from `email_template.py`, unchanged), calls `send_fn`, returns `{"action": "sent"|"skipped_duplicate"|"failed"|"skipped_no_email", ...}`.
- A record with no email or an email missing `@` returns `action: "skipped_no_email"` immediately, before any dedup/send attempt — a new action type not present in the WhatsApp version, since WhatsApp's existing code has no equivalent "no phone" guard (it currently just fails at the API call, which is the 502 bug this feature's design was partly motivated by fixing awareness of — not fixing that bug directly, since this plan only adds the email path, but the new code deliberately does it right from the start).
- `send_email_via_brevo(rec, html, subject, brevo_api_key, email_sender, org_name, to_email_override=None) -> tuple[bool, dict]` — wraps the Brevo POST call from `cert_automation.py`'s `send_email_real()` (same endpoint, same payload shape, same logo-attachment handling), returning `(success, {"message_id": ...} or {"error": ...})` to match `whatsapp_renewal_alerts.py`'s `send_message()` return contract.
- `run_email_alerts(db_path, brevo_api_key, email_sender, org_name, dry_run=False, test_email=None, today=None, send_fn=send_email_via_brevo, on_progress=None) -> list[dict]` — same shape as `whatsapp_renewal_alerts.run()`. `org_name` is always the literal `"Absolute Veritas"`, matching the existing hardcoded value already used by `/api/email-preview`'s `build_email_html()` call in `main.py` — not a new configurable value, just threaded through consistently with what already exists.
- `dedup_key()` is imported from `whatsapp_renewal_alerts.py` and reused as-is — it's a pure `f"{client_id}|{status}|{date_str}"` formatter with no channel-specific behavior, no reason to duplicate it.

### 3. New backend endpoints (`main.py`), mirroring the WhatsApp ones exactly

- `POST /api/send-email/{client_id}` — single-client send, same eligibility/dedup/lock checks as `/api/send/{client_id}`, using `email_sent_log` instead of `sent_log`. Returns 400 if the client has no valid email (checked before attempting, matching goal 4).
- `POST /api/send-all-emails` — background job, identical structure to `/api/send-all` (same `_send_lock`/`_bulk_in_progress`-style guard, but a **separate** lock/flag so an email bulk send and a WhatsApp bulk send don't block each other unnecessarily — two independent `_email_bulk_in_progress`/`_pending_email_sends` guards mirroring the WhatsApp ones). Job dict gains a `skipped_no_email` counter alongside `sent`/`skipped`/`failed`.
- `GET /api/send-all-emails/status/{job_id}` — mirrors `/api/send-all/status/{job_id}`.
- `GET /api/stats` gains one new field: `eligible_not_emailed_today` (mirroring `eligible_not_sent_today`), computed via the same upper-bound-estimate SQL pattern against `email_sent_log` instead of `sent_log`, for the bulk-send confirm modal's shown count.

### 4. Frontend

- `api.js`: `sendEmailAlert(clientId)`, `sendAllEmailAlerts()`, `getSendAllEmailsStatus(jobId)` — mirror the existing WhatsApp functions exactly (same fetch/credentials/auth-header pattern already established).
- `ClientTable.jsx`: a "Send Email" button next to the existing "Preview Email" link per row; disabled (with a tooltip, e.g. "No email on file") when the client's email is missing/invalid — computed client-side from the same record data already in the row.
- `SendAllConfirmModal`-equivalent for email: given the existing `SendAllConfirmModal` is already parameterized by `eligibleCount`/`job`/callbacks with no WhatsApp-specific text baked into its core structure (verify this against the actual current component before deciding), prefer **reusing it with a `channel` prop** ("whatsapp" | "email") that only changes display text, over duplicating the whole component — smaller diff, one component to maintain. If the actual component turns out to have WhatsApp-specific assumptions baked in beyond just labels, fall back to a parallel `SendAllEmailsConfirmModal` instead of forcing an awkward abstraction.
- `App.jsx`: new state/handlers mirroring `bulkModalOpen`/`sendAllJob`/`handleConfirmSendAll`/`handleCloseSendAllModal`, parallel `handleConfirmSendEmail`/job-polling for the email job.

### 5. Test-recipient safety override

New env var `DASHBOARD_TEST_EMAIL` (mirrors `DASHBOARD_TEST_NUMBER`): when set, all email sends (single or bulk) redirect to this address instead of the real client's email, exactly matching how `DASHBOARD_TEST_NUMBER` already works for WhatsApp. Documented in `.env.example` and `docs/DEPLOYMENT.md` alongside the existing WhatsApp test-number warning.

## Testing

- `db.py`: tests for `record_email_sent`/`is_email_already_sent`/`load_email_sent_log`/`save_email_sent_log`, mirroring the existing WhatsApp equivalents' test coverage.
- `email_alerts.py`: tests for `send_one_email_alert` (sent/skipped_duplicate/skipped_no_email/failed paths) and `run_email_alerts`, mirroring `test_whatsapp_renewal_alerts.py`'s structure and using a mocked `send_fn` (never a real Brevo call in tests).
- `main.py`: tests for the three new endpoints, mirroring the existing WhatsApp endpoint tests (dedup, lock/in-progress guards, missing-email 400, job progress polling).
- Frontend: tests for the new `api.js` functions, the `ClientTable` Send Email button (including its disabled-when-no-email state), and the bulk email confirm/progress flow — mirroring the existing WhatsApp test files' structure.

## Out of scope

- Not fixing the existing WhatsApp `/api/send/{client_id}` 502-on-missing-phone behavior — this plan only adds the email path. (Could be a reasonable fast-follow: return a clean 400 there too, matching this design's `skipped_no_email` pattern, but that's a separate, smaller change against already-shipped code.)
- No changes to `cert_automation.py` (the legacy standalone script) — it keeps working exactly as it does today, independent of this dashboard feature.
- No email open/click tracking, no retry-on-failure automation — matches WhatsApp's current scope (fire once, log the result, that's it).
