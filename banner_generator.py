
"""
Generates a professional WhatsApp renewal banner image for each client.
Uses only Pillow (no external fonts needed — uses default).
"""
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252, which crashes on emoji output

LOGO_PATH = Path(__file__).parent / "dashboard-app" / "frontend" / "public" / "company-logo.png"

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
SURFACE_PAGE = "#f9f9f7"
LINE = "#e1e0d9"
ACCENT = "#2a78d6"

STATUS_CRITICAL = "#d03b3b"
STATUS_SERIOUS = "#ec835a"
STATUS_WARNING = "#fab219"

FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ],
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ],
}


def _load_font(size, bold=False):
    for path in FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _tier(days_left):
    if days_left < 0:
        n = abs(days_left)
        return (STATUS_CRITICAL, f"EXPIRED {n} DAY{'S' if n != 1 else ''} AGO", str(n), "DAYS OVERDUE")
    if days_left <= 7:
        return (STATUS_CRITICAL, f"CRITICAL — EXPIRES IN {days_left} DAY{'S' if days_left != 1 else ''}", str(days_left), "DAYS REMAINING")
    if days_left <= 30:
        return (STATUS_SERIOUS, f"URGENT — EXPIRES IN {days_left} DAYS", str(days_left), "DAYS REMAINING")
    return (STATUS_WARNING, f"EXPIRES IN {days_left} DAYS", str(days_left), "DAYS REMAINING")


def _draw_checkmark(draw, center, size, color, width=4):
    cx, cy = center
    r = size / 2
    draw.line(
        [(cx - r, cy + r * 0.05), (cx - r * 0.25, cy + r * 0.65), (cx + r, cy - r * 0.55)],
        fill=color, width=width, joint="curve",
    )


def _rounded_mask(size, box, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    return mask


def generate_banner(client_data: dict, output_path: str):
    """
    Generate a certification renewal banner image.

    client_data keys: name, company, cert_name, cert_id, expiry_date, days_left, renewal_link, contact_number
    """
    W, H = 800, 660
    margin = 24
    card_box = (margin, margin, W - margin, H - margin)
    bar_w = 8
    content_x0 = card_box[0] + bar_w
    cx1 = card_box[2]
    cy0, cy1 = card_box[1], card_box[3]
    content_w = cx1 - content_x0

    tier_color, tier_text, hero_number, hero_label = _tier(client_data["days_left"])

    # --- Base page + drop shadow ---
    page = Image.new("RGBA", (W, H), SURFACE_PAGE)
    shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow_layer).rounded_rectangle(
        [card_box[0], card_box[1] + 8, card_box[2], card_box[3] + 8], radius=16, fill=(11, 11, 11, 60)
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(16))
    page.alpha_composite(shadow_layer)

    # --- Card content, drawn as plain rectangles (clipped by a rounded mask at the end) ---
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rectangle(card_box, fill=SURFACE)
    draw.rectangle([card_box[0], cy0, content_x0, cy1], fill=tier_color)

    font_header = _load_font(23, bold=True)
    font_subheader = _load_font(12)
    font_name = _load_font(19, bold=True)
    font_body = _load_font(15)
    font_small = _load_font(12)
    font_micro = _load_font(11, bold=True)
    font_hero = _load_font(56, bold=True)
    font_cta = _load_font(17, bold=True)

    # --- Header ---
    has_logo = LOGO_PATH.exists()
    logo = None
    logo_h = 0
    if has_logo:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_w = 200
        logo_h = int(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)

    header_bottom = cy0 + (logo_h + 74 if has_logo else 100)

    if has_logo:
        draw.rectangle([content_x0, cy0, cx1, header_bottom], fill=SURFACE)
        logo_x = content_x0 + content_w // 2 - logo.width // 2
        logo_y = cy0 + 18
        card.paste(logo, (logo_x, logo_y), logo)
        draw.text((content_x0 + content_w // 2, logo_y + logo_h + 22), "CERTIFICATION RENEWAL NOTICE", fill=INK_MUTED, font=font_subheader, anchor="mm")
        draw.line([(content_x0, header_bottom), (cx1, header_bottom)], fill=LINE, width=1)
    else:
        draw.rectangle([content_x0, cy0, cx1, header_bottom], fill=ACCENT)
        seal_center = (content_x0 + content_w // 2, cy0 + 34)
        draw.ellipse([seal_center[0] - 22, seal_center[1] - 22, seal_center[0] + 22, seal_center[1] + 22], fill="white")
        _draw_checkmark(draw, seal_center, 22, ACCENT, width=4)
        draw.text((content_x0 + content_w // 2, cy0 + 68), "Absolute Veritas", fill="white", font=font_header, anchor="mm")
        draw.text((content_x0 + content_w // 2, cy0 + 88), "CERTIFICATION RENEWAL NOTICE", fill="#d9e8fa", font=font_subheader, anchor="mm")

    # --- Urgency banner ---
    urgency_top = header_bottom
    urgency_bottom = urgency_top + 34
    draw.rectangle([content_x0, urgency_top, cx1, urgency_bottom], fill=tier_color)
    draw.text((content_x0 + content_w // 2, (urgency_top + urgency_bottom) // 2), tier_text, fill="white", font=font_cta, anchor="mm")

    # --- Company / Client Name ---
    y = urgency_bottom + 34
    draw.text((content_x0 + content_w // 2, y), client_data["company"], fill=INK_PRIMARY, font=font_name, anchor="mm")
    y += 24
    draw.text((content_x0 + content_w // 2, y), f"Attn: {client_data['name']}", fill=INK_SECONDARY, font=font_small, anchor="mm")

    y += 22
    draw.line([(content_x0 + 30, y), (cx1 - 30, y)], fill=LINE, width=1)

    # --- Hero stat ---
    y += 30
    hero_box_h = 130
    draw.rounded_rectangle([content_x0 + 30, y, cx1 - 30, y + hero_box_h], radius=10, fill=SURFACE_PAGE, outline=LINE, width=1)
    hero_cy = y + 52
    draw.text((content_x0 + content_w // 2, hero_cy), hero_number, fill=tier_color, font=font_hero, anchor="mm")
    draw.text((content_x0 + content_w // 2, hero_cy + 42), hero_label, fill=INK_SECONDARY, font=font_micro, anchor="mm")
    draw.text((content_x0 + content_w // 2, hero_cy + 62), f"Expiry: {client_data['expiry_date']}", fill=INK_MUTED, font=font_small, anchor="mm")
    y += hero_box_h + 22

    # --- Certification details ---
    cert_name = client_data["cert_name"]
    if len(cert_name) > 44:
        cert_name = cert_name[:41] + "..."
    draw.text((content_x0 + content_w // 2, y), cert_name, fill=INK_PRIMARY, font=font_body, anchor="mm")
    y += 22
    draw.text((content_x0 + content_w // 2, y), f"Certificate ID: {client_data['cert_id']}", fill=INK_MUTED, font=font_small, anchor="mm")
    y += 26

    # --- Renewal CTA ---
    draw.rounded_rectangle([content_x0 + content_w // 2 - 110, y, content_x0 + content_w // 2 + 110, y + 42], radius=8, fill=ACCENT)
    draw.text((content_x0 + content_w // 2, y + 21), "RENEW NOW", fill="white", font=font_cta, anchor="mm")
    y += 42 + 22

    link = client_data["renewal_link"]
    if len(link) > 58:
        link = link[:55] + "..."
    draw.text((content_x0 + content_w // 2, y), link, fill=ACCENT, font=font_small, anchor="mm")
    y += 24

    contact_number = client_data.get("contact_number")
    if contact_number:
        draw.text((content_x0 + content_w // 2, y), f"For assistance, call {contact_number}", fill=INK_MUTED, font=font_small, anchor="mm")

    # --- Footer ---
    footer_h = 34
    draw.rectangle([content_x0, cy1 - footer_h, cx1, cy1], fill=INK_PRIMARY)
    draw.text((content_x0 + content_w // 2, cy1 - footer_h // 2), "Absolute Veritas — automated notification", fill="white", font=font_small, anchor="mm")

    # --- Clip the whole card to one clean rounded rect, then composite over the shadowed page ---
    mask = _rounded_mask((W, H), card_box, radius=16)
    page.paste(card, (0, 0), mask)

    page.convert("RGB").save(output_path, "PNG", quality=95)
    print(f"  Banner saved: {output_path}")
    return output_path


if __name__ == "__main__":
    # Quick test
    os.makedirs("output/banners", exist_ok=True)
    test = {
        "name": "Rahul Sharma",
        "company": "TechCorp India Pvt Ltd",
        "cert_name": "ISO 9001:2015 Quality Management",
        "cert_id": "ISO-2021-4521",
        "expiry_date": "26 May 2026",
        "days_left": 7,
        "renewal_link": "https://yourcertificationportal.com/renew?id=ISO-2021-4521",
        "contact_number": "",
    }
    generate_banner(test, "output/banners/test_banner.png")
    print("Test banner generated!")
