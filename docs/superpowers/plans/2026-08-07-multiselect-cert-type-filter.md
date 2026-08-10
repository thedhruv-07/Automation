# Multi-Select IS-Number (Cert Type) Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the cert-type ("IS number") filter from single-select to multi-select on both the Client Data page and the Notices page, and wire up real cert-type options on the Notices page for the first time (currently hardcoded to an empty list there).

**Architecture:** `certType` state changes from a string (`"ALL"` default) to an array (`[]` default) everywhere it's used. A new `MultiSelectDropdown` component (searchable checkbox list) replaces the native `<select>` for cert type in `ClientDataFilters.jsx`. The backend's single shared filter builder, `db.py`'s `_client_filters_query()`, switches from an exact `cert_name` match to a `$in` match — every read function that already routes through it (`get_clients_page`, `export_clients_rows`, `get_eligible_clients`, `get_broadcast_clients`, `get_eligible_count`, `get_notice_eligible_count`, `get_broadcast_clients_page`) gets the new behavior with no changes of their own. `main.py`'s ~9 route handlers switch their `cert_type` query param from `str` to `list[str] = Query([])`, FastAPI's native way of collecting repeated `cert_type=A&cert_type=B` query params.

**Tech Stack:** FastAPI (`Query`), MongoDB `$in`, React, Vitest/Testing Library, pytest/mongomock.

---

### Task 1: Backend — `$in` support in the shared filter builder

**Files:**
- Modify: `dashboard-app/backend/db.py:169-192` (`_client_filters_query`)
- Modify: `dashboard-app/backend/db.py` (type hints at lines 210, 292, 303, 318, 332, 365, 382 — all `cert_type: str | None = None` → `cert_type: list[str] | None = None`)
- Modify: `dashboard-app/backend/test_db.py` (5 existing call sites + new tests)

- [ ] **Step 1: Update `_client_filters_query`'s signature and logic**

Replace `dashboard-app/backend/db.py:169-192`:

```python
def _client_filters_query(
    status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> dict:
    """Builds the MongoDB filter dict shared by get_clients_page,
    export_clients_rows, get_eligible_clients, get_broadcast_clients, and
    the eligible-count functions -- so "currently filtered view" always
    means the same thing everywhere it's used."""
    query: dict = {}
    if status and status != "ALL":
        query["status"] = status
    # Defensive: a stale client or a direct API call could still send the
    # old single-value sentinel ("ALL") or blank strings inside the list --
    # both must mean "no filter", not a literal cert_name match.
    cert_type = [c for c in (cert_type or []) if c and c != "ALL"]
    if cert_type:
        query["cert_name"] = {"$in": cert_type}
    if scheme and scheme != "ALL":
        query["scheme"] = scheme
    if expiry_before:
        query["expiry_date_iso"] = {"$lte": expiry_before}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"company": {"$regex": search, "$options": "i"}},
        ]
    return query
```

- [ ] **Step 2: Update the remaining `cert_type` type hints in `db.py` for consistency**

Each of these lines currently reads `cert_type: str | None = None,` — change each to `cert_type: list[str] | None = None,`. No other change on these lines; they already just forward `cert_type` positionally into `_client_filters_query`, which is untyped-safe in Python either way, but the hints should stay accurate:
- Line 210 (`get_clients_page`)
- Line 292 (`export_clients_rows`)
- Line 303 (`get_eligible_clients`)
- Line 318 (`get_broadcast_clients`)
- Line 332 (`get_broadcast_clients_page`)
- Line 365 (`_count_eligible_excluding_recent`)
- Line 382 (`get_eligible_count`, `get_notice_eligible_count` — check both nearby signatures at this line range and update each `cert_type: str | None = None` found)

Run: `grep -n "cert_type: str | None" dashboard-app/backend/db.py`
Expected: no output (all converted to `list[str] | None`).

- [ ] **Step 3: Update the 5 existing test_db.py call sites from a string to a single-item list**

In `dashboard-app/backend/test_db.py`, change each of these from `cert_type="ISO 9001"` to `cert_type=["ISO 9001"]` (same test intent, just matching the new parameter type — a plain string would now iterate character-by-character since `_client_filters_query` treats its input as an iterable of values, silently breaking these tests):

```python
# line 211, inside test_get_clients_page_filters_by_cert_type
rows, total = get_clients_page(mongo_db, page=1, page_size=50, cert_type=["ISO 9001"])
```
```python
# line 300, inside test_export_clients_rows_yields_all_matching_rows_no_pagination
rows = list(export_clients_rows(mongo_db, cert_type=["ISO 9001"]))
```
```python
# line 402, inside test_get_eligible_clients_filters_by_cert_type
rows = get_eligible_clients(mongo_db, cert_type=["ISO 9001"])
```
```python
# line 470, inside test_get_eligible_count_filters_by_cert_type
assert get_eligible_count(mongo_db, today="2026-07-21", channel="whatsapp", cert_type=["ISO 9001"]) == 2
```

- [ ] **Step 4: Write new failing tests for `$in` (OR-match) behavior**

Add to `dashboard-app/backend/test_db.py`, right after `test_get_clients_page_filters_by_cert_type` (uses the existing `FIVE_ROWS` fixture: CLT002 has `cert_name="OSHA"`, CLT004 has `cert_name="GMP"`):

```python
def test_get_clients_page_filters_by_multiple_cert_types(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, cert_type=["OSHA", "GMP"])
    assert total == 2
    assert {r["client_id"] for r in rows} == {"CLT002", "CLT004"}


def test_get_clients_page_cert_type_empty_list_means_no_filter(mongo_db):
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, cert_type=[])
    assert total == 5


def test_get_clients_page_cert_type_all_sentinel_means_no_filter(mongo_db):
    """A stale client or a direct API call could still send the old
    single-value sentinel wrapped in a list -- must not be treated as a
    literal cert_name match."""
    _seeded_db(mongo_db)
    rows, total = get_clients_page(mongo_db, page=1, page_size=50, cert_type=["ALL"])
    assert total == 5
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_db.py -q -k cert_type`
Expected: all pass (existing 5 updated + 3 new = 8 tests matching `cert_type` in their name, though the exact count depends on naming — confirm no failures either way with `python -m pytest test_db.py -q`).

- [ ] **Step 6: Run the full backend test suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add dashboard-app/backend/db.py dashboard-app/backend/test_db.py
git commit -m "feat: support multiple cert types (OR match) in the shared client filter

_client_filters_query is the single builder every filtered read routes
through, so switching its cert_type handling from an exact match to \$in
gives multi-select filtering to every caller (client list, export,
eligible counts, broadcast/notice clients) with no changes of their own."
```

---

### Task 2: Backend — route handlers accept repeated `cert_type` query params

**Files:**
- Modify: `dashboard-app/backend/main.py` (9 route handlers)
- Modify: `dashboard-app/backend/test_main.py` (new integration test)

- [ ] **Step 1: Update each route handler's `cert_type` parameter**

`Query` is already imported in `main.py` (`from fastapi import FastAPI, Form, HTTPException, File, Query, UploadFile`). In each of the following handlers, change the `cert_type` parameter from a string default (`"ALL"` or `""`) to `cert_type: list[str] = Query([])`, and remove any `cert_type or None` conversion at its call site in the same function (an empty list is already falsy/handled correctly by `_client_filters_query`, so pass `cert_type` straight through):

**`get_clients` (`/api/clients`), line ~116-128:**
```python
@app.get("/api/clients")
def get_clients(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    status: str = "ALL", cert_type: list[str] = Query([]), scheme: str = "ALL",
    expiry_before: str = "", search: str = "", sort_key: str = "", sort_dir: str = "asc",
):
    today = _today_str()
    rows, total = get_clients_page(
        DEFAULT_DB_PATH, page=page, page_size=page_size,
        status=status, cert_type=cert_type, scheme=scheme, expiry_before=expiry_before or None,
        search=search or None, sort_key=sort_key or None, sort_dir=sort_dir.lower(),
    )
```

**`eligible_count` (`/api/eligible-count`), line ~144-160:**
```python
@app.get("/api/eligible-count")
def eligible_count(
    status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "", search: str = "", scheme: str = "",
):
    today = _today_str()
    return {
        "whatsapp": get_eligible_count(
            DEFAULT_DB_PATH, today, "whatsapp",
            status=status or None, cert_type=cert_type, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
        "email": get_eligible_count(
            DEFAULT_DB_PATH, today, "email",
            status=status or None, cert_type=cert_type, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
    }
```

**`export_clients` (`/api/clients/export`), line ~172-181:**
```python
@app.get("/api/clients/export")
def export_clients(
    status: str = "ALL", cert_type: list[str] = Query([]), expiry_before: str = "", search: str = "", scheme: str = "ALL",
):
    def generate():
        yield ",".join(_csv_escape(h) for h in REQUIRED_HEADERS) + "\n"
        for rec in export_clients_rows(
            DEFAULT_DB_PATH, status=status, cert_type=cert_type, scheme=scheme,
            expiry_before=expiry_before or None, search=search or None,
        ):
```

**`send_all_alerts` (`/api/send-all`), line ~352-381 — only the signature and the `cert_type or None` in the thread args change:**
```python
@app.post("/api/send-all")
def send_all_alerts(
    status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "", search: str = "", scheme: str = "",
):
    ...
        thread = threading.Thread(
            target=_run_send_all_job,
            args=(
                job_id, token, phone_number_id, test_number,
                status or None, cert_type, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
```

**`send_all_emails` (`/api/send-all-emails`), line ~493-522 — same shape as above:**
```python
@app.post("/api/send-all-emails")
def send_all_emails(
    status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "", search: str = "", scheme: str = "",
):
    ...
        thread = threading.Thread(
            target=_run_send_all_email_job,
            args=(
                job_id, brevo_api_key, email_sender, test_email,
                status or None, cert_type, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
```

**`notice_eligible_count` (`/api/notices/{notice_id}/eligible-count`), line ~561-579:**
```python
@app.get("/api/notices/{notice_id}/eligible-count")
def notice_eligible_count(
    notice_id: str, status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "",
    search: str = "", scheme: str = "",
):
    if get_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown notice_id: {notice_id}")
    return {
        "whatsapp": get_notice_eligible_count(
            DEFAULT_DB_PATH, notice_id, "whatsapp",
            status=status or None, cert_type=cert_type, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
        "email": get_notice_eligible_count(
            DEFAULT_DB_PATH, notice_id, "email",
            status=status or None, cert_type=cert_type, expiry_before=expiry_before or None,
            search=search or None, scheme=scheme or None,
        ),
    }
```

**`notice_clients` (`/api/notices/{notice_id}/clients`), line ~582-596:**
```python
@app.get("/api/notices/{notice_id}/clients")
def notice_clients(
    notice_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=8, ge=1, le=500),
    status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "", search: str = "", scheme: str = "",
):
    if get_notice_module(notice_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown notice_id: {notice_id}")
    rows, total = get_broadcast_clients_page(
        DEFAULT_DB_PATH, notice_id, page=page, page_size=page_size,
        status=status or None, cert_type=cert_type, expiry_before=expiry_before or None,
        search=search or None, scheme=scheme or None,
    )
    return {"rows": rows, "total": total, "page": page, "page_size": page_size}
```

**`send_notice_whatsapp_endpoint` (`/api/notices/{notice_id}/send-whatsapp`), line ~632-661:**
```python
@app.post("/api/notices/{notice_id}/send-whatsapp")
def send_notice_whatsapp_endpoint(
    notice_id: str, status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "",
    search: str = "", scheme: str = "",
):
    ...
        thread = threading.Thread(
            target=_run_send_notice_whatsapp_job,
            args=(
                job_id, notice_id, lock_key, token, phone_number_id, test_number,
                status or None, cert_type, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
```

**`send_notice_email_endpoint` (`/api/notices/{notice_id}/send-email`), line ~713-742:**
```python
@app.post("/api/notices/{notice_id}/send-email")
def send_notice_email_endpoint(
    notice_id: str, status: str = "", cert_type: list[str] = Query([]), expiry_before: str = "",
    search: str = "", scheme: str = "",
):
    ...
        thread = threading.Thread(
            target=_run_send_notice_email_job,
            args=(
                job_id, notice_id, lock_key, brevo_api_key, email_sender, test_email,
                status or None, cert_type, expiry_before or None, search or None, scheme or None,
            ),
            daemon=True,
        )
```

The internal `_run_send_all_job`, `_run_send_all_email_job`, `_run_send_notice_whatsapp_job`, `_run_send_notice_email_job` helper functions need no changes — they already accept `cert_type=None` untyped and forward it straight through to `run`/`run_email_alerts`/`send_notice_whatsapp`/`send_notice_email`, all of which forward it straight through again into the `db.py` functions from Task 1.

- [ ] **Step 2: Write a new integration test confirming multiple `cert_type` values work at the route level**

Add to `dashboard-app/backend/test_main.py`, directly after `test_eligible_count_filters_by_cert_type` (~line 142-154), matching that test's exact fixture pattern (`_write_db`, `monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)`/`"_today_str"`, and the module-level `client`):

```python
def test_eligible_count_filters_by_multiple_cert_types(tmp_path, monkeypatch, mongo_db):
    db_path = mongo_db
    _write_db(db_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISI", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "ISI", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISI", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(main_module, "_today_str", lambda: "2026-07-18")

    # httpx's TestClient expands a list value in `params` into repeated
    # query params (cert_type=ISO+9001&cert_type=OSHA), matching what the
    # real frontend sends.
    response = client.get("/api/eligible-count", params={"cert_type": ["ISO 9001", "OSHA"]})
    assert response.json() == {"whatsapp": 2, "email": 2}
```

- [ ] **Step 3: Run the backend test suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "feat: accept repeated cert_type query params across all filtered routes

Switches cert_type from a single str to list[str] = Query([]) on every
route handler that takes it, FastAPI's native way of collecting repeated
cert_type=A&cert_type=B query params. Each handler already just forwards
cert_type through to db.py, which now does an \$in match (previous commit)."
```

---

### Task 3: Frontend — `MultiSelectDropdown` component

**Files:**
- Create: `dashboard-app/frontend/src/components/MultiSelectDropdown.jsx`
- Create: `dashboard-app/frontend/src/components/MultiSelectDropdown.test.jsx`

- [ ] **Step 1: Write the component**

```jsx
import { useEffect, useRef, useState } from "react";

export default function MultiSelectDropdown({
  options, selected, onChange, label, ariaLabel,
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  const filteredOptions = options.filter((o) =>
    o.toLowerCase().includes(search.toLowerCase())
  );

  function toggle(option) {
    if (selected.includes(option)) {
      onChange(selected.filter((s) => s !== option));
    } else {
      onChange([...selected, option]);
    }
  }

  const buttonLabel = selected.length === 0 ? label : `${selected.length} selected`;

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={ariaLabel}
        aria-expanded={open}
        className="min-w-[180px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary text-left focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        {buttonLabel}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 w-64 bg-surface border border-line rounded-lg shadow-lg p-2">
          <div className="flex items-center justify-between gap-2 mb-2">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search..."
              aria-label={`Search ${ariaLabel}`}
              className="flex-1 bg-surface-page border border-line rounded-lg px-2 py-1 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
            {selected.length > 0 && (
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-xs font-semibold text-accent hover:underline whitespace-nowrap"
              >
                Clear
              </button>
            )}
          </div>
          <div className="max-h-56 overflow-y-auto space-y-1">
            {filteredOptions.length === 0 && (
              <p className="text-sm text-ink-secondary px-1 py-1">No matches</p>
            )}
            {filteredOptions.map((option) => (
              <label
                key={option}
                className="flex items-center gap-2 px-1 py-1 text-sm text-ink-primary hover:bg-surface-page rounded cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={() => toggle(option)}
                />
                {option}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write the component's tests**

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import MultiSelectDropdown from "./MultiSelectDropdown";

const OPTIONS = ["ISO 9001", "OSHA", "GMP"];

describe("MultiSelectDropdown", () => {
  it("shows the label when nothing is selected", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    expect(screen.getByLabelText("Filter by certification type")).toHaveTextContent("All Cert Types");
  });

  it("shows a count when items are selected", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA", "GMP"]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    expect(screen.getByLabelText("Filter by certification type")).toHaveTextContent("2 selected");
  });

  it("opens the panel and lists all options on click", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    expect(screen.getByText("OSHA")).toBeInTheDocument();
    expect(screen.getByText("GMP")).toBeInTheDocument();
  });

  it("filters the option list by the search box", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.change(screen.getByLabelText("Search Filter by certification type"), { target: { value: "osh" } });
    expect(screen.getByText("OSHA")).toBeInTheDocument();
    expect(screen.queryByText("ISO 9001")).not.toBeInTheDocument();
  });

  it("calls onChange with the option added when an unselected checkbox is clicked", () => {
    const onChange = vi.fn();
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA"]} onChange={onChange} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("GMP"));
    expect(onChange).toHaveBeenCalledWith(["OSHA", "GMP"]);
  });

  it("calls onChange with the option removed when a selected checkbox is clicked", () => {
    const onChange = vi.fn();
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA", "GMP"]} onChange={onChange} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("OSHA"));
    expect(onChange).toHaveBeenCalledWith(["GMP"]);
  });

  it("calls onChange with an empty array when Clear is clicked", () => {
    const onChange = vi.fn();
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA", "GMP"]} onChange={onChange} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("Clear"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("closes the panel on outside click", () => {
    render(
      <div>
        <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
        <div data-testid="outside">outside</div>
      </div>
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId("outside"));
    expect(screen.queryByText("ISO 9001")).not.toBeInTheDocument();
  });

  it("closes the panel on Escape", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("ISO 9001")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run the new tests**

Run: `cd dashboard-app/frontend && npx vitest run src/components/MultiSelectDropdown.test.jsx`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard-app/frontend/src/components/MultiSelectDropdown.jsx dashboard-app/frontend/src/components/MultiSelectDropdown.test.jsx
git commit -m "feat: add MultiSelectDropdown component

A searchable checkbox dropdown for picking several items out of a long
list -- built for the cert-type filter, where there are hundreds of IS
standards to choose from."
```

---

### Task 4: Frontend — wire `MultiSelectDropdown` into `ClientDataFilters`

**Files:**
- Modify: `dashboard-app/frontend/src/components/ClientDataFilters.jsx`
- Modify: `dashboard-app/frontend/src/components/ClientDataFilters.test.jsx`

- [ ] **Step 1: Replace the native `<select>` with `MultiSelectDropdown`**

Replace the full contents of `dashboard-app/frontend/src/components/ClientDataFilters.jsx`:

```jsx
import { isoDateMonthsFromToday } from "../sortUtils";
import MultiSelectDropdown from "./MultiSelectDropdown";

const DURATION_PRESETS = [
  { label: "3 months", months: 3 },
  { label: "6 months", months: 6 },
  { label: "1 year", months: 12 },
];

export default function ClientDataFilters({
  certOptions, certType, onCertTypeChange,
  schemeOptions = [], scheme = "ALL", onSchemeChange = () => {},
  expiryBefore, onExpiryBeforeChange, onClearAll,
}) {
  const hasFilters = certType.length > 0 || scheme !== "ALL" || expiryBefore !== "";

  return (
    <div className="bg-surface border border-line rounded-xl p-4 flex flex-wrap gap-4 items-center">
      <span className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
        Filter by
      </span>
      <select
        value={scheme}
        onChange={(e) => onSchemeChange(e.target.value)}
        aria-label="Filter by scheme"
        className="min-w-[150px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
      >
        <option value="ALL">All Schemes</option>
        {schemeOptions.map((s) => (
          <option key={s} value={s}>{s}</option>
        ))}
      </select>
      <MultiSelectDropdown
        options={certOptions}
        selected={certType}
        onChange={onCertTypeChange}
        label="All Cert Types"
        ariaLabel="Filter by certification type"
      />
      <label className="flex items-center gap-2 text-sm text-ink-secondary">
        Expiry before
        <input
          type="date"
          value={expiryBefore}
          onChange={(e) => onExpiryBeforeChange(e.target.value)}
          aria-label="Filter by expiry before date"
          className="bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
      </label>
      <div className="flex items-center gap-1.5">
        {DURATION_PRESETS.map((preset) => (
          <button
            key={preset.label}
            type="button"
            onClick={() => onExpiryBeforeChange(isoDateMonthsFromToday(preset.months))}
            className="px-3 py-1.5 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
          >
            {preset.label}
          </button>
        ))}
      </div>
      {hasFilters && (
        <button
          type="button"
          onClick={onClearAll}
          className="ml-auto text-sm font-semibold text-accent hover:underline"
        >
          Clear All
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update `ClientDataFilters.test.jsx` for array-based `certType`**

Replace the full contents of `dashboard-app/frontend/src/components/ClientDataFilters.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientDataFilters from "./ClientDataFilters";
import { isoDateMonthsFromToday } from "../sortUtils";

describe("ClientDataFilters", () => {
  it("calls onCertTypeChange when a cert type is checked", () => {
    const onCertTypeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={["ISO 9001", "OSHA"]}
        certType={[]}
        onCertTypeChange={onCertTypeChange}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("OSHA"));
    expect(onCertTypeChange).toHaveBeenCalledWith(["OSHA"]);
  });

  it("calls onSchemeChange when a scheme is selected", () => {
    const onSchemeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        schemeOptions={["ISI", "FMCS"]}
        scheme="ALL"
        onSchemeChange={onSchemeChange}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by scheme"), { target: { value: "FMCS" } });
    expect(onSchemeChange).toHaveBeenCalledWith("FMCS");
  });

  it("shows Clear All when a scheme filter is active", () => {
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        schemeOptions={["ISI", "FMCS"]}
        scheme="FMCS"
        onSchemeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.getByText("Clear All")).toBeInTheDocument();
  });

  it("calls onExpiryBeforeChange when the date input changes", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by expiry before date"), { target: { value: "2026-12-31" } });
    expect(onExpiryBeforeChange).toHaveBeenCalledWith("2026-12-31");
  });

  it("calls onExpiryBeforeChange with the correct date when '3 months' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("3 months"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(3));
  });

  it("calls onExpiryBeforeChange with the correct date when '6 months' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("6 months"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(6));
  });

  it("calls onExpiryBeforeChange with the correct date when '1 year' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("1 year"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(12));
  });

  it("only shows Clear All when a filter is active", () => {
    const { rerender } = render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.queryByText("Clear All")).not.toBeInTheDocument();

    rerender(
      <ClientDataFilters
        certOptions={[]}
        certType={["ISO 9001"]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.getByText("Clear All")).toBeInTheDocument();
  });

  it("calls onClearAll when Clear All is clicked", () => {
    const onClearAll = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={["ISO 9001"]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={onClearAll}
      />
    );
    fireEvent.click(screen.getByText("Clear All"));
    expect(onClearAll).toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Run the tests**

Run: `cd dashboard-app/frontend && npx vitest run src/components/ClientDataFilters.test.jsx`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard-app/frontend/src/components/ClientDataFilters.jsx dashboard-app/frontend/src/components/ClientDataFilters.test.jsx
git commit -m "feat: use MultiSelectDropdown for the cert-type filter"
```

---

### Task 5: Frontend — `api.js` sends repeated `cert_type` query params

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Update `getClients`**

In `dashboard-app/frontend/src/api.js`, replace:
```js
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
```
(the one inside `getClients`, ~line 8) with:
```js
  for (const c of params.certType || []) query.append("cert_type", c);
```

- [ ] **Step 2: Update `scopeQueryString`**

Replace, in `scopeQueryString` (~line 63):
```js
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
```
with:
```js
  for (const c of params.certType || []) query.append("cert_type", c);
```

This single change covers every caller of `scopeQueryString`: `sendAllAlerts`, `sendAllEmailAlerts`, `getEligibleCount`, `getNoticeEligibleCount`, and `sendNotice`.

- [ ] **Step 3: Update `clientsExportUrl`**

Replace, in `clientsExportUrl` (~line 133):
```js
  if (certType && certType !== "ALL") query.set("cert_type", certType);
```
with:
```js
  for (const c of certType || []) query.append("cert_type", c);
```

- [ ] **Step 4: Update `getNoticeClients`**

Replace, in `getNoticeClients` (~line 205):
```js
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
```
with:
```js
  for (const c of params.certType || []) query.append("cert_type", c);
```

- [ ] **Step 5: Update the 3 existing api.test.js call sites**

In `dashboard-app/frontend/src/api.test.js`, each of these 3 tests currently passes `certType: "OSHA"` and expects `cert_type=OSHA` in the URL — change the input to `certType: ["OSHA"]` (the expected URL stays identical, since a single-item array still produces one `cert_type=OSHA`):

```js
// ~line 210, inside "adds status/cert_type/expiry_before/search/scheme as query params when given" (sendAllAlerts)
await sendAllAlerts({
  status: "CRITICAL", certType: ["OSHA"], expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
});
```
```js
// ~line 273, same test name for sendAllEmailAlerts
await sendAllEmailAlerts({
  status: "CRITICAL", certType: ["OSHA"], expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
});
```
```js
// ~line 313, same test name for getEligibleCount
await getEligibleCount({
  status: "CRITICAL", certType: ["OSHA"], expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
});
```

- [ ] **Step 6: Add a new test verifying multiple cert types produce repeated query params**

Add to `dashboard-app/frontend/src/api.test.js`, right after the `getEligibleCount` test updated in Step 5:

```js
it("sends multiple cert_type values as repeated query params", async () => {
  global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 1, email: 1 }) });
  await getEligibleCount({ certType: ["OSHA", "GMP"] });
  expect(global.fetch).toHaveBeenCalledWith(
    "/api/eligible-count?cert_type=OSHA&cert_type=GMP",
    { credentials: "include", headers: {} }
  );
});
```

- [ ] **Step 7: Run the tests**

Run: `cd dashboard-app/frontend && npx vitest run src/api.test.js`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "feat: send cert_type as repeated query params for multi-select"
```

---

### Task 6: Frontend — `App.jsx` uses array-based `certType`

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Modify: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Change the state default**

In `dashboard-app/frontend/src/App.jsx:39`, change:
```js
  const [certType, setCertType] = useState("ALL");
```
to:
```js
  const [certType, setCertType] = useState([]);
```

- [ ] **Step 2: Change the clear-all reset**

In `handleClearAllFilters` (~line 127), change:
```js
    setCertType("ALL");
```
to:
```js
    setCertType([]);
```

- [ ] **Step 3: Pass `certOptions` down to `NoticesView`**

In the `NoticesView` render call (~line 445-456), add `certOptions={certOptions}`:
```jsx
          {activeView === "notices" && (

<NoticesView
              listNotices={listNotices}
              getNoticeEligibleCount={getNoticeEligibleCount}
              sendNotice={sendNotice}
              getNoticeSendStatus={getNoticeSendStatus}
              getNoticePreview={getNoticePreview}
              getNoticeClients={getNoticeClients}
              schemeOptions={schemeOptions}
              certOptions={certOptions}
            />
          )}
```

No other change is needed in `App.jsx` — every other `certType` reference (`queryParams`, the eligible-count effect, `handleConfirmSendAll`/`handleConfirmSendAllEmails`'s `filters` objects, `ClientDataFilters`'s props, `ClientTable`'s `exportFilters`) already just passes the `certType` variable through unchanged, and an empty array is exactly what `_client_filters_query` (Task 1) and every `api.js` function (Task 5) now expect as "no filter."

- [ ] **Step 4: Update the 5 existing App.test.jsx assertions**

In `dashboard-app/frontend/src/App.test.jsx`, each of these 5 occurrences currently asserts `certType: "ALL"` as part of an expected default-state API call payload — change each to `certType: []`:
- ~line 185 (`sendAllEmailAlerts` call assertion)
- ~line 370 (`getEligibleCount` call assertion)
- ~line 389 (`getEligibleCount` call assertion, with search term)
- ~line 439 (`sendAllAlerts` call assertion, with status filter)
- ~line 477 (`sendAllAlerts` call assertion, with search term)

Example (~line 183-187):
```js
    await waitFor(() =>
      expect(api.sendAllEmailAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: [], scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
```

Apply the same `certType: "ALL"` → `certType: []` change at each of the other 4 sites, keeping every other field in those assertions unchanged.

- [ ] **Step 5: Run the frontend test suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "feat: use array-based certType state on the Client Data page

Also passes the real cert-type options down to NoticesView, which
previously hardcoded an empty list."
```

---

### Task 7: Frontend — `NoticesView.jsx` uses array-based `certType` and real options

**Files:**
- Modify: `dashboard-app/frontend/src/components/NoticesView.jsx`
- Modify: `dashboard-app/frontend/src/components/NoticesView.test.jsx`

- [ ] **Step 1: Accept a real `certOptions` prop and default `certType` to an array**

In `dashboard-app/frontend/src/components/NoticesView.jsx`, change the function signature (line 9-13):
```jsx
export default function NoticesView({
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  getNoticeClients,
  schemeOptions = [], certOptions = [],
}) {
```

Change the state default (line 17):
```js
  const [certType, setCertType] = useState([]);
```

Change the clear-all reset (line 71, inside `handleClearAllFilters`):
```js
    setCertType([]);
```

Change the `ClientDataFilters` render (line 142-152) to pass the real options through instead of `[]`:
```jsx
      <ClientDataFilters
        certOptions={certOptions}
        certType={certType}
        onCertTypeChange={setCertType}
        schemeOptions={schemeOptions}
        scheme={scheme}
        onSchemeChange={setScheme}
        expiryBefore={expiryBefore}
        onExpiryBeforeChange={setExpiryBefore}
        onClearAll={handleClearAllFilters}
      />
```

No other change is needed — every other `certType` reference in this file (the eligible-count effect, the clients-page effect, `startSend`'s filters object) already just passes the `certType` variable through unchanged.

- [ ] **Step 2: Add new tests for the real `certOptions` wiring**

Add to `dashboard-app/frontend/src/components/NoticesView.test.jsx`, inside the existing `describe("NoticesView", ...)` block, using the file's existing `setup()` helper:

```jsx
  it("passes real cert-type options through to the filter dropdown", async () => {
    setup({ certOptions: ["ISO 9001", "OSHA"] });
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    expect(screen.getByText("OSHA")).toBeInTheDocument();
  });

  it("includes selected cert types in the eligible-count request", async () => {
    const { props } = setup({ certOptions: ["ISO 9001", "OSHA"] });
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("OSHA"));
    await waitFor(() => expect(props.getNoticeEligibleCount).toHaveBeenCalledWith(
      "transition_facilitation_2026", expect.objectContaining({ certType: ["OSHA"] })
    ));
  });
```

- [ ] **Step 3: Run the frontend test suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add dashboard-app/frontend/src/components/NoticesView.jsx dashboard-app/frontend/src/components/NoticesView.test.jsx
git commit -m "feat: wire real cert-type options into the Notices page filter

Previously hardcoded to an empty list, so this filter did nothing there."
```

---

### Task 8: Final verification

**Files:** none modified — verification only.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd dashboard-app/backend && python -m pytest -q`
Expected: all pass.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all pass.

- [ ] **Step 3: Manual smoke test against local dev**

With both local dev servers running (backend on 8040, frontend on its Vite port):
1. Open Client Data — click the cert-type filter, search for a partial IS number, select 2-3 results, confirm the table and export both reflect the OR-matched selection, confirm "Clear All" resets it.
2. Open Notices — confirm the cert-type filter now shows real options (not just "All Cert Types"), select a couple, confirm the eligible-count and client-list update accordingly.
3. Confirm both pages' cert-type dropdown closes on outside-click and Escape, and the closed-state label correctly shows "All Cert Types" vs. "N selected".

Report back: pass/fail on each, and any visual issues (dropdown positioning, overflow) noticed that the design didn't anticipate.
