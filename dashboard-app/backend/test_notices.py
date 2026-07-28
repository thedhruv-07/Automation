"""Tests for notices.py's notice registry."""
import notice_meity_series_guidelines_2026
from notices import get_notice_module, list_notices


def test_list_notices_includes_meity_series_guidelines_2026():
    notices = list_notices()
    ids = {n["id"] for n in notices}
    assert "meity_series_guidelines_2026" in ids
    entry = next(n for n in notices if n["id"] == "meity_series_guidelines_2026")
    assert entry["label"] == "MeitY Series Guidelines — IS/IEC 62368-1:2023"


def test_get_notice_module_returns_the_content_module():
    assert get_notice_module("meity_series_guidelines_2026") is notice_meity_series_guidelines_2026


def test_get_notice_module_returns_none_for_unknown_id():
    assert get_notice_module("does_not_exist") is None
