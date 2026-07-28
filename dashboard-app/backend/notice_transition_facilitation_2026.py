"""Content for the "Transition Facilitation Order 2026" one-time broadcast
notice. Summarizes DPIIT's Transition Facilitation (Quality Control) Order,
2026 (S.O. 3417(E), effective 25 June 2026) -- see
https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/
for the full article this summarizes. Unlike the per-scheme renewal alert
content in scheme_templates.py, this isn't about any individual client's own
certificate -- it's a general compliance-awareness announcement."""
from email_template import CALENDLY_URL

NOTICE_URL = "https://absoluteveritas.com/transition-facilitation-quality-control-order-2026/"

EMAIL_SUBJECT = "Important: BIS Transition Facilitation Order, 2026 — What It Means for You"


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
            DPIIT's new <strong>Transition Facilitation (Quality Control) Order, 2026</strong>
            (effective 25 June 2026) lets eligible companies source BIS Scheme-II
            certified product while their own ISI Mark certification is still in
            process — covering ten notified Quality Control Orders including toys,
            footwear, air conditioners, water heaters, washing machines, hinges,
            furniture, and household electrical appliances.
          </p>
          <p style="color:#52514e;font-size:14px;line-height:1.7;margin:0 0 26px;">
            The application window is <strong>24 months from 25 June 2026</strong>.
            If your business handles products under any of these categories, or is
            currently working through ISI Mark certification, this is worth
            building into your compliance planning now.
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
            Want help assessing your eligibility or compiling documentation?
            Reach out to {org_name} — we support BIS Certification, QCO
            compliance, and regulatory coordination across India.
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
    name = os.environ.get("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME")
    lang = os.environ.get("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG")
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
