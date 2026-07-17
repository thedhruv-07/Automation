# Renewal Dashboard — Design Spec

Date: 2026-07-17
Project: Absolute Veritas certification consultancy

## Purpose

A view-only dashboard for browsing `clients_certifications.xlsx` in a
browser — sortable/filterable table with status color-coding and expiry
countdowns, plus an optional overlay showing whether the WhatsApp automation
(`whatsapp_renewal_alerts.py`, spec: `2026-07-17-whatsapp-renewal-alerts-design.md`)
already sent an alert today for a given client/status. No send capability —
sends remain CLI-driven via that script.

## Runtime Model

Single self-contained file: `cert_automation_scripts/dashboard.html`. Opened
directly in a browser (double-click), no local server, no build step.

Browsers block a `file://` page from silently reading other local files, so
data loads via two "Choose File" `<input>` pickers rather than an automatic
fetch:

1. **Required**: `clients_certifications.xlsx` — parsed client-side with
   SheetJS (`xlsx.full.min.js`, loaded via CDN `<script>` tag — needs
   internet on first load of the page, no live network calls after that).
2. **Optional**: `sent_log.json` — the dedup log written by
   `whatsapp_renewal_alerts.py`. If not loaded, the "Alert Sent Today"
   column shows "—" for every row.

Re-picking either file is how you refresh the view after the underlying
data changes (regenerating the xlsx, or a new automation run updating the
log).

## Table Columns

Client ID, Full Name, Company, Certification Name, Certification ID,
Expiry Date, Days-left (computed client-side from Expiry Date vs the
browser's current date — e.g. "in 7 days" / "5 days ago"), Status badge,
Alert Sent Today.

**Alert Sent Today** is only evaluated for rows whose Status is CRITICAL,
URGENT, or DUE SOON (the only statuses the automation script ever sends
for). It looks up `f"{client_id}|{status}|{today}"` in the loaded
`sent_log.json` (same key format as the automation spec) and shows "✅
Sent" if present, "Not sent" if the log is loaded but no matching entry
exists, or "—" if no log file has been loaded. ACTIVE/EXPIRED rows always
show "—" since the automation never targets them.

## Status Colors

Reuses the palette already established in `create_dummy_data.py` for
visual consistency between the generator's Excel output and the dashboard:

- EXPIRED — red (`#FF0000`)
- CRITICAL — orange (`#FF6600`)
- URGENT — amber (`#FFA500`)
- DUE SOON — gold (`#FFD700`)
- ACTIVE — green (`#00B050`)

## Filtering & Sorting

- Status filter as tabs: All / Critical / Urgent / Due Soon / Active /
  Expired.
- Free-text search box filtering on Full Name and Company.
- Clicking a column header sorts ascending/descending by that column.

## Out of Scope (explicitly, per YAGNI)

- No editing of client data (that stays in the xlsx, edited by hand or via
  `create_dummy_data.py`/the user's generation script).
- No triggering of WhatsApp sends from the dashboard.
- No server, no persistence, no auth — this is a local single-user
  convenience view.

## Testing Plan

1. Open `dashboard.html` directly in a browser.
2. Load the current `clients_certifications.xlsx` (8 rows from
   `create_dummy_data.py`) — verify all 8 rows appear with correct columns,
   correct days-left math, correct status colors.
3. Verify status tab filters and column sorting behave correctly.
4. Once `sent_log.json` exists (after the WhatsApp script's first live
   run), load it and verify the Alert Sent Today column reflects it
   correctly for CRITICAL/URGENT/DUE SOON rows.
