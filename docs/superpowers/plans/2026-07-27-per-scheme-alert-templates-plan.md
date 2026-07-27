
# Per-Scheme Alert Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select WhatsApp templates and email subject/intro wording per-client based on their `scheme` (ISI, CRS, etc.), resolved per record so a mixed-scheme bulk send routes each client correctly, configured via env vars.

**Architecture:** A new `scheme_templates.py` module is the single source of truth for scheme → content lookup, used by both `whatsapp_renewal_alerts.py` and `email_alerts.py`. WhatsApp template selection happens per-record inside `run()`/`send_one_alert()`; a scheme with no configured template is skipped (new `skipped_no_template` action) rather than sent with the wrong wording. Email always has a safe generic fallback, so it never skips. `main.py`'s single-send, bulk-send-job, and `/api/email-preview` endpoints are updated to match — no endpoint keeps its own hardcoded template/subject anymore.

**Tech Stack:** Python/FastAPI/SQLite (`dashboard-app/backend/`), React/Vite (`dashboard-app/frontend/`), pytest, Vitest + React Testing Library.

---

### Task 1: `scheme_templates.py` — new lookup module

**Files:**
- Modify: `dashboard-app/backend/email_template.py`
- Create: `dashboard-app/backend/scheme_templates.py`
- Create: `dashboard-app/backend/test_scheme_templates.py`

- [ ] **Step 1: Move the email intro-text default into `email_template.py` as a named constant**

This is the single canonical copy of the default sentence — `scheme_templates.py` will import it rather than duplicating the string, and `cert_automation.py` (the legacy script that calls `build_email_html` directly, out of scope for this plan) keeps working via the same default.

Current (`dashboard-app/backend/email_template.py`):

```python
ACCENT = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE_PAGE = "#f9f9f7"
LINE = "#e1e0d9"

STATUS_CRITICAL = "#d03b3b"
STATUS_SERIOUS = "#ec835a"
STATUS_WARNING = "#fab219"
STATUS_GOOD = "#0ca30c"
```

Replace with:

```python
ACCENT = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE_PAGE = "#f9f9f7"
LINE = "#e1e0d9"

STATUS_CRITICAL = "#d03b3b"
STATUS_SERIOUS = "#ec835a"
STATUS_WARNING = "#fab219"
STATUS_GOOD = "#0ca30c"

DEFAULT_INTRO_TEXT = (
    "This is a notification regarding the certification held by "
    "<strong>{company}</strong>. Please review the details below and "
    "take action to ensure compliance continuity."
)
```

- [ ] **Step 2: Give `build_email_html` an `intro_text` parameter, defaulting to that constant**

Current:

```python
def build_email_html(
    rec: dict,
    org_name: str = "Absolute Veritas",
    org_website: str = "",
    org_contact: str = "",
    org_email: str = "cs@absoluteveritas.com",
    logo_src: str = "",
) -> str:
```

Replace with:

```python
def build_email_html(
    rec: dict,
    org_name: str = "Absolute Veritas",
    org_website: str = "",
    org_contact: str = "",
    org_email: str = "cs@absoluteveritas.com",
    logo_src: str = "",
    intro_text: str = DEFAULT_INTRO_TEXT,
) -> str:
```

Current (the hardcoded intro paragraph in the function body):

```python
                <p style="color:{INK_SECONDARY};font-size:14px;line-height:1.7;margin:0 0 26px;">
                  This is a notification regarding the certification held by
                  <strong>{rec['company']}</strong>. Please review the details below and
                  take action to ensure compliance continuity.
                </p>
```

Replace with:

```python
                <p style="color:{INK_SECONDARY};font-size:14px;line-height:1.7;margin:0 0 26px;">
                  {intro_text.format(company=rec['company'])}
                </p>
```

- [ ] **Step 3: Run `test_email_template.py` to confirm nothing broke**

Run: `cd dashboard-app/backend && python -m pytest test_email_template.py -v`
Expected: all 10 pre-existing tests still pass (none of them assert on the intro paragraph's exact text, and the default value produces identical rendered output to before).

- [ ] **Step 4: Add a test proving the new `intro_text` parameter is overridable and defaults correctly**

Add to the end of `dashboard-app/backend/test_email_template.py`:

```python
def test_default_intro_text_matches_original_wording():
    html = build_email_html(make_rec(5))
    assert (
        "This is a notification regarding the certification held by "
        "<strong>TechCorp</strong>. Please review the details below and "
        "take action to ensure compliance continuity." in html
    )


def test_custom_intro_text_overrides_default():
    html = build_email_html(
        make_rec(5), intro_text="Custom notice for <strong>{company}</strong>.",
    )
    assert "Custom notice for <strong>TechCorp</strong>." in html
    assert "This is a notification regarding" not in html
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_email_template.py -v`
Expected: 12 passed.

- [ ] **Step 6: Write the failing tests for `scheme_templates.py`**

Create `dashboard-app/backend/test_scheme_templates.py`:

```python
"""Tests for scheme_templates.py's per-scheme content lookup."""
from email_template import DEFAULT_INTRO_TEXT
from scheme_templates import (
    DEFAULT_EMAIL_SUBJECT_TEMPLATE, get_email_content, get_whatsapp_template,
)


def test_get_whatsapp_template_returns_scheme_specific_override_when_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_CRS", "crs_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_CRS", "en_US")

    assert get_whatsapp_template("CRS") == ("crs_renewal_alert", "en_US")


def test_get_whatsapp_template_isi_falls_back_to_bare_env_vars_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_ISI", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_ISI", raising=False)
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "legacy_template")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en_GB")

    assert get_whatsapp_template("ISI") == ("legacy_template", "en_GB")


def test_get_whatsapp_template_isi_defaults_when_nothing_set(monkeypatch):
    for var in ("WHATSAPP_TEMPLATE_NAME_ISI", "WHATSAPP_TEMPLATE_LANG_ISI",
                "WHATSAPP_TEMPLATE_NAME", "WHATSAPP_TEMPLATE_LANG"):
        monkeypatch.delenv(var, raising=False)

    assert get_whatsapp_template("ISI") == ("cert_renewal_alert", "en")


def test_get_whatsapp_template_isi_specific_override_takes_priority_over_bare_fallback(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_ISI", "isi_specific_template")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_ISI", "en_US")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "legacy_template")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en_GB")

    assert get_whatsapp_template("ISI") == ("isi_specific_template", "en_US")


def test_get_whatsapp_template_returns_none_for_unconfigured_non_isi_scheme(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)

    assert get_whatsapp_template("CRS") is None


def test_get_whatsapp_template_requires_both_name_and_lang_for_scheme_override(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_CRS", "crs_renewal_alert")
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)

    assert get_whatsapp_template("CRS") is None


def test_get_email_content_returns_scheme_specific_override_when_configured(monkeypatch):
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal for {cert_name}")
    monkeypatch.setenv("EMAIL_INTRO_TEXT_CRS", "Your CRS registration for <strong>{company}</strong> needs renewal.")

    subject_template, intro_text = get_email_content("CRS")

    assert subject_template == "Registration renewal for {cert_name}"
    assert intro_text == "Your CRS registration for <strong>{company}</strong> needs renewal."


def test_get_email_content_falls_back_to_generic_default_when_unconfigured(monkeypatch):
    for var in ("EMAIL_SUBJECT_TEMPLATE_ISI", "EMAIL_INTRO_TEXT_ISI"):
        monkeypatch.delenv(var, raising=False)

    subject_template, intro_text = get_email_content("ISI")

    assert subject_template == DEFAULT_EMAIL_SUBJECT_TEMPLATE
    assert intro_text == DEFAULT_INTRO_TEXT


def test_get_email_content_falls_back_independently_per_field(monkeypatch):
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal for {cert_name}")
    monkeypatch.delenv("EMAIL_INTRO_TEXT_CRS", raising=False)

    subject_template, intro_text = get_email_content("CRS")

    assert subject_template == "Registration renewal for {cert_name}"
    assert intro_text == DEFAULT_INTRO_TEXT
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_scheme_templates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scheme_templates'` — the module doesn't exist yet.

- [ ] **Step 8: Create `scheme_templates.py`**

Create `dashboard-app/backend/scheme_templates.py`:

```python
"""Per-scheme alert content selection for WhatsApp and email.

Configuration is env-var driven, matching the project's existing
WHATSAPP_TEMPLATE_NAME pattern: WHATSAPP_TEMPLATE_NAME_<SCHEME> /
WHATSAPP_TEMPLATE_LANG_<SCHEME> for WhatsApp, EMAIL_SUBJECT_TEMPLATE_<SCHEME> /
EMAIL_INTRO_TEXT_<SCHEME> for email. Adding a new scheme's wording is an env
var change + redeploy, not a code change.
"""
import os

from email_template import DEFAULT_INTRO_TEXT

DEFAULT_EMAIL_SUBJECT_TEMPLATE = "Renew {cert_name} — {company}"


def get_whatsapp_template(scheme: str) -> tuple[str, str] | None:
    """Returns (template_name, template_lang) for the given scheme, or None
    if nothing is configured for it and it isn't ISI.

    ISI falls back to the bare WHATSAPP_TEMPLATE_NAME/WHATSAPP_TEMPLATE_LANG
    env vars when no ISI-specific override is set -- this is what keeps
    existing ISI sends working with zero new configuration. Any other
    scheme (e.g. CRS, before its template is approved in Meta Business
    Manager) returns None when unconfigured, so callers skip it rather than
    sending the wrong wording."""
    scheme_key = scheme.upper()
    name = os.environ.get(f"WHATSAPP_TEMPLATE_NAME_{scheme_key}")
    lang = os.environ.get(f"WHATSAPP_TEMPLATE_LANG_{scheme_key}")
    if name and lang:
        return name, lang

    if scheme == "ISI":
        name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        return name, lang

    return None


def get_email_content(scheme: str) -> tuple[str, str]:
    """Returns (subject_template, intro_text) for the given scheme, each
    format strings with {cert_name}/{company} placeholders (intro_text only
    uses {company}). Always returns something -- there's no external
    approval blocker for email (unlike WhatsApp templates), so falling back
    to a generic default is always safe to send. Each field falls back
    independently: configuring only a scheme's subject still gets the
    default intro, and vice versa."""
    scheme_key = scheme.upper()
    subject_template = os.environ.get(f"EMAIL_SUBJECT_TEMPLATE_{scheme_key}")
    intro_text = os.environ.get(f"EMAIL_INTRO_TEXT_{scheme_key}")
    return (
        subject_template or DEFAULT_EMAIL_SUBJECT_TEMPLATE,
        intro_text or DEFAULT_INTRO_TEXT,
    )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_scheme_templates.py -v`
Expected: 9 passed.

- [ ] **Step 10: Commit**

```bash
git add dashboard-app/backend/email_template.py dashboard-app/backend/scheme_templates.py dashboard-app/backend/test_email_template.py dashboard-app/backend/test_scheme_templates.py
git commit -m "feat: add scheme_templates.py for per-scheme WhatsApp/email content lookup"
```

---

### Task 2: WhatsApp send path — `whatsapp_renewal_alerts.py`

**Files:**
- Modify: `dashboard-app/backend/whatsapp_renewal_alerts.py`
- Modify: `dashboard-app/backend/test_whatsapp_renewal_alerts.py`

- [ ] **Step 1: Add the import**

Current (`dashboard-app/backend/whatsapp_renewal_alerts.py`):

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, read_clients, find_client_by_id, load_sent_log, save_sent_log,
    RECORD_FIELDS, get_eligible_clients,
)
```

Replace with:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, read_clients, find_client_by_id, load_sent_log, save_sent_log,
    RECORD_FIELDS, get_eligible_clients,
)
from scheme_templates import get_whatsapp_template  # noqa: E402
```

- [ ] **Step 2: Update `send_one_alert` to resolve its template per-record**

Current:

```python
def send_one_alert(
    record: dict,
    sent_log: dict,
    today: str,
    token: str,
    phone_number_id: str,
    template_name: str,
    template_lang: str,
    to_phone_override: str | None = None,
    send_fn=send_message,
) -> dict:
    """Send (or skip if already sent today) one alert-eligible client's WhatsApp
    renewal message. Mutates sent_log in place on a successful send. Returns a
    result dict with action one of 'sent' / 'skipped_duplicate' / 'failed'."""
    key = dedup_key(record["client_id"], record["status"], today)
    to_phone = (
        normalize_phone(to_phone_override) if to_phone_override
        else normalize_phone(record["phone"])
    )

    if key in sent_log:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "skipped_duplicate",
            "to": to_phone,
        }

    try:
        payload = build_payload(record, to_phone, template_name, template_lang)
        ok, info = send_fn(payload, token, phone_number_id)
        if ok:
            sent_log[key] = {
                "sent_at": datetime.now().isoformat(),
                "message_id": info.get("message_id"),
                "phone": to_phone,
            }
            return {
                "client_id": record["client_id"], "name": record["name"],
                "status": record["status"], "action": "sent",
                "to": to_phone, "message_id": info.get("message_id"),
            }
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_phone, "error": info.get("error"),
        }
    except Exception as exc:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_phone, "error": str(exc),
        }
```

Replace with:

```python
def send_one_alert(
    record: dict,
    sent_log: dict,
    today: str,
    token: str,
    phone_number_id: str,
    to_phone_override: str | None = None,
    send_fn=send_message,
) -> dict:
    """Send (or skip) one alert-eligible client's WhatsApp renewal message.
    Mutates sent_log in place on a successful send. Returns a result dict
    with action one of 'sent' / 'skipped_duplicate' / 'skipped_no_template' /
    'failed'."""
    key = dedup_key(record["client_id"], record["status"], today)
    to_phone = (
        normalize_phone(to_phone_override) if to_phone_override
        else normalize_phone(record["phone"])
    )

    if key in sent_log:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "skipped_duplicate",
            "to": to_phone,
        }

    template = get_whatsapp_template(record["scheme"])
    if template is None:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "skipped_no_template",
            "to": to_phone,
        }
    template_name, template_lang = template

    try:
        payload = build_payload(record, to_phone, template_name, template_lang)
        ok, info = send_fn(payload, token, phone_number_id)
        if ok:
            sent_log[key] = {
                "sent_at": datetime.now().isoformat(),
                "message_id": info.get("message_id"),
                "phone": to_phone,
            }
            return {
                "client_id": record["client_id"], "name": record["name"],
                "status": record["status"], "action": "sent",
                "to": to_phone, "message_id": info.get("message_id"),
            }
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_phone, "error": info.get("error"),
        }
    except Exception as exc:
        return {
            "client_id": record["client_id"], "name": record["name"],
            "status": record["status"], "action": "failed",
            "to": to_phone, "error": str(exc),
        }
```

- [ ] **Step 3: Update `run()` to resolve the template per-record too**

Current:

```python
def run(
    db_path,
    token: str,
    phone_number_id: str,
    template_name: str,
    template_lang: str,
    dry_run: bool = False,
    test_number: str | None = None,
    today: str | None = None,
    send_fn=send_message,
    on_progress=None,
    status: str | None = None,
    cert_type: str | None = None,
    expiry_before: str | None = None,
    search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    sent_log = load_sent_log(db_path)
    persist_log = not dry_run and not test_number
    log_dirty = False
    results = []

    for rec in records:
        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])
        key = dedup_key(rec["client_id"], rec["status"], today)

        if key in sent_log:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "skipped_duplicate",
                "to": to_phone,
            }
        elif dry_run:
            payload = build_payload(rec, to_phone, template_name, template_lang)
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "dry_run",
                "to": to_phone, "payload": payload,
            }
        else:
            result = send_one_alert(
                rec, sent_log, today, token, phone_number_id,
                template_name, template_lang,
                to_phone_override=test_number, send_fn=send_fn,
            )
            if result["action"] == "sent":
                log_dirty = True

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    if persist_log and log_dirty:
        save_sent_log(db_path, sent_log)

    return results
```

Replace with:

```python
def run(
    db_path,
    token: str,
    phone_number_id: str,
    dry_run: bool = False,
    test_number: str | None = None,
    today: str | None = None,
    send_fn=send_message,
    on_progress=None,
    status: str | None = None,
    cert_type: str | None = None,
    expiry_before: str | None = None,
    search: str | None = None,
    scheme: str | None = None,
) -> list[dict]:
    today = today or datetime.now().strftime("%Y-%m-%d")
    records = get_eligible_clients(
        db_path, status=status, cert_type=cert_type, expiry_before=expiry_before,
        search=search, scheme=scheme,
    )
    sent_log = load_sent_log(db_path)
    persist_log = not dry_run and not test_number
    log_dirty = False
    results = []

    for rec in records:
        to_phone = normalize_phone(test_number) if test_number else normalize_phone(rec["phone"])
        key = dedup_key(rec["client_id"], rec["status"], today)

        if key in sent_log:
            result = {
                "client_id": rec["client_id"], "name": rec["name"],
                "status": rec["status"], "action": "skipped_duplicate",
                "to": to_phone,
            }
        else:
            template = get_whatsapp_template(rec["scheme"])
            if template is None:
                result = {
                    "client_id": rec["client_id"], "name": rec["name"],
                    "status": rec["status"], "action": "skipped_no_template",
                    "to": to_phone,
                }
            elif dry_run:
                template_name, template_lang = template
                payload = build_payload(rec, to_phone, template_name, template_lang)
                result = {
                    "client_id": rec["client_id"], "name": rec["name"],
                    "status": rec["status"], "action": "dry_run",
                    "to": to_phone, "payload": payload,
                }
            else:
                result = send_one_alert(
                    rec, sent_log, today, token, phone_number_id,
                    to_phone_override=test_number, send_fn=send_fn,
                )
                if result["action"] == "sent":
                    log_dirty = True

        results.append(result)
        if on_progress:
            try:
                on_progress(result, len(records))
            except Exception as exc:
                print(f"⚠ on_progress callback raised {exc!r}; continuing send batch.")

    if persist_log and log_dirty:
        save_sent_log(db_path, sent_log)

    return results
```

- [ ] **Step 4: Update the CLI `main()` function — it no longer resolves a single template up front**

Current:

```python
def main(argv=None) -> int:
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args(argv)

    token = os.environ.get("WHATSAPP_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    if not args.dry_run and (not token or not phone_number_id):
        print("❌ WHATSAPP_TOKEN and PHONE_NUMBER_ID must be set in .env (not required for --dry-run).")
        return 1

    template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")

    results = run(
        db_path=args.db,
        token=token,
        phone_number_id=phone_number_id,
        template_name=template_name,
        template_lang=template_lang,
        dry_run=args.dry_run,
        test_number=args.test_number,
    )
```

Replace with:

```python
def main(argv=None) -> int:
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args(argv)

    token = os.environ.get("WHATSAPP_TOKEN")
    phone_number_id = os.environ.get("PHONE_NUMBER_ID")
    if not args.dry_run and (not token or not phone_number_id):
        print("❌ WHATSAPP_TOKEN and PHONE_NUMBER_ID must be set in .env (not required for --dry-run).")
        return 1

    results = run(
        db_path=args.db,
        token=token,
        phone_number_id=phone_number_id,
        dry_run=args.dry_run,
        test_number=args.test_number,
    )
```

- [ ] **Step 5: Add a `skipped_no_template` icon and summary count so the CLI doesn't crash on a skipped record**

Current:

```python
def format_result_line(result: dict) -> str:
    icons = {"sent": "✅ SENT", "skipped_duplicate": "⏭ SKIP",
              "failed": "❌ FAIL", "dry_run": "🧪 DRY-RUN"}
    label = icons[result["action"]]
```

Replace with:

```python
def format_result_line(result: dict) -> str:
    icons = {"sent": "✅ SENT", "skipped_duplicate": "⏭ SKIP",
              "skipped_no_template": "⏭ SKIP (no template)",
              "failed": "❌ FAIL", "dry_run": "🧪 DRY-RUN"}
    label = icons[result["action"]]
```

Current:

```python
    sent = sum(1 for r in results if r["action"] == "sent")
    skipped = sum(1 for r in results if r["action"] == "skipped_duplicate")
    failed = sum(1 for r in results if r["action"] == "failed")
    dry = sum(1 for r in results if r["action"] == "dry_run")
    print(f"\nSummary: {sent} sent, {skipped} skipped (duplicate), {failed} failed, {dry} dry-run.")
    return 0
```

Replace with:

```python
    sent = sum(1 for r in results if r["action"] == "sent")
    skipped = sum(1 for r in results if r["action"] == "skipped_duplicate")
    skipped_no_template = sum(1 for r in results if r["action"] == "skipped_no_template")
    failed = sum(1 for r in results if r["action"] == "failed")
    dry = sum(1 for r in results if r["action"] == "dry_run")
    print(
        f"\nSummary: {sent} sent, {skipped} skipped (duplicate), "
        f"{skipped_no_template} skipped (no template), {failed} failed, {dry} dry-run."
    )
    return 0
```

- [ ] **Step 6: Run the full backend test suite and confirm the expected failures**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: many failures — every existing call to `run(...)` or `send_one_alert(...)` in this file still passes `template_name=`/`template_lang=` (or the two positional args), which those functions no longer accept, producing `TypeError: run() got an unexpected keyword argument 'template_name'` (or the positional equivalent). This is expected — Step 7 fixes every one of these calls.

- [ ] **Step 7: Fix every existing test call site**

`test_run_dry_run_makes_no_calls_and_no_log_writes`. Current:

```python
    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )
```

Replace with:

```python
    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )
```

`test_run_dry_run_honors_dedup_log_for_already_sent_client`. Current:

```python
    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )
```

Replace with:

```python
    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        dry_run=True, today="2026-07-17", send_fn=send_fn,
    )
```

`test_run_live_sends_and_dedups_on_second_call` has two calls. Current:

```python
    first = run(db_path=db_path, token="tok", phone_number_id="pid",
                template_name="cert_renewal_alert", template_lang="en_US",
                today="2026-07-17", send_fn=send_fn)
    assert first[0]["action"] == "sent"
    assert send_fn.call_count == 1
    assert "CLT001|CRITICAL|2026-07-17" in load_sent_log(db_path)

    second = run(db_path=db_path, token="tok", phone_number_id="pid",
                 template_name="cert_renewal_alert", template_lang="en_US",
                 today="2026-07-17", send_fn=send_fn)
    assert second[0]["action"] == "skipped_duplicate"
    assert send_fn.call_count == 1
```

Replace with:

```python
    first = run(db_path=db_path, token="tok", phone_number_id="pid",
                today="2026-07-17", send_fn=send_fn)
    assert first[0]["action"] == "sent"
    assert send_fn.call_count == 1
    assert "CLT001|CRITICAL|2026-07-17" in load_sent_log(db_path)

    second = run(db_path=db_path, token="tok", phone_number_id="pid",
                 today="2026-07-17", send_fn=send_fn)
    assert second[0]["action"] == "skipped_duplicate"
    assert send_fn.call_count == 1
```

`test_run_test_number_overrides_phone_and_skips_log_write`. Current:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  test_number="+919999999999", today="2026-07-17", send_fn=send_fn)
```

Replace with:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  test_number="+919999999999", today="2026-07-17", send_fn=send_fn)
```

`test_run_failed_send_does_not_write_log`. Current:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn)
```

Replace with:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)
```

`test_run_mixed_outcomes_in_single_call_preserves_earlier_successes`. Current:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn)
```

Replace with:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)
```

`test_run_filters_by_cert_type`. Current:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn, cert_type="OSHA")
```

Replace with:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn, cert_type="OSHA")
```

`test_run_filters_by_search`. Current:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn, search="BuildRight")
```

Replace with:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn, search="BuildRight")
```

`test_run_filters_by_scheme`. Current:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  template_name="cert_renewal_alert", template_lang="en_US",
                  today="2026-07-17", send_fn=send_fn, scheme="FMCS")
```

Replace with:

```python
    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn, scheme="FMCS")
```

`test_run_calls_on_progress_for_each_record`. Current:

```python
    run(
        db_path=db_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )
```

Replace with:

```python
    run(
        db_path=db_path, token="tok", phone_number_id="pid",
        today="2026-07-17", send_fn=send_fn,
        on_progress=lambda result, total: progress_calls.append((result["action"], total)),
    )
```

`test_run_survives_raising_on_progress_and_still_persists_sent_log`. Current:

```python
    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        template_name="cert_renewal_alert", template_lang="en_US",
        today="2026-07-17", send_fn=send_fn,
        on_progress=flaky_on_progress,
    )
```

Replace with:

```python
    results = run(
        db_path=db_path, token="tok", phone_number_id="pid",
        today="2026-07-17", send_fn=send_fn,
        on_progress=flaky_on_progress,
    )
```

`test_send_one_alert_success_updates_log_in_place`. Current:

```python
def test_send_one_alert_success_updates_log_in_place():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return True, {"message_id": "wamid.ABC"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        "cert_renewal_alert", "en", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "sent", "to": "919876543210", "message_id": "wamid.ABC",
    }
    assert "CLT001|CRITICAL|2026-07-18" in sent_log
    assert sent_log["CLT001|CRITICAL|2026-07-18"]["message_id"] == "wamid.ABC"
```

Replace with:

```python
def test_send_one_alert_success_updates_log_in_place():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return True, {"message_id": "wamid.ABC"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "sent", "to": "919876543210", "message_id": "wamid.ABC",
    }
    assert "CLT001|CRITICAL|2026-07-18" in sent_log
    assert sent_log["CLT001|CRITICAL|2026-07-18"]["message_id"] == "wamid.ABC"
```

`test_send_one_alert_skips_when_already_in_log`. Current:

```python
def test_send_one_alert_skips_when_already_in_log():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.OLD"}}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called when already sent")

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        "cert_renewal_alert", "en", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "skipped_duplicate", "to": "919876543210",
    }
```

Replace with:

```python
def test_send_one_alert_skips_when_already_in_log():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {"CLT001|CRITICAL|2026-07-18": {"message_id": "wamid.OLD"}}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called when already sent")

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "skipped_duplicate", "to": "919876543210",
    }
```

`test_send_one_alert_uses_override_phone_and_reports_failure`. Current:

```python
def test_send_one_alert_uses_override_phone_and_reports_failure():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return False, {"error": "Invalid parameter"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        "cert_renewal_alert", "en", to_phone_override="919000000000",
        send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "failed", "to": "919000000000", "error": "Invalid parameter",
    }
    assert sent_log == {}
```

Replace with:

```python
def test_send_one_alert_uses_override_phone_and_reports_failure():
    record = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "cert_name": "ISO 9001", "cert_id": "ISO-1", "scheme": "ISI",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919876543210",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        return False, {"error": "Invalid parameter"}

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123",
        to_phone_override="919000000000", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT001", "name": "Rahul Sharma", "status": "CRITICAL",
        "action": "failed", "to": "919000000000", "error": "Invalid parameter",
    }
    assert sent_log == {}
```

- [ ] **Step 8: Run tests to verify the existing suite passes again**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: all previously-existing tests pass.

- [ ] **Step 9: Add new tests for per-scheme template resolution**

Add after `test_send_one_alert_uses_override_phone_and_reports_failure`:

```python
def test_run_resolves_template_per_record_in_mixed_scheme_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_CRS", "crs_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_CRS", "en")
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026",
         "https://x/renew?id=ISO-1", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=CRS-1", "URGENT"],
    ])
    send_fn = Mock(return_value=(True, {"message_id": "wamid.ABC"}))

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)

    assert [r["action"] for r in results] == ["sent", "sent"]
    isi_payload, crs_payload = (call.args[0] for call in send_fn.call_args_list)
    assert isi_payload["template"]["name"] == "cert_renewal_alert"
    assert crs_payload["template"]["name"] == "crs_renewal_alert"


def test_run_skips_records_when_scheme_has_no_configured_template(tmp_path, monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026",
         "https://x/renew?id=CRS-1", "URGENT"],
    ])
    send_fn = Mock()

    results = run(db_path=db_path, token="tok", phone_number_id="pid",
                  today="2026-07-17", send_fn=send_fn)

    assert results[0]["action"] == "skipped_no_template"
    send_fn.assert_not_called()
    assert load_sent_log(db_path) == {}


def test_send_one_alert_skips_when_scheme_has_no_configured_template(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)
    record = {
        "client_id": "CLT002", "name": "Priya Mehta", "company": "BuildRight",
        "cert_name": "CRS-Cert", "cert_id": "CRS-1", "scheme": "CRS",
        "expiry_date": "24-07-2026", "status": "CRITICAL", "phone": "919812345678",
    }
    sent_log = {}

    def fake_send(payload, token, phone_number_id):
        raise AssertionError("should not be called when scheme has no configured template")

    result = send_one_alert(
        record, sent_log, "2026-07-18", "tok", "pid123", send_fn=fake_send,
    )

    assert result == {
        "client_id": "CLT002", "name": "Priya Mehta", "status": "CRITICAL",
        "action": "skipped_no_template", "to": "919812345678",
    }
```

Add after `test_format_result_line_skipped`:

```python
def test_format_result_line_skipped_no_template():
    result = {"action": "skipped_no_template", "client_id": "CLT001",
              "name": "Rahul Sharma", "status": "CRITICAL"}
    assert format_result_line(result) == "⏭ SKIP (no template) | CLT001 Rahul Sharma | CRITICAL"
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_whatsapp_renewal_alerts.py -v`
Expected: all passed.

- [ ] **Step 11: Commit**

```bash
git add dashboard-app/backend/whatsapp_renewal_alerts.py dashboard-app/backend/test_whatsapp_renewal_alerts.py
git commit -m "feat: resolve WhatsApp template per-record by scheme, skipping unconfigured schemes"
```

---

### Task 3: Email send path — `email_alerts.py`

**Files:**
- Modify: `dashboard-app/backend/email_alerts.py`
- Modify: `dashboard-app/backend/test_email_alerts.py`

- [ ] **Step 1: Add the import and use `get_email_content` in `send_email_via_brevo`**

Current (`dashboard-app/backend/email_alerts.py`):

```python
from db import get_eligible_clients, load_email_sent_log, save_email_sent_log
from email_template import build_email_html
from whatsapp_renewal_alerts import dedup_key
```

Replace with:

```python
from db import get_eligible_clients, load_email_sent_log, save_email_sent_log
from email_template import build_email_html
from scheme_templates import get_email_content
from whatsapp_renewal_alerts import dedup_key
```

Current:

```python
def send_email_via_brevo(rec: dict, brevo_api_key: str, email_sender: str, org_name: str, to_email: str):
    """Builds the HTML (same build_email_html() the preview endpoint uses) and
    sends via Brevo's transactional email API. Returns (success, info_dict)
    matching whatsapp_renewal_alerts.send_message()'s contract."""
    expiry_dt = _parse_expiry(rec["expiry_date"])
    days_left = (expiry_dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    template_rec = {
        **rec,
        "days_left": days_left,
        "expiry_formatted": expiry_dt.strftime("%d %B %Y"),
    }

    logo_exists = LOGO_PATH.exists()
    logo_src = f"cid:{LOGO_CID}" if logo_exists else ""
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src,
    )
    subject = f"[Action Required] Renew {rec['cert_name']} — {rec['company']}"
```

Replace with:

```python
def send_email_via_brevo(rec: dict, brevo_api_key: str, email_sender: str, org_name: str, to_email: str):
    """Builds the HTML (same build_email_html() the preview endpoint uses) and
    sends via Brevo's transactional email API. Returns (success, info_dict)
    matching whatsapp_renewal_alerts.send_message()'s contract."""
    expiry_dt = _parse_expiry(rec["expiry_date"])
    days_left = (expiry_dt - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days
    template_rec = {
        **rec,
        "days_left": days_left,
        "expiry_formatted": expiry_dt.strftime("%d %B %Y"),
    }

    logo_exists = LOGO_PATH.exists()
    logo_src = f"cid:{LOGO_CID}" if logo_exists else ""
    subject_template, intro_text = get_email_content(rec["scheme"])
    html = build_email_html(
        template_rec, org_name=org_name, org_website="", org_contact="",
        org_email="cs@absoluteveritas.com", logo_src=logo_src, intro_text=intro_text,
    )
    subject = subject_template.format(cert_name=rec["cert_name"], company=rec["company"])
```

- [ ] **Step 2: Run tests to see the one expected failure**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: `test_send_email_via_brevo_success` FAILS — it still asserts the old `"[Action Required] Renew ISO 9001 — TechCorp"` subject, which no longer matches the new default (`"Renew ISO 9001 — TechCorp"`, no prefix). Every other test passes unchanged.

- [ ] **Step 3: Fix the one affected assertion**

Current (`dashboard-app/backend/test_email_alerts.py`):

```python
    assert payload["subject"] == "[Action Required] Renew ISO 9001 — TechCorp"
```

Replace with:

```python
    assert payload["subject"] == "Renew ISO 9001 — TechCorp"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all passed.

- [ ] **Step 5: Add a test proving per-scheme subject/intro selection**

Add after `test_send_email_via_brevo_success`:

```python
def test_send_email_via_brevo_uses_scheme_specific_subject_and_intro(monkeypatch):
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal: {cert_name}")
    monkeypatch.setenv("EMAIL_INTRO_TEXT_CRS", "Your CRS registration for <strong>{company}</strong> needs renewal.")
    crs_row = ("CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
               "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT")
    record = _record_dict(crs_row)
    mock_response = Mock(status_code=201)
    mock_response.json.return_value = {"messageId": "brevo-msg-2"}

    with patch("email_alerts.requests.post", return_value=mock_response) as mock_post:
        send_email_via_brevo(record, "api-key", "sender@x.com", "Absolute Veritas", to_email="d@x.com")

    payload = mock_post.call_args.kwargs["json"]
    assert payload["subject"] == "Registration renewal: CRS-Cert"
    assert "Your CRS registration for <strong>FreshFoods</strong> needs renewal." in payload["htmlContent"]
```

- [ ] **Step 6: Run tests to verify it passes**

Run: `cd dashboard-app/backend && python -m pytest test_email_alerts.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/email_alerts.py dashboard-app/backend/test_email_alerts.py
git commit -m "feat: resolve email subject/intro per-record by scheme, drop [Action Required] prefix"
```

---

### Task 4: `main.py` — endpoints, bulk-send jobs, email preview

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Import `get_email_content`**

Current:

```python
from email_template import build_email_html  # noqa: E402
from import_helpers import RowCollector  # noqa: E402
from import_formats import IMPORT_FORMATS  # noqa: E402
```

Replace with:

```python
from email_template import build_email_html  # noqa: E402
from import_helpers import RowCollector  # noqa: E402
from import_formats import IMPORT_FORMATS  # noqa: E402
from scheme_templates import get_email_content  # noqa: E402
```

- [ ] **Step 2: Update `/api/email-preview/{client_id}` to use scheme-specific content**

Current:

```python
    html = build_email_html(
        rec,
        org_name="Absolute Veritas",
        org_website="",
        org_contact="",
        org_email="cs@absoluteveritas.com",
        logo_src=_logo_data_uri(),
    )
    subject = f"[Action Required] Renew {record['cert_name']} — {record['company']}"
    return {"subject": subject, "html": html}
```

Replace with:

```python
    subject_template, intro_text = get_email_content(record["scheme"])
    html = build_email_html(
        rec,
        org_name="Absolute Veritas",
        org_website="",
        org_contact="",
        org_email="cs@absoluteveritas.com",
        logo_src=_logo_data_uri(),
        intro_text=intro_text,
    )
    subject = subject_template.format(cert_name=record["cert_name"], company=record["company"])
    return {"subject": subject, "html": html}
```

- [ ] **Step 3: Update the single-send WhatsApp endpoint `/api/send/{client_id}`**

Current:

```python
    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        result = send_one_alert(
            record, sent_log, today, token, phone_number_id,
            template_name, template_lang, to_phone_override=test_number,
        )

        if result["action"] == "sent":
            if not test_number:
                save_sent_log(DEFAULT_DB_PATH, sent_log)
            return {"status": "sent", "message_id": result["message_id"]}
        if result["action"] == "skipped_duplicate":
            raise HTTPException(
                status_code=409,
                detail="Alert already sent today for this client/status",
            )
        raise HTTPException(status_code=502, detail=result.get("error", "Unknown error"))
    finally:
        with _send_lock:
            _pending_sends.discard(client_id)
```

Replace with:

```python
    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        result = send_one_alert(
            record, sent_log, today, token, phone_number_id, to_phone_override=test_number,
        )

        if result["action"] == "sent":
            if not test_number:
                save_sent_log(DEFAULT_DB_PATH, sent_log)
            return {"status": "sent", "message_id": result["message_id"]}
        if result["action"] == "skipped_duplicate":
            raise HTTPException(
                status_code=409,
                detail="Alert already sent today for this client/status",
            )
        if result["action"] == "skipped_no_template":
            raise HTTPException(
                status_code=400,
                detail=f"No WhatsApp template configured for scheme {record['scheme']!r} yet.",
            )
        raise HTTPException(status_code=502, detail=result.get("error", "Unknown error"))
    finally:
        with _send_lock:
            _pending_sends.discard(client_id)
```

- [ ] **Step 4: Update `_run_send_all_job` and `/api/send-all`**

Current:

```python
def _run_send_all_job(
    job_id, token, phone_number_id, template_name, template_lang, test_number,
    status=None, cert_type=None, expiry_before=None, search=None, scheme=None,
):
    def progress(result, total):
        job = _send_all_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        run(
            DEFAULT_DB_PATH, token, phone_number_id, template_name, template_lang,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
        )
```

Replace with:

```python
def _run_send_all_job(
    job_id, token, phone_number_id, test_number,
    status=None, cert_type=None, expiry_before=None, search=None, scheme=None,
):
    def progress(result, total):
        job = _send_all_jobs[job_id]
        job["total"] = total
        if result["action"] == "sent":
            job["sent"] += 1
        elif result["action"] == "skipped_duplicate":
            job["skipped"] += 1
        elif result["action"] == "skipped_no_template":
            job["skipped_no_template"] += 1
        elif result["action"] == "failed":
            job["failed"] += 1

    try:
        run(
            DEFAULT_DB_PATH, token, phone_number_id,
            dry_run=False, test_number=test_number, on_progress=progress,
            status=status, cert_type=cert_type, expiry_before=expiry_before, search=search, scheme=scheme,
        )
```

Current:

```python
    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        job_id = str(uuid.uuid4())
        _send_all_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "failed": 0, "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(
                job_id, token, phone_number_id, template_name, template_lang, test_number,
                status or None, cert_type or None, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
```

Replace with:

```python
    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        job_id = str(uuid.uuid4())
        _send_all_jobs[job_id] = {
            "total": 0, "sent": 0, "skipped": 0, "skipped_no_template": 0, "failed": 0,
            "done": False, "error": None,
        }
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(
                job_id, token, phone_number_id, test_number,
                status or None, cert_type or None, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
```

- [ ] **Step 5: Run the full backend test suite and confirm the expected failures**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: a handful of failures in `test_main.py`:
- `test_email_preview_returns_subject_and_html` (old `"[Action Required]"` subject no longer matches)
- `test_send_all_respects_scheme_filter` (its FMCS-scheme record now has no configured WhatsApp template, so it's skipped instead of sent — `final["sent"] == 1` fails)

Everything else should still pass, since `main_module.run`/`send_one_alert`'s call sites were fully updated in Steps 3-4 and no other test sets `template_name`/`template_lang` directly against these functions.

- [ ] **Step 6: Fix `test_email_preview_returns_subject_and_html`**

Current (`dashboard-app/backend/test_main.py`):

```python
    assert data["subject"] == "[Action Required] Renew ISO 9001 — TechCorp"
```

Replace with:

```python
    assert data["subject"] == "Renew ISO 9001 — TechCorp"
```

- [ ] **Step 7: Fix `test_send_all_respects_scheme_filter` — give its FMCS record a configured template**

Current:

```python
def test_send_all_respects_scheme_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all", params={"scheme": "FMCS"})
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/send-all/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["total"] == 1
    assert final["sent"] == 1
```

Replace with:

```python
def test_send_all_respects_scheme_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "FMCS-Cert", "FMCS", "FMCS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_FMCS", "fmcs_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_FMCS", "en")

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all", params={"scheme": "FMCS"})
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/send-all/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["total"] == 1
    assert final["sent"] == 1
```

- [ ] **Step 8: Run tests to verify the existing suite passes again**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all previously-existing tests pass.

- [ ] **Step 9: Add a test for the single-send endpoint's new skip response**

Add after `test_send_alert_skipped_duplicate_from_send_one_alert_returns_409` (find it in `dashboard-app/backend/test_main.py` and add immediately after its closing line):

```python
def test_send_alert_no_template_for_scheme_returns_400(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)

    response = client.post("/api/send/CLT001")

    assert response.status_code == 400
    assert "CRS" in response.json()["detail"]
```

- [ ] **Step 10: Add a test proving the bulk-send job reports the new skip count for a mixed-scheme batch**

Add after `test_send_all_reports_sent_for_all_alertable_statuses`:

```python
def test_send_all_reports_skipped_no_template_for_unconfigured_scheme(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid")
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all")
        job_id = response.json()["job_id"]

        import time
        status_response = None
        for _ in range(50):
            status_response = client.get(f"/api/send-all/status/{job_id}")
            if status_response.json()["done"]:
                break
            time.sleep(0.05)

    final = status_response.json()
    assert final["done"] is True
    assert final["total"] == 2
    assert final["sent"] == 1
    assert final["skipped_no_template"] == 1
```

- [ ] **Step 11: Add a test proving `/api/email-preview` reflects scheme-specific content**

Add after `test_email_preview_returns_subject_and_html`:

```python
def test_email_preview_uses_scheme_specific_content(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT004", "Deepa Rao", "FreshFoods", "d@x.com", "919000000001",
         "CRS-Cert", "CRS", "CRS-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal: {cert_name}")
    monkeypatch.setenv("EMAIL_INTRO_TEXT_CRS", "Your CRS registration for <strong>{company}</strong> needs renewal.")

    response = client.get("/api/email-preview/CLT004")

    assert response.status_code == 200
    data = response.json()
    assert data["subject"] == "Registration renewal: CRS-Cert"
    assert "Your CRS registration for <strong>FreshFoods</strong> needs renewal." in data["html"]
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 13: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: wire scheme-aware templates through send/send-all/email-preview endpoints"
```

---

### Task 5: Frontend — `SendAllConfirmModal.jsx`

**Files:**
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`
- Modify: `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`

- [ ] **Step 1: Write the failing tests**

Add after `it("omits the no-email skip count when job.skipped_no_email is absent (WhatsApp job)", ...)` in `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`:

```jsx
  it("shows the no-template skip count when job.skipped_no_template is a number", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, skipped_no_template: 2, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.getByText(/2 no template/)).toBeInTheDocument();
  });

  it("omits the no-template skip count when job.skipped_no_template is absent (email job)", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} channel="email" onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, skipped_no_email: 0, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.queryByText(/no template/)).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: FAIL — the modal doesn't render a no-template count yet, so `screen.getByText(/2 no template/)` finds nothing.

- [ ] **Step 3: Add the conditional line**

Current (`dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`):

```jsx
            <p className="text-sm text-ink-secondary mb-3">
              {job.sent} sent, {job.skipped} skipped, {job.failed} failed
              {typeof job.skipped_no_email === "number" ? ` (${job.skipped_no_email} no email)` : ""}
              {job.total ? ` (of ${job.total})` : ""}
            </p>
```

Replace with:

```jsx
            <p className="text-sm text-ink-secondary mb-3">
              {job.sent} sent, {job.skipped} skipped, {job.failed} failed
              {typeof job.skipped_no_email === "number" ? ` (${job.skipped_no_email} no email)` : ""}
              {typeof job.skipped_no_template === "number" ? ` (${job.skipped_no_template} no template)` : ""}
              {job.total ? ` (of ${job.total})` : ""}
            </p>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/SendAllConfirmModal.test.jsx`
Expected: all passed, including every pre-existing test (all of them omit `skipped_no_template`, which the `typeof ... === "number"` guard treats identically to omitting `skipped_no_email`).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/SendAllConfirmModal.jsx dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx
git commit -m "feat: show the no-template skip count on WhatsApp bulk-send jobs"
```

---

### Task 6: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all tests pass, zero regressions, with roughly 20 new tests added across Tasks 1-4.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all tests pass.

- [ ] **Step 3: Manually dry-run the CLI against the real ISI data to confirm the WhatsApp path still works end to end**

```bash
cd dashboard-app/backend
python whatsapp_renewal_alerts.py --dry-run
```

Expected: every alert-eligible client in `data/clients.db` produces a `🧪 DRY-RUN` line (since every real row today is scheme `"ISI"`, and `WHATSAPP_TEMPLATE_NAME`/`WHATSAPP_TEMPLATE_LANG` still resolve via the unconfigured-ISI fallback) — no `skipped_no_template` lines should appear for real production data yet. The summary line at the end should show `0 skipped (no template)`.

- [ ] **Step 4: Manual smoke test against a real dev server**

Start the backend (`cd dashboard-app/backend && python -m uvicorn main:app --port 8040`) and frontend (`cd dashboard-app/frontend && npm run dev`) locally. In the browser:
1. Open "Preview Email" for an ISI client — confirm the subject reads `"Renew <cert> — <company>"` (no `[Action Required]` prefix) and the body looks unchanged otherwise.
2. If you have a CRS-scheme test client loaded, set `EMAIL_SUBJECT_TEMPLATE_CRS`/`EMAIL_INTRO_TEXT_CRS` in your local `.env`, restart the backend, and confirm that client's preview shows the CRS-specific wording instead.
3. Open "Send All Eligible" with no scheme filter — confirm the progress text shows `X sent, Y skipped, Z failed` and, if any CRS records are present without a configured WhatsApp template, a `(N no template)` suffix appears.

Expected: no console errors; every step matches the description above.
