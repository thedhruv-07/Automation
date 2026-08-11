import { useEffect, useState } from "react";
import { initialsFor, formatSentAt } from "../sortUtils";
import { downloadNoticeLogCsv } from "../csvExport";

const PAGE_SIZE = 8;

export default function NoticeLogView({ fetchLog }) {
  const [entries, setEntries] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);
  const [refreshing, setRefreshing] = useState(false);

  function load() {
    setRefreshing(true);
    fetchLog()
      .then((data) => {
        setEntries(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setRefreshing(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  let rows = entries;
  if (searchTerm) {
    const term = searchTerm.toLowerCase();
    rows = rows.filter(
      (e) => e.name.toLowerCase().includes(term) || e.company.toLowerCase().includes(term)
    );
  }

  useEffect(() => {
    setPage(1);
  }, [searchTerm]);

  const totalRows = rows.length;
  const pageCount = Math.max(1, Math.ceil(totalRows / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const start = (safePage - 1) * PAGE_SIZE;
  const pageRows = rows.slice(start, start + PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink-primary">Notice Log</h2>
          <p className="text-ink-secondary text-sm mt-1">
            Real record of one-time notice broadcasts actually sent (from notice_sent_log).
          </p>
        </div>
        <div className="flex gap-3">
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search name or company..."
            aria-label="Search notice log"
            className="px-4 py-1.5 rounded-full border border-line bg-surface text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
          />
          <button
            type="button"
            onClick={load}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
          >
            {refreshing ? "Refreshing…" : "Refresh Log"}
          </button>
        </div>
      </div>

      {loadError && (
        <div
          className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2"
          data-testid="notice-log-error"
        >
          Could not load notice log: {loadError}.
        </div>
      )}

      <div className="bg-surface rounded-xl border border-line overflow-hidden">
        <div className="px-4 py-3 border-b border-line flex items-center justify-between">
          <h5 className="font-semibold text-ink-primary">{totalRows} message{totalRows === 1 ? "" : "s"}</h5>
          <button
            type="button"
            onClick={() => downloadNoticeLogCsv(rows)}
            disabled={totalRows === 0}
            className="px-3 py-1.5 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors disabled:opacity-40"
          >
            Export CSV
          </button>
        </div>

        <table className="w-full">
          <thead>
            <tr className="bg-surface-page text-xs uppercase tracking-wide text-ink-secondary border-b-2 border-line">
              <th className="px-3 py-2 text-left font-semibold">Client / Company</th>
              <th className="px-3 py-2 text-left font-semibold">Notice</th>
              <th className="px-3 py-2 text-left font-semibold">Channel</th>
              <th className="px-3 py-2 text-left font-semibold">Sent At</th>
              <th className="px-3 py-2 text-left font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((e, i) => (
              <tr key={`${e.client_id}-${e.notice_id}-${e.channel}-${i}`} className="border-b border-line text-sm text-ink-primary hover:bg-surface-page transition-colors">
                <td className="px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="h-8 w-8 shrink-0 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold">
                      {initialsFor(e.company)}
                    </span>
                    <div>
                      <p className="font-medium">{e.name}</p>
                      <p className="text-xs text-ink-muted">{e.company}{e.phone ? ` · ${e.phone}` : ""}</p>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2">{e.notice_label}</td>
                <td className="px-3 py-2 capitalize">{e.channel}</td>
                <td className="px-3 py-2 tabular-nums">{formatSentAt(e.sent_at)}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line">
                    <span className="h-1.5 w-1.5 rounded-full bg-status-good" aria-hidden="true" />
                    Sent
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="px-4 py-3 border-t border-line flex items-center justify-between">
          <p className="text-sm text-ink-secondary">
            {totalRows === 0
              ? "Showing 0 of 0 messages"
              : `Showing ${start + 1}–${Math.min(start + PAGE_SIZE, totalRows)} of ${totalRows} messages`}
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={safePage <= 1}
              aria-label="Previous page"
              className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
            >
              ‹
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
              disabled={safePage >= pageCount}
              aria-label="Next page"
              className="px-3 py-1.5 rounded-lg border border-line text-ink-secondary hover:text-ink-primary transition-colors disabled:opacity-30"
            >
              ›
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
