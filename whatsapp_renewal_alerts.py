"""WhatsApp Cloud API renewal-alert sender for Absolute Veritas."""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")


def normalize_phone(raw) -> str:
    return re.sub(r"\D", "", str(raw))
