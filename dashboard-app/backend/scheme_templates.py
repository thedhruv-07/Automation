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

# Per-scheme hardcoded defaults (subject_template, intro_text), used when no
# EMAIL_SUBJECT_TEMPLATE_<SCHEME>/EMAIL_INTRO_TEXT_<SCHEME> env var is set --
# unlike the single generic default above, these ship in code (not an env
# var someone has to remember to set on every environment) since they're a
# deliberately designed, scheme-specific wording, not a per-deploy tweak.
# subject_template also supports {cert_id}/{expiry_date} in addition to the
# usual {cert_name}/{company} -- see send_email_via_brevo's .format() call.
SCHEME_EMAIL_DEFAULTS = {
    "ISI": (
        "BIS ISI Licence Renewal — {company} — {cert_id} — Expiry {expiry_date}",
        (
            "This is a reminder regarding the upcoming renewal of the BIS ISI "
            "Licence held by <strong>{company}</strong>. To maintain continuity "
            "of the BIS licence and avoid any disruption related to its "
            "validity, we recommend initiating/completing the renewal process "
            "before the current licence expiry date."
        ),
    ),
}


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


def get_whatsapp_image_id(scheme: str) -> str | None:
    """Returns the WhatsApp media ID for the given scheme's renewal-alert
    header image, or None if that scheme's template has no image header
    configured. Independent per scheme -- a scheme's template may or may not
    have an image header at all, unlike get_whatsapp_template's ISI default,
    so there's no bare-env-var fallback here."""
    return os.environ.get(f"WHATSAPP_TEMPLATE_IMAGE_ID_{scheme.upper()}")


def get_email_content(scheme: str) -> tuple[str, str]:
    """Returns (subject_template, intro_text) for the given scheme, each
    format strings with {cert_name}/{company} placeholders (intro_text only
    uses {company}). Always returns something -- there's no external
    approval blocker for email (unlike WhatsApp templates), so falling back
    to a generic default is always safe to send. Each field falls back
    independently: configuring only a scheme's subject still gets the
    default intro, and vice versa."""
    scheme_key = scheme.upper()
    default_subject, default_intro = SCHEME_EMAIL_DEFAULTS.get(
        scheme_key, (DEFAULT_EMAIL_SUBJECT_TEMPLATE, DEFAULT_INTRO_TEXT),
    )
    subject_template = os.environ.get(f"EMAIL_SUBJECT_TEMPLATE_{scheme_key}")
    intro_text = os.environ.get(f"EMAIL_INTRO_TEXT_{scheme_key}")
    return (
        subject_template or default_subject,
        intro_text or default_intro,
    )
