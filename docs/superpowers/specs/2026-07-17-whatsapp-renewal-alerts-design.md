# WhatsApp Renewal-Alert Automation — Design Spec

Date: 2026-07-17
Project: Absolute Veritas certification consultancy

## Purpose

Send WhatsApp Cloud API template messages to clients whose certification
`Status` is `CRITICAL`, `URGENT`, or `DUE SOON`, sourced from
`clients_certifications.xlsx`. Replaces the Twilio-based prototype
(`cert_automation.py`) for WhatsApp specifically; that script is untouched.

## Data Source

`clients_certifications.xlsx`, columns:
`Client ID, Full Name, Company, Email, Phone (WhatsApp), Certification Name,
Certification ID, Issue Date, Expiry Date, Renewal Link, Status`

- `Status` is precomputed by the existing generation script — this
  automation does not recompute urgency from dates, it just filters on the
  `Status` value.
- `Phone (WhatsApp)` is stored as bare digits including country code (e.g.
  `919354567496`), no `+` — matches Cloud API's expected `to` format
  directly.

## WhatsApp Message Template (submit in Meta dashboard)

- Name: `cert_renewal_alert`
- Category: Utility
- Language: English (US)
- One template covers all three tiers (no tier-specific wording — DUE
  SOON/URGENT/CRITICAL only affect *whether* a message is sent, not its
  text).

```
Header (Text, static):
Certification Renewal Notice

Body:
Dear {{1}}, this is a compliance notice from Absolute Veritas for {{2}}.

Your certification *{{4}}* (ID: {{3}}) is due to expire on *{{5}}*.

Please renew before this date to avoid a lapse in certification status. Tap
the button below to renew online, or reply to this message if you need
assistance.

Footer (static):
Absolute Veritas Certification Services

Buttons:
[Visit Website] -> Dynamic URL
  Base: https://yourcertificationportal.com/renew?id=
  Sample suffix: ISO13-2021-6634
```

Placeholder fill order: `{{1}}`=client name, `{{2}}`=company,
`{{3}}`=certification ID, `{{4}}`=certification name, `{{5}}`=expiry date
(formatted `DD Month YYYY`). The button's dynamic suffix reuses `{{3}}`
(certification ID) — assumes the real renewal portal accepts
`?id=<certification_id>`. If the production renewal URLs don't follow that
pattern, the button design must be revisited (Meta allows only one dynamic
suffix per URL button).

## Script: `whatsapp_renewal_alerts.py`

Dependencies: `openpyxl`, `requests`, `python-dotenv` (no pandas — reads the
xlsx directly with openpyxl to match the generation script's stack and keep
the dependency footprint small).

### Config (via `.env`, loaded with python-dotenv)

- `WHATSAPP_TOKEN` — permanent system-user access token (required)
- `PHONE_NUMBER_ID` — `2128020858096338` (required)
- `WHATSAPP_TEMPLATE_NAME` — default `cert_renewal_alert`
- `WHATSAPP_TEMPLATE_LANG` — default `en_US`
- API endpoint: `https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages`

`.env` is gitignored; `.env.example` is committed showing the variable names
with placeholder values.

### CLI flags

- `--dry-run` — no API calls, no log writes; prints the payload/preview that
  would be sent for each qualifying client.
- `--test-number <digits>` — redirects every send's `to` field to this
  number, while still using each real client's data to fill placeholders.
  Real API calls are made, but **dedup log writes are suppressed** (see
  below).
- No flags — live run against real client numbers, writes dedup log.

### Filtering & flow

1. Load `clients_certifications.xlsx` via openpyxl, skip blank rows.
2. Keep rows where `Status` in `{CRITICAL, URGENT, DUE SOON}`.
3. For each kept row, compute dedup key `f"{client_id}|{status}|{today}"`
   (`today` = local machine date, `YYYY-MM-DD`).
4. If key exists in `sent_log.json` → skip, print "already sent today".
5. Otherwise build the template payload and POST to the Graph API.
6. On HTTP success: print ✅, and — only in a true live run (no `--dry-run`,
   no `--test-number`) — write `{key: {sent_at, message_id, phone}}` to
   `sent_log.json`.
7. On HTTP failure or network exception: print ❌ with Meta's error message,
   continue to the next client (one failure never aborts the batch), and do
   **not** write a dedup entry so it retries on the next run same day.

### Why test-number skips the dedup log

If a `--test-number` run wrote dedup entries under the *real* client's key,
a same-day production run afterward would see "already sent" and skip that
client for real — even though the real client never received anything (the
test phone did). So `--test-number` reads the dedup log (to accurately show
what production would skip) but never writes to it.

### Logging

- Console: one line per client, ✅/⏭/❌ with client name and reason.
- Also appended (with timestamps) to `whatsapp_automation.log` in the script
  folder — gitignored, grows across runs.
- End-of-run summary: counts of sent / skipped-duplicate / failed.

## Files added

```
cert_automation_scripts/
  whatsapp_renewal_alerts.py
  .env.example
  .env                      (gitignored)
  .gitignore
  sent_log.json             (auto-created, gitignored)
  whatsapp_automation.log   (auto-created, gitignored)
  run_whatsapp_alerts.ps1   (Task Scheduler wrapper)
```

## Task Scheduler

`run_whatsapp_alerts.ps1` changes directory into `cert_automation_scripts`
and invokes `C:\Python314\python.exe whatsapp_renewal_alerts.py` (no flags —
live run), redirecting output to the log. Registered via `schtasks` (or the
Task Scheduler GUI) to trigger daily at 9:30 AM IST.

## Testing plan (before live use)

1. `--dry-run` — verify payload content and which clients qualify, no
   network calls.
2. `--test-number <your number>` — verify real delivery formatting end to
   end, confirm dedup log is untouched afterward.
3. Live run (no flags) against real client numbers.
