"""Tests for scheme_templates.py's per-scheme content lookup."""
from email_template import DEFAULT_INTRO_TEXT
from scheme_templates import (
    DEFAULT_EMAIL_SUBJECT_TEMPLATE, get_email_content, get_whatsapp_template,
)


def test_get_whatsapp_template_returns_scheme_specific_override_when_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_CRS", "crs_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_CRS", "en_US")

    assert get_whatsapp_template("CRS") == ("crs_renewal_alert", "en_US")


def test_get_whatsapp_template_isi_falls_back_to_bare_env_vars_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_ISI", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_ISI", raising=False)
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "legacy_template")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en_GB")

    assert get_whatsapp_template("ISI") == ("legacy_template", "en_GB")


def test_get_whatsapp_template_isi_defaults_when_nothing_set(monkeypatch):
    for var in ("WHATSAPP_TEMPLATE_NAME_ISI", "WHATSAPP_TEMPLATE_LANG_ISI",
                "WHATSAPP_TEMPLATE_NAME", "WHATSAPP_TEMPLATE_LANG"):
        monkeypatch.delenv(var, raising=False)

    assert get_whatsapp_template("ISI") == ("cert_renewal_alert", "en")


def test_get_whatsapp_template_isi_specific_override_takes_priority_over_bare_fallback(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_ISI", "isi_specific_template")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG_ISI", "en_US")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "legacy_template")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en_GB")

    assert get_whatsapp_template("ISI") == ("isi_specific_template", "en_US")


def test_get_whatsapp_template_returns_none_for_unconfigured_non_isi_scheme(monkeypatch):
    monkeypatch.delenv("WHATSAPP_TEMPLATE_NAME_CRS", raising=False)
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)

    assert get_whatsapp_template("CRS") is None


def test_get_whatsapp_template_requires_both_name_and_lang_for_scheme_override(monkeypatch):
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME_CRS", "crs_renewal_alert")
    monkeypatch.delenv("WHATSAPP_TEMPLATE_LANG_CRS", raising=False)

    assert get_whatsapp_template("CRS") is None


def test_get_email_content_returns_scheme_specific_override_when_configured(monkeypatch):
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal for {cert_name}")
    monkeypatch.setenv("EMAIL_INTRO_TEXT_CRS", "Your CRS registration for <strong>{company}</strong> needs renewal.")

    subject_template, intro_text = get_email_content("CRS")

    assert subject_template == "Registration renewal for {cert_name}"
    assert intro_text == "Your CRS registration for <strong>{company}</strong> needs renewal."


def test_get_email_content_falls_back_to_generic_default_when_unconfigured(monkeypatch):
    for var in ("EMAIL_SUBJECT_TEMPLATE_ISI", "EMAIL_INTRO_TEXT_ISI"):
        monkeypatch.delenv(var, raising=False)

    subject_template, intro_text = get_email_content("ISI")

    assert subject_template == DEFAULT_EMAIL_SUBJECT_TEMPLATE
    assert intro_text == DEFAULT_INTRO_TEXT


def test_get_email_content_falls_back_independently_per_field(monkeypatch):
    monkeypatch.setenv("EMAIL_SUBJECT_TEMPLATE_CRS", "Registration renewal for {cert_name}")
    monkeypatch.delenv("EMAIL_INTRO_TEXT_CRS", raising=False)

    subject_template, intro_text = get_email_content("CRS")

    assert subject_template == "Registration renewal for {cert_name}"
    assert intro_text == DEFAULT_INTRO_TEXT
