"""Content for the "Independence Day Special Offer" one-time WhatsApp-only
broadcast, sent to a flat imported list of phone numbers with no
corresponding roster/client record (see adhoc_recipients in db.py, and
import_adhoc_recipients.py which populates it). Unlike the roster-based
notices in this file's sibling modules, there is no build_email_html (this
notice is WhatsApp-only) and the BODY is fully static -- no per-recipient
personalization, since the phone list has no name/company data to
personalize with.

The approved template (id 4474587969457169) has a VIDEO header, discovered
by querying the template directly via the Graph API after a real send
failed with #132012 "Parameter format does not match format in the created
template" -- a real send always needs to supply that header's media, the
same way notice_meity_series_guidelines_2026's IMAGE_ID header works."""
import os


def get_whatsapp_template() -> tuple[str, str] | None:
    name = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_NAME")
    lang = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_LANG")
    if name and lang:
        return name, lang
    return None


def build_whatsapp_payload(to_phone: str, template_name: str, template_lang: str) -> dict:
    video_id = os.environ.get("WHATSAPP_ADHOC_INDEPENDENCE_DAY_2026_VIDEO_ID")

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
        },
    }
    if video_id:
        payload["template"]["components"] = [{
            "type": "header",
            "parameters": [{"type": "video", "video": {"id": video_id}}],
        }]
    return payload
