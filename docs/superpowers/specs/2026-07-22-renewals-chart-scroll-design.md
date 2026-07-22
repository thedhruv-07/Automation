# Renewals-by-Month Chart: Fixed Card, Internal Scroll, Jump-to-Month Filter

**Status:** Approved
**Component:** `dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx`

## Problem

`RenewalsByMonthChart` lays out one bar per month in a `flex items-end justify-between gap-3` row, with each bar column set to `flex-1`. Flex items default to `min-width: auto`, meaning a column can't shrink below the intrinsic width of its `whitespace-nowrap` month label (e.g. "Aug 2026"). Against the real migrated dataset, `renewals_by_month` spans dozens of months, so the row refuses to compress and instead pushes the whole page wider, producing a page-level horizontal scrollbar (see bug screenshot: dashboard scrolls sideways, `Client Renewals` list not visible until scrolling right).

## Goals

1. The chart card never grows wider than its normal place in the dashboard layout (fills the content column, same as today) — no more page-level horizontal stretch.
2. When there are more months than fit in the card, the user can reach them without the page scrolling — via a scrollbar local to the chart.
3. The user can jump directly to a specific month instead of scrolling through all of them.

## Design

All changes are internal to `RenewalsByMonthChart.jsx`. No prop shape change (`renewalsByMonth` stays the only prop) and no backend/API change.

### 1. Static card, internal scroll region

The card (`bg-surface rounded-xl border border-line p-6`) keeps its current width behavior — it fills its parent column in `App.jsx`, unchanged. Inside the card, the bars row is wrapped in a new scroll container:

```jsx
<div className="overflow-x-auto" ref={scrollRef}>
  <div className="flex items-end gap-3 h-40" style={{ width: `${groups.length * BAR_SLOT_WIDTH}px` }}>
    {/* bars */}
  </div>
</div>
```

- `BAR_SLOT_WIDTH` is a fixed pixel constant (e.g. `64`) covering the bar plus its label and spacing.
- Each bar column switches from `flex-1` to a fixed width (`w-[64px]` or equivalent inline style) so total row width is `groups.length * BAR_SLOT_WIDTH`, deterministic regardless of label length.
- `justify-between` is dropped (no longer meaningful with fixed-width children); bars lay out left-to-right in month order as they do today.

### 2. Native horizontal scrollbar ("slidebar below")

`overflow-x-auto` on the wrapping div is sufficient: when the inner row's fixed width exceeds the card's content width, the browser renders its normal horizontal scrollbar directly under the bars, scoped to the card. No custom slider component, no extra dependency. This satisfies "add slidebar below" using the platform control rather than a hand-built one.

### 3. Jump-to-month dropdown

A `<select>` added to the card header, next to the "Renewals by Month" heading:

```jsx
<select onChange={(e) => scrollToMonth(e.target.value)} className="...">
  <option value="">Jump to month…</option>
  {groups.map((g) => (
    <option key={g.key} value={g.key}>{g.label} ({g.count})</option>
  ))}
</select>
```

`scrollToMonth(key)` finds the corresponding bar's DOM node (via a `ref` map keyed by `g.key`) and calls `scrollIntoView({ inline: "center", behavior: "smooth", block: "nearest" })` on it, scoped within the `overflow-x-auto` container (setting `block: "nearest"` avoids also scrolling the outer page vertically). This is pure navigation — it does not filter or hide other months; all bars remain rendered and reachable by scrolling.

### Edge cases

- `groups.length === 0`: unchanged — existing "No certification expiry dates to chart yet." message, no scroll region or dropdown rendered.
- Small `groups.length` (fewer months than fit the card): `overflow-x-auto` container simply doesn't overflow; no scrollbar appears (browser default behavior) — dropdown still renders but scrolling has nothing to do.

## Testing

Update `RenewalsByMonthChart.test.jsx`:
- Existing coverage (bars render, counts/labels correct, empty state) stays as-is, adjusted for the new DOM structure (scroll wrapper div).
- New: dropdown lists one `<option>` per month with the "Label (count)" format.
- New: selecting a month option calls `scrollIntoView` (mocked, since jsdom doesn't implement real scrolling) on the corresponding bar's element, with `inline: "center"`.

## Out of scope

- No change to how `/api/stats` computes `renewals_by_month` (backend untouched).
- No date-range filtering of the underlying data — the dropdown only navigates the existing full set of bars.
- No custom-styled/always-visible scrollbar CSS — relies on the browser's native scrollbar for the overflow container.
