# Multi-Select IS-Number (Cert Type) Filter — Design

## Problem

The "Cert Type" filter on both the Client Data page and the Notices page is currently single-select — an admin can only filter by one IS standard at a time. With hundreds of distinct IS standards in the roster, comparing or acting on a handful of related standards at once (e.g. sending one notice to clients across 5 specific IS numbers) requires repeating the whole filter-and-send flow once per standard.

Separately, the Notices page's cert-type filter is currently non-functional: `NoticesView.jsx` hardcodes `certOptions={[]}` when rendering `ClientDataFilters`, so the dropdown only ever shows "All Cert Types" there today, regardless of what's actually in the roster.

## Scope

- Convert the cert-type filter to multi-select on **both** the Client Data page and the Notices page.
- Wire up real cert-type options on the Notices page for the first time (fixes the `certOptions={[]}` gap above).
- Every other filter (status, scheme, expiry before, search) is unaffected — this only touches cert type.

## Architecture

### Frontend: new `MultiSelectDropdown` component

A new reusable component (`dashboard-app/frontend/src/components/MultiSelectDropdown.jsx`) replaces the native `<select>` used for cert type in `ClientDataFilters.jsx`. Behavior:

- **Closed state**: shows "All Cert Types" when nothing is selected, or "N selected" (e.g. "3 selected") otherwise.
- **Open state**: a search input at the top filters the option list client-side (case-insensitive substring match against the IS-standard string), with a scrollable checkbox list below showing the filtered options. Toggling a checkbox takes effect immediately — no separate "Apply" button, matching how every other filter on these pages already behaves.
- A "Clear" link inside the open panel resets the selection to empty.
- Closes on outside-click or Escape.

Props: `options: string[]`, `selected: string[]`, `onChange: (string[]) => void`, `label: string` (for the closed-state placeholder, e.g. "All Cert Types"), `ariaLabel: string`.

### Frontend: state shape change

`certType` changes from a string (`"ALL"` default) to an array (`[]` default, meaning "no filter" — equivalent to today's `"ALL"`) in:
- `App.jsx` (Client Data page)
- `NoticesView.jsx` (Notices page)

`NoticesView.jsx` additionally receives a new `certOptions` prop (real `stats.cert_types` list, passed down from `App.jsx`, the same source `App.jsx` already uses for its own Client Data cert options) instead of hardcoding `[]`.

### Wire format

Selected cert types travel to the backend as **repeated query params**: `cert_type=A&cert_type=B`. This is FastAPI's native way of collecting a `list[str]` query parameter — no custom encoding/parsing needed on either side.

In `api.js`, every existing `query.set("cert_type", params.certType)` call (4 call sites: `getClientsPage`, `getEligibleCount`, `clientsExportUrl`, and the notices equivalent) becomes a loop:

```js
for (const c of params.certType || []) query.append("cert_type", c);
```

### Backend: single shared filter builder

`db.py`'s `_client_filters_query()` is the one place every filtered read already routes through (`get_clients_page`, `export_clients_rows`, `get_eligible_clients`, `get_broadcast_clients`, `get_eligible_count`, `get_notice_eligible_count`, `get_broadcast_clients_page`). Its `cert_type` parameter changes from `str | None` to `list[str] | None`, and the query changes from an exact match to an `$in`:

```python
def _client_filters_query(
    status: str | None = None, cert_type: list[str] | None = None,
    expiry_before: str | None = None, search: str | None = None,
    scheme: str | None = None,
) -> dict:
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

A client matches if its `cert_name` is *any* of the selected values (OR semantics — the only sensible interpretation, since each client has exactly one `cert_name`). An empty or absent list means "no cert filter," identical to today's `"ALL"` behavior.

Because every read funnels through this one builder, **no other function in `db.py` needs new query logic** — they already just forward whatever `cert_type` they're given straight into `_client_filters_query()`.

### Backend: route handlers

Every route handler in `main.py` currently accepting `cert_type: str = "ALL"` or `cert_type: str = ""` (about 9 handlers, covering `/api/clients`, `/api/clients/export`, `/api/eligible-count`, `/api/broadcast-clients` and its paginated variant, and the notice-scoped equivalents: eligible-count, clients, send) changes to:

```python
cert_type: list[str] = Query([])
```

The old `str = "ALL"` sentinel values (`"ALL"`, `""`) are dropped in favor of "empty list means no filter" — consistent with how FastAPI naturally represents "no repeated query param given." Each handler continues to pass `cert_type` straight through to its corresponding `db.py` function unchanged, since the type change is transparent to that call site (a `list[str]`, possibly empty, is exactly what `_client_filters_query` now expects).

## What Does Not Change

- Status, scheme, expiry-before, and search filters — unaffected, still single-value.
- CSV export, notice sending, eligible-count logic, and broadcast-clients pagination — all keep working exactly as before, just with `$in` instead of an exact match when multiple cert types are selected.
- The frontend's other filter controls (scheme dropdown, expiry-before date input, duration presets, Clear All) — unchanged.

## Testing Strategy

**Backend** (`test_db.py`): new/updated cases for `_client_filters_query()` and `get_clients_page()` with a 2+ item `cert_type` list, verifying OR-match across multiple standards; a single-item list still behaves like today's exact match; an empty list behaves like today's "ALL" (no filter); a list containing `"ALL"` or blank strings (the defensive-guard case) also behaves like "no filter."

**Frontend**:
- New `MultiSelectDropdown.test.jsx`: open/close behavior, search-box filtering, checkbox toggling, "Clear" link, outside-click/Escape close, closed-state label text (none selected vs. "N selected").
- `ClientDataFilters.test.jsx`: updated for the new component in place of the native `<select>`.
- `App.test.jsx` / `NoticesView.test.jsx`: updated for array-based `certType` state and (for Notices) the newly-wired real `certOptions`.
