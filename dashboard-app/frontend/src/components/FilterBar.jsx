const STATUS_TABS = ["ALL", "CRITICAL", "URGENT", "DUE SOON", "ACTIVE", "EXPIRED"];

const STATUS_LABELS = {
  ALL: "All",
  CRITICAL: "Critical",
  URGENT: "Urgent",
  "DUE SOON": "Due Soon",
  ACTIVE: "Active",
  EXPIRED: "Expired",
};

export default function FilterBar({ activeStatus, onStatusChange }) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="filter-bar">
      {STATUS_TABS.map((status) => (
        <button
          key={status}
          type="button"
          onClick={() => onStatusChange(status)}
          aria-pressed={activeStatus === status}
          className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors border ${
            activeStatus === status
              ? "bg-accent border-accent text-white"
              : "bg-surface border-line text-ink-secondary hover:text-ink-primary"
          }`}
        >
          {STATUS_LABELS[status]}
        </button>
      ))}
    </div>
  );
}
