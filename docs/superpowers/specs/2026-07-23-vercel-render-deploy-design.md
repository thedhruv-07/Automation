# Split-Origin Deployment: Frontend on Vercel, Backend on Render

**Status:** Approved
**Scope:** `dashboard-app/backend/main.py`, `dashboard-app/frontend/src/api.js` (and consumers), `db.py`, deployment config files, and a deployment runbook.

## Problem

The dashboard currently runs as a single local process pair (FastAPI backend + Vite dev server, or backend serving the built frontend as static files) with:
- **No authentication** — anyone who can reach the backend can browse all client PII (names, emails, phone numbers) and trigger WhatsApp sends.
- **Same-origin assumption** — `dashboard-app/frontend/src/api.js` calls `/api/...` as relative paths, assuming the frontend and backend are always served from the same host.
- **A hardcoded local db path** — `db.py`'s `DEFAULT_DB_PATH` is `SCRIPT_DIR / "clients.db"`, always relative to the repo checkout.

The user wants to deploy the frontend to Vercel and the backend to Render (chosen for its persistent-disk support on paid tiers) so the dashboard is reachable from anywhere, still as a solo-admin tool. This requires: authentication (since it becomes internet-reachable), a configurable cross-origin API base URL, CORS changes, a configurable db path (for Render's persistent disk), and deployment configuration/documentation for both platforms.

## Goals

1. Backend rejects unauthenticated requests once deployed, without adding a login UI or new dependency (HTTP Basic Auth is sufficient for a solo admin).
2. Local development is unaffected — auth and the API base URL both no-op to today's behavior unless explicitly configured via env vars.
3. Frontend can be built once and pointed at any backend URL via a build-time env var.
4. `clients.db`'s location is configurable so it can live on a Render persistent disk instead of the repo checkout path.
5. A clear, followable runbook exists for deploying and updating both halves, including the real client PII data.

## Design

### 1. Backend Basic Auth (`dashboard-app/backend/main.py`)

Add a FastAPI dependency using `fastapi.security.HTTPBasic` + `secrets.compare_digest` (timing-safe), applied globally via `app.middleware` or a router-level `Depends`, whichever integrates more cleanly with this file's existing structure (read the current file before choosing — it already has some route grouping).

```python
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic(auto_error=False)

def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    expected_user = os.environ.get("DASHBOARD_USERNAME")
    expected_pass = os.environ.get("DASHBOARD_PASSWORD")
    if not expected_user or not expected_pass:
        return  # auth disabled: local dev / not configured
    if credentials is None or not (
        secrets.compare_digest(credentials.username, expected_user)
        and secrets.compare_digest(credentials.password, expected_pass)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
```

- Applied as a dependency on the whole app/router (not per-route duplication) so every `/api/*` route requires it once both env vars are set.
- `auto_error=False` on `HTTPBasic` lets the function itself decide the response (rather than FastAPI's default), so the "auth disabled" branch works cleanly when no `Authorization` header is sent at all.
- **When `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` are unset (the case for local dev and the existing test suite), auth is a no-op.** This is a deliberate, explicit off-switch — not a fallback to insecure defaults — and only matters because this codebase already has no auth today; existing tests must keep passing unmodified.
- The browser's native Basic Auth prompt appears on first `401`; no custom login page.

### 2. Configurable API base URL (frontend)

New constant at the top of `dashboard-app/frontend/src/api.js`:

```javascript
const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
```

Every `fetch(...)` call and URL-building helper (`clientsExportUrl`, `downloadClientTemplate`) prefixes its path with `API_BASE` instead of using a bare `/api/...` literal. When `VITE_API_BASE_URL` is unset (local dev, Vite's existing dev-server proxy), `API_BASE` is `""` and all paths remain exactly as they are today — zero behavior change locally.

Cross-origin requests carrying Basic Auth credentials need `credentials: "include"` added to every `fetch()` call in `api.js` (browsers don't forward `Authorization` cross-origin by default even after the user authenticates once via the native prompt, unless the request opts in).

### 3. CORS update (`main.py`)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        *([os.environ["DASHBOARD_ALLOWED_ORIGIN"]] if os.environ.get("DASHBOARD_ALLOWED_ORIGIN") else []),
    ],
    allow_credentials=True,
    ...
)
```

`DASHBOARD_ALLOWED_ORIGIN` is set to the deployed Vercel URL (e.g. `https://absolute-veritas-dashboard.vercel.app`) as a Render env var, so the origin list doesn't need a code change per deploy. `allow_credentials=True` is required for the browser to send the Basic Auth header on cross-origin requests; per the Fetch spec this means `allow_origins` must be an explicit list, never `"*"` — already true here.

### 4. Configurable db path (`db.py`)

```python
DEFAULT_DB_PATH = Path(os.environ.get("DASHBOARD_DB_PATH", str(SCRIPT_DIR / "clients.db")))
```

Unset locally (falls back to today's path, unchanged). On Render, set to the persistent disk's mount path (e.g. `/data/clients.db`) so writes survive restarts/redeploys — Render's default filesystem is ephemeral outside an attached Disk.

### 5. Deployment config files

- `render.yaml` at repo root (Render "Blueprint" — lets the user create the service from a single file instead of manual dashboard clicking): defines the web service (root dir `dashboard-app/backend`, build command `pip install -r requirements.txt`, start command `uvicorn main:app --host 0.0.0.0 --port $PORT`), a disk mounted at `/data`, and lists the required env vars as `sync: false` placeholders (Render prompts for their values at creation, they're never written into the file — keeps secrets out of git).
- No new file needed for Vercel — its zero-config Vite detection handles the frontend build; the only per-project setting is the `VITE_API_BASE_URL` env var, set in the Vercel dashboard (documented in the runbook, not a file, since it's an actual secret-adjacent per-deployment value).

### 6. Runbook (documentation, not code)

A step-by-step doc covering:
- Creating the Render service from `render.yaml`, setting env vars (`WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANG`, `EMAIL_SENDER`, `BREVO_API_KEY`, `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, `DASHBOARD_DB_PATH=/data/clients.db`).
- Getting the real `clients.db` (56,737 rows) onto the Render disk once: either (a) upload `clients_certifications.xlsx` to the Render instance via its shell and run `migrate_to_sqlite.py` there, or (b) run the migration locally and copy the resulting `clients.db` file up directly. The runbook documents both, recommending (a) since it avoids transferring the already-migrated binary db file and keeps the xlsx (which the user already treats as the source of truth) as the thing that travels.
- Deploying the Vercel frontend (import the GitHub repo, set root directory to `dashboard-app/frontend`, set `VITE_API_BASE_URL` to the Render service's public URL) and adding `DASHBOARD_ALLOWED_ORIGIN` on Render once the Vercel URL is known (chicken-and-egg: deploy Render first without needing to know the Vercel URL yet since CORS only matters once the frontend calls it, then set `DASHBOARD_ALLOWED_ORIGIN` after the Vercel deploy exists).
- Setting `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` to real values (not committed anywhere) before making the Render URL reachable by anyone else.

## Out of scope

- No custom login page — native Basic Auth prompt is accepted as sufficient for a solo admin.
- No rate limiting / brute-force lockout on the auth check — noted as a possible fast-follow, not blocking.
- No change to the Windows Task Scheduler job or the local dev workflow — both continue working exactly as before, since every new env var is optional and defaults to current behavior when unset.
- No CI/CD pipeline setup beyond what Render/Vercel provide natively from a GitHub push.

## Testing

- Backend: new tests for `require_auth` — request without credentials when env vars are set → 401; request with correct credentials → 200; request with wrong credentials → 401; request with no env vars set (today's default) → 200 with no credentials at all (auth disabled). Existing `test_main.py` tests must keep passing unmodified (they never set `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`, so auth stays off for them).
- Frontend: `api.js`'s existing tests (`api.test.js`) must keep passing with `API_BASE` defaulting to `""`; add one test confirming a set `VITE_API_BASE_URL`-equivalent prefixes a request URL (Vitest can stub `import.meta.env` for this).
- Manual: not automatable — actually deploying to Render/Vercel and clicking through the live site is a runbook step for the user, not something this plan's automated tests cover.
