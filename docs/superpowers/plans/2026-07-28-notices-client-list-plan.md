# Notices Page Client List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paginated client list to the Notices page, showing everyone matching the current audience filters with per-row "Sent via WhatsApp" / "Sent via Email" status badges for the selected notice.

**Architecture:** A new `get_broadcast_clients_page()` in `db.py` (paginated sibling to `get_broadcast_clients`, each row annotated with two per-channel booleans via `EXISTS` subqueries against `notice_sent_log`), a new `GET /api/notices/{notice_id}/clients` endpoint mirroring `/api/clients`'s shape, and a new lightweight `NoticeClientsTable.jsx` component (not a reuse of the heavier `ClientTable`, whose per-row send actions and status-tier columns don't apply here) wired into `NoticesView.jsx`.

**Tech Stack:** Python/FastAPI/SQLite (`dashboard-app/backend/`), React/Vite (`dashboard-app/frontend/`), pytest, Vitest + React Testing Library.

---

### Task 1: `db.py` — `get_broadcast_clients_page`

**Files:**
- Modify: `dashboard-app/backend/db.py`
- Modify: `dashboard-app/backend/test_db.py`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/backend/test_db.py`, immediately after `test_get_notice_eligible_count_is_independent_per_notice_and_channel` (the last test in the file):

```python
def test_get_broadcast_clients_page_paginates_and_totals(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
        ("CLT003", "Amit Verma", "HealthFirst", "a@x.com", "919898765432",
         "GMP", "CRS", "GMP-1", "01-01-2025", "10-09-2026", "https://x", "DUE SOON"),
    ], mode="replace")

    rows, total = get_broadcast_clients_page(db_path, "transition_facilitation_2026", page=1, page_size=2)

    assert total == 3
    assert len(rows) == 2
    assert [r["client_id"] for r in rows] == ["CLT001", "CLT002"]

    rows_page2, total2 = get_broadcast_clients_page(db_path, "transition_facilitation_2026", page=2, page_size=2)
    assert total2 == 3
    assert [r["client_id"] for r in rows_page2] == ["CLT003"]


def test_get_broadcast_clients_page_honors_filters(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")

    rows, total = get_broadcast_clients_page(db_path, "transition_facilitation_2026", scheme="CRS")

    assert total == 1
    assert rows[0]["client_id"] == "CLT002"


def test_get_broadcast_clients_page_reports_per_channel_notice_status(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
        ("CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"),
    ], mode="replace")
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    rows, _ = get_broadcast_clients_page(db_path, "transition_facilitation_2026")
    by_id = {r["client_id"]: r for r in rows}

    assert by_id["CLT001"]["notice_sent_whatsapp"] is True
    assert by_id["CLT001"]["notice_sent_email"] is False
    assert by_id["CLT002"]["notice_sent_whatsapp"] is False
    assert by_id["CLT002"]["notice_sent_email"] is False


def test_get_broadcast_clients_page_notice_status_is_independent_per_notice(tmp_path):
    db_path = tmp_path / "clients.db"
    upsert_clients(db_path, [
        ("CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"),
    ], mode="replace")
    record_notice_sent(db_path, "CLT001", "some_other_notice", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    rows, _ = get_broadcast_clients_page(db_path, "transition_facilitation_2026")

    assert rows[0]["notice_sent_whatsapp"] is False
```

Also add `get_broadcast_clients_page` to the file's existing `from db import (is_notice_already_sent, record_notice_sent, get_broadcast_clients, get_notice_eligible_count)` import block (find it and add the new name to that same parenthesized import — read the file first to confirm its current exact line, since prior tasks this session have appended to it).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -k get_broadcast_clients_page -v`
Expected: FAIL — `get_broadcast_clients_page` doesn't exist yet.

- [ ] **Step 3: Implement `get_broadcast_clients_page`**

Add to `dashboard-app/backend/db.py`, immediately after `get_broadcast_clients`:

```python
def get_broadcast_clients_page(
    db_path, notice_id: str, page: int = 1, page_size: int = 50,
    status: str | None = None, cert_type: str | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> tuple[list[dict], int]:
    """Paginated sibling to get_broadcast_clients, each row additionally
    annotated with notice_sent_whatsapp/notice_sent_email booleans -- powers
    the Notices page's client list, which shows the whole filtered audience
    (not excluded by send status, since WhatsApp/Email are tracked and can
    diverge independently) with per-channel status visible per row."""
    conn = get_connection(db_path)
    try:
        where, params = _client_filters_where(status, cert_type, expiry_before, search, scheme)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(f"SELECT COUNT(*) FROM clients {where_clause}", params).fetchone()[0]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT {', '.join(RECORD_FIELDS)},
                EXISTS(
                    SELECT 1 FROM notice_sent_log n
                    WHERE n.client_id = clients.client_id AND n.notice_id = ? AND n.channel = 'whatsapp'
                ) AS notice_sent_whatsapp,
                EXISTS(
                    SELECT 1 FROM notice_sent_log n
                    WHERE n.client_id = clients.client_id AND n.notice_id = ? AND n.channel = 'email'
                ) AS notice_sent_email
            FROM clients {where_clause}
            ORDER BY rowid
            LIMIT ? OFFSET ?
            """,
            [notice_id, notice_id] + params + [page_size, offset],
        ).fetchall()

        result = []
        for r in rows:
            rec = _row_to_dict(r)
            rec["notice_sent_whatsapp"] = bool(r["notice_sent_whatsapp"])
            rec["notice_sent_email"] = bool(r["notice_sent_email"])
            result.append(rec)
        return result, total
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -v`
Expected: all passed.

- [ ] **Step 5: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/test_db.py
git commit -m "feat: add get_broadcast_clients_page for the Notices client list"
```

---

### Task 2: `main.py` — `/api/notices/{notice_id}/clients`

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Add the import**

Current:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
    get_eligible_count, get_notice_eligible_count,
)
```

Replace with:

```python
from db import (  # noqa: E402
    DEFAULT_DB_PATH, get_clients_page, get_stats, export_clients_rows,
    upsert_clients, find_client_by_id, load_sent_log, save_sent_log,
    is_already_sent, load_email_sent_log, save_email_sent_log, is_email_already_sent,
    get_eligible_count, get_notice_eligible_count, get_broadcast_clients_page,
)
```

- [ ] **Step 2: Write the failing tests**

Add to `dashboard-app/backend/test_main.py`, at the end of the file (after `test_send_notice_email_status_returns_404_for_unknown_job`):

```python
def test_notice_clients_unknown_notice_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", tmp_path / "clients.db")
    response = client.get("/api/notices/does_not_exist/clients")
    assert response.status_code == 404


def test_notice_clients_returns_paginated_rows_with_notice_status(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    from db import record_notice_sent
    record_notice_sent(db_path, "CLT001", "transition_facilitation_2026", "whatsapp", "wamid.ABC", "2026-07-27T10:00:00")

    response = client.get(
        "/api/notices/transition_facilitation_2026/clients",
        params={"scheme": "CRS", "page": 1, "page_size": 8},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 8
    by_id = {r["client_id"]: r for r in body["rows"]}
    assert by_id["CLT001"]["notice_sent_whatsapp"] is True
    assert by_id["CLT001"]["notice_sent_email"] is False
    assert by_id["CLT002"]["notice_sent_whatsapp"] is False


def test_notice_clients_respects_page_size(tmp_path, monkeypatch):
    db_path = tmp_path / "clients.db"
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "CRS", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "CRS", "OSHA-1", "01-01-2025", "01-01-2027", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)

    response = client.get(
        "/api/notices/transition_facilitation_2026/clients",
        params={"page": 1, "page_size": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["rows"]) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k notice_clients -v`
Expected: FAIL — the endpoint doesn't exist yet (404 for every request, including the ones expecting 200).

- [ ] **Step 4: Add the endpoint**

Add to `dashboard-app/backend/main.py`, immediately after `notice_eligible_count` (find `def notice_eligible_count(...)` and its closing `}` return, and add this right after):

```python
@app.get("/api/notices/{notice_id}/clients", dependencies=[Depends(require_auth)])
def notice_clients(
    notice_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=500),
    status: str = "", cert_type: str = "", expiry_before: str = "", search: str = "", scheme: str = "",
):
    if get_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown notice_id: {notice_id}")
    rows, total = get_broadcast_clients_page(
        DEFAULT_DB_PATH, notice_id, page=page, page_size=page_size,
        status=status or None, cert_type=cert_type or None, expiry_before=expiry_before or None,
        search=search or None, scheme=scheme or None,
    )
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k notice_clients -v`
Expected: all passed.

- [ ] **Step 6: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 7: Restart the backend manually and verify live (read-only)**

`--reload` has proven unreliable in this environment. Stop whatever backend process is running and start fresh without it:

```bash
cd dashboard-app/backend
python -m uvicorn main:app --port 8040
```

Confirm the new process's start time is after this task's edits, then verify read-only:

```bash
python -c "
import requests
r = requests.get('http://127.0.0.1:8040/api/notices/transition_facilitation_2026/clients', params={'page': 1, 'page_size': 5})
print(r.status_code, r.json()['total'], len(r.json()['rows']))
"
```

Expected: `200`, a total matching your real roster's CRS/notice-eligible population, and up to 5 rows.

- [ ] **Step 8: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: add /api/notices/{notice_id}/clients endpoint"
```

---

### Task 3: Frontend — `getNoticeClients` + `NoticeClientsTable.jsx`

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`
- Create: `dashboard-app/frontend/src/components/NoticeClientsTable.jsx`
- Create: `dashboard-app/frontend/src/components/NoticeClientsTable.test.jsx`

- [ ] **Step 1: Write the failing test for `getNoticeClients`**

Add to `dashboard-app/frontend/src/api.test.js`, immediately after the `getNoticeEligibleCount` describe block:

```javascript
describe("getNoticeClients", () => {
  it("passes pagination and filters as query params", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 8 }),
    });
    const result = await getNoticeClients("transition_facilitation_2026", { page: 1, pageSize: 8, scheme: "CRS" });
    expect(result).toEqual({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 8 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/clients?page=1&page_size=8&scheme=CRS",
      { credentials: "include", headers: {} }
    );
  });
});
```

Add `getNoticeClients` to the file's existing `import { ... } from "./api"` line.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js -t getNoticeClients`
Expected: FAIL — `getNoticeClients` doesn't exist in `api.js` yet.

- [ ] **Step 3: Add `getNoticeClients` to `api.js`**

Add to `dashboard-app/frontend/src/api.js`, immediately after `getNoticeEligibleCount`:

```javascript
export async function getNoticeClients(noticeId, params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.scheme && params.scheme !== "ALL") query.set("scheme", params.scheme);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  const qs = query.toString();
  const url = `/api/notices/${noticeId}/clients${qs ? `?${qs}` : ""}`;
  const res = await fetch(`${API_BASE}${url}`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load notice clients: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all passed.

- [ ] **Step 5: Write the failing tests for `NoticeClientsTable`**

Create `dashboard-app/frontend/src/components/NoticeClientsTable.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import NoticeClientsTable from "./NoticeClientsTable";

const pageOf = (rows, total = rows.length, page = 1) => ({ rows, total, page, page_size: 2 });

const clients = [
  {
    client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
    phone: "919876543210", notice_sent_whatsapp: true, notice_sent_email: false,
  },
  {
    client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", email: null,
    phone: "919812345678", notice_sent_whatsapp: false, notice_sent_email: false,
  },
];

describe("NoticeClientsTable", () => {
  it("renders each client's identity and contact info", () => {
    render(<NoticeClientsTable page={pageOf(clients)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.getByText("TechCorp")).toBeInTheDocument();
    expect(screen.getByText("919876543210")).toBeInTheDocument();
  });

  it("shows an em dash for a missing email", () => {
    render(<NoticeClientsTable page={pageOf(clients)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows Sent for a client already notified via that channel, Not yet otherwise", () => {
    render(<NoticeClientsTable page={pageOf([clients[0]])} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText("Sent")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
  });

  it("shows the total row count from the server, not just the rendered page", () => {
    render(<NoticeClientsTable page={pageOf(clients, 137, 1)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText(/of 137 clients/)).toBeInTheDocument();
  });

  it("calls onPageChange with the next page when Next is clicked", () => {
    const onPageChange = vi.fn();
    render(<NoticeClientsTable page={pageOf(clients, 10, 1)} loading={false} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("disables Previous on the first page", () => {
    render(<NoticeClientsTable page={pageOf(clients, 10, 1)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });

  it("shows a loading message while loading and no rows are cached yet", () => {
    render(<NoticeClientsTable page={pageOf([])} loading={true} onPageChange={() => {}} />);
    expect(screen.getByText("Loading clients…")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/NoticeClientsTable.test.jsx`
Expected: FAIL — `NoticeClientsTable.jsx` doesn't exist yet.

- [ ] **Step 7: Create `NoticeClientsTable.jsx`**

Create `dashboard-app/frontend/src/components/NoticeClientsTable.jsx`:

```jsx
function StatusBadge({ sent }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line ${
        sent ? "text-status-good" : "text-ink-muted"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${sent ? "bg-status-good" : "bg-ink-muted"}`} aria-hidden="true" />
      {sent ? "Sent" : "Not yet"}
    </span>
  );
}

export default function NoticeClientsTable({ page, loading, onPageChange }) {
  const { rows, total, page: currentPage, page_size: pageSize } = page;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const start = (currentPage - 1) * pageSize;
  const isEmptyLoading = loading && rows.length === 0;

  return (
    <div className="bg-surface rounded-xl border border-line overflow-hidden">
      <table className="w-full" data-testid="notice-clients-table">
        <thead>
          <tr className="bg-surface-page text-xs uppercase tracking-wide text-ink-secondary border-b-2 border-line">
            <th className="px-3 py-2 text-left font-semibold">Client ID</th>
            <th className="px-3 py-2 text-left font-semibold">Full Name</th>
            <th className="px-3 py-2 text-left font-semibold">Company</th>
            <th className="px-3 py-2 text-left font-semibold">Email</th>
            <th className="px-3 py-2 text-left font-semibold">Phone</th>
            <th className="px-3 py-2 text-left font-semibold">WhatsApp</th>
            <th className="px-3 py-2 text-left font-semibold">Email Sent</th>
          </tr>
        </thead>
        <tbody>
          {isEmptyLoading && (
            <tr>
              <td colSpan={7} className="px-3 py-10 text-center text-ink-secondary">
                Loading clients…
              </td>
            </tr>
          )}
          {rows.map((c) => (
            <tr key={c.client_id} className="border-b border-line text-sm text-ink-primary hover:bg-surface-page transition-colors">
              <td className="px-3 py-2">{c.client_id}</td>
              <td className="px-3 py-2">{c.name}</td>
              <td className="px-3 py-2">{c.company}</td>
              <td className="px-3 py-2">{c.email || "—"}</td>
              <td className="px-3 py-2 tabular-nums">{c.phone || "—"}</td>
              <td className="px-3 py-2"><StatusBadge sent={c.notice_sent_whatsapp} /></td>
              <td className="px-3 py-2"><StatusBadge sent={c.notice_sent_email} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="px-4 py-3 border-t border-line flex items-center justify-between">
        <p className="text-sm text-ink-secondary">
          {isEmptyLoading
            ? ""
            : total === 0
            ? "Showing 0 of 0 clients"
            : `Showing ${start + 1}–${Math.min(start + pageSize, total)} of ${total} clients`}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            disabled={currentPage <= 1}
            aria-label="Previous page"
            className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
            disabled={currentPage >= pageCount}
            aria-label="Next page"
            className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/NoticeClientsTable.test.jsx`
Expected: all passed.

- [ ] **Step 9: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed.

- [ ] **Step 10: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js dashboard-app/frontend/src/components/NoticeClientsTable.jsx dashboard-app/frontend/src/components/NoticeClientsTable.test.jsx
git commit -m "feat: add getNoticeClients API function and the NoticeClientsTable component"
```

---

### Task 4: Wire `NoticeClientsTable` into `NoticesView.jsx`

**Files:**
- Modify: `dashboard-app/frontend/src/components/NoticesView.jsx`
- Modify: `dashboard-app/frontend/src/components/NoticesView.test.jsx`

- [ ] **Step 1: Add `getNoticeClients` to the existing tests' default mocked props**

Current (`dashboard-app/frontend/src/components/NoticesView.test.jsx`):

```jsx
function setup(overrides = {}) {
  const props = {
    listNotices: vi.fn().mockResolvedValue([
      { id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" },
    ]),
    getNoticeEligibleCount: vi.fn().mockResolvedValue({ whatsapp: 3, email: 3 }),
    sendNotice: vi.fn().mockResolvedValue({ job_id: "job-1" }),
    getNoticeSendStatus: vi.fn().mockResolvedValue({
      total: 3, sent: 3, skipped: 0, failed: 0, done: true,
    }),
    getNoticePreview: vi.fn().mockResolvedValue({ subject: "Test Subject", html: "<p>Test</p>" }),
    ...overrides,
  };
  return { ...render(<NoticesView {...props} />), props };
}
```

Replace with:

```jsx
function setup(overrides = {}) {
  const props = {
    listNotices: vi.fn().mockResolvedValue([
      { id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" },
    ]),
    getNoticeEligibleCount: vi.fn().mockResolvedValue({ whatsapp: 3, email: 3 }),
    sendNotice: vi.fn().mockResolvedValue({ job_id: "job-1" }),
    getNoticeSendStatus: vi.fn().mockResolvedValue({
      total: 3, sent: 3, skipped: 0, failed: 0, done: true,
    }),
    getNoticePreview: vi.fn().mockResolvedValue({ subject: "Test Subject", html: "<p>Test</p>" }),
    getNoticeClients: vi.fn().mockResolvedValue({ rows: [], total: 0, page: 1, page_size: 8 }),
    ...overrides,
  };
  return { ...render(<NoticesView {...props} />), props };
}
```

(Without this, every existing test that selects a notice would now throw, since `NoticesView` will call `getNoticeClients` whenever a notice is selected and the prop would be `undefined`.)

- [ ] **Step 2: Write the new failing tests**

Add to `dashboard-app/frontend/src/components/NoticesView.test.jsx`, immediately after `it("does not show an eligible count before a notice is selected", ...)`:

```jsx
  it("fetches the client list once a notice is selected", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(props.getNoticeClients).toHaveBeenCalledWith(
      "transition_facilitation_2026", expect.objectContaining({ page: 1, pageSize: 8, scheme: "ALL" })
    ));
  });

  it("renders the client list once loaded", async () => {
    setup({
      getNoticeClients: vi.fn().mockResolvedValue({
        rows: [{
          client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "r@x.com",
          phone: "919876543210", notice_sent_whatsapp: false, notice_sent_email: false,
        }],
        total: 1, page: 1, page_size: 8,
      }),
    });
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(screen.getByText("Rahul Sharma")).toBeInTheDocument());
  });

  it("does not show the client list before a notice is selected", async () => {
    setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    expect(screen.queryByTestId("notice-clients-table")).not.toBeInTheDocument();
  });
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/NoticesView.test.jsx`
Expected: the three new tests FAIL (the client list isn't wired in yet); the rest still pass thanks to Step 1's default mock.

- [ ] **Step 4: Wire the table into `NoticesView.jsx`**

Current (`dashboard-app/frontend/src/components/NoticesView.jsx`):

```jsx
import { useEffect, useRef, useState } from "react";
import ClientDataFilters from "./ClientDataFilters";
import SendAllConfirmModal from "./SendAllConfirmModal";
import EmailPreviewModal from "./EmailPreviewModal";

const JOB_POLL_MS = 500;

export default function NoticesView({
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  schemeOptions = [],
}) {
  const [notices, setNotices] = useState([]);
  const [selectedNoticeId, setSelectedNoticeId] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [certType, setCertType] = useState("ALL");
  const [scheme, setScheme] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
  const [eligibleCount, setEligibleCount] = useState({ whatsapp: 0, email: 0 });
  const [whatsappModalOpen, setWhatsappModalOpen] = useState(false);
  const [whatsappJob, setWhatsappJob] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailJob, setEmailJob] = useState(null);
  const [error, setError] = useState(null);
  const jobPollRef = useRef(null);

  useEffect(() => {
    listNotices().then(setNotices).catch((err) => setError(err.message));
  }, [listNotices]);

  useEffect(() => {
    if (!selectedNoticeId) return;
    getNoticeEligibleCount(selectedNoticeId, { status, certType, scheme, expiryBefore })
      .then(setEligibleCount)
      .catch(() => {});
  }, [selectedNoticeId, status, certType, scheme, expiryBefore, getNoticeEligibleCount]);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);
```

Replace with:

```jsx
import { useEffect, useRef, useState } from "react";
import ClientDataFilters from "./ClientDataFilters";
import SendAllConfirmModal from "./SendAllConfirmModal";
import EmailPreviewModal from "./EmailPreviewModal";
import NoticeClientsTable from "./NoticeClientsTable";

const JOB_POLL_MS = 500;

export default function NoticesView({
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  getNoticeClients, schemeOptions = [],
}) {
  const [notices, setNotices] = useState([]);
  const [selectedNoticeId, setSelectedNoticeId] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [certType, setCertType] = useState("ALL");
  const [scheme, setScheme] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
  const [eligibleCount, setEligibleCount] = useState({ whatsapp: 0, email: 0 });
  const [clientsPageNum, setClientsPageNum] = useState(1);
  const [clientsPage, setClientsPage] = useState({ rows: [], total: 0, page: 1, page_size: 8 });
  const [clientsLoading, setClientsLoading] = useState(false);
  const [whatsappModalOpen, setWhatsappModalOpen] = useState(false);
  const [whatsappJob, setWhatsappJob] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailJob, setEmailJob] = useState(null);
  const [error, setError] = useState(null);
  const jobPollRef = useRef(null);

  useEffect(() => {
    listNotices().then(setNotices).catch((err) => setError(err.message));
  }, [listNotices]);

  useEffect(() => {
    if (!selectedNoticeId) return;
    getNoticeEligibleCount(selectedNoticeId, { status, certType, scheme, expiryBefore })
      .then(setEligibleCount)
      .catch(() => {});
  }, [selectedNoticeId, status, certType, scheme, expiryBefore, getNoticeEligibleCount]);

  useEffect(() => {
    setClientsPageNum(1);
  }, [selectedNoticeId, status, certType, scheme, expiryBefore]);

  useEffect(() => {
    if (!selectedNoticeId) {
      setClientsPage({ rows: [], total: 0, page: 1, page_size: 8 });
      return;
    }
    setClientsLoading(true);
    getNoticeClients(selectedNoticeId, {
      page: clientsPageNum, pageSize: 8, status, certType, scheme, expiryBefore,
    })
      .then(setClientsPage)
      .catch(() => {})
      .finally(() => setClientsLoading(false));
  }, [selectedNoticeId, clientsPageNum, status, certType, scheme, expiryBefore, getNoticeClients]);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);
```

- [ ] **Step 5: Render the table**

Current:

```jsx
      {selectedNoticeId && (
        <p className="text-sm text-ink-secondary">
          {eligibleCount.whatsapp} client{eligibleCount.whatsapp === 1 ? "" : "s"} matching your filters haven't received this via WhatsApp,{" "}
          {eligibleCount.email} client{eligibleCount.email === 1 ? "" : "s"} via Email.
        </p>
      )}

      <div className="flex items-center gap-3">
```

Replace with:

```jsx
      {selectedNoticeId && (
        <p className="text-sm text-ink-secondary">
          {eligibleCount.whatsapp} client{eligibleCount.whatsapp === 1 ? "" : "s"} matching your filters haven't received this via WhatsApp,{" "}
          {eligibleCount.email} client{eligibleCount.email === 1 ? "" : "s"} via Email.
        </p>
      )}

      {selectedNoticeId && (
        <NoticeClientsTable page={clientsPage} loading={clientsLoading} onPageChange={setClientsPageNum} />
      )}

      <div className="flex items-center gap-3">
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/NoticesView.test.jsx`
Expected: all passed.

- [ ] **Step 7: Wire `getNoticeClients` through `App.jsx`**

Current (`dashboard-app/frontend/src/App.jsx`):

```javascript
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
} from "./api";
```

Replace with:

```javascript
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  getNoticeClients,
} from "./api";
```

Current:

```javascript
              getNoticeSendStatus={getNoticeSendStatus}
              getNoticePreview={getNoticePreview}
              schemeOptions={schemeOptions}
            />
```

Replace with:

```javascript
              getNoticeSendStatus={getNoticeSendStatus}
              getNoticePreview={getNoticePreview}
              getNoticeClients={getNoticeClients}
              schemeOptions={schemeOptions}
            />
```

- [ ] **Step 8: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed.

- [ ] **Step 9: Commit**

```bash
git add dashboard-app/frontend/src/components/NoticesView.jsx dashboard-app/frontend/src/components/NoticesView.test.jsx dashboard-app/frontend/src/App.jsx
git commit -m "feat: show the client list on the Notices page"
```

---

### Task 5: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all passed.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed.

- [ ] **Step 3: Manual browser check**

Open the Notices page, select "Transition Facilitation Order 2026", and set Scheme = CRS. Confirm:
1. The eligible-count text and the new client table both appear below the filters.
2. The table shows real client rows (Client ID, Name, Company, Email, Phone) with "Sent via WhatsApp"/"Sent via Email" badges — all "Not yet" if this notice hasn't been sent to anyone yet.
3. Previous/Next pagination works and the "Showing X–Y of Z" text updates correctly.
4. Changing a filter (e.g. clearing the Scheme filter) refetches both the count and the table, resetting to page 1.
