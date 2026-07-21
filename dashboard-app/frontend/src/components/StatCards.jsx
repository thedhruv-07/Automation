import { motion } from "framer-motion";

const ICONS = {
  total: <path d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m5-9.13a4 4 0 110 8 4 4 0 010-8zm6 8a4 4 0 100-8" />,
  CRITICAL: <path d="M12 9v4m0 4h.01M10.29 3.86l-8.18 14.18A2 2 0 004 21h16a2 2 0 001.89-2.96L13.71 3.86a2 2 0 00-3.42 0z" />,
  URGENT: <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />,
  "DUE SOON": <path d="M8 7V3m8 4V3M3 11h18M5 5h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2z" />,
};

const CARD_CONFIG = [
  { key: "total", label: "Total Clients", accent: "bg-ink-muted" },
  { key: "CRITICAL", label: "Critical", accent: "bg-status-critical" },
  { key: "URGENT", label: "Urgent", accent: "bg-status-serious" },
  { key: "DUE SOON", label: "Due Soon", accent: "bg-status-warning" },
];

function StatIcon({ name, className }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  );
}

export default function StatCards({ stats }) {
  const statusCounts = stats?.status_counts || {};
  const counts = CARD_CONFIG.reduce((acc, { key }) => {
    acc[key] = statusCounts[key] || 0;
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="stat-cards">
      {CARD_CONFIG.map((card) => (
        <motion.div
          key={card.key}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="relative overflow-hidden rounded-xl bg-surface border border-line pl-5 pr-4 py-4 shadow-sm"
        >
          <span className={`absolute left-0 top-0 h-full w-1 ${card.accent}`} aria-hidden="true" />
          <span className="inline-flex p-2 rounded-lg bg-surface-page mb-3">
            <StatIcon name={card.key} className="h-5 w-5 text-ink-secondary" />
          </span>
          <div className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">
            {card.label}
          </div>
          <div
            className="mt-1 text-3xl font-bold text-ink-primary tabular-nums"
            data-testid={`stat-${card.key}`}
          >
            {counts[card.key]}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
