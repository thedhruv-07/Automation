# Split-Origin Deployment (Vercel + Render) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Absolute Veritas certification dashboard deployable with the frontend on Vercel and the backend on Render, protected by Basic Auth, without changing local-dev behavior.

**Architecture:** The backend (`dashboard-app/backend/main.py`) gains an opt-in Basic Auth dependency (no-ops unless `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` are set), CORS `allow_credentials` plus a configurable extra allowed origin, and a configurable `clients.db` path (`db.py`) for Render's persistent disk. The frontend gains a build-time-configurable API base URL (`VITE_API_BASE_URL`), a small `auth.js` module that stores a Basic Auth header in `sessionStorage`, and a `LoginScreen` component that gates the app — but only when `VITE_API_BASE_URL` is actually set, so local dev (`npm run dev`, no env var) shows the dashboard immediately exactly as today.

**Tech Stack:** FastAPI's `HTTPBasic` (no new dependency), Vite's `import.meta.env`, existing React/Vitest/pytest stack.

**Reference spec:** `docs/superpowers/specs/2026-07-23-vercel-render-deploy-design.md`

**Correction from the spec during planning:** the spec assumed the browser's native Basic Auth popup would handle login ("no custom login page needed"). That's wrong for this app: the native popup only fires on top-level navigations, never on `fetch()` calls, and this entire SPA talks to the backend exclusively via `fetch()`. This plan adds a small `LoginScreen` component instead (approved after flagging the gap) — everything else in the spec is unchanged.

---

## File Structure

**New files:**
- `dashboard-app/frontend/src/auth.js` — sessionStorage-backed Basic Auth header storage + header-building helper.
- `dashboard-app/frontend/src/auth.test.js` — tests for `auth.js`.
- `dashboard-app/frontend/src/components/LoginScreen.jsx` — login form gating the app when deployed.
- `dashboard-app/frontend/src/components/LoginScreen.test.jsx` — tests for `LoginScreen`.
- `render.yaml` — Render Blueprint (best-effort convenience; the runbook's manual dashboard steps are the authoritative path since Render's blueprint schema can drift from what's written here).
- `docs/DEPLOYMENT.md` — the runbook: step-by-step deploy instructions for both platforms, including the real client PII data.

**Modified files:**
- `db.py` — `DEFAULT_DB_PATH` becomes overridable via `DASHBOARD_DB_PATH`.
- `test_db.py` — tests for the new override.
- `dashboard-app/backend/main.py` — `require_auth` dependency wired onto every `/api/*` route except `/api/health`; CORS gains `allow_credentials` and an optional extra origin.
- `dashboard-app/backend/test_main.py` — tests for auth and CORS origin resolution.
- `dashboard-app/frontend/src/api.js` — every request prefixed with `API_BASE`, carries `credentials: "include"` and a stored `Authorization` header if present; new `verifyCredentials` export.
- `dashboard-app/frontend/src/api.test.js` — updated for the new fetch call shape; new tests for `API_BASE` prefixing and `verifyCredentials`.
- `dashboard-app/frontend/src/main.jsx` — wraps `App` in an auth gate, active only when `VITE_API_BASE_URL` is set.
- `.env.example` — documents the new optional env vars.

---

### Task 1: `db.py` — configurable `DEFAULT_DB_PATH`

**Files:**
- Modify: `db.py`
- Test: `test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_db.py`:

```python
def test_resolve_default_db_path_uses_env_override(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DB_PATH", "/tmp/custom-dir/clients.db")
    from db import _resolve_default_db_path
    assert _resolve_default_db_path() == Path("/tmp/custom-dir/clients.db")


def test_resolve_default_db_path_falls_back_to_script_dir(monkeypatch):
    monkeypatch.delenv("DASHBOARD_DB_PATH", raising=False)
    from db import _resolve_default_db_path, SCRIPT_DIR
    assert _resolve_default_db_path() == SCRIPT_DIR / "clients.db"
```

(`Path` is already imported at the top of `test_db.py` — check; if not, add `from pathlib import Path`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_db.py -v -k resolve_default_db_path`
Expected: FAIL with `ImportError: cannot import name '_resolve_default_db_path'`

- [ ] **Step 3: Update `db.py`**

Add `import os` to the top import block (currently `shutil`, `sqlite3`, `datetime`, `Path` — no `os` yet). Replace:

```python
SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB_PATH = SCRIPT_DIR / "clients.db"
```

with:

```python
SCRIPT_DIR = Path(__file__).parent


def _resolve_default_db_path() -> Path:
    override = os.environ.get("DASHBOARD_DB_PATH")
    return Path(override) if override else SCRIPT_DIR / "clients.db"


DEFAULT_DB_PATH = _resolve_default_db_path()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_db.py -v`
Expected: all passed (existing tests unaffected — `DEFAULT_DB_PATH` still resolves identically when `DASHBOARD_DB_PATH` is unset, which is the case for the whole existing suite)

- [ ] **Step 5: Commit**

```bash
git add db.py test_db.py
git commit -m "feat: make clients.db path configurable via DASHBOARD_DB_PATH"
```

---

### Task 2: `main.py` — Basic Auth on every `/api/*` route except health

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Test: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/backend/test_main.py` (near the top-level tests, after `test_health_endpoint`):

```python
def test_protected_route_allows_request_when_auth_env_vars_unset(monkeypatch):
    monkeypatch.delenv("DASHBOARD_USERNAME", raising=False)
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    response = client.get("/api/stats")
    assert response.status_code == 200


def test_protected_route_rejects_missing_credentials_when_auth_configured(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "s3cret")
    response = client.get("/api/stats")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_protected_route_rejects_wrong_credentials_when_auth_configured(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "s3cret")
    response = client.get("/api/stats", auth=("admin", "wrong"))
    assert response.status_code == 401


def test_protected_route_accepts_correct_credentials_when_auth_configured(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "s3cret")
    response = client.get("/api/stats", auth=("admin", "s3cret"))
    assert response.status_code == 200


def test_health_endpoint_never_requires_auth(monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "s3cret")
    response = client.get("/api/health")
    assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v -k "protected_route or health_endpoint_never"`
Expected: `test_protected_route_rejects_*` tests FAIL (currently return 200, not 401) — `test_protected_route_allows_*` and `test_health_endpoint_never_requires_auth` already pass today since there's no auth at all yet.

- [ ] **Step 3: Add `require_auth` to `main.py` and wire it onto every route except `/api/health`**

Add `import secrets` to the stdlib import block (alongside `base64`, `io`, `os`, `sqlite3`, `threading`, `uuid`). Change the FastAPI import line:

```python
from fastapi import FastAPI, HTTPException, File, Query, UploadFile  # noqa: E402
```

to:

```python
from fastapi import Depends, FastAPI, HTTPException, File, Query, UploadFile, status  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
```

After the CORS `app.add_middleware(...)` block (before `@app.get("/api/health")`), add:

```python
security = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    """No-ops when DASHBOARD_USERNAME/DASHBOARD_PASSWORD aren't set (local dev,
    and the existing test suite, which never sets them). Once both are set --
    intended for a public deployment -- every route depending on this requires
    them."""
    expected_user = os.environ.get("DASHBOARD_USERNAME")
    expected_pass = os.environ.get("DASHBOARD_PASSWORD")
    if not expected_user or not expected_pass:
        return
    valid = (
        credentials is not None
        and secrets.compare_digest(credentials.username, expected_user)
        and secrets.compare_digest(credentials.password, expected_pass)
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
```

Then add `dependencies=[Depends(require_auth)]` to every route decorator **except** `/api/health`. Twelve routes change:

```python
@app.get("/api/clients", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/stats", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/clients/export", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/email-preview/{client_id}", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/settings-info", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/message-log", dependencies=[Depends(require_auth)])
```
```python
@app.post("/api/send/{client_id}", dependencies=[Depends(require_auth)])
```
```python
@app.post("/api/send-all", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/send-all/status/{job_id}", dependencies=[Depends(require_auth)])
```
```python
@app.get("/api/client-template", dependencies=[Depends(require_auth)])
```
```python
@app.post("/api/upload-clients", dependencies=[Depends(require_auth)])
```
```python
@app.post("/api/merge-clients", dependencies=[Depends(require_auth)])
```

`@app.get("/api/health")` is left exactly as-is (no `dependencies=`) — Render's health check probe doesn't send credentials, and a health check that can't succeed would cause Render to treat the service as perpetually down.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed, including every pre-existing test (none of them set `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`, so `require_auth` no-ops for all of them, matching today's behavior).

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add opt-in Basic Auth to every /api route except /api/health"
```

---

### Task 3: `main.py` — CORS credentials + configurable extra origin

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Test: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_main.py`:

```python
def test_resolve_allowed_origins_includes_localhost_by_default(monkeypatch):
    monkeypatch.delenv("DASHBOARD_ALLOWED_ORIGIN", raising=False)
    from main import _resolve_allowed_origins
    assert _resolve_allowed_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_resolve_allowed_origins_appends_configured_origin(monkeypatch):
    monkeypatch.setenv("DASHBOARD_ALLOWED_ORIGIN", "https://example.vercel.app")
    from main import _resolve_allowed_origins
    assert _resolve_allowed_origins() == [
        "http://localhost:5173", "http://127.0.0.1:5173", "https://example.vercel.app",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v -k resolve_allowed_origins`
Expected: FAIL with `ImportError: cannot import name '_resolve_allowed_origins'`

- [ ] **Step 3: Update the CORS middleware block in `main.py`**

Replace:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

with:

```python
def _resolve_allowed_origins() -> list[str]:
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    extra = os.environ.get("DASHBOARD_ALLOWED_ORIGIN")
    if extra:
        origins.append(extra)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_credentials=True` is required for the browser to forward the stored `Authorization` header on cross-origin requests once the frontend is split onto Vercel (Task 5/6). Per the Fetch spec this requires `allow_origins` to be an explicit list rather than `"*"` — already true here.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: allow credentialed CORS requests and a configurable extra allowed origin"
```

---

### Task 4: Frontend — `auth.js` credential storage module

**Files:**
- Create: `dashboard-app/frontend/src/auth.js`
- Test: `dashboard-app/frontend/src/auth.test.js`

- [ ] **Step 1: Write the failing tests**

```javascript
// dashboard-app/frontend/src/auth.test.js
import { describe, it, expect, beforeEach } from "vitest";
import { getStoredAuthHeader, setStoredAuthHeader, buildAuthHeader } from "./auth";

beforeEach(() => {
  sessionStorage.clear();
});

describe("getStoredAuthHeader / setStoredAuthHeader", () => {
  it("returns null when nothing is stored", () => {
    expect(getStoredAuthHeader()).toBeNull();
  });

  it("returns the value set by setStoredAuthHeader", () => {
    setStoredAuthHeader("Basic abc123");
    expect(getStoredAuthHeader()).toBe("Basic abc123");
  });
});

describe("buildAuthHeader", () => {
  it("base64-encodes username:password with a Basic prefix", () => {
    expect(buildAuthHeader("admin", "s3cret")).toBe("Basic " + btoa("admin:s3cret"));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/auth.test.js`
Expected: FAIL with `Failed to resolve import "./auth"`

- [ ] **Step 3: Write `auth.js`**

```javascript
// dashboard-app/frontend/src/auth.js
const STORAGE_KEY = "dashboard_auth_header";

export function getStoredAuthHeader() {
  return sessionStorage.getItem(STORAGE_KEY);
}

export function setStoredAuthHeader(value) {
  sessionStorage.setItem(STORAGE_KEY, value);
}

export function buildAuthHeader(username, password) {
  return "Basic " + btoa(`${username}:${password}`);
}
```

`sessionStorage` (not `localStorage`) is deliberate: credentials are cleared when the tab closes rather than persisting indefinitely, while still surviving page refreshes within a session. No `clearStoredAuthHeader` — nothing in this plan's scope (no logout flow) needs it; add it when a logout feature is actually designed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/auth.test.js`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/auth.js dashboard-app/frontend/src/auth.test.js
git commit -m "feat: add sessionStorage-backed Basic Auth header storage"
```

---

### Task 5: Frontend — `api.js` gains `API_BASE`, credentials, and `verifyCredentials`

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Replace `dashboard-app/frontend/src/api.test.js` entirely with:

```javascript
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus, verifyCredentials,
} from "./api";
import { setStoredAuthHeader } from "./auth";

beforeEach(() => {
  global.fetch = vi.fn();
  sessionStorage.clear();
});

describe("getClients", () => {
  it("returns the paginated response and passes query params", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 50 }),
    });
    const result = await getClients({ page: 1, pageSize: 50, status: "CRITICAL", search: "tech" });
    expect(result).toEqual({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 50 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/clients?page=1&page_size=50&status=CRITICAL&search=tech",
      { credentials: "include", headers: {} }
    );
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getClients({})).rejects.toThrow("Failed to load clients: 500");
  });
});

describe("getStats", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status_counts: { total: 5 }, cert_types: ["ISO 9001"] }),
    });
    const stats = await getStats();
    expect(stats).toEqual({ status_counts: { total: 5 }, cert_types: ["ISO 9001"] });
    expect(global.fetch).toHaveBeenCalledWith("/api/stats", { credentials: "include", headers: {} });
  });
});

describe("getEmailPreview", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ subject: "Renew ISO 9001", html: "<html></html>" }),
    });
    const preview = await getEmailPreview("CLT001");
    expect(preview).toEqual({ subject: "Renew ISO 9001", html: "<html></html>" });
    expect(global.fetch).toHaveBeenCalledWith("/api/email-preview/CLT001", { credentials: "include", headers: {} });
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 404 });
    await expect(getEmailPreview("NOPE")).rejects.toThrow("Failed to load email preview: 404");
  });
});

describe("getSettingsInfo", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ template_name: "cert_renewal_alert", critical_days: 7 }),
    });
    const info = await getSettingsInfo();
    expect(info).toEqual({ template_name: "cert_renewal_alert", critical_days: 7 });
    expect(global.fetch).toHaveBeenCalledWith("/api/settings-info", { credentials: "include", headers: {} });
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getSettingsInfo()).rejects.toThrow("Failed to load settings info: 500");
  });
});

describe("getMessageLog", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ client_id: "CLT001", message_id: "wamid.ABC" }],
    });
    const log = await getMessageLog();
    expect(log).toEqual([{ client_id: "CLT001", message_id: "wamid.ABC" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/message-log", { credentials: "include", headers: {} });
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getMessageLog()).rejects.toThrow("Failed to load message log: 500");
  });
});

describe("sendAlert", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "sent", message_id: "wamid.ABC" }),
    });
    const result = await sendAlert("CLT001");
    expect(result).toEqual({ status: "sent", message_id: "wamid.ABC" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send/CLT001",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Alert already sent today for this client/status" }),
    });
    await expect(sendAlert("CLT001")).rejects.toThrow(
      "Alert already sent today for this client/status"
    );
  });
});

describe("uploadClientsFile", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 3 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await uploadClientsFile(file);
    expect(result).toEqual({ status: "ok", row_count: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/upload-clients",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Column headers don't match the expected format" }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(uploadClientsFile(file)).rejects.toThrow(
      "Column headers don't match the expected format"
    );
  });
});

describe("sendAllAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});

describe("getSendAllStatus", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ total: 5, sent: 2, skipped: 1, failed: 0, done: false }),
    });
    const status = await getSendAllStatus("abc-123");
    expect(status).toEqual({ total: 5, sent: 2, skipped: 1, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all/status/abc-123", { credentials: "include", headers: {} });
  });
});

describe("verifyCredentials", () => {
  it("returns true when the backend accepts the credentials", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const ok = await verifyCredentials("Basic dGVzdDp0ZXN0");
    expect(ok).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/stats",
      { credentials: "include", headers: { Authorization: "Basic dGVzdDp0ZXN0" } }
    );
  });

  it("returns false when the backend rejects the credentials", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 401 });
    const ok = await verifyCredentials("Basic d3Jvbmc6d3Jvbmc=");
    expect(ok).toBe(false);
  });
});

describe("authenticated requests", () => {
  it("adds the stored Authorization header to requests once set", async () => {
    setStoredAuthHeader("Basic dGVzdDp0ZXN0");
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ status_counts: { total: 1 } }) });
    await getStats();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/stats",
      { credentials: "include", headers: { Authorization: "Basic dGVzdDp0ZXN0" } }
    );
  });
});

describe("API_BASE prefixing", () => {
  it("prefixes requests with VITE_API_BASE_URL when set", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE_URL", "https://backend.example.com");
    const { getStats: getStatsWithBase } = await import("./api");
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ status_counts: { total: 1 } }) });
    await getStatsWithBase();
    expect(global.fetch).toHaveBeenCalledWith(
      "https://backend.example.com/api/stats",
      { credentials: "include", headers: {} }
    );
    vi.unstubAllEnvs();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: most tests FAIL — every existing `fetch` call currently passes only a bare URL (or a plain `{method: "POST"}`), not the new `{credentials, headers}` shape; `verifyCredentials` doesn't exist yet.

- [ ] **Step 3: Replace `api.js`**

```javascript
import { getStoredAuthHeader } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function authHeaders(extra = {}) {
  const stored = getStoredAuthHeader();
  return stored ? { ...extra, Authorization: stored } : extra;
}

export async function getClients(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.sortKey) query.set("sort_key", params.sortKey);
  if (params.sortDir) query.set("sort_dir", params.sortDir);
  const qs = query.toString();
  const res = await fetch(`${API_BASE}${qs ? `/api/clients?${qs}` : "/api/clients"}`, {
    credentials: "include",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/api/stats`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load stats: ${res.status}`);
  return res.json();
}

export async function getEmailPreview(clientId) {
  const res = await fetch(`${API_BASE}/api/email-preview/${clientId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load email preview: ${res.status}`);
  return res.json();
}

export async function getSettingsInfo() {
  const res = await fetch(`${API_BASE}/api/settings-info`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load settings info: ${res.status}`);
  return res.json();
}

export async function getMessageLog() {
  const res = await fetch(`${API_BASE}/api/message-log`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load message log: ${res.status}`);
  return res.json();
}

export async function sendAlert(clientId) {
  const res = await fetch(`${API_BASE}/api/send/${clientId}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Send failed: ${res.status}`);
  }
  return data;
}

export async function sendAllAlerts() {
  const res = await fetch(`${API_BASE}/api/send-all`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}

export async function getSendAllStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/send-all/status/${jobId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load send-all status: ${res.status}`);
  return res.json();
}

export function clientsExportUrl({ status, certType, expiryBefore, search } = {}) {
  const query = new URLSearchParams();
  if (status && status !== "ALL") query.set("status", status);
  if (certType && certType !== "ALL") query.set("cert_type", certType);
  if (expiryBefore) query.set("expiry_before", expiryBefore);
  if (search) query.set("search", search);
  const qs = query.toString();
  return `${API_BASE}${qs ? `/api/clients/export?${qs}` : "/api/clients/export"}`;
}

export async function uploadClientsFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Upload failed: ${res.status}`);
  }
  return data;
}

export async function mergeClientsFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/merge-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Merge failed: ${res.status}`);
  }
  return data;
}

export function downloadClientTemplate() {
  const link = document.createElement("a");
  link.href = `${API_BASE}/api/client-template`;
  link.download = "clients_certifications_template.xlsx";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export async function verifyCredentials(authHeaderValue) {
  const res = await fetch(`${API_BASE}/api/stats`, {
    credentials: "include",
    headers: { Authorization: authHeaderValue },
  });
  return res.ok;
}
```

`authHeaders()` reads `getStoredAuthHeader()` fresh on every call (not cached at import time), so a credential set after the module first loads (i.e. right after the user logs in) is picked up by the very next request with no extra wiring.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed.

- [ ] **Step 5: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed (no other file references `api.js`'s internals in a way that would break — consumers only call the exported functions, whose signatures are unchanged).

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: api.js sends credentials and supports a configurable cross-origin API base URL"
```

---

### Task 6: Frontend — `LoginScreen` component + `main.jsx` auth gate

**Files:**
- Create: `dashboard-app/frontend/src/components/LoginScreen.jsx`
- Create: `dashboard-app/frontend/src/components/LoginScreen.test.jsx`
- Modify: `dashboard-app/frontend/src/main.jsx`

- [ ] **Step 1: Write the failing tests**

```javascript
// dashboard-app/frontend/src/components/LoginScreen.test.jsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import LoginScreen from "./LoginScreen";
import * as api from "../api";

vi.mock("../api");

beforeEach(() => {
  vi.resetAllMocks();
});

describe("LoginScreen", () => {
  it("calls onSuccess once verification succeeds", async () => {
    api.verifyCredentials.mockResolvedValue(true);
    const onSuccess = vi.fn();
    render(<LoginScreen onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByText("Sign in"));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(api.verifyCredentials).toHaveBeenCalledWith("Basic " + btoa("admin:s3cret"));
  });

  it("shows an error and does not call onSuccess when verification fails", async () => {
    api.verifyCredentials.mockResolvedValue(false);
    const onSuccess = vi.fn();
    render(<LoginScreen onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByText("Sign in"));

    await waitFor(() => expect(screen.getByText("Invalid username or password.")).toBeInTheDocument());
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/LoginScreen.test.jsx`
Expected: FAIL with `Failed to resolve import "./LoginScreen"`

- [ ] **Step 3: Write `LoginScreen.jsx`**

```jsx
import { useState } from "react";
import { verifyCredentials } from "../api";
import { buildAuthHeader, setStoredAuthHeader } from "../auth";

export default function LoginScreen({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setChecking(true);
    setError(null);
    const header = buildAuthHeader(username, password);
    const ok = await verifyCredentials(header);
    setChecking(false);
    if (!ok) {
      setError("Invalid username or password.");
      return;
    }
    setStoredAuthHeader(header);
    onSuccess();
  }

  return (
    <div className="min-h-screen bg-surface-page flex items-center justify-center p-6">
      <form
        onSubmit={handleSubmit}
        className="bg-surface rounded-2xl shadow-xl border border-line w-full max-w-sm p-6 space-y-4"
      >
        <h1 className="text-lg font-bold text-ink-primary">Certification Manager</h1>
        <p className="text-sm text-ink-secondary">Sign in to continue.</p>
        {error && (
          <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
            {error}
          </div>
        )}
        <div>
          <label htmlFor="login-username" className="block text-sm font-medium text-ink-secondary mb-1">
            Username
          </label>
          <input
            id="login-username"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            className="w-full px-4 py-2 rounded-lg border border-line bg-surface-page text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
          />
        </div>
        <div>
          <label htmlFor="login-password" className="block text-sm font-medium text-ink-secondary mb-1">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="w-full px-4 py-2 rounded-lg border border-line bg-surface-page text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
          />
        </div>
        <button
          type="submit"
          disabled={checking}
          className="w-full px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
        >
          {checking ? "Checking…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/LoginScreen.test.jsx`
Expected: 2 passed.

- [ ] **Step 5: Wire the gate into `main.jsx`**

Replace `dashboard-app/frontend/src/main.jsx` entirely with:

```jsx
import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import LoginScreen from './components/LoginScreen.jsx'
import { getStoredAuthHeader } from './auth.js'

const REQUIRE_LOGIN = Boolean(import.meta.env.VITE_API_BASE_URL)

function Root() {
  const [authed, setAuthed] = useState(() => !REQUIRE_LOGIN || Boolean(getStoredAuthHeader()))
  if (REQUIRE_LOGIN && !authed) {
    return <LoginScreen onSuccess={() => setAuthed(true)} />
  }
  return <App />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
```

`REQUIRE_LOGIN` is `false` whenever `VITE_API_BASE_URL` is unset — which is every local `npm run dev` run today, and stays that way. The login gate only activates for a build that actually sets `VITE_API_BASE_URL` (the Vercel production build, Task 7). No test file is added for `main.jsx` — it's the composition root with no existing test precedent in this project (no `main.test.jsx` exists today), and its only logic (the `REQUIRE_LOGIN` boolean and which component to mount) is a two-line conditional already covered in spirit by `LoginScreen.test.jsx` and the existing `App.test.jsx` suite testing the pieces it assembles.

- [ ] **Step 6: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed.

- [ ] **Step 7: Run the frontend production build to catch any build-time errors**

Run: `cd dashboard-app/frontend && npm run build`
Expected: builds successfully (Vite statically replaces `import.meta.env.VITE_API_BASE_URL` at build time; confirms the new `auth.js`/`LoginScreen.jsx`/`main.jsx` code is build-clean, not just dev-server-clean).

- [ ] **Step 8: Commit**

```bash
git add dashboard-app/frontend/src/components/LoginScreen.jsx dashboard-app/frontend/src/components/LoginScreen.test.jsx dashboard-app/frontend/src/main.jsx
git commit -m "feat: gate the dashboard behind a login screen when deployed with a remote API base URL"
```

---

### Task 7: Deployment config — `render.yaml` and `.env.example`

**Files:**
- Create: `render.yaml`
- Modify: `.env.example`

- [ ] **Step 1: Create `render.yaml`**

```yaml
# Render Blueprint for the FastAPI backend. This is a best-effort convenience
# file -- Render's Blueprint schema has changed across versions, so verify
# the field names here against Render's current "Blueprint (render.yaml)"
# docs before relying on it. docs/DEPLOYMENT.md's manual dashboard steps are
# the authoritative path if this file is stale by the time you deploy.
services:
  - type: web
    name: absolute-veritas-dashboard-backend
    runtime: python
    rootDir: dashboard-app/backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
    disk:
      name: dashboard-data
      mountPath: /data
      sizeGB: 1
    envVars:
      - key: WHATSAPP_TOKEN
        sync: false
      - key: PHONE_NUMBER_ID
        sync: false
      - key: WHATSAPP_TEMPLATE_NAME
        value: cert_renewal_alert
      - key: WHATSAPP_TEMPLATE_LANG
        value: en
      - key: EMAIL_SENDER
        sync: false
      - key: BREVO_API_KEY
        sync: false
      - key: DASHBOARD_USERNAME
        sync: false
      - key: DASHBOARD_PASSWORD
        sync: false
      - key: DASHBOARD_DB_PATH
        value: /data/clients.db
      - key: DASHBOARD_ALLOWED_ORIGIN
        sync: false
```

`sync: false` entries are secrets/deployment-specific values Render prompts for at service creation rather than storing in this file — nothing sensitive is committed.

- [ ] **Step 2: Update `.env.example`**

The existing file uses placeholder *text* per line (e.g. `WHATSAPP_TOKEN=your_permanent_system_user_token_here`), not blank values — match that convention. Append to `.env.example`:

```
# Optional -- only needed for a public deployment (e.g. Render). Unset
# locally, auth is disabled and the dashboard behaves exactly as before.
DASHBOARD_USERNAME=choose_an_admin_username
DASHBOARD_PASSWORD=choose_a_strong_password
# Optional -- the deployed frontend's origin, added to the CORS allow-list.
DASHBOARD_ALLOWED_ORIGIN=https://your-frontend.vercel.app
# Optional -- overrides where clients.db lives (e.g. a Render persistent
# disk mount path like /data/clients.db). Defaults to the repo checkout.
DASHBOARD_DB_PATH=/data/clients.db
```

- [ ] **Step 3: Verify no secrets are committed**

Run: `git diff --cached render.yaml .env.example`
Expected: `render.yaml` contains no real credentials (`sync: false` placeholders only); `.env.example` contains only placeholder text, no real values.

- [ ] **Step 4: Commit**

```bash
git add render.yaml .env.example
git commit -m "feat: add Render blueprint and document new deployment env vars"
```

---

### Task 8: Deployment runbook (`docs/DEPLOYMENT.md`)

**Files:**
- Create: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Deploying the Dashboard: Render (backend) + Vercel (frontend)

This app is a solo-admin tool. Deploying it makes it reachable from anywhere
you're logged in — it does **not** make it safe to leave undefended. Follow
every step, especially the credentials one.

## 1. Deploy the backend to Render

1. In the Render dashboard, create a new **Web Service** from this GitHub repo.
   If `render.yaml` at the repo root is still accurate (check it against
   Render's current Blueprint docs first — schemas drift), use "New Blueprint
   Instance" to create it from that file directly. Otherwise configure manually:
   - Root directory: `dashboard-app/backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/api/health`
2. Add a **Disk** (Render's persistent storage add-on — requires a paid
   instance type, not the free tier): mount path `/data`, 1 GB is plenty for
   this dataset size.
3. Set environment variables (Render dashboard → your service → Environment):
   - `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `WHATSAPP_TEMPLATE_NAME`,
     `WHATSAPP_TEMPLATE_LANG`, `EMAIL_SENDER`, `BREVO_API_KEY` — same values
     as your local `.env`.
   - `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` — **pick real, unique
     credentials now, not placeholders.** Anyone with these can read every
     client's name/email/phone number and trigger WhatsApp sends.
   - `DASHBOARD_DB_PATH=/data/clients.db` — points the app at the persistent
     disk instead of the ephemeral checkout path.
   - Leave `DASHBOARD_ALLOWED_ORIGIN` unset for now — you'll set it after
     step 2, once you know the Vercel URL.
4. Deploy. Confirm `https://<your-service>.onrender.com/api/health` returns
   `{"status": "ok"}`.

## 2. Get the real client data onto the Render disk

The disk starts empty — `clients.db` doesn't exist there yet. Recommended:
transfer the source spreadsheet (which you already treat as the source of
truth) and run the same migration script Render will run, rather than
copying the already-built `.db` file:

1. Open a shell on the Render service (Render dashboard → your service →
   "Shell").
2. Upload `clients_certifications.xlsx` to the service (Render's shell
   supports file upload via its web UI, or `scp`/`rsync` if you've set up
   SSH access — check Render's current docs for the supported method).
3. From the shell, at the repo root: `python migrate_to_sqlite.py`. It reads
   `clients_certifications.xlsx` and writes to `$DASHBOARD_DB_PATH`
   (`/data/clients.db`), verifying the row count matches before declaring
   success — the same script and safety check you already ran locally.
4. Confirm: `python -c "from db import read_clients, DEFAULT_DB_PATH; print(len(read_clients(DEFAULT_DB_PATH)))"`
   should print the same row count as your local `clients.db`.

## 3. Deploy the frontend to Vercel

1. Import this GitHub repo into Vercel as a new project.
2. Set the project's root directory to `dashboard-app/frontend`. Vercel's
   zero-config Vite detection handles the build command/output directory.
3. Add an environment variable: `VITE_API_BASE_URL` = your Render service's
   URL from step 1 (e.g. `https://absolute-veritas-dashboard-backend.onrender.com`,
   no trailing slash).
4. Deploy. Note the resulting Vercel URL (e.g.
   `https://absolute-veritas-dashboard.vercel.app`).

## 4. Close the loop: tell the backend about the frontend's origin

Back in Render (step 1's service) → Environment: set
`DASHBOARD_ALLOWED_ORIGIN` to the Vercel URL from step 3. Save — Render
redeploys automatically.

## 5. Verify end to end

1. Open the Vercel URL. You should land on the login screen (not the
   dashboard directly — if you see the dashboard immediately, `VITE_API_BASE_URL`
   likely wasn't set at build time; check step 3.2 and redeploy).
2. Sign in with the `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` you set in
   step 1.3. You should land on the dashboard with real client data loaded.
3. Confirm pagination, search, filters, and CSV export all work.
4. **Do not** test "Send Alert" / "Send All Eligible" against this deployment
   unless `DASHBOARD_TEST_NUMBER` is also set on Render to a verified test
   number — otherwise a test click sends a real WhatsApp message to a real
   client.

## Updating later

- Backend code changes: push to the branch Render is tracking; it redeploys
  automatically. `clients.db` on the disk is untouched by a redeploy.
- Frontend code changes: push to the branch Vercel is tracking; it redeploys
  automatically.
- Client roster changes: use the dashboard's own Excel Sync page (Replace or
  Merge) against the live deployment — no need to re-run the migration
  script or touch the Render shell again after the initial data load in
  step 2.
```

- [ ] **Step 2: Commit**

```bash
git add docs/DEPLOYMENT.md
git commit -m "docs: add Vercel + Render deployment runbook"
```

---

### Task 9: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `python -m pytest -q`
Expected: all passed (this now includes the new `db.py`/`main.py` auth and CORS tests alongside every pre-existing test).

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed.

- [ ] **Step 3: Run the frontend production build**

Run: `cd dashboard-app/frontend && npm run build`
Expected: succeeds with no errors.

- [ ] **Step 4: Confirm local dev is genuinely unaffected**

Start both servers as usual (backend: `cd dashboard-app/backend && python -m uvicorn main:app --port 8040`; frontend: `cd dashboard-app/frontend && npm run dev -- --port 5173`, matching `vite.config.js`'s proxy target) with no new env vars set. Open `http://localhost:5173` and confirm the dashboard loads immediately — **no login screen appears**, exactly as before this plan.

- [ ] **Step 5: Confirm auth actually engages when configured**

With the backend still running, stop it and restart with `DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD` set (e.g. `DASHBOARD_USERNAME=admin DASHBOARD_PASSWORD=test123` prefixed to the uvicorn command, or added to `.env` temporarily and removed after). Confirm:
- `curl http://127.0.0.1:8040/api/stats` → `401`.
- `curl -u admin:test123 http://127.0.0.1:8040/api/stats` → `200`.
- `curl http://127.0.0.1:8040/api/health` → `200` (no credentials needed).

Then remove the temporary env vars so local dev goes back to its unauthenticated default before continuing any other work in this repo.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: verify split-origin deployment changes end-to-end"
```
