"""Content for the "MeitY Series Guidelines — IS/IEC 62368-1:2023" one-time
broadcast notice. Summarizes MeitY Circular No. W-47/34/2025-IPHW (20 May
2026), prescribing revised series-formation guidelines for products under
the standard IS/IEC 62368 -- Part 1: 2023 (migrated from IS 13252 Part 1:
2020 and IS 616:2017 vide Gazette Notification S.O. No. 4997(E), 29 Oct
2025) -- see
https://absoluteveritas.com/meity-series-guidelines-isiec-62368-part1-2023/
for the full circular. Unlike the per-scheme renewal alert content in
scheme_templates.py, this isn't about any individual client's own
certificate -- it's a general compliance-awareness announcement."""
from email_template import CALENDLY_URL

NOTICE_URL = "https://absoluteveritas.com/meity-series-guidelines-isiec-62368-part1-2023/"

EMAIL_SUBJECT = "Important: MeitY Series Guidelines for IS/IEC 62368-1:2023 — What It Means for You"


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
            MeitY has issued <strong>Circular No. W-47/34/2025-IPHW (20 May 2026)</strong>
            prescribing revised series-formation guidelines for products under
            <strong>IS/IEC 62368 &ndash; Part 1: 2023</strong> &mdash; the standard that
            IS 13252 Part 1:2020 and IS 616:2017 have migrated to (Gazette
            Notification S.O. 4997(E), 29 Oct 2025). This is binding on all
            BIS licence holders, applicants, manufacturers, importers, and
            sellers of audio/video, IT, and communication equipment.
          </p>
          <p style="color:#52514e;font-size:14px;line-height:1.7;margin:0 0 26px;">
            Key changes: a maximum of <strong>10 models per series</strong>, matching
            IP ratings and enclosure design across the series, a single class
            of construction, and matching energy source/safeguard system per
            model &mdash; effective immediately from the date of issuance.
          </p>
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
          <p style="color:#52514e;font-size:13px;line-height:1.7;margin:0;">
            Want help assessing how this affects your existing or upcoming
            series certification? Reach out to {org_name} — we support BIS
            Certification, QCO compliance, and regulatory coordination
            across India.
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
    return {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": rec["name"]},
                        {"type": "text", "text": rec["company"]},
                        {"type": "text", "text": NOTICE_URL},
                    ],
                },
            ],
        },
    }
