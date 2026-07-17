from datetime import datetime
from whatsapp_renewal_alerts import normalize_phone, format_expiry


def test_normalize_phone_strips_plus_sign():
    assert normalize_phone("+919876543210") == "919876543210"


def test_normalize_phone_handles_bare_digits():
    assert normalize_phone("919876543210") == "919876543210"


def test_normalize_phone_handles_int_input():
    assert normalize_phone(919876543210) == "919876543210"


def test_normalize_phone_strips_spaces_and_hyphens():
    assert normalize_phone("+91 98765-43210") == "919876543210"


def test_format_expiry_from_ddmmyyyy_string():
    assert format_expiry("24-07-2026") == "24 July 2026"


def test_format_expiry_from_datetime_object():
    assert format_expiry(datetime(2026, 7, 24)) == "24 July 2026"


def test_format_expiry_raises_on_unparseable_value():
    import pytest as pytest_mod
    with pytest_mod.raises(ValueError):
        format_expiry("not-a-date")
