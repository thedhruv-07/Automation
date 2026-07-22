# Renewals-by-Month Chart Scroll Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `RenewalsByMonthChart` from stretching the whole dashboard page horizontally when there are many months of data, by giving it a fixed-width card with an internally-scrollable bar strip and a dropdown to jump directly to a month.

**Architecture:** All changes are contained in `dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx` (and its test file). No prop shape change, no backend/API change. The bars row switches from `flex-1` children (which refuse to shrink below their label's width, causing the overflow) to fixed-width children inside an `overflow-x-auto` wrapper, so the browser's native horizontal scrollbar appears under the bars instead of the page growing. A `<select>` in the card header lets the user jump to a specific month via `scrollIntoView`.

**Tech Stack:** React 19, Vitest + Testing Library (existing project stack, no new dependencies).

**Reference spec:** `docs/superpowers/specs/2026-07-22-renewals-chart-scroll-design.md`

---

### Task 1: Fix the layout — fixed-width bars inside an internally-scrolling strip

**Files:**
- Modify: `dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx`
- Test: `dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx` (no changes needed this task — existing tests must keep passing unmodified, since this task only changes layout/CSS, not the text content or presence of any element they assert on)

- [ ] **Step 1: Run the existing tests to confirm the current baseline passes**

Run: `cd dashboard-app/frontend && npx vitest run src/components/RenewalsByMonthChart.test.jsx`
Expected: 2 passed (the two tests already in the file: bars render with count/label, empty state message)

- [ ] **Step 2: Replace the bars section of `RenewalsByMonthChart.jsx`**

Replace the entire file with:

```jsx
const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function labelFor(yearMonth) {
  const [year, month] = yearMonth.split("-").map(Number);
  return `${MONTH_LABELS[month - 1]} ${year}`;
}

export default function RenewalsByMonthChart({ renewalsByMonth }) {
  const groups = renewalsByMonth.map((g) => ({ key: g.year_month, label: labelFor(g.year_month), count: g.count }));
  const max = Math.max(1, ...groups.map((g) => g.count));

  return (
    <div className="bg-surface rounded-xl border border-line p-6" data-testid="renewals-by-month-chart">
      <h5 className="font-semibold text-ink-primary mb-6">Renewals by Month</h5>
      {groups.length === 0 ? (
        <p className="text-sm text-ink-muted">No certification expiry dates to chart yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <div className="inline-flex items-end gap-3 h-40 min-w-full">
            {groups.map((g) => (
              <div
                key={g.key}
                className="flex flex-col items-center h-full justify-end group shrink-0 w-16"
                title={`${g.label}: ${g.count} renewal${g.count === 1 ? "" : "s"}`}
              >
                <span className="text-xs font-semibold text-ink-secondary mb-1 tabular-nums">{g.count}</span>
                <div
                  className="w-full max-w-[36px] bg-accent rounded-t group-hover:bg-accent-dark transition-colors"
                  style={{ height: `${Math.max(6, (g.count / max) * 100)}%` }}
                />
                <span className="text-xs text-ink-muted mt-2 whitespace-nowrap">{g.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

What changed from the current file: the bars row (`flex items-end justify-between gap-3 h-40`, children `flex-1`) is now wrapped in an `overflow-x-auto` div, and the inner row is `inline-flex` (shrink-to-fit, so it only takes the width its children actually need — this is what makes `overflow-x-auto` on the parent trigger a scrollbar instead of the whole page stretching) with `min-w-full` (so on months that fit fine, the row still fills the card instead of collapsing to the left). Each bar column drops `flex-1` for `shrink-0 w-16` (fixed 64px width, doesn't shrink, doesn't grow) and `justify-between` on the row is removed since it's meaningless once children are fixed-width.

- [ ] **Step 3: Run the existing tests to verify they still pass unmodified**

Run: `cd dashboard-app/frontend && npx vitest run src/components/RenewalsByMonthChart.test.jsx`
Expected: 2 passed (same two tests as Step 1 — this change is layout-only, the text content and elements they query for are unchanged)

- [ ] **Step 4: Run the full frontend suite to confirm no regressions elsewhere**

Run: `cd dashboard-app/frontend && npx vitest run`
Expected: all passed, same file/test count as before this task

- [ ] **Step 5: Commit**

```bash
git add dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx
git commit -m "fix: contain RenewalsByMonthChart overflow to an internal scroll strip instead of stretching the page"
```

---

### Task 2: Add a jump-to-month dropdown

**Files:**
- Modify: `dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx`
- Test: `dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx`

- [ ] **Step 1: Write the failing tests**

Replace `dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx` with:

```jsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import RenewalsByMonthChart from "./RenewalsByMonthChart";

describe("RenewalsByMonthChart", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("renders a bar with the count and month label for each bucket", () => {
    render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    expect(screen.getByText("Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("Sep 2026")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows an empty state when there are no buckets", () => {
    render(<RenewalsByMonthChart renewalsByMonth={[]} />);
    expect(screen.getByText("No certification expiry dates to chart yet.")).toBeInTheDocument();
  });

  it("does not render the jump-to-month dropdown when there are no buckets", () => {
    render(<RenewalsByMonthChart renewalsByMonth={[]} />);
    expect(screen.queryByLabelText("Jump to month")).not.toBeInTheDocument();
  });

  it("lists every month as a dropdown option with its label and count", () => {
    render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    expect(screen.getByLabelText("Jump to month")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Jul 2026 (2)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Sep 2026 (1)" })).toBeInTheDocument();
  });

  it("scrolls the selected month's bar into view when chosen from the dropdown", () => {
    render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    const select = screen.getByLabelText("Jump to month");
    fireEvent.change(select, { target: { value: "2026-09" } });
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ inline: "center", block: "nearest" })
    );
  });
});
```

- [ ] **Step 2: Run tests to verify the three new tests fail**

Run: `cd dashboard-app/frontend && npx vitest run src/components/RenewalsByMonthChart.test.jsx`
Expected: 2 passed (the pre-existing two), 3 failed (`getByLabelText("Jump to month")` finds nothing — no dropdown exists yet)

- [ ] **Step 3: Add the dropdown and scroll-to-month behavior**

Replace `dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx` with:

```jsx
import { useRef } from "react";

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function labelFor(yearMonth) {
  const [year, month] = yearMonth.split("-").map(Number);
  return `${MONTH_LABELS[month - 1]} ${year}`;
}

export default function RenewalsByMonthChart({ renewalsByMonth }) {
  const groups = renewalsByMonth.map((g) => ({ key: g.year_month, label: labelFor(g.year_month), count: g.count }));
  const max = Math.max(1, ...groups.map((g) => g.count));
  const barRefs = useRef({});

  function scrollToMonth(key) {
    const node = barRefs.current[key];
    if (node) {
      node.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    }
  }

  return (
    <div className="bg-surface rounded-xl border border-line p-6" data-testid="renewals-by-month-chart">
      <div className="flex items-center justify-between mb-6 gap-3">
        <h5 className="font-semibold text-ink-primary">Renewals by Month</h5>
        {groups.length > 0 && (
          <select
            onChange={(e) => e.target.value && scrollToMonth(e.target.value)}
            aria-label="Jump to month"
            defaultValue=""
            className="min-w-[180px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            <option value="">Jump to month…</option>
            {groups.map((g) => (
              <option key={g.key} value={g.key}>{g.label} ({g.count})</option>
            ))}
          </select>
        )}
      </div>
      {groups.length === 0 ? (
        <p className="text-sm text-ink-muted">No certification expiry dates to chart yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <div className="inline-flex items-end gap-3 h-40 min-w-full">
            {groups.map((g) => (
              <div
                key={g.key}
                ref={(node) => { barRefs.current[g.key] = node; }}
                className="flex flex-col items-center h-full justify-end group shrink-0 w-16"
                title={`${g.label}: ${g.count} renewal${g.count === 1 ? "" : "s"}`}
              >
                <span className="text-xs font-semibold text-ink-secondary mb-1 tabular-nums">{g.count}</span>
                <div
                  className="w-full max-w-[36px] bg-accent rounded-t group-hover:bg-accent-dark transition-colors"
                  style={{ height: `${Math.max(6, (g.count / max) * 100)}%` }}
                />
                <span className="text-xs text-ink-muted mt-2 whitespace-nowrap">{g.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they all pass**

Run: `cd dashboard-app/frontend && npx vitest run src/components/RenewalsByMonthChart.test.jsx`
Expected: 5 passed

- [ ] **Step 5: Run the full frontend suite and lint**

Run: `cd dashboard-app/frontend && npx vitest run && npx oxlint src/components/RenewalsByMonthChart.jsx src/components/RenewalsByMonthChart.test.jsx`
Expected: all tests passed, lint clean

- [ ] **Step 6: Commit**

```bash
git add dashboard-app/frontend/src/components/RenewalsByMonthChart.jsx dashboard-app/frontend/src/components/RenewalsByMonthChart.test.jsx
git commit -m "feat: add jump-to-month dropdown to RenewalsByMonthChart"
```

---

### Task 3: Manual verification against the real migrated dataset

**Files:** none (verification only)

- [ ] **Step 1: Confirm the dashboard backend and frontend dev servers are running**

Backend: `cd dashboard-app/backend && python -m uvicorn main:app --port 8040` (port must be 8040 — this is the port `vite.config.js`'s dev proxy targets)
Frontend: `cd dashboard-app/frontend && npm run dev -- --port 5173`

- [ ] **Step 2: Open the dashboard and check the Dashboard view**

Open `http://localhost:5173`, land on the Dashboard view (default). Confirm:
- The page itself does not scroll horizontally (no page-level horizontal scrollbar).
- The "Renewals by Month" card has its own horizontal scrollbar directly under the bars, and dragging/scrolling it pans through months without moving the rest of the page.
- The "Jump to month…" dropdown lists every month present in the real data (spans multiple years against the live 56,737-row dataset) with its count, and selecting one smooth-scrolls that month's bar into view within the card.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify RenewalsByMonthChart scroll fix against the real migrated dataset"
```
