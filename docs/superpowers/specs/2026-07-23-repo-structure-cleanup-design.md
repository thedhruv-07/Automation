# Repo Structure Cleanup: Consolidate Python Into dashboard-app/backend/

**Status:** Approved

## Problem

The repo root currently mixes ~10 Python source modules, ~9 test files, real data files (`clients.db` + 3 backup `.db` files, `clients_certifications.xlsx` + backup, `sent_log.json`), and log files (`whatsapp_automation.log`, `scheduler_output.log`) all at the same top level, alongside `dashboard-app/` (which already has a clean `backend/`/`frontend/` split). This makes it hard to see what's what, and is at odds with the app's own dependency graph — `dashboard-app/backend/main.py` already imports `db`, `whatsapp_renewal_alerts`, `email_template`, and `import_bis_isi_data` from the repo root via a `sys.path.insert` hack.

## Goals

1. Every Python source file and its test lives in `dashboard-app/backend/` — one location for all backend code, matching what `main.py` already treats as its dependency set.
2. Real data files move to a new gitignored `data/` directory; logs move to a new gitignored `logs/` directory. Repo root holds only config, docs, and the two code folders (`dashboard-app/`, plus generated `output/`).
3. `main.py`'s `sys.path.insert(0, str(REPO_ROOT))` hack is removed — no longer needed once `db.py` etc. live alongside it, and removes an ambiguity already flagged for the Render deployment (whether `sys.path` tricks resolve correctly under Render's `rootDir` setting).
4. Every file whose behavior depends on its own location (`Path(__file__).parent`-style paths) is updated so nothing silently breaks — verified file-by-file, not assumed.
5. The Windows Task Scheduler job (`run_whatsapp_alerts.ps1`) keeps working after the move.
6. Full test suite passes throughout, moves done with `git mv` to preserve history.

## Files Moving (git mv, no content change beyond path fixes below)

Into `dashboard-app/backend/`:
- `db.py`, `test_db.py`
- `whatsapp_renewal_alerts.py`, `test_whatsapp_renewal_alerts.py`
- `email_template.py`, `test_email_template.py`
- `import_bis_isi_data.py`, `test_import_bis_isi_data.py`
- `migrate_to_sqlite.py`
- `fix_bis_isi_cert_names.py`, `test_fix_bis_isi_cert_names.py`
- `cert_automation.py`, `test_cert_automation.py`
- `banner_generator.py`
- `create_dummy_data.py`

Into `data/` (new, gitignored):
- `clients.db`, `clients.backup.db`, `clients.backup-20260723-111643.db`, `clients.backup-20260723-115406.db`
- `clients_certifications.xlsx`, `clients_certifications.backup.xlsx`
- `sent_log.json`

Into `logs/` (new, gitignored):
- `whatsapp_automation.log`, `scheduler_output.log`

Deleted (redundant once backend's is the only one): root `requirements.txt` (backend's is already a strict superset: adds `fastapi`, `uvicorn[standard]`, `httpx`, `python-multipart`).

Unchanged: `dashboard-app/frontend/` (already fine), `output/` (its own path handling is CWD-relative, not file-relative — see below), `docs/`, `render.yaml`, `.env`/`.env.example`, `.gitignore`, `run_whatsapp_alerts.ps1` (path *reference* updates only, file itself stays at root since it's the OS-level entrypoint), `.claude/`, `.superpowers/`.

## Path Fixes Required (verified per-file, not assumed)

Each of these currently computes a path via `Path(__file__).parent` (or a bare relative-to-CWD string), which breaks once the file moves one directory deeper (`dashboard-app/backend/` instead of repo root):

1. **`db.py`**: `DEFAULT_DB_PATH` currently falls back to `SCRIPT_DIR / "clients.db"` when `DASHBOARD_DB_PATH` is unset. Change the fallback to resolve to the new `data/clients.db` location — three levels up from the new file location (`backend/` → `dashboard-app/` → repo root) then into `data/`.

2. **`whatsapp_renewal_alerts.py`**: two fixes —
   - `DEFAULT_TEXT_LOG_PATH = SCRIPT_DIR / "whatsapp_automation.log"` → point at the new `logs/` location.
   - `load_dotenv(SCRIPT_DIR / ".env")` inside `main()` → point at the repo-root `.env` (three levels up from the new file location). This one is easy to miss: it only fires when the script runs standalone (the Task Scheduler path), so a missed fix wouldn't show up in local dashboard testing — it would silently break the daily scheduled job with "WHATSAPP_TOKEN must be set."

3. **`migrate_to_sqlite.py`**: `SOURCE_XLSX = SCRIPT_DIR / "clients_certifications.xlsx"` and `SOURCE_LOG = SCRIPT_DIR / "sent_log.json"` → both point at the new `data/` location.

4. **`banner_generator.py`**: `LOGO_PATH = Path(__file__).parent / "dashboard-app" / "frontend" / "public" / "company-logo.png"` — currently assumes it's at repo root. Once moved, needs one more `.parent` and to drop the now-redundant `"dashboard-app"` segment (`Path(__file__).parent.parent / "frontend" / "public" / "company-logo.png"`).

5. **`import_bis_isi_data.py`**: the `__main__` block's default output path, `str(Path(__file__).parent / "clients_certifications.xlsx")`, → point at the new `data/` location (three levels up then into `data/`).

6. **`create_dummy_data.py`**: `output_path = Path(__file__).parent / "clients_certifications.xlsx"` → same fix, point at `data/`.

7. **`main.py`**: remove the `sys.path.insert(0, str(REPO_ROOT))` line and the `BACKEND_DIR`/`sys` setup that exists purely to support it — no longer needed once `db.py` etc. are in the same directory (Python auto-adds a running script's own directory to `sys.path`). Keep computing a `REPO_ROOT`-equivalent constant for the two things that still need it: `LOGO_PATH` and `FRONTEND_DIST` (both still resolve two levels up from `dashboard-app/backend/`, unaffected by this move since `main.py` isn't moving).

8. **`cert_automation.py`**: its `excel_path="clients_certifications.xlsx"` and `output_dir: str = "output"` defaults in the `__main__` block are both CWD-relative (not `Path(__file__)`-based), so as long as it's still invoked from the repo root (the existing convention), a *file-location* fix isn't needed for either. But `clients_certifications.xlsx` itself is moving to `data/` as part of this cleanup, so the `excel_path` string literal needs updating to `"data/clients_certifications.xlsx"` to keep pointing at the real file — this is a consequence of the *data* move, not the *code* move. `output_dir="output"` stays exactly as `"output"` — that directory isn't moving.

9. **`fix_bis_isi_cert_names.py`**: NOT changed. It only uses `DEFAULT_DB_PATH` (imported from `db.py`, already fixed above) and derives its backup path from `Path(db_path).parent` dynamically — self-adjusting, no hardcoded path of its own.

10. **`.gitignore`**: NOT changed. Every relevant pattern (`clients_certifications.xlsx`, `sent_log.json`, `*.db`, `whatsapp_automation.log`, `scheduler_output.log`, `output/`) is unanchored (no leading `/`), so git already matches them at any depth — moving the real files into `data/`/`logs/` subdirectories keeps them correctly ignored with zero `.gitignore` changes.

11. **`run_whatsapp_alerts.ps1`**: update the invoked script path (`whatsapp_renewal_alerts.py` → `dashboard-app\backend\whatsapp_renewal_alerts.py`) and the log redirect target (`scheduler_output.log` → `logs\scheduler_output.log`). Keep `Set-Location -Path $PSScriptRoot` (still cd's to repo root, which is correct — `whatsapp_renewal_alerts.py`'s own path logic is all `Path(__file__)`-anchored and doesn't depend on CWD).

12. **`docs/DEPLOYMENT.md`**: update the Render-shell migration command from `python migrate_to_sqlite.py` to `python dashboard-app/backend/migrate_to_sqlite.py` (run from the repo root, matching how the Render shell's working directory behaves).

13. **`render.yaml`**: NOT changed. `rootDir: dashboard-app/backend` was already correct, and is now even more accurate since every file the backend needs truly lives there.

14. **Requirements**: delete root `requirements.txt`; `dashboard-app/backend/requirements.txt` (already a superset) becomes the only one.

## Testing

Run the full suite (`python -m pytest -q` from the repo root — recursive discovery finds everything in `dashboard-app/backend/` with no config changes needed) after the moves and path fixes. All existing tests must pass unmodified in behavior (only their file location changes) — a regression here means a path fix was missed or wrong.

Manual verification after the automated suite passes:
- Both dev servers start and the dashboard loads real data (proves `db.py`'s new default path and `main.py`'s working `sys.path` removal).
- `python dashboard-app/backend/whatsapp_renewal_alerts.py --dry-run` run from the repo root succeeds and doesn't error on missing `.env` (proves the `load_dotenv` fix).
- `python dashboard-app/backend/migrate_to_sqlite.py` (against a throwaway copy, not the real `data/clients.db` — don't actually re-run migration against live data) at least reaches its "no source file" or path-resolution point without a `FileNotFoundError` on the wrong path, confirming `SOURCE_XLSX`/`SOURCE_LOG` resolve correctly.

## Out of scope

- No change to `dashboard-app/frontend/`'s structure (already fine).
- No change to `output/`'s location or `cert_automation.py`'s `output_dir` default.
- No attempt to fix the pre-existing gap that `cert_automation.py` imports `pandas` but neither `requirements.txt` lists it — unrelated to this cleanup, not touched.
- No CI/lint config changes.
