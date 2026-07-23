"""One-time migration: reads the real clients_certifications.xlsx and
sent_log.json and populates clients.db. Run once: python migrate_to_sqlite.py
Verifies row counts match the source files before declaring success.

Refuses to run against a clients.db that already has rows (pass --force to
override) — see the guard in migrate() for why: mode="replace" truncates the
whole table, so an accidental re-run after go-live could silently discard
newer data written by the dashboard in the meantime.
"""
import argparse
import json
import sys
from pathlib import Path

import openpyxl

from db import DEFAULT_DB_PATH, RECORD_FIELDS, upsert_clients, record_sent, read_clients

SCRIPT_DIR = Path(__file__).parent
SOURCE_XLSX = SCRIPT_DIR / "clients_certifications.xlsx"
SOURCE_LOG = SCRIPT_DIR / "sent_log.json"

# Used when a sent_log.json entry is missing sent_at, whose column is
# NOT NULL in the schema. We backfill rather than skip: the entry still
# represents a real, successfully-sent message (client_id/status/sent_date
# are known-good), and dropping it would make is_already_sent() return False
# for it post-migration, causing whatsapp_renewal_alerts.py to re-send an
# alert that already went out. A missing timestamp is a data-quality gap,
# not evidence the send didn't happen, so we preserve the row with an
# explicit placeholder instead of losing the dedup fact it encodes.
PLACEHOLDER_SENT_AT = "1970-01-01T00:00:00+00:00"


def _read_xlsx_rows(path) -> list[tuple]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows_iter = wb.active.iter_rows(values_only=True)
        next(rows_iter)  # header
        return [tuple(row[:len(RECORD_FIELDS)]) for row in rows_iter if row and row[0] is not None]
    finally:
        wb.close()


def _db_already_populated() -> bool:
    """True if DEFAULT_DB_PATH exists and its clients table already has rows.
    Guards against an accidental re-run silently reverting newer data (see
    module docstring). The db file may exist without the clients table yet
    initialized (e.g. created empty by some other code path), so read errors
    are treated as "not populated" rather than propagating."""
    if not Path(DEFAULT_DB_PATH).exists():
        return False
    try:
        return len(read_clients(DEFAULT_DB_PATH)) > 0
    except Exception:
        return False


def migrate(force: bool = False) -> None:
    if not SOURCE_XLSX.exists():
        print(f"No source file at {SOURCE_XLSX} — nothing to migrate.")
        return

    if not force and _db_already_populated():
        print(
            f"{DEFAULT_DB_PATH} already has client rows — this looks like a "
            "re-run after the initial migration. Refusing to proceed: "
            "mode=\"replace\" would truncate the table and could silently "
            "discard newer data written since the original migration. "
            "Pass --force if you really want to overwrite it."
        )
        sys.exit(1)

    rows = _read_xlsx_rows(SOURCE_XLSX)
    stats = upsert_clients(DEFAULT_DB_PATH, rows, mode="replace")
    print(f"Migrated {stats['row_count']} client rows into {DEFAULT_DB_PATH}")

    migrated_count = len(read_clients(DEFAULT_DB_PATH))
    if migrated_count != len(rows):
        print(f"MISMATCH: source had {len(rows)} rows, db has {migrated_count}")
        sys.exit(1)

    if SOURCE_LOG.exists():
        log = json.loads(SOURCE_LOG.read_text(encoding="utf-8"))
        backfilled_sent_at_count = 0
        for key, info in log.items():
            client_id, status, sent_date = key.split("|", 2)
            sent_at = info.get("sent_at")
            if not sent_at:
                # sent_at is NOT NULL in the schema; backfill rather than
                # skip (see PLACEHOLDER_SENT_AT comment above) so the
                # already-sent fact is not lost.
                sent_at = PLACEHOLDER_SENT_AT
                backfilled_sent_at_count += 1
            # message_id and phone are nullable TEXT columns in db.py's
            # sent_log schema, so passing None straight through for either
            # is safe and requires no guard.
            record_sent(
                DEFAULT_DB_PATH, client_id, status, sent_date,
                info.get("message_id"), info.get("phone"), sent_at,
            )
        print(f"Migrated {len(log)} sent-log entries")
        if backfilled_sent_at_count:
            print(f"WARNING: {backfilled_sent_at_count} sent-log entries had no sent_at; "
                  f"backfilled with placeholder {PLACEHOLDER_SENT_AT}")

    print("Migration verified OK. Source files left untouched.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-time migration of clients_certifications.xlsx / sent_log.json into clients.db."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Proceed even if clients.db already has rows (overwrites it). "
             "Use only if you intend to discard whatever is currently in clients.db.",
    )
    return parser


if __name__ == "__main__":
    args = build_arg_parser().parse_args()
    migrate(force=args.force)
