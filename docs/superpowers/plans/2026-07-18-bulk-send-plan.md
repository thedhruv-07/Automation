# Bulk "Send All Eligible" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click "Send All Eligible" bulk action to the React dashboard, alongside the existing per-client Send Alert button, reusing the CLI script's existing `run()` function for the actual send loop.

**Architecture:** New `POST /api/send-all` backend endpoint calls the already-existing `run()` from `whatsapp_renewal_alerts.py` directly (no new send-loop logic). New `SendAllConfirmModal.jsx` (separate from the existing per-client `SendConfirmModal`) gates it behind confirmation. `App.jsx` gets a new button, state, and a summary toast.

**Tech Stack:** Same as the rest of the dashboard — FastAPI/pytest backend, React/Vitest frontend.

Spec: `docs/superpowers/specs/2026-07-18-bulk-send-design.md`

---

## File Structure

```
cert_automation_scripts/
  dashboard-app/
    backend/
      main.py            (modified — add POST /api/send-all)
      test_main.py        (modified — new tests)
    frontend/
      src/
        api.js             (modified — add sendAllAlerts())
        api.test.js         (modified — new tests)
        App.jsx             (modified — wire in bulk send)
        App.test.jsx        (modified — new tests)
        components/
          SendAllConfirmModal.jsx       (new)
          SendAllConfirmModal.test.jsx  (new)
```

---

### Task 1: `POST /api/send-all` endpoint

**Files:**
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/backend/test_main.py`:

```python
def test_send_all_alerts_success(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
        ["CLT002", "Priya Mehta", "BuildRight", "p@x.com", "919812345678",
         "OSHA", "OSHA-1", "01-01-2025", "11-08-2026", "https://x", "URGENT"],
        ["CLT004", "Sneha Kapoor", "EduTech", "s@x.com", "919765432109",
         "ISO 27001", "ISO27-1", "01-01-2025", "15-10-2026", "https://x", "ACTIVE"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
    monkeypatch.setenv("WHATSAPP_TEMPLATE_LANG", "en")
    monkeypatch.delenv("DASHBOARD_TEST_NUMBER", raising=False)

    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.ABC"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response):
        response = client.post("/api/send-all")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # only CRITICAL/URGENT are alertable; ACTIVE excluded
    actions = {r["client_id"]: r["action"] for r in data}
    assert actions == {"CLT001": "sent", "CLT002": "sent"}


def test_send_all_alerts_uses_test_number_override(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setenv("WHATSAPP_TOKEN", "tok")
    monkeypatch.setenv("PHONE_NUMBER_ID", "pid123")
    monkeypatch.setenv("DASHBOARD_TEST_NUMBER", "919000000000")
    mock_response = type("Resp", (), {
        "status_code": 200,
        "json": lambda self: {"messages": [{"id": "wamid.TEST"}]},
    })()
    with patch("whatsapp_renewal_alerts.requests.post", return_value=mock_response) as mock_post:
        response = client.post("/api/send-all")
    assert response.status_code == 200
    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["to"] == "919000000000"


def test_send_all_alerts_blocks_concurrent_calls(tmp_path, monkeypatch):
    xlsx_path = tmp_path / "clients.xlsx"
    _write_xlsx(xlsx_path, [])
    log_path = tmp_path / "sent_log.json"
    log_path.write_text("{}")
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", xlsx_path)
    monkeypatch.setattr(main_module, "DEFAULT_LOG_PATH", log_path)
    monkeypatch.setattr(main_module, "_bulk_in_progress", True)
    response = client.post("/api/send-all")
    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k send_all -v`
Expected: FAIL — 404, the route doesn't exist yet

- [ ] **Step 3: Implement the endpoint**

In `dashboard-app/backend/main.py`, change this existing import line:

```python
from whatsapp_renewal_alerts import (  # noqa: E402
    read_clients, ALERT_STATUSES, dedup_key, load_sent_log, save_sent_log,
    send_one_alert, DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH,
)
```

to add `run`:

```python
from whatsapp_renewal_alerts import (  # noqa: E402
    read_clients, ALERT_STATUSES, dedup_key, load_sent_log, save_sent_log,
    send_one_alert, run, DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH,
)
```

Add module-level state near the existing `_send_lock`/`_pending_sends` (right after that block):

```python
_bulk_lock = threading.Lock()
_bulk_in_progress = False
```

Add the endpoint. It must come BEFORE the `from fastapi.staticfiles import StaticFiles` / static-mount block at the end of the file (that block must stay last, same reasoning as the existing routes):

```python
@app.post("/api/send-all")
def send_all_alerts():
    global _bulk_in_progress
    with _bulk_lock:
        if _bulk_in_progress:
            raise HTTPException(status_code=409, detail="A bulk send is already in progress")
        _bulk_in_progress = True

    try:
        token = os.environ["WHATSAPP_TOKEN"]
        phone_number_id = os.environ["PHONE_NUMBER_ID"]
        template_name = os.environ.get("WHATSAPP_TEMPLATE_NAME", "cert_renewal_alert")
        template_lang = os.environ.get("WHATSAPP_TEMPLATE_LANG", "en")
        test_number = os.environ.get("DASHBOARD_TEST_NUMBER") or None

        return run(
            DEFAULT_EXCEL_PATH, DEFAULT_LOG_PATH, token, phone_number_id,
            template_name, template_lang, dry_run=False, test_number=test_number,
        )
    finally:
        with _bulk_lock:
            _bulk_in_progress = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: 15 passed (12 existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "Add POST /api/send-all endpoint reusing run() for bulk sending"
```

---

### Task 2: `api.js` — `sendAllAlerts()`

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/frontend/src/api.test.js`:

```js
describe("sendAllAlerts", () => {
  it("returns parsed JSON array on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ client_id: "CLT001", action: "sent" }],
    });
    const result = await sendAllAlerts();
    expect(result).toEqual([{ client_id: "CLT001", action: "sent" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});
```

Add `sendAllAlerts` to the existing import line at the top of the file:
```js
import { getClients, sendAlert, sendAllAlerts } from "./api";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test` (from `dashboard-app/frontend/`)
Expected: FAIL — `sendAllAlerts` is not exported

- [ ] **Step 3: Implement `sendAllAlerts()`**

Add to `dashboard-app/frontend/src/api.js`:

```js
export async function sendAllAlerts() {
  const res = await fetch("/api/send-all", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/api.js dashboard-app/frontend/src/api.test.js
git commit -m "Add sendAllAlerts() to api.js"
```

---

### Task 3: `SendAllConfirmModal` component

**Files:**
- Create: `dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`
- Create: `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SendAllConfirmModal from "./SendAllConfirmModal";

describe("SendAllConfirmModal", () => {
  it("renders nothing when open is false", () => {
    const { container } = render(
      <SendAllConfirmModal open={false} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the eligible count when open", () => {
    render(<SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/eligible clients/)).toBeInTheDocument();
  });

  it("calls onConfirm when Confirm Send All is clicked", () => {
    const onConfirm = vi.fn();
    render(<SendAllConfirmModal open={true} eligibleCount={3} onConfirm={onConfirm} onCancel={() => {}} />);
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(<SendAllConfirmModal open={true} eligibleCount={3} onConfirm={() => {}} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("only calls onConfirm once when Confirm Send All is clicked twice in quick succession", () => {
    const onConfirm = vi.fn();
    render(<SendAllConfirmModal open={true} eligibleCount={3} onConfirm={onConfirm} onCancel={() => {}} />);
    const button = screen.getByText("Confirm Send All");
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test` (from `dashboard-app/frontend/`)
Expected: FAIL — `SendAllConfirmModal.jsx` doesn't exist

- [ ] **Step 3: Implement `SendAllConfirmModal.jsx`**

Create `dashboard-app/frontend/src/components/SendAllConfirmModal.jsx`. This mirrors the existing `SendConfirmModal`'s focus-trap/Escape/double-submit-guard pattern exactly, adapted for an `open`/`eligibleCount` prop shape instead of a single `client`:

```jsx
import { useEffect, useRef, useState } from "react";

export default function SendAllConfirmModal({ open, eligibleCount, onConfirm, onCancel }) {
  const [confirming, setConfirming] = useState(false);
  const cancelButtonRef = useRef(null);
  const confirmButtonRef = useRef(null);

  useEffect(() => {
    if (open) {
      setConfirming(false);
      cancelButtonRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") {
        onCancel();
      } else if (e.key === "Tab") {
        const first = cancelButtonRef.current;
        const last = confirmButtonRef.current;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm();
  }

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50"
      data-testid="send-all-confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="send-all-confirm-title"
    >
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full">
        <h3 id="send-all-confirm-title" className="text-lg font-bold text-slate-800 mb-2">
          Send to all eligible clients?
        </h3>
        <p className="text-sm text-slate-600 mb-6">
          Send a real WhatsApp renewal alert to all <strong>{eligibleCount}</strong> eligible
          client{eligibleCount === 1 ? "" : "s"} (Critical, Urgent, or Due Soon, not yet sent today)?
        </p>
        <div className="flex justify-end gap-3">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200"
          >
            Cancel
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            onClick={handleConfirmClick}
            disabled={confirming}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 disabled:opacity-50"
          >
            Confirm Send All
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/SendAllConfirmModal.jsx dashboard-app/frontend/src/components/SendAllConfirmModal.test.jsx
git commit -m "Add SendAllConfirmModal component"
```

---

### Task 4: Wire bulk send into `App.jsx`, rebuild, and verify

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Modify: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/frontend/src/App.test.jsx`, inside the existing `describe("App", ...)` block (and add `sendAllAlerts` to the existing `import * as api from "./api";`-adjacent mock usage — no import line change needed since `api` is already imported as a namespace):

```jsx
it("does not send-all until the bulk confirmation modal is accepted", async () => {
  render(<App />);
  await waitFor(() => screen.getByText("Send Alert"));
  fireEvent.click(screen.getByText("Send All Eligible"));
  expect(screen.getByTestId("send-all-confirm-modal")).toBeInTheDocument();
  expect(api.sendAllAlerts).not.toHaveBeenCalled();
});

it("sends all and shows a summary toast after confirming", async () => {
  api.sendAllAlerts.mockResolvedValue([
    { client_id: "CLT001", name: "Rahul Sharma", status: "CRITICAL", action: "sent", message_id: "wamid.ABC" },
  ]);
  render(<App />);
  await waitFor(() => screen.getByText("Send Alert"));
  fireEvent.click(screen.getByText("Send All Eligible"));
  fireEvent.click(screen.getByText("Confirm Send All"));
  await waitFor(() => expect(api.sendAllAlerts).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByText("1 sent, 0 already sent, 0 failed")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test` (from `dashboard-app/frontend/`)
Expected: FAIL — no "Send All Eligible" button exists yet

- [ ] **Step 3: Wire it into `App.jsx`**

Change the import line:
```jsx
import { getClients, sendAlert } from "./api";
```
to:
```jsx
import { getClients, sendAlert, sendAllAlerts } from "./api";
```

Add the import for the new modal, alongside the existing component imports:
```jsx
import SendAllConfirmModal from "./components/SendAllConfirmModal";
```

Add a constant near the top of the file (after the imports, before `export default function App()`):
```jsx
const ALERT_ELIGIBLE_STATUSES = new Set(["CRITICAL", "URGENT", "DUE SOON"]);
```

Add new state, alongside the existing `useState` calls:
```jsx
const [bulkModalOpen, setBulkModalOpen] = useState(false);
const [bulkSending, setBulkSending] = useState(false);
```

Add a computed value right before the `return (`:
```jsx
const eligibleCount = clients.filter(
  (c) => ALERT_ELIGIBLE_STATUSES.has(c.status) && !c.alert_sent_today
).length;
```

Add a new handler function, alongside `handleConfirmSend`:
```jsx
async function handleConfirmSendAll() {
  setBulkModalOpen(false);
  setBulkSending(true);
  try {
    const results = await sendAllAlerts();
    const sent = results.filter((r) => r.action === "sent").length;
    const skipped = results.filter((r) => r.action === "skipped_duplicate").length;
    const failed = results.filter((r) => r.action === "failed").length;
    setToast({
      type: failed > 0 ? "error" : "success",
      message: `${sent} sent, ${skipped} already sent, ${failed} failed`,
    });
    loadClients();
  } catch (err) {
    setToast({ type: "error", message: err.message });
  } finally {
    setBulkSending(false);
  }
}
```

In the JSX, add a new button right after the existing Refresh button (inside the same header `<div className="flex items-center justify-between">`):
```jsx
<button
  type="button"
  onClick={() => setBulkModalOpen(true)}
  disabled={bulkSending || eligibleCount === 0}
  className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 disabled:opacity-50"
>
  Send All Eligible
</button>
```
(The header's Refresh button and this new button both live in that same flex row — put this new button immediately after Refresh, still inside the same wrapping `<div>`.)

Add the new modal near the existing `SendConfirmModal`/`Toast`:
```jsx
<SendAllConfirmModal
  open={bulkModalOpen}
  eligibleCount={eligibleCount}
  onConfirm={handleConfirmSendAll}
  onCancel={() => setBulkModalOpen(false)}
/>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed (every component suite + full App integration suite)

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "Wire Send All Eligible bulk action into App"
```

- [ ] **Step 6: Rebuild the frontend**

Run (from `dashboard-app/frontend/`):
```bash
npm run build
```
Expected: `dashboard-app/frontend/dist/` is regenerated with the new button included.

- [ ] **Step 7: Verify the backend's full test suite still passes**

Run (from `dashboard-app/backend/`):
```bash
python -m pytest test_main.py -v
```
Expected: 15 passed, no regressions.

- [ ] **Step 8: Note for the user**

If a `uvicorn` server from an earlier session is already running, it's serving the OLD build. Restart it (stop the old process, run `python -m uvicorn main:app --port 8000` from `dashboard-app/backend/` again) to pick up the new `dist/` with the Send All Eligible button, before doing a manual check.
