from email_template import build_email_html


def make_rec(days_left, **overrides):
    rec = {
        "name": "Rahul Sharma",
        "company": "TechCorp",
        "cert_name": "ISO 9001",
        "cert_id": "ISO-1",
        "days_left": days_left,
        "expiry_formatted": "24 July 2026",
        "renewal_link": "https://example.com/renew",
    }
    rec.update(overrides)
    return rec


def test_uses_default_absolute_veritas_branding():
    html = build_email_html(make_rec(5))
    assert "Absolute Veritas" in html
    assert "cs@absoluteveritas.com" in html


def test_critical_tier_for_few_days_left():
    html = build_email_html(make_rec(5))
    assert "CRITICAL" in html
    assert "#d03b3b" in html  # status-critical color


def test_urgent_tier_for_moderate_days_left():
    html = build_email_html(make_rec(20))
    assert "URGENT" in html
    assert "#ec835a" in html  # status-serious color


def test_due_soon_tier_for_many_days_left():
    html = build_email_html(make_rec(60))
    assert "DUE SOON" in html
    assert "#fab219" in html  # status-warning color


def test_expired_tier_for_negative_days_left():
    html = build_email_html(make_rec(-3))
    assert "EXPIRED" in html
    assert "3 days ago" in html


def test_omits_website_and_contact_when_blank():
    html = build_email_html(make_rec(5), org_website="", org_contact="")
    assert "yourcertportal" not in html
    # no dangling empty <a href=""> link for the website line
    assert 'href=""' not in html


def test_includes_website_and_contact_when_provided():
    html = build_email_html(make_rec(5), org_website="https://example.com", org_contact="+1 555-0100")
    assert "https://example.com" in html
    assert "+1 555-0100" in html


def test_uses_checkmark_seal_header_when_no_logo_given():
    html = build_email_html(make_rec(5))
    assert "&#10003;" in html
    assert '<img src="cid:' not in html


def test_uses_logo_image_header_when_logo_src_given():
    html = build_email_html(make_rec(5), logo_src="cid:company-logo.png")
    assert '<img src="cid:company-logo.png"' in html
    assert "&#10003;" not in html
