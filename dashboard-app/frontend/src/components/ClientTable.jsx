import { useEffect, useState } from "react";
import { formatDaysLeft, initialsFor } from "../sortUtils";
import { clientsExportUrl } from "../api";

const STATUS_DOT = {
  EXPIRED: "bg-status-critical",
  CRITICAL: "bg-status-critical",
  URGENT: "bg-status-serious",
  "DUE SOON": "bg-status-warning",
  ACTIVE: "bg-status-good",
};

const ALERT_ELIGIBLE = new Set(["CRITICAL", "URGENT", "DUE SOON", "EXPIRED"]);

const COLUMNS = [
  { key: "client_id", label: "Client ID" },
  { key: "name", label: "Full Name" },
  { key: "company", label: "Company" },
  { key: "phone", label: "Phone", sortable: false },
  { key: "cert_name", label: "Certification" },
  { key: "cert_id", label: "Cert ID" },
  { key: "expiry_date", label: "Expiry Date" },
  { key: "days_left", label: "Days Left" },
  { key: "status", label: "Status" },
];

export default function ClientTable({
  page, loading, sortKey, sortAsc, onSort, onPageChange,
  onSendClick, onSendSelected, onPreviewEmail, onSendEmailClick, exportFilters = {},
}) {
  const [selectedIds, setSelectedIds] = useState(new Set());
  const { rows, total, page: currentPage, page_size: pageSize } = page;

  useEffect(() => {
    setSelectedIds(new Set());
  }, [currentPage, sortKey, sortAsc]);

  function toggleRow(clientId) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(clientId)) next.delete(clientId);
      else next.add(clientId);
      return next;
    });
  }

  function toggleSelectAllOnPage() {
    setSelectedIds((prev) => {
      const allSelected = rows.length > 0 && rows.every((c) => prev.has(c.client_id));
      if (allSelected) return new Set();
      return new Set(rows.map((c) => c.client_id));
    });
  }

  const allOnPageSelected = rows.length > 0 && rows.every((c) => selectedIds.has(c.client_id));
  const selectedClients = rows.filter((c) => selectedIds.has(c.client_id));
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const start = (currentPage - 1) * pageSize;
  const isEmptyLoading = loading && rows.length === 0;

  return (
    <div className="bg-surface rounded-xl border border-line overflow-hidden">
      <div className="px-4 py-3 border-b border-line flex items-center justify-between">
        <h5 className="font-semibold text-ink-primary">Client Renewals</h5>
        <a
          href={clientsExportUrl(exportFilters)}
          className="px-3 py-1.5 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
        >
          Export CSV
        </a>
      </div>

      {selectedIds.size > 0 && (
        <div className="px-4 py-2 bg-surface-page border-b border-line flex items-center gap-3 text-sm">
          <span className="text-ink-primary font-medium">{selectedClients.length} selected</span>
          <button
            type="button"
            onClick={() => onSendSelected(selectedClients)}
            className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
          >
            Send Reminder to Selected
          </button>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="text-ink-secondary hover:text-ink-primary transition-colors"
          >
            Clear selection
          </button>
        </div>
      )}

      <table className="w-full" data-testid="client-table">
        <thead>
          <tr className="bg-surface-page text-xs uppercase tracking-wide text-ink-secondary border-b-2 border-line">
            <th className="px-3 py-2 w-8">
              <input
                type="checkbox"
                aria-label="Select all on this page"
                checked={allOnPageSelected}
                onChange={toggleSelectAllOnPage}
              />
            </th>
            {COLUMNS.map((col) => (
              col.sortable === false ? (
                <th key={col.key} className="px-3 py-2 text-left font-semibold">
                  {col.label}
                </th>
              ) : (
                <th
                  key={col.key}
                  onClick={() => onSort(col.key)}
                  aria-sort={sortKey === col.key ? (sortAsc ? "ascending" : "descending") : "none"}
                  className="px-3 py-2 text-left font-semibold cursor-pointer select-none hover:text-ink-primary transition-colors"
                >
                  {col.label}
                  {sortKey === col.key ? (sortAsc ? " ▲" : " ▼") : ""}
                </th>
              )
            ))}
            <th className="px-3 py-2 text-left font-semibold">Action</th>
          </tr>
        </thead>
        <tbody>
          {isEmptyLoading && (
            <tr>
              <td colSpan={COLUMNS.length + 2} className="px-3 py-10 text-center text-ink-secondary">
                Loading clients…
              </td>
            </tr>
          )}
          {rows.map((c) => {
            const dot = STATUS_DOT[c.status] || "bg-ink-muted";
            return (
              <tr key={c.client_id} className="border-b border-line text-sm text-ink-primary hover:bg-surface-page transition-colors">
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Select ${c.name}`}
                    checked={selectedIds.has(c.client_id)}
                    onChange={() => toggleRow(c.client_id)}
                  />
                </td>
                <td className="px-3 py-2">{c.client_id}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="h-8 w-8 shrink-0 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold">
                      {initialsFor(c.company)}
                    </span>
                    <div>
                      <p className="font-medium">{c.name}</p>
                      {c.email && <p className="text-xs text-ink-muted">{c.email}</p>}
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2">{c.company}</td>
                <td className="px-3 py-2 tabular-nums">{c.phone || "—"}</td>
                <td className="px-3 py-2">{c.cert_name}</td>
                <td className="px-3 py-2">{c.cert_id}</td>
                <td className="px-3 py-2 tabular-nums">{c.expiry_date}</td>
                <td className="px-3 py-2 tabular-nums">{formatDaysLeft(c.expiry_date)}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line bg-surface text-ink-primary">
                    <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
                    {c.status}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    {!ALERT_ELIGIBLE.has(c.status) ? (
                      <span className="text-ink-muted">—</span>
                    ) : c.alert_sent_today ? (
                      <span className="px-3 py-1 rounded-full text-xs font-semibold border border-line bg-surface text-ink-primary">
                        ✅ Sent
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSendClick(c)}
                        className="px-3 py-1 rounded-full text-xs font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
                      >
                        Send Alert
                      </button>
                    )}
                    {ALERT_ELIGIBLE.has(c.status) && (
                      <button
                        type="button"
                        onClick={() => onSendEmailClick(c)}
                        disabled={!c.email || !c.email.includes("@")}
                        title={!c.email || !c.email.includes("@") ? "No email on file" : undefined}
                        className="px-3 py-1 rounded-full text-xs font-semibold border border-accent text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
                      >
                        Send Email
                      </button>
                    )}
                    {c.email && (
                      <button
                        type="button"
                        onClick={() => onPreviewEmail(c.client_id)}
                        className="text-xs font-semibold text-accent hover:underline"
                      >
                        Preview Email
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="px-4 py-3 border-t border-line flex items-center justify-between">
        <p className="text-sm text-ink-secondary">
          {isEmptyLoading
            ? ""
            : total === 0
            ? "Showing 0 of 0 clients"
            : `Showing ${start + 1}–${Math.min(start + pageSize, total)} of ${total} clients`}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, currentPage - 1))}
            disabled={currentPage <= 1}
            aria-label="Previous page"
            className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
            disabled={currentPage >= pageCount}
            aria-label="Next page"
            className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}
