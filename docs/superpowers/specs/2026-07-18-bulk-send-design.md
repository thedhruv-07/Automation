# Bulk "Send All Eligible" — Design Spec

Date: 2026-07-18
Project: Absolute Veritas certification consultancy

## Purpose

Add a one-click bulk send to the React dashboard, alongside the existing per-client
"Send Alert" button, so the user isn't required to click every eligible row
individually. This is in addition to, not a replacement for, per-client sending and
the existing 9:30 AM scheduled automation — all three paths share the same dedup log,
so none of them can double-send a client the same day.

## Backend

**`POST /api/send-all`** (new endpoint, `dashboard-app/backend/main.py`) — reuses the
existing `run()` function from `whatsapp_renewal_alerts.py` directly (it already
implements "loop over all alert-eligible clients, skip already-sent ones, send,
persist the log once" — exactly what bulk send needs, no new send-loop logic
required). Reads the same env vars the per-client endpoint uses
(`WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`,
`WHATSAPP_TEMPLATE_LANG`, `DASHBOARD_TEST_NUMBER`), calls
`run(DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH, token, phone_number_id, template_name,
template_lang, dry_run=False, test_number=test_number)`, and returns the resulting
list of per-client result dicts (`client_id`, `name`, `status`, `action`, plus
`message_id`/`error` depending on outcome) as JSON.

## Frontend

- **`SendAllConfirmModal.jsx`** (new component, separate from the existing
  `SendConfirmModal` to keep each component single-purpose) — takes an `open`
  boolean and an `eligibleCount` number, shows "Send renewal alerts to all N
  eligible clients?" with Confirm/Cancel, mirrors the existing modal's visual style
  and the same double-submit guard (disable Confirm after first click, reset when
  reopened).
- **`api.js`** — new `sendAllAlerts()` function, `POST /api/send-all`, returns the
  parsed JSON array or throws on failure (same error-handling shape as `sendAlert`).
- **`App.jsx`** — new "Send All Eligible" button next to the existing Refresh
  button in the header. Disabled while a bulk send is in flight. Clicking opens
  `SendAllConfirmModal` with the current count of alert-eligible clients (status in
  CRITICAL/URGENT/DUE SOON) not yet sent today. On confirm, calls `sendAllAlerts()`,
  then shows a summary toast counting `sent`/`skipped_duplicate`/`failed` outcomes
  (e.g., "5 sent, 2 already sent, 0 failed") — toast type is `"error"` if any
  failed, otherwise `"success"` — and refreshes the client list.

## Out of Scope

- A live per-client progress indicator during the bulk send (the request completes
  and returns a full summary in one response, matching the existing CLI script's
  batch behavior — no streaming/progress UI).
- Any change to the per-client "Send Alert" button or the existing scheduled task.
