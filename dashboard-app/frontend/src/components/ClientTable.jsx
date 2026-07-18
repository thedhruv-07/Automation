import { sortClients, formatDaysLeft } from "../sortUtils";

const STATUS_COLORS = {
  EXPIRED: "bg-red-500 text-white",
  CRITICAL: "bg-orange-500 text-white",
  URGENT: "bg-amber-400 text-slate-900",
  "DUE SOON": "bg-yellow-300 text-slate-900",
  ACTIVE: "bg-emerald-500 text-white",
};

const ALERT_ELIGIBLE = new Set(["CRITICAL", "URGENT", "DUE SOON"]);

const COLUMNS = [
  { key: "client_id", label: "Client ID" },
  { key: "name", label: "Full Name" },
  { key: "company", label: "Company" },
  { key: "cert_name", label: "Certification" },
  { key: "cert_id", label: "Cert ID" },
  { key: "expiry_date", label: "Expiry Date" },
  { key: "days_left", label: "Days Left" },
  { key: "status", label: "Status" },
];

export default function ClientTable({
  clients, activeStatus, searchTerm, sortKey, sortAsc, onSort, onSendClick,
}) {
  let rows = clients;
  if (activeStatus !== "ALL") {
    rows = rows.filter((c) => c.status === activeStatus);
  }
  if (searchTerm) {
    const term = searchTerm.toLowerCase();
    rows = rows.filter(
      (c) => c.name.toLowerCase().includes(term) || c.company.toLowerCase().includes(term)
    );
  }
  rows = sortClients(rows, sortKey, sortAsc);

  return (
    <table className="w-full bg-white rounded-2xl overflow-hidden shadow" data-testid="client-table">
      <thead>
        <tr className="bg-gradient-to-r from-slate-800 to-slate-700 text-white text-sm">
          {COLUMNS.map((col) => (
            <th
              key={col.key}
              onClick={() => onSort(col.key)}
              aria-sort={sortKey === col.key ? (sortAsc ? "ascending" : "descending") : "none"}
              className="px-3 py-2 text-left cursor-pointer select-none"
            >
              {col.label}
              {sortKey === col.key ? (sortAsc ? " ▲" : " ▼") : ""}
            </th>
          ))}
          <th className="px-3 py-2 text-left">Action</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr key={c.client_id} className="border-b border-slate-100 text-sm hover:bg-slate-50 transition-colors">
            <td className="px-3 py-2">{c.client_id}</td>
            <td className="px-3 py-2">{c.name}</td>
            <td className="px-3 py-2">{c.company}</td>
            <td className="px-3 py-2">{c.cert_name}</td>
            <td className="px-3 py-2">{c.cert_id}</td>
            <td className="px-3 py-2">{c.expiry_date}</td>
            <td className="px-3 py-2">{formatDaysLeft(c.expiry_date)}</td>
            <td className="px-3 py-2">
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${STATUS_COLORS[c.status] || "bg-slate-300"}`}>
                {c.status}
              </span>
            </td>
            <td className="px-3 py-2">
              {!ALERT_ELIGIBLE.has(c.status) ? (
                <span className="text-slate-400">—</span>
              ) : c.alert_sent_today ? (
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
                  ✅ Sent
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => onSendClick(c)}
                  className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 shadow hover:opacity-90 transition-opacity"
                >
                  Send Alert
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
