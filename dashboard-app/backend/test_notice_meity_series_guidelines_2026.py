"""Tests for notice_meity_series_guidelines_2026.py's content."""
import notice_meity_series_guidelines_2026 as notice


def _rec(**overrides):
    rec = {
        "client_id": "CLT001", "name": "Rahul Sharma", "company": "TechCorp",
        "email": "r@x.com", "phone": "919876543210",
    }
    rec.update(overrides)
    return rec


def test_build_email_html_includes_name_company_and_notice_url():
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert "Rahul Sharma" in html
    assert "TechCorp" in html
    assert notice.NOTICE_URL in html
    assert "Absolute Veritas" in html


def test_build_email_html_cta_link_opens_in_a_new_tab():
    """Without target="_blank", clicking (or a browser/extension attempting
    to preview) the link tries to navigate the current viewing context in
    place -- inside the dashboard's own preview iframe, that fails outright
    since the target site correctly sets X-Frame-Options against being
    framed by another origin."""
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert f'href="{notice.NOTICE_URL}"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_build_email_html_includes_learn_more_cta_and_reply_instruction():
    """Lowercase, non-shouty wording -- Gmail's Promotions-tab classifier
    weighs marketing-style phrasing (all-caps "FREE", multiple styled CTA
    buttons) heavily, and this is a compliance notice, not an ad."""
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert "Learn More" in html
    assert "free consultation" in html
    assert "FREE" not in html
    assert "reply to this message or contact us" in html


def test_build_email_html_includes_calendly_link_alongside_learn_more():
    from email_template import CALENDLY_URL
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert "Learn More" in html
    assert "book an appointment directly" in html
    assert f'href="{CALENDLY_URL}"' in html
    assert html.count('target="_blank"') == 2  # both links open in a new tab
    assert html.count('rel="noopener noreferrer"') == 2


def test_build_email_html_shows_logo_image_when_logo_src_given():
    html = notice.build_email_html(_rec(), "Absolute Veritas", logo_src="cid:company-logo.png")
    assert '<img src="cid:company-logo.png"' in html


def test_build_email_html_falls_back_to_text_header_when_no_logo_src():
    html = notice.build_email_html(_rec(), "Absolute Veritas")
    assert "<img" not in html


def test_email_subject_mentions_the_circular():
    assert "IS/IEC 62368" in notice.EMAIL_SUBJECT
    assert "2023" in notice.EMAIL_SUBJECT


def test_get_whatsapp_template_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", raising=False)

    assert notice.get_whatsapp_template() is None


def test_get_whatsapp_template_returns_configured_pair(monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_NAME", "meity_series_guidelines_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_LANG", "en")

    assert notice.get_whatsapp_template() == ("meity_series_guidelines_2026", "en")


def test_build_whatsapp_payload_structure(monkeypatch):
    monkeypatch.delenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_IMAGE_ID", raising=False)
    payload = notice.build_whatsapp_payload(_rec(), "919876543210", "meity_series_guidelines_2026", "en")

    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "919876543210"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "meity_series_guidelines_2026"
    assert payload["template"]["language"] == {"code": "en"}
    assert len(payload["template"]["components"]) == 1
    params = payload["template"]["components"][0]["parameters"]
    assert params[0] == {"type": "text", "text": "Rahul Sharma"}
    assert params[1] == {"type": "text", "text": "TechCorp"}
    assert params[2] == {"type": "text", "text": notice.NOTICE_URL}


def test_build_whatsapp_payload_includes_header_image_when_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_MEITY_SERIES_GUIDELINES_2026_IMAGE_ID", "4343868019158502")
    payload = notice.build_whatsapp_payload(_rec(), "919876543210", "meity_series_guidelines_2026", "en")

    components = payload["template"]["components"]
    assert len(components) == 2
    assert components[0] == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "4343868019158502"}}],
    }
    assert components[1]["type"] == "body"
