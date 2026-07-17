from whatsapp_renewal_alerts import normalize_phone


def test_normalize_phone_strips_plus_sign():
    assert normalize_phone("+919876543210") == "919876543210"


def test_normalize_phone_handles_bare_digits():
    assert normalize_phone("919876543210") == "919876543210"


def test_normalize_phone_handles_int_input():
    assert normalize_phone(919876543210) == "919876543210"


def test_normalize_phone_strips_spaces_and_hyphens():
    assert normalize_phone("+91 98765-43210") == "919876543210"
