# Professional React Dashboard with Live Sending — Design Spec

Date: 2026-07-18
Project: Absolute Veritas certification consultancy

## Purpose

Replace the static, view-only `dashboard.html` for daily use with a professional,
visually polished dashboard that can also **send WhatsApp renewal alerts
directly from the UI**, per-client, on demand — in addition to the existing
9:30 AM scheduled automation. The original `dashboard.html` is left untouched
as a lightweight, no-backend fallback; this is a new, separate system.

## Why a Backend Is Required

Sending a WhatsApp message requires the permanent Meta API token. That token
must never be shipped to browser-side JavaScript (anyone viewing page source
or the network tab could extract it and send messages as the business). A
small local backend is required to hold the token server-side; the browser
only ever talks to this backend over `localhost`.

## Architecture

New folder, alongside the existing scripts (not replacing them):

```
cert_automation_scripts/
  dashboard-app/
    backend/
      main.py              # FastAPI app: endpoints below
      requirements.txt      # fastapi, uvicorn (+ existing script's deps)
      test_main.py          # pytest, FastAPI TestClient
    frontend/
      (Vite + React project)
      src/
        App.jsx
        components/
          StatCards.jsx
          FilterBar.jsx
          ClientTable.jsx
          SendConfirmModal.jsx
          Toast.jsx
      package.json
  whatsapp_renewal_alerts.py   # existing script — gets one small refactor (below)
  dashboard.html               # existing static dashboard — untouched, kept as fallback
```

**Running it day to day:** the backend serves the frontend's production build as
static files, so the whole thing is one process on one port
(`http://localhost:8000`), started with a single command. A separate Vite dev
server is only used during development for hot-reload, not for daily use.

## Refactor to `whatsapp_renewal_alerts.py`

The per-record "check dedup → build payload → send → update log" sequence
currently lives inline inside `run()`'s loop. It's extracted into a standalone
function:

```python
def send_one_alert(record, log_path, token, phone_number_id, template_name,
                    template_lang, today=None, send_fn=send_message):
    """Send (or skip if already sent today) one alert-eligible client's
    renewal message. Returns a result dict identical in shape to what run()
    already produces per record (action: sent/skipped_duplicate/failed)."""
```

`run()` (CLI, loops over every eligible client) and the new
`POST /api/send/{client_id}` endpoint (handles exactly one client) both call
this function, so the send logic exists in exactly one place. All 32 existing
tests must still pass after this refactor; new tests cover `send_one_alert`
directly.

## Backend API

- **`GET /api/health`** — trivial liveness check the frontend pings on load.

- **`GET /api/clients`** — reads `clients_certifications.xlsx` and
  `sent_log.json` fresh from disk on every call (no caching). Returns each
  client record plus a computed `alert_sent_today` field:
  - `true` / `false` for CRITICAL / URGENT / DUE SOON clients (via the same
    `dedup_key()` used by the CLI script)
  - `null` for ACTIVE / EXPIRED clients (not applicable)

- **`POST /api/send/{client_id}`** — sends one real WhatsApp alert:
  1. Look up the client fresh from the xlsx (404 if unknown)
  2. 400 if status isn't CRITICAL/URGENT/DUE SOON
  3. 409 if already sent today for that status (dedup enforced — a dashboard
     send and the 9:30 AM scheduled run can never double-send the same client
     the same day)
  4. Calls `send_one_alert()` — real Meta API call
  5. On success: updates the same `sent_log.json` the CLI reads/writes;
     returns `{status: "sent", message_id}`
  6. On failure: returns the real error message from Meta, HTTP 502

**Test-mode safety net:** an optional `DASHBOARD_TEST_NUMBER` variable in
`.env`. If set, every dashboard send redirects to that number instead of the
real client's number — mirrors the CLI's `--test-number` flag, letting the
whole Send Alert → Confirm → success flow be verified safely before pointing
it at real clients. Unset once confident.

## Frontend

**Stack:** React + Vite, Tailwind CSS, Framer Motion for animations.

**Visual style:** "Vibrant Gradient SaaS" — light background, bold
blue-to-violet gradients on brand text/buttons/badges, pill-shaped controls,
soft colored shadows (chosen from mockups during brainstorming).

**Page layout, top to bottom:**
1. Header — "Absolute Veritas" in gradient text, plus a Refresh button
2. Stat cards row — Total Clients, Critical, Urgent, Due Soon (counts,
   animated count-up on load/refresh)
3. Filter bar — status tabs (All/Critical/Urgent/Due Soon/Active/Expired) +
   search box (name/company), same behavior as the current dashboard
4. Client table — Client ID, Full Name, Company, Certification, Cert ID,
   Expiry Date, Days Left, Status (colored badge, readable text), and a new
   **Action** column:
   - Eligible + not sent today → gradient "Send Alert" button
   - Eligible + already sent today → disabled "✅ Sent" pill
   - Not eligible (ACTIVE/EXPIRED) → "—"
5. Send confirmation modal — "Send renewal alert to {name} at {company}?"
   with Confirm/Cancel, before the real API call fires
6. Toast notifications — success or the real Meta error message, shown
   briefly after each send attempt

**Carried forward unchanged from the current dashboard:** click-to-sort on
every column, with numeric-aware sorting for Days Left and Expiry Date (not
lexicographic — this was a real bug caught and fixed once already in the
static dashboard's build, and must not be reintroduced here); search + status
filter composition; the dark-text-on-light-badge fix for URGENT/DUE SOON
readability.

**Animation level:** subtle micro-interactions only — row hover/press
feedback, animated count-up on stat cards, gentle fade/slide when
filtering/sorting, a small success animation on send completion. Not
decorative/bold motion.

## Testing Plan

- **Backend:** pytest, following the existing test file's patterns (mocked
  `requests.post`, no real API calls in tests). Covers `send_one_alert()`'s
  paths (success, dedup-blocked, API failure) and all three endpoints via
  FastAPI's `TestClient` (client list shape; send success/409-duplicate/
  400-ineligible/404-unknown/502-error-passthrough).
- **Frontend:** Vitest + React Testing Library — unlike the static dashboard
  (no build tooling, hence manual-only verification), this is a proper build
  with real interactive risk (blocking sends behind confirmation, correctly
  disabling already-sent buttons, correct status/color mapping), so
  component-level automated tests are warranted here.
- **Manual walkthrough (final step, done by the user):** with
  `DASHBOARD_TEST_NUMBER` set, start the backend, open the dashboard, and
  click through: stat cards match the data, filters/search/sort all work,
  clicking Send Alert shows the confirmation modal, confirming sends a real
  message to the test number and the row updates to "✅ Sent" without a page
  reload, a second click on an already-sent row is blocked. Only once this is
  confirmed should `DASHBOARD_TEST_NUMBER` be unset for real client use.

## Out of Scope

- Editing client data from the UI (still view + send only, not a CRUD tool)
- Authentication/login (this is a local, single-operator tool on the
  consultancy's own machine)
- Bulk "send all eligible" button (explicitly deferred — per-client only, per
  this design's scope decision)
- Replacing or modifying the existing 9:30 AM Task Scheduler job — it
  continues to run independently; the dashboard's dedup log-sharing ensures
  it won't double-send anything the dashboard already sent that day
