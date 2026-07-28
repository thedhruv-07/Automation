# Notices Page — Client List

## Problem

The Notices page shows an aggregate "N clients matching your filters
haven't received this via WhatsApp, M via Email" count, but no way to see
*who* those clients actually are before sending — unlike Client Data, which
shows the full matching roster in a table.

## Scope

Add a paginated client list to the Notices page, showing everyone matching
the current audience filters (scheme/status/cert type/expiry/search — the
same filters already driving the eligible-count text), each row tagged
with its own per-channel notice status. Not an exclusion-filtered list:
since WhatsApp and Email have two independently-tracked counts that can
diverge (a client might be notified via one channel and not the other),
there's no single "matches the count" rule that could apply to a whole
list — the correct, transparent design is showing everyone in the
audience with clear per-row status, not silently excluding rows against
one arbitrarily-chosen channel.

## 1. Data layer — `db.py`

**New function**: `get_broadcast_clients_page(db_path, notice_id, page=1,
page_size=50, status=None, cert_type=None, expiry_before=None, search=None,
scheme=None) -> tuple[list[dict], int]` — paginated sibling to
`get_broadcast_clients` (same audience-filter shape, any status, not just
`ALERT_STATUSES`), matching `get_clients_page`'s `(rows, total)` return
shape. Each row dict includes two additional boolean keys beyond the usual
`RECORD_FIELDS`: `notice_sent_whatsapp` and `notice_sent_email`, each
computed via a per-row `EXISTS` subquery against `notice_sent_log` scoped
to this specific `notice_id` and that channel.

## 2. API — `main.py`

**New endpoint**: `GET /api/notices/{notice_id}/clients` — same query
param shape as `/api/clients` (`page`, `page_size`, `status`, `cert_type`,
`expiry_before`, `search`, `scheme`), returning
`{"rows": [...], "total": N, "page": P, "page_size": S}`. 404s for an
unknown `notice_id`, matching every other `/api/notices/{notice_id}/*`
endpoint's existing behavior.

## 3. Frontend

- **`api.js`**: `getNoticeClients(noticeId, params)`, mirroring
  `getClients`'s param-to-querystring handling.
- **New lightweight table** rendered on `NoticesView.jsx`, below the
  eligible-count text and above the send buttons. Not a reuse of the full
  `ClientTable` component — that component's per-row Send Alert/Send Email
  action buttons and expiry/status-tier columns don't apply here, so
  forcing reuse would mean stripping out most of what makes it useful. A
  new component with columns: Client ID, Full Name, Company, Email, Phone,
  Sent via WhatsApp (badge), Sent via Email (badge) — plus the same
  Previous/Next pagination control style already used by `ClientTable` and
  `MessageLogView`.
- Refetches whenever the selected notice, page, or any filter changes —
  same trigger shape as the existing eligible-count `useEffect`.
- The table's own "Showing X–Y of Z clients" total will not equal either
  the WhatsApp or Email eligible-count number above it, by design — it
  reflects the whole filtered audience, the counts reflect each channel's
  *remaining* (not-yet-notified) subset of that same audience.

## Testing

- `db.py`: `get_broadcast_clients_page` returns the right page/total for
  the given filters; `notice_sent_whatsapp`/`notice_sent_email` correctly
  reflect `notice_sent_log` state per client, independently per channel
  (a client sent via WhatsApp only shows `notice_sent_whatsapp: True,
  notice_sent_email: False`); a client with no notice history shows both
  `False`.
- `main.py`: the new endpoint returns paginated rows with the two status
  booleans; honors the same filters as `/api/notices/{notice_id}/eligible-count`;
  404s for an unknown notice.
- Frontend: the new table renders rows from the API, shows correct
  per-channel status badges, paginates via Previous/Next, and refetches
  when the notice/filters change.
