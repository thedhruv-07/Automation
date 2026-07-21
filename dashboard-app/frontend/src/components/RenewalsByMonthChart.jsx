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
        <div className="flex items-end justify-between gap-3 h-40">
          {groups.map((g) => (
            <div key={g.key} className="flex flex-col items-center flex-1 h-full justify-end group" title={`${g.label}: ${g.count} renewal${g.count === 1 ? "" : "s"}`}>
              <span className="text-xs font-semibold text-ink-secondary mb-1 tabular-nums">{g.count}</span>
              <div
                className="w-full max-w-[36px] bg-accent rounded-t group-hover:bg-accent-dark transition-colors"
                style={{ height: `${Math.max(6, (g.count / max) * 100)}%` }}
              />
              <span className="text-xs text-ink-muted mt-2 whitespace-nowrap">{g.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
