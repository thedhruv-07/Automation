"""Content for the "MeitY Series Guidelines — IS/IEC 62368-1:2023" one-time
broadcast notice. A lead-gen message to existing BIS licence holders under
IS 13252 (Part 1):2010 and/or IS 616:2017, pointing them at the BIS/CRS
transition guide and offering a free consultation -- see
https://absoluteveritas.com/is-iec-62368-12023-bis-crs-transition-guide/.
Unlike the per-scheme renewal alert content in scheme_templates.py, this
isn't about any individual client's own certificate -- it's a general
compliance-awareness announcement."""
NOTICE_URL = "https://absoluteveritas.com/is-iec-62368-12023-bis-crs-transition-guide/"

EMAIL_SUBJECT = "Free Consultation: Transition Your BIS Licence to IS/IEC 62368-1:2023"


def build_email_html(rec: dict, org_name: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:#f9f9f7;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9f9f7;padding:30px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e1e0d9;border-radius:12px;overflow:hidden;box-shadow:0 8px 24px rgba(11,11,11,0.10);">
        <tr><td style="background:#2a78d6;padding:28px 30px;text-align:center;">
          <h1 style="color:#fff;margin:0;font-size:20px;font-weight:700;">{org_name}</h1>
          <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;">
            BIS Compliance Notice
          </p>
        </td></tr>
        <tr><td style="padding:32px 40px;">
          <p style="color:#0b0b0b;font-size:16px;margin:0 0 18px;">Dear <strong>{rec['name']}</strong> ({rec['company']}),</p>
          <p style="color:#52514e;font-size:14px;line-height:1.7;margin:0 0 18px;">
            As an existing BIS licence holder under <strong>IS 13252 (Part 1):2010</strong>
            and/or <strong>IS 616:2017</strong>, your products will need to transition to
            <strong>IS/IEC 62368-1:2023</strong> as per the BIS implementation timeline.
          </p>
          <p style="color:#52514e;font-size:14px;line-height:1.7;margin:0 0 26px;">
            We are offering a <strong>FREE consultation</strong> to review your existing
            licences, identify the affected models, and prepare a smooth
            transition plan.
          </p>
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:4px 0 26px;">
              <a href="{NOTICE_URL}" target="_blank" rel="noopener noreferrer"
                 style="background:#2a78d6;color:#fff;padding:15px 42px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px;display:inline-block;">
                Learn More
              </a>
            </td></tr>
          </table>
          <p style="color:#52514e;font-size:13px;line-height:1.7;margin:0;">
            Please reply to this message or contact us to schedule your free consultation.
          </p>
        </td></tr>
        <tr><td style="background:#0b0b0b;padding:18px;text-align:center;">
          <p style="color:rgba(255,255,255,0.6);font-size:11px;margin:0;">
            {org_name} — This is an automated notification.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def get_whatsapp_template() -> tuple[str, str] | None:
    import os
    name = os.environ.get("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME")
    lang = os.environ.get("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG")
    if name and lang:
        return name, lang
    return None


def build_whatsapp_payload(rec: dict, to_phone: str, template_name: str, template_lang: str) -> dict:
    import os
    image_id = os.environ.get("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_IMAGE_ID")

    components = []
    if image_id:
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": image_id}}],
        })
    components.append({
        "type": "body",
        "parameters": [
            {"type": "text", "text": rec["name"]},
            {"type": "text", "text": rec["company"]},
            {"type": "text", "text": NOTICE_URL},
        ],
    })

    return {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": components,
        },
    }
