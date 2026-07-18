const STATUS_TABS = ["ALL", "CRITICAL", "URGENT", "DUE SOON", "ACTIVE", "EXPIRED"];

const STATUS_LABELS = {
  ALL: "All",
  CRITICAL: "Critical",
  URGENT: "Urgent",
  "DUE SOON": "Due Soon",
  ACTIVE: "Active",
  EXPIRED: "Expired",
};

export default function FilterBar({ activeStatus, onStatusChange, searchTerm, onSearchChange }) {
  return (
    <div className="flex flex-wrap items-center gap-3" data-testid="filter-bar">
      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => onStatusChange(status)}
            aria-pressed={activeStatus === status}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${
              activeStatus === status
                ? "bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow"
                : "bg-white text-slate-600 border border-slate-200"
            }`}
          >
            {STATUS_LABELS[status]}
          </button>
        ))}
      </div>
      <input
        type="text"
        value={searchTerm}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder="Search name or company..."
        aria-label="Search name or company"
        className="ml-auto px-4 py-1.5 rounded-full border border-slate-200 text-sm min-w-[220px] focus:outline-none focus:ring-2 focus:ring-indigo-400"
      />
    </div>
  );
}
