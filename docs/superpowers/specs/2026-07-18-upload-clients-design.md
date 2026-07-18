# Upload Excel from Dashboard — Design Spec

Date: 2026-07-18
Project: Absolute Veritas certification consultancy

## Purpose

Let the user upload a new `clients_certifications.xlsx` directly from the React
dashboard, instead of only reading whatever file already sits on disk. Since the
same file is also read by the WhatsApp CLI script and its 9:30 AM scheduled
automation, an upload **replaces the shared master file** — there is no
separate "preview only" mode, since a preview that doesn't match what
Send Alert/Send All actually operate on would be actively misleading.

## Backend

**`POST /api/upload-clients`** (new endpoint, `dashboard-app/backend/main.py`),
accepting a multipart file upload (`UploadFile`):

1. Reject (400) if the filename doesn't end in `.xlsx`.
2. Write the uploaded bytes to a temp file, open it with `openpyxl`, and read
   the first (header) row.
3. **Validate column headers exactly, in order**, against the fixed 11-column
   format (`Client ID, Full Name, Company, Email, Phone (WhatsApp),
   Certification Name, Certification ID, Issue Date, Expiry Date, Renewal
   Link, Status`). This matters beyond cosmetics: `read_clients()` reads
   columns **positionally** (zips rows against a fixed field-name list), not
   by header lookup — a file with the right column names in the wrong order
   would silently produce corrupted data (e.g., Company landing in the `name`
   field) rather than erroring. Reject (400) with a clear message on mismatch;
   delete the temp file; the real file on disk is untouched.
4. If validation passes: if `clients_certifications.xlsx` already exists, copy
   it to `clients_certifications.backup.xlsx` (overwriting any previous
   backup) before replacing it.
5. Atomically replace the real file with the uploaded one (write to temp, then
   `shutil.move` — a same-directory move is an atomic rename on both Windows
   and POSIX, so a concurrent `GET /api/clients` read can never observe a
   half-written file; no additional locking needed for this).
6. Return `{"status": "ok", "row_count": N}`.

Requires adding `python-multipart` to `dashboard-app/backend/requirements.txt`
(FastAPI needs it to parse multipart file uploads).

## Frontend

- **`api.js`** — new `uploadClients(file)`: builds a `FormData`, POSTs to
  `/api/upload-clients` (no manual `Content-Type` — the browser sets the
  multipart boundary automatically), same error-handling shape as
  `sendAlert`/`sendAllAlerts` (throws `data.detail` on failure).
- **`UploadClientsButton.jsx`** (new component) — a hidden
  `<input type="file" accept=".xlsx">` triggered by a visible button (styled
  like Refresh), calling an `onUpload(file)` prop on file selection, showing a
  "Uploading..." disabled state while in flight.
- **`App.jsx`** — new `handleUpload(file)` calling `uploadClients`, showing a
  success toast (with the row count) or error toast, then refreshing the
  client list via the existing `loadClients()`. Button placed in the same
  header button group as Refresh/Send All Eligible.

## Out of Scope

- Any UI preview of the uploaded file's contents before committing — validate
  and replace in one step, no staging area.
- Restoring from the `.backup.xlsx` file via the UI (the backup exists purely
  as manual recovery insurance — the user can rename it back manually if
  needed).
- Any change to how `whatsapp_renewal_alerts.py`'s CLI or scheduled task reads
  the file — they already read `clients_certifications.xlsx` from the same
  path, so an upload transparently becomes what they see on their next run.
