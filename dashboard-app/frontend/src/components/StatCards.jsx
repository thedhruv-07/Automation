import { motion } from "framer-motion";

const CARD_CONFIG = [
  { key: "total", label: "Total Clients", gradient: "from-sky-500 to-indigo-500" },
  { key: "CRITICAL", label: "Critical", gradient: "from-rose-500 to-orange-500" },
  { key: "URGENT", label: "Urgent", gradient: "from-amber-500 to-orange-400" },
  { key: "DUE SOON", label: "Due Soon", gradient: "from-yellow-400 to-amber-500" },
];

export default function StatCards({ clients }) {
  const counts = {
    total: clients.length,
    CRITICAL: clients.filter((c) => c.status === "CRITICAL").length,
    URGENT: clients.filter((c) => c.status === "URGENT").length,
    "DUE SOON": clients.filter((c) => c.status === "DUE SOON").length,
  };

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="stat-cards">
      {CARD_CONFIG.map((card) => (
        <motion.div
          key={card.key}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-2xl p-4 text-white shadow-lg bg-gradient-to-br ${card.gradient}`}
        >
          <div className="text-sm font-medium opacity-90">{card.label}</div>
          <div className="text-3xl font-bold" data-testid={`stat-${card.key}`}>
            {counts[card.key]}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
