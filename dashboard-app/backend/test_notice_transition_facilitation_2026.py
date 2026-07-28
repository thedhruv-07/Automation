"""Tests for notice_transition_facilitation_2026.py's content."""
import notice_transition_facilitation_2026 as notice


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


def test_email_subject_mentions_the_order():
    assert "Transition Facilitation" in notice.EMAIL_SUBJECT
    assert "2026" in notice.EMAIL_SUBJECT


def test_get_whatsapp_template_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", raising=False)
    monkeypatch.delenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", raising=False)

    assert notice.get_whatsapp_template() is None


def test_get_whatsapp_template_returns_configured_pair(monkeypatch):
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_NAME", "transition_notice_2026")
    monkeypatch.setenv("WHATSAPP_NOTICE_TRANSITION_FACILITATION_2026_LANG", "en")

    assert notice.get_whatsapp_template() == ("transition_notice_2026", "en")


def test_build_whatsapp_payload_structure():
    payload = notice.build_whatsapp_payload(_rec(), "919876543210", "transition_notice_2026", "en")

    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "919876543210"
    assert payload["type"] == "template"
    assert payload["template"]["name"] == "transition_notice_2026"
    assert payload["template"]["language"] == {"code": "en"}
    params = payload["template"]["components"][0]["parameters"]
    assert params[0] == {"type": "text", "text": "Rahul Sharma"}
    assert params[1] == {"type": "text", "text": "TechCorp"}
    assert params[2] == {"type": "text", "text": notice.NOTICE_URL}
