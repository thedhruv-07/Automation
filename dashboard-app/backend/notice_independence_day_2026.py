"""Content for the "Independence Day Special Offer" one-time WhatsApp-only
broadcast, sent to a flat imported list of phone numbers with no
corresponding roster/client record (see adhoc_recipients in db.py, and
import_adhoc_recipients.py which populates it). Unlike the roster-based
notices in this file's sibling modules, there is no build_email_html (this
notice is WhatsApp-only) and the message is fully static -- no
per-recipient personalization, since the phone list has no name/company
data to personalize with. The approved Meta template itself must have zero
body variables to match."""
import os


def get_whatsapp_template() -> tuple[str, str] | None:
    name = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME")
    lang = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG")
    if name and lang:
        return name, lang
    return None


def build_whatsapp_payload(to_phone: str, template_name: str, template_lang: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
        },
    }
