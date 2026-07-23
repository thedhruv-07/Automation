# Repo Structure Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate every Python source file and test into `dashboard-app/backend/`, move real data/log files out of the repo root into gitignored `data/`/`logs/` directories, and fix every path reference that breaks as a result — without changing any behavior.

**Architecture:** This is a pure structural move with targeted path-constant fixes, not a behavior change. Files that compute paths via `Path(__file__).parent` need their fallback/default paths adjusted for the new one-directory-deeper location; files that use CWD-relative paths (`cert_automation.py`'s `output_dir`) are unaffected by the code move but may still need a literal string updated if the *data file itself* is moving. Every fix in this plan was verified against the actual current file content before being written — none are guesses.

**Tech Stack:** No new dependencies. Plain `git mv` for tracked files (only the Python source/tests are git-tracked — data/log files are all gitignored, so those moves are plain filesystem moves, nothing to `git mv`).

**Reference spec:** `docs/superpowers/specs/2026-07-23-repo-structure-cleanup-design.md`

---

### Task 1: Move data and log files into `data/`/`logs/`

**Files:** (moved, not git-tracked — no `git mv` needed, these are all gitignored)
- `clients.db`, `clients.backup.db`, `clients.backup-20260723-111643.db`, `clients.backup-20260723-115406.db` → `data/`
- `clients_certifications.xlsx`, `clients_certifications.backup.xlsx`, `sent_log.json` → `data/`
- `whatsapp_automation.log`, `scheduler_output.log` → `logs/`

- [ ] **Step 1: Create the directories and move the files**

From the repo root:

```bash
mkdir -p data logs
mv clients.db clients.backup.db clients.backup-20260723-111643.db clients.backup-20260723-115406.db data/
mv clients_certifications.xlsx clients_certifications.backup.xlsx sent_log.json data/
mv whatsapp_automation.log scheduler_output.log logs/
```

(If a "no such file" error occurs for any single file — e.g. a backup `.db` filename that's since been cleaned up or renamed — skip that one file and continue with the rest; the exact backup filenames present depend on when this plan is executed.)

- [ ] **Step 2: Add placeholder files so the directories exist on a fresh clone**

Since every real file in `data/`/`logs/` is gitignored, the directories themselves would otherwise vanish from a fresh clone (git doesn't track empty directories) and code expecting them to exist (e.g. `sqlite3.connect()` on a path whose parent directory doesn't exist) would fail. Add a tracked placeholder to each:

```bash
touch data/.gitkeep logs/.gitkeep
```

- [ ] **Step 3: Verify `.gitignore` still correctly ignores the moved files in their new location**

Run: `git status --short`
Expected: only `data/.gitkeep` and `logs/.gitkeep` show as untracked/new — none of the real data/log files appear (confirming the existing unanchored `.gitignore` patterns still match them at the new depth).

- [ ] **Step 4: Commit**

```bash
git add data/.gitkeep logs/.gitkeep
git commit -m "chore: move data and log files into gitignored data/ and logs/ directories"
```

---

### Task 2: Move all Python source and test files into `dashboard-app/backend/`

**Files (git mv):**
- `db.py`, `test_db.py`
- `whatsapp_renewal_alerts.py`, `test_whatsapp_renewal_alerts.py`
- `email_template.py`, `test_email_template.py`
- `import_bis_isi_data.py`, `test_import_bis_isi_data.py`
- `migrate_to_sqlite.py`
- `fix_bis_isi_cert_names.py`, `test_fix_bis_isi_cert_names.py`
- `cert_automation.py`, `test_cert_automation.py`
- `banner_generator.py`
- `create_dummy_data.py`

- [ ] **Step 1: Move every file with `git mv`, preserving history**

From the repo root:

```bash
git mv db.py dashboard-app/backend/db.py
git mv test_db.py dashboard-app/backend/test_db.py
git mv whatsapp_renewal_alerts.py dashboard-app/backend/whatsapp_renewal_alerts.py
git mv test_whatsapp_renewal_alerts.py dashboard-app/backend/test_whatsapp_renewal_alerts.py
git mv email_template.py dashboard-app/backend/email_template.py
git mv test_email_template.py dashboard-app/backend/test_email_template.py
git mv import_bis_isi_data.py dashboard-app/backend/import_bis_isi_data.py
git mv test_import_bis_isi_data.py dashboard-app/backend/test_import_bis_isi_data.py
git mv migrate_to_sqlite.py dashboard-app/backend/migrate_to_sqlite.py
git mv fix_bis_isi_cert_names.py dashboard-app/backend/fix_bis_isi_cert_names.py
git mv test_fix_bis_isi_cert_names.py dashboard-app/backend/test_fix_bis_isi_cert_names.py
git mv cert_automation.py dashboard-app/backend/cert_automation.py
git mv test_cert_automation.py dashboard-app/backend/test_cert_automation.py
git mv banner_generator.py dashboard-app/backend/banner_generator.py
git mv create_dummy_data.py dashboard-app/backend/create_dummy_data.py
```

- [ ] **Step 2: Confirm the moves, don't commit yet**

Run: `git status --short`
Expected: 15 `R  <old path> -> dashboard-app/backend/<same filename>` rename entries. Nothing else changed yet — this task only moves files; the path fixes happen in Task 3 as a separate commit so a `git bisect` later can distinguish "file moved" from "path constant changed."

- [ ] **Step 3: Commit the pure move**

```bash
git commit -m "chore: move Python source and tests into dashboard-app/backend/"
```

(Tests will fail to import/run correctly at this exact commit — that's expected and fixed in Task 3. This is a deliberate two-step history, not a mistake.)

---

### Task 3: Fix every path reference broken by the move

**Files (content changes only, no further moves):**
- `dashboard-app/backend/db.py`
- `dashboard-app/backend/whatsapp_renewal_alerts.py`
- `dashboard-app/backend/migrate_to_sqlite.py`
- `dashboard-app/backend/banner_generator.py`
- `dashboard-app/backend/import_bis_isi_data.py`
- `dashboard-app/backend/create_dummy_data.py`
- `dashboard-app/backend/cert_automation.py`

- [ ] **Step 1: Run the full suite to see the current failures**

Run: `python -m pytest -q` (from the repo root)
Expected: some failures — at minimum, tests that exercise `DEFAULT_DB_PATH`'s fallback or the migration/BIS-ISI scripts' default paths, since those still point at the old (now-empty, moved-away) repo-root location. Note the exact failures before fixing, to confirm each fix below addresses a real one.

- [ ] **Step 2: Fix `dashboard-app/backend/db.py`**

Current:
```python
SCRIPT_DIR = Path(__file__).parent


def _resolve_default_db_path() -> Path:
    override = os.environ.get("DASHBOARD_DB_PATH")
    return Path(override) if override else SCRIPT_DIR / "clients.db"
```

Replace with:
```python
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def _resolve_default_db_path() -> Path:
    override = os.environ.get("DASHBOARD_DB_PATH")
    return Path(override) if override else REPO_ROOT / "data" / "clients.db"
```

- [ ] **Step 3: Fix `dashboard-app/backend/whatsapp_renewal_alerts.py`**

Current (near the top, after the existing function definitions):
```python
SCRIPT_DIR = Path(__file__).parent
DEFAULT_TEXT_LOG_PATH = SCRIPT_DIR / "whatsapp_automation.log"
```

Replace with:
```python
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_TEXT_LOG_PATH = REPO_ROOT / "logs" / "whatsapp_automation.log"
```

Then, inside `main()`, current:
```python
def main(argv=None) -> int:
    load_dotenv(SCRIPT_DIR / ".env")
```

Replace with:
```python
def main(argv=None) -> int:
    load_dotenv(REPO_ROOT / ".env")
```

- [ ] **Step 4: Fix `dashboard-app/backend/migrate_to_sqlite.py`**

Current:
```python
SCRIPT_DIR = Path(__file__).parent
SOURCE_XLSX = SCRIPT_DIR / "clients_certifications.xlsx"
SOURCE_LOG = SCRIPT_DIR / "sent_log.json"
```

Replace with:
```python
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SOURCE_XLSX = REPO_ROOT / "data" / "clients_certifications.xlsx"
SOURCE_LOG = REPO_ROOT / "data" / "sent_log.json"
```

- [ ] **Step 5: Fix `dashboard-app/backend/banner_generator.py`**

Current:
```python
LOGO_PATH = Path(__file__).parent / "dashboard-app" / "frontend" / "public" / "company-logo.png"
```

Replace with:
```python
LOGO_PATH = Path(__file__).parent.parent / "frontend" / "public" / "company-logo.png"
```

- [ ] **Step 6: Fix `dashboard-app/backend/import_bis_isi_data.py`**

Current (in the `__main__` block):
```python
    source = sys.argv[1]
    output = str(Path(__file__).parent / "clients_certifications.xlsx")
```

Replace with:
```python
    source = sys.argv[1]
    output = str(Path(__file__).parent.parent.parent / "data" / "clients_certifications.xlsx")
```

- [ ] **Step 7: Fix `dashboard-app/backend/create_dummy_data.py`**

Current:
```python
    ws.row_dimensions[1].height = 25
    output_path = Path(__file__).parent / "clients_certifications.xlsx"
```

Replace with:
```python
    ws.row_dimensions[1].height = 25
    output_path = Path(__file__).parent.parent.parent / "data" / "clients_certifications.xlsx"
```

- [ ] **Step 8: Fix `dashboard-app/backend/cert_automation.py`**

Current (in the `__main__` block):
```python
if __name__ == "__main__":
    run_automation(
        excel_path="clients_certifications.xlsx",
        test_mode=True  # Change to False (after setting real credentials in .env) to send real messages
    )
```

Replace with:
```python
if __name__ == "__main__":
    run_automation(
        excel_path="../../data/clients_certifications.xlsx",
        test_mode=True  # Change to False (after setting real credentials in .env) to send real messages
    )
```

(`output_dir` stays exactly `"output"` — unchanged, per the spec: that directory isn't moving, and this default is CWD-relative, correct as long as the script is still invoked from the repo root.)

- [ ] **Step 9: Run the full suite again**

Run: `python -m pytest -q` (from the repo root)
Expected: all passed, with the same total test count reported by this task's own Step 1 run (the pre-fix, post-move failing run) — confirming these fixes resolved every failure Step 1 found without collecting a different set of tests.

- [ ] **Step 10: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/whatsapp_renewal_alerts.py \
        dashboard-app/backend/migrate_to_sqlite.py dashboard-app/backend/banner_generator.py \
        dashboard-app/backend/import_bis_isi_data.py dashboard-app/backend/create_dummy_data.py \
        dashboard-app/backend/cert_automation.py
git commit -m "fix: update path references for the dashboard-app/backend/ and data/ moves"
```

---

### Task 4: Remove the now-unnecessary sys.path hack from main.py, consolidate requirements.txt

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Delete: `requirements.txt` (repo root)

- [ ] **Step 1: Simplify `main.py`'s top-of-file setup**

Current:
```python
"""FastAPI backend for the Absolute Veritas React dashboard."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import base64  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import threading  # noqa: E402
import uuid  # noqa: E402

import openpyxl  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from fastapi import Depends, FastAPI, HTTPException, File, Query, UploadFile, status  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

from datetime import datetime  # noqa: E402
```

Replace with (drops `sys`/`sys.path.insert` — no longer needed since `db`, `whatsapp_renewal_alerts`, `email_template`, and `import_bis_isi_data` now live in this same directory and Python automatically adds a running script's own directory to `sys.path`; the `# noqa: E402` markers on the imports below are also no longer needed since nothing precedes them that would trigger an E402 lint warning, but are left in place here as a no-op — removing them is optional cleanup, not required for correctness):

```python
"""FastAPI backend for the Absolute Veritas React dashboard."""
from pathlib import Path

BACKEND_DIR = Path(__file__).parent
REPO_ROOT = BACKEND_DIR.parent.parent

import base64
import io
import os
import sqlite3
import threading
import uuid

import openpyxl
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, File, Query, UploadFile, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from datetime import datetime
```

`REPO_ROOT` is kept — `main.py` still uses it for `LOGO_PATH` and `FRONTEND_DIST`, both unrelated to Python import resolution and still two levels up from `dashboard-app/backend/`, unaffected by this change.

- [ ] **Step 2: Delete the now-redundant root `requirements.txt`**

`dashboard-app/backend/requirements.txt` already lists everything the root one did (`openpyxl`, `requests`, `python-dotenv`, `pytest`) plus `fastapi`, `uvicorn[standard]`, `httpx`, `python-multipart` — a strict superset.

```bash
rm requirements.txt
```

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q` (from the repo root)
Expected: all passed, same count as Task 3.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: drop main.py's now-unnecessary sys.path hack, consolidate requirements.txt"
```

---

### Task 5: Update the Task Scheduler script and deployment runbook

**Files:**
- Modify: `run_whatsapp_alerts.ps1`
- Modify: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Update `run_whatsapp_alerts.ps1`**

Current:
```powershell
# run_whatsapp_alerts.ps1
Set-Location -Path $PSScriptRoot
& "C:\Python314\python.exe" "whatsapp_renewal_alerts.py" *>> "scheduler_output.log"
```

Replace with:
```powershell
# run_whatsapp_alerts.ps1
Set-Location -Path $PSScriptRoot
& "C:\Python314\python.exe" "dashboard-app\backend\whatsapp_renewal_alerts.py" *>> "logs\scheduler_output.log"
```

(`Set-Location -Path $PSScriptRoot` is unchanged — it still `cd`s to the repo root, which is correct: `whatsapp_renewal_alerts.py`'s own path logic is all `Path(__file__)`-anchored per Task 3 and doesn't depend on the caller's working directory.)

- [ ] **Step 2: Update `docs/DEPLOYMENT.md`'s migration command**

Find this line in the "Get the real client data onto the Render disk" section:
```
3. From the shell, at the repo root: `python migrate_to_sqlite.py`. It reads
```

Replace with:
```
3. From the shell, at the repo root: `python dashboard-app/backend/migrate_to_sqlite.py`. It reads
```

- [ ] **Step 3: Commit**

```bash
git add run_whatsapp_alerts.ps1 docs/DEPLOYMENT.md
git commit -m "docs: update Task Scheduler script and deployment runbook for the new file locations"
```

---

### Task 6: Full end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full automated suite one more time**

Run: `python -m pytest -q` (from the repo root)
Expected: all passed.

- [ ] **Step 2: Start both dev servers and confirm the dashboard loads real data**

Backend: `cd dashboard-app/backend && python -m uvicorn main:app --port 8040`
Frontend: `cd dashboard-app/frontend && npm run dev -- --port 5173`

Open `http://localhost:5173`. Confirm the dashboard loads with real client data (proves `db.py`'s new `data/clients.db` default path resolves correctly, and that `main.py` can still import `db`/`whatsapp_renewal_alerts`/`email_template`/`import_bis_isi_data` without the removed `sys.path` hack).

- [ ] **Step 3: Confirm the WhatsApp CLI script's paths resolve correctly**

From the repo root (not from inside `dashboard-app/backend/`):
```bash
python dashboard-app/backend/whatsapp_renewal_alerts.py --dry-run
```
Expected: it runs (dry-run mode doesn't require real credentials to *start*, though it will still print an error if `WHATSAPP_TOKEN`/`PHONE_NUMBER_ID` aren't loaded from `.env` for anything beyond the dry-run path) and does **not** raise `FileNotFoundError` or complain that `.env` is missing — confirming both the `DEFAULT_TEXT_LOG_PATH` and `load_dotenv(REPO_ROOT / ".env")` fixes from Task 3 are correct. If it does raise a path-related error, that's a signal one of Task 3's fixes has a wrong relative-depth count (`.parent.parent` vs `.parent.parent.parent`) — re-check against this plan's exact code before assuming the file layout itself is wrong.

- [ ] **Step 4: Confirm `migrate_to_sqlite.py`'s source paths resolve correctly (without touching real data)**

```bash
python dashboard-app/backend/migrate_to_sqlite.py
```
Since `data/clients.db` already has rows (the real migrated data), this should print the idempotency guard's refusal message (`"...already has client rows — this looks like a re-run..."`) rather than a `FileNotFoundError` on `SOURCE_XLSX`/`SOURCE_LOG` — confirming those two paths resolve to the real `data/clients_certifications.xlsx` and `data/sent_log.json` correctly. **Do not pass `--force`** — this step only needs to prove the paths resolve, not to actually re-run the migration against live data.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: verify repo structure cleanup end-to-end"
```
