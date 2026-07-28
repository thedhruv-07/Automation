"""Registry of one-time broadcast notices (distinct from the per-scheme
renewal alert content in scheme_templates.py -- a notice isn't about any
individual client's own certificate, it's a general announcement sent once
to everyone matching a filter). Each entry names a module implementing:
  - EMAIL_SUBJECT: str
  - build_email_html(rec, org_name) -> str
  - get_whatsapp_template() -> (name, lang) | None
  - build_whatsapp_payload(rec, to_phone, template_name, template_lang) -> dict

To add a new notice: write notice_<id>.py implementing the above, then add
one line below plus a display label. No endpoint/frontend changes needed --
the Notices page and its endpoints already iterate this registry.
"""
import notice_meity_series_guidelines_2026

NOTICES = {
    "meity_series_guidelines_2026": {
        "label": "MeitY Series Guidelines — IS/IEC 62368-1:2023",
        "module": notice_meity_series_guidelines_2026,
    },
}


def list_notices() -> list[dict]:
    return [{"id": notice_id, "label": entry["label"]} for notice_id, entry in NOTICES.items()]


def get_notice_module(notice_id: str):
    entry = NOTICES.get(notice_id)
    return entry["module"] if entry else None
