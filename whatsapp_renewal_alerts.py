"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252, which crashes on emoji output


def normalize_phone(raw: str | int) -> str:
    return re.sub(r"\D", "", str(raw))
