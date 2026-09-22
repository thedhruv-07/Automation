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

CALENDLY_URL = "https://calendly.com/cs-absoluteveritas/30min/2026-09-23T10:00:00+05:30"


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
    detail_rows: list[tuple[str, str]] | None = None,
    expiry_label: str = "Expiry date:",
    cta_label: str = "",
    signature_html: str = "",
) -> str:
    """detail_rows/expiry_label/cta_label/signature_html let a caller swap in
    a scheme-specific layout (see email_alerts.send_email_via_brevo's ISI
    branch) without this function needing to know about individual schemes
    itself -- detail_rows defaults to the original 2-row Certification/
    Certificate ID box, cta_label adds an optional heading above the button,
    and signature_html replaces the org_email/org_contact/org_website block
    entirely when given."""
    label, color, message, _hero_label = _tier(rec["days_left"])
    expiry_date_color = STATUS_CRITICAL if rec["days_left"] < 0 else INK_PRIMARY
    if detail_rows is None:
        detail_rows = [("Certification", rec["cert_name"]), ("Certificate ID", rec["cert_id"])]

    header_html = (
        f'<img src="{logo_src}" alt="{org_name}" width="160" style="display:block;border:0;margin:0 0 16px;">'
        if logo_src else ""
    )

    contact_lines = []
    if org_email:
        contact_lines.append(f'<p style="margin:0 0 2px;">{org_email}</p>')
    if org_contact:
        contact_lines.append(f'<p style="margin:0 0 2px;">{org_contact}</p>')
    if org_website:
        contact_lines.append(f'<p style="margin:0;"><a href="{org_website}" style="color:{ACCENT};">{org_website}</a></p>')
    contact_html = signature_html or "\n      ".join(contact_lines)

    detail_rows_html = "\n        ".join(
        f'<tr><td style="border:1px solid {LINE};padding:9px 16px;font-size:14px;color:{INK_SECONDARY};font-weight:700;vertical-align:top;">{row_label}</td>'
        f'<td style="border:1px solid {LINE};padding:9px 16px;font-size:14px;">{row_value}</td></tr>'
        for row_label, row_value in detail_rows
    )

    cta_label_html = f'<p style="margin:0 0 4px;font-weight:700;">{cta_label}</p>' if cta_label else ""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#ffffff;">
  <div style="max-width:560px;margin:0 auto;padding:24px 20px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:{INK_PRIMARY};">
    {header_html}

    <p>Dear {rec['name']},</p>

    <p>{intro_text.format(company=f"M/s {rec['company']}")}</p>

    <p><strong style="color:{color};">{label}</strong> — {message}<br>
    <span style="font-size:17px;">{expiry_label} <strong style="color:{expiry_date_color};">{rec['expiry_formatted']}</strong></span></p>

    <table width="100%" cellpadding="0" cellspacing="0" style="margin:12px 0;border-collapse:collapse;">
      {detail_rows_html}
    </table>

    <p>
      {cta_label_html}
      <a href="{CALENDLY_URL}" target="_blank" rel="noopener noreferrer" style="color:{ACCENT};">Book an Appointment</a>
    </p>

    <p>If you need assistance or have questions about the renewal process, please don't hesitate to contact us.</p>
    {contact_html}

    <p style="margin-top:24px;font-size:12px;color:{INK_MUTED};">
      {org_name} — This is an automated notification.<br>
      If you have already renewed, please disregard this message.
    </p>
  </div>
</body>
</html>"""
