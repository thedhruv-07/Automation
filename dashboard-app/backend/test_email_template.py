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


def test_active_tier_for_many_days_left():
    html = build_email_html(make_rec(90))
    assert "ACTIVE" in html
    assert "#0ca30c" in html  # status-good color
    assert "DUE SOON" not in html


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


def test_no_header_content_when_no_logo_given():
    html = build_email_html(make_rec(5))
    assert "&#10003;" not in html
    assert "<img" not in html


def test_uses_logo_image_header_when_logo_src_given():
    html = build_email_html(make_rec(5), logo_src="cid:company-logo.png")
    assert '<img src="cid:company-logo.png"' in html
    assert "&#10003;" not in html


def test_default_intro_text_matches_original_wording():
    """Company name always gets an "M/s" prefix in body text, as a mark of
    respect (common convention in formal Indian business correspondence)."""
    html = build_email_html(make_rec(5))
    assert (
        "This is a notification regarding the certification held by "
        "<strong>M/s TechCorp</strong>. Please review the details below and "
        "take action to ensure compliance continuity." in html
    )


def test_custom_intro_text_overrides_default():
    html = build_email_html(
        make_rec(5), intro_text="Custom notice for <strong>{company}</strong>.",
    )
    assert "Custom notice for <strong>M/s TechCorp</strong>." in html
    assert "This is a notification regarding" not in html


def test_book_an_appointment_is_the_sole_cta_button():
    from email_template import CALENDLY_URL
    html = build_email_html(make_rec(5))
    assert "Renew Now" not in html
    assert "Book an Appointment" in html
    assert f'href="{CALENDLY_URL}"' in html
    assert 'target="_blank"' in html


def test_default_detail_rows_show_certification_and_certificate_id():
    html = build_email_html(make_rec(5))
    assert "Certification</td>" in html
    assert "ISO 9001" in html
    assert "Certificate ID</td>" in html
    assert "ISO-1" in html


def test_custom_detail_rows_override_the_default_two_rows():
    html = build_email_html(
        make_rec(5), detail_rows=[("Company / Manufacturer", "TechCorp"), ("Indian Standard", "IS 4250:2015")],
    )
    assert "Company / Manufacturer</td>" in html
    assert "Indian Standard</td>" in html
    assert "IS 4250:2015" in html
    assert "Certificate ID</td>" not in html


def test_default_expiry_label_is_unchanged():
    html = build_email_html(make_rec(5))
    assert "Expiry date: <strong" in html


def test_custom_expiry_label_overrides_default():
    html = build_email_html(make_rec(5), expiry_label="BIS License Expiry date:")
    assert "BIS License Expiry date: <strong" in html
    assert ">Expiry date: <strong" not in html


def test_detail_row_labels_are_bold():
    html = build_email_html(make_rec(5))
    assert 'font-weight:700;vertical-align:top;">Certification</td>' in html


def test_expiry_date_is_red_when_already_expired():
    html = build_email_html(make_rec(-3))
    assert '<strong style="color:#d03b3b;">24 July 2026</strong>' in html


def test_expiry_date_is_default_color_when_not_expired():
    html = build_email_html(make_rec(5))
    assert '<strong style="color:#d03b3b;">24 July 2026</strong>' not in html
    assert '<strong style="color:#0b0b0b;">24 July 2026</strong>' in html


def test_cta_label_is_empty_by_default():
    html = build_email_html(make_rec(5))
    assert "Proceed with Renewal" not in html


def test_custom_cta_label_renders_above_the_button():
    html = build_email_html(make_rec(5), cta_label="Proceed with Renewal")
    assert "Proceed with Renewal" in html
    assert html.index("Proceed with Renewal") < html.index("Book an Appointment")


def test_default_contact_block_used_when_no_signature_html():
    html = build_email_html(make_rec(5), org_website="https://example.com", org_contact="+1 555-0100")
    assert "+1 555-0100" in html


def test_signature_html_overrides_the_default_contact_block():
    html = build_email_html(
        make_rec(5), org_website="https://example.com", org_contact="+1 555-0100",
        signature_html="<p>Absolute Veritas<br>Inspection, Testing &amp; Certifications</p>",
    )
    assert "Inspection, Testing &amp; Certifications" in html
    assert "+1 555-0100" not in html
    assert "https://example.com" not in html
    assert 'rel="noopener noreferrer"' in html
