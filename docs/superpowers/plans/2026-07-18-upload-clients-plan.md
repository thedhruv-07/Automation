# Upload Clients Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user upload a new `clients_certifications.xlsx` from the React dashboard, validating column structure and backing up the previous file before replacing it.

**Architecture:** New `POST /api/upload-clients` endpoint validates the uploaded file's headers (positionally — `read_clients()` reads by column position, not name lookup, so wrong order would silently corrupt data), backs up the existing file, then atomically replaces it via a temp-file-then-rename. New `UploadClientsButton.jsx` component + `uploadClients()` in `api.js`, wired into `App.jsx`.

**Tech Stack:** Same as the rest of the dashboard — FastAPI/pytest backend (plus `python-multipart` for file uploads), React/Vitest frontend.

Spec: `docs/superpowers/specs/2026-07-18-upload-clients-design.md`

---

## File Structure

```
cert_automation_scripts/
  dashboard-app/
    backend/
      requirements.txt   (modified — add python-multipart)
      main.py            (modified — add POST /api/upload-clients)
      test_main.py       (modified — new tests)
    frontend/
      src/
        api.js             (modified — add uploadClients())
        api.test.js         (modified — new tests)
        App.jsx             (modified — wire in upload button)
        App.test.jsx        (modified — new tests)
        components/
          UploadClientsButton.jsx       (new)
          UploadClientsButton.test.jsx  (new)
```

---

### Task 1: `POST /api/upload-clients` endpoint

**Files:**
- Modify: `dashboard-app/backend/requirements.txt`
- Modify: `dashboard-app/backend/main.py`
- Modify: `dashboard-app/backend/test_main.py`

- [ ] **Step 1: Add `python-multipart` to requirements**

Add to `dashboard-app/backend/requirements.txt`:
```
python-multipart>=0.0.12
```

Run: `python -m pip install -r dashboard-app/backend/requirements.txt`

- [ ] **Step 2: Write the failing tests**

Add to `dashboard-app/backend/test_main.py`:

```python
def test_upload_clients_success(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)

    upload_path = tmp_path / "upload.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("clients.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "row_count": 1}
    assert excel_path.exists()


def test_upload_clients_rejects_non_xlsx_extension(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)
    response = client.post(
        "/api/upload-clients",
        files={"file": ("clients.csv", b"not,a,real,xlsx", "text/csv")},
    )
    assert response.status_code == 400


def test_upload_clients_rejects_wrong_headers(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)

    upload_path = tmp_path / "bad.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Wrong", "Headers", "Here"])
    ws.append(["a", "b", "c"])
    wb.save(upload_path)

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("bad.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 400
    assert not excel_path.exists()


def test_upload_clients_backs_up_existing_file(tmp_path, monkeypatch):
    excel_path = tmp_path / "clients.xlsx"
    _write_xlsx(excel_path, [
        ["CLT999", "Old Client", "OldCo", "o@x.com", "919999999999",
         "Old Cert", "OLD-1", "01-01-2025", "01-01-2026", "https://x", "ACTIVE"],
    ])
    monkeypatch.setattr(main_module, "DEFAULT_EXCEL_PATH", excel_path)

    upload_path = tmp_path / "new.xlsx"
    _write_xlsx(upload_path, [
        ["CLT001", "Rahul Sharma", "TechCorp", "r@x.com", "919876543210",
         "ISO 9001", "ISO-1", "01-01-2025", "24-07-2026", "https://x", "CRITICAL"],
    ])

    with open(upload_path, "rb") as f:
        response = client.post(
            "/api/upload-clients",
            files={"file": ("new.xlsx", f,
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 200

    backup_path = excel_path.parent / "clients_certifications.backup.xlsx"
    assert backup_path.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -k upload_clients -v`
Expected: FAIL — 404, the route doesn't exist yet

- [ ] **Step 4: Implement the endpoint**

Change this line in `dashboard-app/backend/main.py`:
```python
from fastapi import FastAPI, HTTPException  # noqa: E402
```
to:
```python
from fastapi import FastAPI, HTTPException, File, UploadFile  # noqa: E402
```

Add near the top of the file, after the existing imports:
```python
import shutil  # noqa: E402

import openpyxl  # noqa: E402
```

Add a constant near `_bulk_in_progress`:
```python
REQUIRED_HEADERS = [
    "Client ID", "Full Name", "Company", "Email", "Phone (WhatsApp)",
    "Certification Name", "Certification ID", "Issue Date", "Expiry Date",
    "Renewal Link", "Status",
]
```

Add the endpoint, before the `from fastapi.staticfiles import StaticFiles` block at the end of the file:

```python
@app.post("/api/upload-clients")
async def upload_clients(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    contents = await file.read()
    tmp_path = DEFAULT_EXCEL_PATH.parent / "_upload_tmp.xlsx"
    tmp_path.write_bytes(contents)

    try:
        wb = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
        try:
            header_row = next(wb.active.iter_rows(values_only=True))
        finally:
            wb.close()
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded file as a valid .xlsx spreadsheet",
        )

    actual_headers = list(header_row[: len(REQUIRED_HEADERS)])
    if actual_headers != REQUIRED_HEADERS:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Column headers don't match the expected format. Expected: {', '.join(REQUIRED_HEADERS)}",
        )

    if DEFAULT_EXCEL_PATH.exists():
        backup_path = DEFAULT_EXCEL_PATH.parent / "clients_certifications.backup.xlsx"
        shutil.copyfile(DEFAULT_EXCEL_PATH, backup_path)

    shutil.move(str(tmp_path), str(DEFAULT_EXCEL_PATH))

    row_count = len(read_clients(DEFAULT_EXCEL_PATH))
    return {"status": "ok", "row_count": row_count}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd dashboard-app/backend && python -m pytest test_main.py -v`
Expected: 21 passed (17 existing + 4 new)

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/backend/requirements.txt dashboard-app/backend/main.py dashboard-app/backend/test_main.py
git commit -m "Add POST /api/upload-clients endpoint with header validation and backup"
```

---

### Task 2: `api.js` — `uploadClients()`

**Files:**
- Modify: `dashboard-app/frontend/src/api.js`
- Modify: `dashboard-app/frontend/src/api.test.js`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/frontend/src/api.test.js`:

```js
describe("uploadClients", () => {
  it("posts the file as form data and returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 8 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await uploadClients(file);
    expect(result).toEqual({ status: "ok", row_count: 8 });
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe("/api/upload-clients");
    expect(options.method).toBe("POST");
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Column headers don't match the expected format." }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(uploadClients(file)).rejects.toThrow(
      "Column headers don't match the expected format."
    );
  });
});
```

Add `uploadClients` to the existing import line at the top of the file:
```js
import { getClients, sendAlert, sendAllAlerts, uploadClients } from "./api";
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test` (from `dashboard-app/frontend/`)
Expected: FAIL — `uploadClients` is not exported

- [ ] **Step 3: Implement `uploadClients()`**

Add to `dashboard-app/frontend/src/api.js`:

```js
export async function uploadClients(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/upload-clients", { method: "POST", body: formData });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Upload failed: ${res.status}`);
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
git commit -m "Add uploadClients() to api.js"
```

---

### Task 3: `UploadClientsButton` component

**Files:**
- Create: `dashboard-app/frontend/src/components/UploadClientsButton.jsx`
- Create: `dashboard-app/frontend/src/components/UploadClientsButton.test.jsx`

- [ ] **Step 1: Write the failing tests**

Create `dashboard-app/frontend/src/components/UploadClientsButton.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import UploadClientsButton from "./UploadClientsButton";

describe("UploadClientsButton", () => {
  it("calls onUpload with the selected file", async () => {
    const onUpload = vi.fn().mockResolvedValue();
    render(<UploadClientsButton onUpload={onUpload} />);
    const file = new File(["dummy"], "clients.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const input = screen.getByTestId("upload-input");
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(file));
  });

  it("does nothing when no file is selected", () => {
    const onUpload = vi.fn();
    render(<UploadClientsButton onUpload={onUpload} />);
    const input = screen.getByTestId("upload-input");
    fireEvent.change(input, { target: { files: [] } });
    expect(onUpload).not.toHaveBeenCalled();
  });

  it("disables the button and shows Uploading... while in flight", async () => {
    let resolveUpload;
    const onUpload = vi.fn(() => new Promise((resolve) => { resolveUpload = resolve; }));
    render(<UploadClientsButton onUpload={onUpload} />);
    const file = new File(["dummy"], "clients.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const input = screen.getByTestId("upload-input");
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText("Uploading...")).toBeInTheDocument());
    resolveUpload();
    await waitFor(() => expect(screen.getByText("Upload Excel")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test` (from `dashboard-app/frontend/`)
Expected: FAIL — `UploadClientsButton.jsx` doesn't exist

- [ ] **Step 3: Implement `UploadClientsButton.jsx`**

Create `dashboard-app/frontend/src/components/UploadClientsButton.jsx`:

```jsx
import { useRef, useState } from "react";

export default function UploadClientsButton({ onUpload }) {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await onUpload(file);
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx"
        onChange={handleChange}
        className="hidden"
        data-testid="upload-input"
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200 bg-white disabled:opacity-50"
      >
        {uploading ? "Uploading..." : "Upload Excel"}
      </button>
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/UploadClientsButton.jsx dashboard-app/frontend/src/components/UploadClientsButton.test.jsx
git commit -m "Add UploadClientsButton component"
```

---

### Task 4: Wire upload into `App.jsx`, rebuild, and verify

**Files:**
- Modify: `dashboard-app/frontend/src/App.jsx`
- Modify: `dashboard-app/frontend/src/App.test.jsx`

- [ ] **Step 1: Write the failing tests**

Add to `dashboard-app/frontend/src/App.test.jsx`, inside the existing `describe("App", ...)` block:

```jsx
it("uploads a file and shows a success toast with the row count", async () => {
  api.uploadClients.mockResolvedValue({ status: "ok", row_count: 8 });
  render(<App />);
  await waitFor(() => screen.getByText("Send Alert"));
  const file = new File(["dummy"], "clients.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  fireEvent.change(screen.getByTestId("upload-input"), { target: { files: [file] } });
  await waitFor(() => expect(api.uploadClients).toHaveBeenCalledWith(file));
  await waitFor(() => expect(screen.getByText("Uploaded 8 clients")).toBeInTheDocument());
});

it("shows an error toast when upload fails", async () => {
  api.uploadClients.mockRejectedValue(
    new Error("Column headers don't match the expected format.")
  );
  render(<App />);
  await waitFor(() => screen.getByText("Send Alert"));
  const file = new File(["dummy"], "clients.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  fireEvent.change(screen.getByTestId("upload-input"), { target: { files: [file] } });
  await waitFor(() =>
    expect(screen.getByText("Column headers don't match the expected format.")).toBeInTheDocument()
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test` (from `dashboard-app/frontend/`)
Expected: FAIL — no upload input exists yet

- [ ] **Step 3: Wire it into `App.jsx`**

Change the import line:
```jsx
import { getClients, sendAlert, sendAllAlerts } from "./api";
```
to:
```jsx
import { getClients, sendAlert, sendAllAlerts, uploadClients } from "./api";
```

Add the import for the new component, alongside the existing component imports:
```jsx
import UploadClientsButton from "./components/UploadClientsButton";
```

Add a new handler function, alongside `handleConfirmSend`/`handleConfirmSendAll`:
```jsx
async function handleUpload(file) {
  try {
    const result = await uploadClients(file);
    setToast({ type: "success", message: `Uploaded ${result.row_count} clients` });
    loadClients();
  } catch (err) {
    setToast({ type: "error", message: err.message });
  }
}
```

In the JSX, add the new button inside the existing `<div className="flex gap-3">` button group (alongside Refresh and Send All Eligible):
```jsx
<UploadClientsButton onUpload={handleUpload} />
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: all tests passed

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/App.jsx dashboard-app/frontend/src/App.test.jsx
git commit -m "Wire Upload Excel button into App"
```

- [ ] **Step 6: Rebuild the frontend**

Run (from `dashboard-app/frontend/`):
```bash
npm run build
```

- [ ] **Step 7: Verify the backend's full test suite still passes**

Run (from `dashboard-app/backend/`):
```bash
python -m pytest test_main.py -v
```
Expected: 21 passed, no regressions.

- [ ] **Step 8: Note for the user**

Restart any already-running `uvicorn` server to pick up the new build before testing the upload button live.
