# "Book an Appointment" Calendly Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secondary "Book an Appointment" button (linking to `https://calendly.com/cs-absoluteveritas/30min`) to both the renewal/expiry email template and the Transition Facilitation notice email, below their existing primary CTA buttons.

**Architecture:** `CALENDLY_URL` becomes a shared constant in `email_template.py` (matching how `DEFAULT_INTRO_TEXT` already lives there), imported into `notice_transition_facilitation_2026.py` rather than duplicated. Both templates get a second `<tr>` row below their existing CTA button row, styled as an outlined secondary button so it doesn't visually compete with the primary action. WhatsApp needs no code change — it's a template-configuration step in Meta Business Manager, out of scope for this plan (documented in Task 2's verification step as a reminder, not implemented).

**Tech Stack:** Python (`dashboard-app/backend/`), pytest.

---

### Task 1: Add `CALENDLY_URL` and the secondary button to both email templates

**Files:**
- Modify: `dashboard-app/backend/email_template.py`
- Modify: `dashboard-app/backend/test_email_template.py`
- Modify: `dashboard-app/backend/notice_transition_facilitation_2026.py`
- Modify: `dashboard-app/backend/test_notice_transition_facilitation_2026.py`

- [ ] **Step 1: Write the failing tests for `email_template.py`**

Add to the end of `dashboard-app/backend/test_email_template.py`:

```python
def test_includes_book_an_appointment_button_alongside_renew_now():
    from email_template import CALENDLY_URL
    html = build_email_html(make_rec(5))
    assert "Renew Now" in html
    assert "Book an Appointment" in html
    assert f'href="{CALENDLY_URL}"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_email_template.py::test_includes_book_an_appointment_button_alongside_renew_now -v`
Expected: FAIL — `CALENDLY_URL` doesn't exist yet, and the button isn't in the HTML.

- [ ] **Step 3: Add `CALENDLY_URL` to `email_template.py`**

Current:

```python
DEFAULT_INTRO_TEXT = (
    "This is a notification regarding the certification held by "
    "<strong>{company}</strong>. Please review the details below and "
    "take action to ensure compliance continuity."
)
```

Replace with:

```python
DEFAULT_INTRO_TEXT = (
    "This is a notification regarding the certification held by "
    "<strong>{company}</strong>. Please review the details below and "
    "take action to ensure compliance continuity."
)

CALENDLY_URL = "https://calendly.com/cs-absoluteveritas/30min"
```

- [ ] **Step 4: Add the secondary button below "Renew Now"**

Current:

```python
                <!-- CTA Button -->
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr><td align="center" style="padding:4px 0 28px;">
                    <a href="{rec['renewal_link']}"
                       style="background:{ACCENT};color:#fff;padding:15px 42px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;box-shadow:0 4px 10px rgba(42,120,214,0.35);">
                      Renew Now
                    </a>
                  </td></tr>
                </table>
```

Replace with:

```python
                <!-- CTA Button -->
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr><td align="center" style="padding:4px 0 14px;">
                    <a href="{rec['renewal_link']}"
                       style="background:{ACCENT};color:#fff;padding:15px 42px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;box-shadow:0 4px 10px rgba(42,120,214,0.35);">
                      Renew Now
                    </a>
                  </td></tr>
                  <tr><td align="center" style="padding:0 0 28px;">
                    <a href="{CALENDLY_URL}" target="_blank" rel="noopener noreferrer"
                       style="background:#ffffff;color:{ACCENT};padding:13px 40px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;border:2px solid {ACCENT};">
                      Book an Appointment
                    </a>
                  </td></tr>
                </table>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_email_template.py -v`
Expected: all passed (12 tests).

- [ ] **Step 6: Write the failing test for the notice template**

Add to `dashboard-app/backend/test_notice_transition_facilitation_2026.py`, after `test_build_email_html_cta_link_opens_in_a_new_tab`:

```python
def test_build_email_html_includes_book_an_appointment_button_alongside_read_more():
    from email_template import CALENDLY_URL
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert "Read the Full Breakdown" in html
    assert "Book an Appointment" in html
    assert f'href="{CALENDLY_URL}"' in html
    assert html.count('target="_blank"') == 2  # both buttons open in a new tab
    assert html.count('rel="noopener noreferrer"') == 2
```

- [ ] **Step 7: Run test to verify it fails**

Run: `cd dashboard-app/backend && python -m pytest test_notice_transition_facilitation_2026.py::test_build_email_html_includes_book_an_appointment_button_alongside_read_more -v`
Expected: FAIL — the second button doesn't exist yet.

- [ ] **Step 8: Import `CALENDLY_URL` and add the secondary button**

Current:

```python
"""Content for the "Transition Facilitation Order 2026" one-time broadcast
notice. Summarizes DPIIT's Transition Facilitation (Quality Control) Order,
2026 (S.O. 3417(E), effective 25 June 2026) -- see
https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/
for the full article this summarizes. Unlike the per-scheme renewal alert
content in scheme_templates.py, this isn't about any individual client's own
certificate -- it's a general compliance-awareness announcement."""

NOTICE_URL = "https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/"
```

Replace with:

```python
"""Content for the "Transition Facilitation Order 2026" one-time broadcast
notice. Summarizes DPIIT's Transition Facilitation (Quality Control) Order,
2026 (S.O. 3417(E), effective 25 June 2026) -- see
https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/
for the full article this summarizes. Unlike the per-scheme renewal alert
content in scheme_templates.py, this isn't about any individual client's own
certificate -- it's a general compliance-awareness announcement."""
from email_template import CALENDLY_URL

NOTICE_URL = "https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/"
```

Current:

```python
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:4px 0 26px;">
              <a href="{NOTICE_URL}" target="_blank" rel="noopener noreferrer"
                 style="background:#2a78d6;color:#fff;padding:15px 42px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                Read the Full Breakdown
              </a>
            </td></tr>
          </table>
```

Replace with:

```python
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:4px 0 14px;">
              <a href="{NOTICE_URL}" target="_blank" rel="noopener noreferrer"
                 style="background:#2a78d6;color:#fff;padding:15px 42px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                Read the Full Breakdown
              </a>
            </td></tr>
            <tr><td align="center" style="padding:0 0 26px;">
              <a href="{CALENDLY_URL}" target="_blank" rel="noopener noreferrer"
                 style="background:#ffffff;color:#2a78d6;padding:13px 40px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;display:inline-block;border:2px solid #2a78d6;">
                Book an Appointment
              </a>
            </td></tr>
          </table>
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_notice_transition_facilitation_2026.py -v`
Expected: all passed (7 tests).

- [ ] **Step 10: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed, zero regressions.

- [ ] **Step 11: Commit**

```bash
git add dashboard-app/backend/email_template.py dashboard-app/backend/test_email_template.py dashboard-app/backend/notice_transition_facilitation_2026.py dashboard-app/backend/test_notice_transition_facilitation_2026.py
git commit -m "feat: add a Book an Appointment (Calendly) button to both email templates"
```

---

### Task 2: Verification and the WhatsApp reminder

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 2: Restart the backend server manually**

`--reload` has proven unreliable in this environment (confirmed twice already this session — edits silently failed to take effect). Stop whatever backend process is currently running and start a fresh one without `--reload`:

```bash
cd dashboard-app/backend
python -m uvicorn main:app --port 8040
```

Verify the new process's start time is after this task's file edits (e.g. via `Get-Process -Name python | Select-Object Id,StartTime` on Windows) before considering the restart complete.

- [ ] **Step 3: Verify live, read-only, against the running server**

First look up one real `client_id` (read-only, no write) to use for the renewal-email preview check:

```bash
cd dashboard-app/backend
PYTHONPATH="$(pwd)" python -c "
from db import read_clients, DEFAULT_DB_PATH
rows = read_clients(DEFAULT_DB_PATH)
print(rows[0]['client_id'] if rows else 'NO CLIENTS IN DB')
"
```

Then, substituting that `client_id` for `<client_id>` below:

```bash
python -c "
import requests
r = requests.get('http://127.0.0.1:8040/api/email-preview/<client_id>')
assert 'Book an Appointment' in r.json()['html']
r2 = requests.get('http://127.0.0.1:8040/api/notices/transition_facilitation_2026/preview')
assert 'Book an Appointment' in r2.json()['html']
print('CONFIRMED: both templates include the Calendly button')
"
```

Use a GET request only (as above) — do not hit any upload/replace endpoint live, per the lesson learned earlier this session about accidentally wiping production data with a live write during verification.

- [ ] **Step 4: Manual browser check**

Open the dashboard, preview an email from Client Data (any client) and from Notices, and confirm both show two buttons — the primary action on top, "Book an Appointment" (outlined style) below it — and that clicking "Book an Appointment" opens Calendly in a new tab rather than attempting to load in place.

- [ ] **Step 5: WhatsApp reminder (manual, external, not implemented by this plan)**

No code work remains for WhatsApp. When you create or update WhatsApp templates in Meta Business Manager — the per-scheme renewal templates and the `transition_facilitation_2026` notice template, all still pending approval — add a **URL-type button** component pointing to `https://calendly.com/cs-absoluteveritas/30min`. Since the link is static (not personalized per client), it needs no parameter in the send payload; `build_payload`/`build_whatsapp_payload` require no changes for this.
