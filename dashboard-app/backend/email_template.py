"""Shared, dependency-light HTML email template for certification renewal
notices. Used by both cert_automation.py (real sends) and the dashboard
backend (preview only) — kept as a standalone module (no pandas/Pillow) so
neither caller takes on heavy dependencies just to build an email string.
"""

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

CALENDLY_URL = "https://calendly.com/cs-absoluteveritas/30min"


def _tier(days_left: int) -> tuple[str, str, str, str]:
    """Returns (label, color, message, hero_label) for the given days-left count."""
    if days_left < 0:
        n = abs(days_left)
        return ("EXPIRED", STATUS_CRITICAL, f"Expired {n} day{'s' if n != 1 else ''} ago — immediate renewal required", "DAYS OVERDUE")
    if days_left == 0:
        return ("CRITICAL", STATUS_CRITICAL, "Expires today", "EXPIRES TODAY")
    if days_left <= 7:
        return ("CRITICAL", STATUS_CRITICAL, f"Expires in {days_left} day{'s' if days_left != 1 else ''}", "DAYS REMAINING")
    if days_left <= 30:
        return ("URGENT", STATUS_SERIOUS, f"Expires in {days_left} days", "DAYS REMAINING")
    if days_left <= 60:
        return ("DUE SOON", STATUS_WARNING, f"Expires in {days_left} days", "DAYS REMAINING")
    return ("ACTIVE", STATUS_GOOD, f"Expires in {days_left} days — no action needed yet", "DAYS REMAINING")


def build_email_html(
    rec: dict,
    org_name: str = "Absolute Veritas",
    org_website: str = "",
    org_contact: str = "",
    org_email: str = "cs@absoluteveritas.com",
    logo_src: str = "",
    intro_text: str = DEFAULT_INTRO_TEXT,
) -> str:
    label, color, message, hero_label = _tier(rec["days_left"])
    hero_number = abs(rec["days_left"]) if rec["days_left"] != 0 else 0

    if logo_src:
        header_html = f"""
              <tr><td style="background:#ffffff;padding:28px 30px 18px;text-align:center;border-bottom:1px solid {LINE};">
                <img src="{logo_src}" alt="{org_name}" width="200" style="display:block;margin:0 auto 10px;border:0;">
                <p style="color:{INK_MUTED};margin:0;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;">
                  Certification Renewal Notice
                </p>
              </td></tr>"""
    else:
        header_html = f"""
              <tr><td style="background:{ACCENT};padding:32px 30px 26px;text-align:center;">
                <table cellpadding="0" cellspacing="0" align="center" style="margin:0 auto 14px;">
                  <tr><td width="56" height="56" align="center" valign="middle"
                      style="background:#ffffff;border-radius:50%;border:2px solid rgba(255,255,255,0.7);font-size:26px;color:{ACCENT};font-weight:700;">
                    &#10003;
                  </td></tr>
                </table>
                <h1 style="color:#fff;margin:0;font-size:22px;font-weight:700;letter-spacing:0.2px;">{org_name}</h1>
                <p style="color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:12px;text-transform:uppercase;letter-spacing:1.2px;">
                  Certification Renewal Notice
                </p>
              </td></tr>"""

    contact_lines = []
    if org_email:
        contact_lines.append(f'<p style="color:{INK_SECONDARY};font-size:14px;margin:0 0 4px;">{org_email}</p>')
    if org_contact:
        contact_lines.append(f'<p style="color:{INK_SECONDARY};font-size:14px;margin:0 0 4px;">{org_contact}</p>')
    if org_website:
        contact_lines.append(
            f'<p style="margin:0;"><a href="{org_website}" style="color:{ACCENT};font-size:14px;">{org_website}</a></p>'
        )
    contact_html = "\n            ".join(contact_lines)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Arial,sans-serif;background:{SURFACE_PAGE};">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:{SURFACE_PAGE};padding:30px 0;">
    <tr><td align="center">
      <!-- Card with left accent bar (severity color) -->
      <table width="620" cellpadding="0" cellspacing="0" style="box-shadow:0 8px 24px rgba(11,11,11,0.10);border-radius:12px;overflow:hidden;">
        <tr>
          <td width="6" style="background:{color};font-size:0;line-height:0;">&nbsp;</td>
          <td>
            <table width="614" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid {LINE};border-left:none;border-radius:0 12px 12px 0;">

              <!-- Header -->
              {header_html}

              <!-- Urgency Banner -->
              <tr><td style="background:{color};padding:11px;text-align:center;">
                <span style="color:#fff;font-weight:700;font-size:13px;letter-spacing:0.6px;">{label} — {message}</span>
              </td></tr>

              <!-- Body -->
              <tr><td style="padding:34px 40px 8px;">
                <p style="color:{INK_PRIMARY};font-size:16px;margin:0 0 18px;">Dear <strong>{rec['name']}</strong>,</p>
                <p style="color:{INK_SECONDARY};font-size:14px;line-height:1.7;margin:0 0 26px;">
                  {intro_text.format(company=rec['company'])}
                </p>

                <!-- Hero stat -->
                <table width="100%" cellpadding="0" cellspacing="0" style="background:{SURFACE_PAGE};border:1px solid {LINE};border-radius:10px;margin-bottom:22px;">
                  <tr><td align="center" style="padding:24px 20px;">
                    <div style="font-size:44px;line-height:1;font-weight:700;color:{color};">{hero_number}</div>
                    <div style="font-size:11px;font-weight:700;letter-spacing:1.4px;color:{INK_SECONDARY};margin-top:8px;text-transform:uppercase;">{hero_label}</div>
                    <div style="font-size:13px;color:{INK_MUTED};margin-top:10px;">Expiry date: <strong style="color:{INK_PRIMARY};">{rec['expiry_formatted']}</strong></div>
                  </td></tr>
                </table>

                <!-- Cert Info Box -->
                <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {LINE};border-radius:8px;margin-bottom:26px;">
                  <tr><td style="padding:18px 20px;">
                    <div style="font-size:10px;font-weight:700;letter-spacing:1.2px;color:{INK_MUTED};text-transform:uppercase;margin-bottom:12px;">Certification Details</div>
                    <table width="100%" cellpadding="5" cellspacing="0">
                      <tr>
                        <td style="color:{INK_SECONDARY};font-size:13px;width:40%;">Certification</td>
                        <td style="color:{INK_PRIMARY};font-weight:700;font-size:14px;">{rec['cert_name']}</td>
                      </tr>
                      <tr>
                        <td style="color:{INK_SECONDARY};font-size:13px;">Certificate ID</td>
                        <td style="color:{INK_PRIMARY};font-weight:700;font-size:14px;">{rec['cert_id']}</td>
                      </tr>
                    </table>
                  </td></tr>
                </table>

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

                <p style="color:{INK_SECONDARY};font-size:13px;line-height:1.7;margin:0 0 12px;">
                  If you need assistance or have questions about the renewal process,
                  please don't hesitate to contact us.
                </p>
                {contact_html}
              </td></tr>

              <tr><td style="padding:0 40px;"><div style="border-top:1px solid {LINE};"></div></td></tr>

              <!-- Footer -->
              <tr><td style="background:{INK_PRIMARY};padding:18px;text-align:center;">
                <p style="color:rgba(255,255,255,0.6);font-size:11px;margin:0;">
                  {org_name} — This is an automated notification.<br>
                  If you have already renewed, please disregard this message.
                </p>
              </td></tr>

            </table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
