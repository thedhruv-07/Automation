function StatusBadge({ sent }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line ${
        sent ? "text-status-good" : "text-ink-muted"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${sent ? "bg-status-good" : "bg-ink-muted"}`} aria-hidden="true" />
      {sent ? "Sent" : "Not yet"}
    </span>
  );
}

export default function NoticeClientsTable({ page, loading, onPageChange }) {
  const { rows, total, page: currentPage, page_size: pageSize } = page;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const start = (currentPage - 1) * pageSize;
  const isEmptyLoading = loading && rows.length === 0;

  return (
    <div className="bg-surface rounded-xl border border-line overflow-hidden">
      <table className="w-full" data-testid="notice-clients-table">
        <thead>
          <tr className="bg-surface-page text-xs uppercase tracking-wide text-ink-secondary border-b-2 border-line">
            <th className="px-3 py-2 text-left font-semibold">Client ID</th>
            <th className="px-3 py-2 text-left font-semibold">Full Name</th>
            <th className="px-3 py-2 text-left font-semibold">Company</th>
            <th className="px-3 py-2 text-left font-semibold">Email</th>
            <th className="px-3 py-2 text-left font-semibold">Phone</th>
            <th className="px-3 py-2 text-left font-semibold">WhatsApp</th>
            <th className="px-3 py-2 text-left font-semibold">Email Sent</th>
          </tr>
        </thead>
        <tbody>
          {isEmptyLoading && (
            <tr>
              <td colSpan={7} className="px-3 py-10 text-center text-ink-secondary">
                Loading clients…
              </td>
            </tr>
          )}
          {rows.map((c) => (
            <tr key={c.client_id} className="border-b border-line text-sm text-ink-primary hover:bg-surface-page transition-colors">
              <td className="px-3 py-2">{c.client_id}</td>
              <td className="px-3 py-2">{c.name}</td>
              <td className="px-3 py-2">{c.company}</td>
              <td className="px-3 py-2">{c.email || "—"}</td>
              <td className="px-3 py-2 tabular-nums">{c.phone || "—"}</td>
              <td className="px-3 py-2"><StatusBadge sent={c.notice_sent_whatsapp} /></td>
              <td className="px-3 py-2"><StatusBadge sent={c.notice_sent_email} /></td>
            </tr>
          ))}
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
