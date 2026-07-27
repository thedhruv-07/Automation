# Per-Scheme Alert Templates (WhatsApp + Email)

## Problem

Every renewal alert — WhatsApp and email — currently uses one fixed template
for every client, regardless of `scheme`. With CRS data (~1,800 rows) now
entering the roster alongside ISI, sending the same wording to both is wrong:
ISI's messaging is framed around "license renewal," which doesn't fit CRS.
Both channels need scheme-appropriate content, selected automatically per
client, including when a single bulk-send batch mixes multiple schemes.

## Scope

Add per-scheme template/content selection to both the WhatsApp and email send
paths. Selection happens per record, not once per batch, so an unfiltered
"Send All Eligible" spanning multiple schemes sends each client the right
content. Configuration is via environment variables (matching the project's
existing `WHATSAPP_TEMPLATE_NAME` pattern), not a database table or admin UI
— adding a new scheme's wording later is an env var + redeploy, not a code
change.

Getting a CRS WhatsApp template approved in Meta Business Manager is a
manual, external process and out of scope here. This round wires up the
selection mechanism so it's ready the moment that approval lands; until then,
CRS WhatsApp sends are skipped (see below), not sent with wrong content.

## 1. `scheme_templates.py` (new module)

Single source of truth for scheme → content lookup, used by both channels.

```python
def get_whatsapp_template(scheme: str) -> tuple[str, str] | None:
    """Returns (template_name, template_lang) for the given scheme, or None
    if nothing is configured for it and it isn't ISI (which has a
    backward-compatible fallback -- see below)."""

def get_email_content(scheme: str) -> tuple[str, str]:
    """Returns (subject_template, intro_text) for the given scheme. Always
    returns something -- falls back to the generic default when no
    scheme-specific override is configured."""
```

**WhatsApp** (`get_whatsapp_template`):
- Reads `WHATSAPP_TEMPLATE_NAME_{SCHEME}` / `WHATSAPP_TEMPLATE_LANG_{SCHEME}`
  (e.g. `WHATSAPP_TEMPLATE_NAME_CRS`, uppercased scheme value).
- If both are set for that scheme, returns them.
- If unset and `scheme == "ISI"`, falls back to reading today's bare
  `WHATSAPP_TEMPLATE_NAME` / `WHATSAPP_TEMPLATE_LANG` env vars — this is what
  makes the change backward compatible: ISI needs zero new configuration.
- If unset for any other scheme (e.g. `"CRS"` before its template is
  approved), returns `None`.

**Email** (`get_email_content`):
- Reads `EMAIL_SUBJECT_TEMPLATE_{SCHEME}` (a Python format string with
  `{cert_name}`/`{company}` placeholders) and `EMAIL_INTRO_TEXT_{SCHEME}`
  (replaces the current hardcoded intro sentence in the email body).
- If either is unset for a given scheme (including ISI), falls back to the
  current generic default — updated as part of this change to drop the
  "[Action Required]" prefix:
  - Subject default: `"Renew {cert_name} — {company}"`
  - Intro default: today's existing sentence, unchanged (`"This is a
    notification regarding the certification held by <strong>{company}</strong>.
    Please review the details below and take action to ensure compliance
    continuity."`)
- Never returns `None` — there's no external approval blocker for email, so a
  reasonable generic default is always safe to send.

## 2. WhatsApp send path (`whatsapp_renewal_alerts.py`)

- `build_payload`, `send_one_alert`, and `run()` stop taking a single
  `template_name`/`template_lang` for the whole batch.
- Inside `run()`'s per-record loop, call
  `get_whatsapp_template(record["scheme"])`:
  - If it returns `(name, lang)`, build and send the payload as today, using
    that record's own template.
  - If it returns `None`, skip the record without attempting a send. Result
    dict gets `action: "skipped_no_template"` (new, alongside the existing
    `"skipped_duplicate"`/`"failed"`/`"sent"` actions).

## 3. Email send path (`email_alerts.py`)

- `send_email_via_brevo` calls `get_email_content(rec["scheme"])` per record
  to build the subject line and fill the body's intro sentence (passed
  through to `build_email_html`, which gains an `intro_text` parameter).
- `intro_text` defaults to today's exact hardcoded sentence, so
  `cert_automation.py` — the legacy standalone script that also calls
  `build_email_html` directly and is intentionally untouched by this project
  — keeps working unmodified without passing the new parameter at all.
- No new skip action for email — there's always a subject/intro to use.

## 4. `main.py` and job reporting

- `_run_send_all_job`/`_run_send_all_email_job` and the single-send endpoints
  stop reading `WHATSAPP_TEMPLATE_NAME`/`_LANG` from env and stop passing
  them into `run()` — selection now happens inside `run()` per record.
- **`/api/email-preview`** currently builds its own hardcoded subject
  (`f"[Action Required] Renew {record['cert_name']} — {record['company']}"`,
  main.py:242) and calls `build_email_html` directly with no intro text
  parameter — a separate, duplicate copy of the same content
  `send_email_via_brevo` builds. Left alone, the preview would show old
  generic wording while real sends became scheme-aware, silently lying about
  what's actually sent. This endpoint is updated to call
  `get_email_content(record["scheme"])` too, exactly like
  `send_email_via_brevo` does, so what the admin previews always matches what
  actually goes out.
- `_send_all_jobs[job_id]` (WhatsApp job dict) gains a `skipped_no_template`
  counter, initialized to `0`, incremented in the `progress()` callback when
  `result["action"] == "skipped_no_template"` — mirrors exactly how
  `skipped_no_email` was added to the email job dict in the previous round.
- Email job dicts are unaffected (no new counter there).

## 5. Frontend (`SendAllConfirmModal.jsx`)

- Gains one more conditional line, following the existing `skipped_no_email`
  pattern exactly:
  ```jsx
  {typeof job.skipped_no_template === "number" ? ` (${job.skipped_no_template} no template)` : ""}
  ```
- Shown only on WhatsApp jobs (email job dicts won't have this key, same as
  how `skipped_no_email` only appears on email jobs today).
- No new admin page for managing templates — adding a scheme's wording is an
  env var change + redeploy.

## Testing

- `scheme_templates.py`: fallback behavior for ISI (uses bare env vars),
  configured non-ISI scheme (uses its own suffixed vars), and unconfigured
  non-ISI scheme (`None` for WhatsApp, generic default for email).
- `run()`: a batch mixing ISI and CRS records sends each with its own
  template; an unconfigured CRS record is skipped with
  `action: "skipped_no_template"` and doesn't count as `failed`.
- `run_email_alerts()`: a mixed-scheme batch sends each record with its own
  subject/intro; an unconfigured scheme uses the generic (no
  "[Action Required]") default.
- `SendAllConfirmModal`: shows the no-template skip count when present on a
  WhatsApp job, omits it when absent (email jobs, or older job shapes).
- `/api/email-preview`: previewing a CRS record with `EMAIL_SUBJECT_TEMPLATE_CRS`
  configured returns that scheme's subject/intro, not the generic default.
- `build_email_html`: called the same way `cert_automation.py` calls it today
  (no `intro_text` argument) still renders today's exact sentence, confirming
  the default preserves that untouched script's behavior.
