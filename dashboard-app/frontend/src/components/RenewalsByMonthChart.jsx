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
          <div className="inline-flex items-end justify-center gap-3 h-40 min-w-full">
            {groups.map((g) => (
              <div
                key={g.key}
                ref={(node) => { barRefs.current[g.key] = node; }}
                data-month={g.key}
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
