import { useState } from "react";

export default function RenewalsImport({ importRenewals }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);

  function reset() {
    setFile(null);
    setPreview(null);
    setDone(null);
    setError(null);
  }

  async function run(apply) {
    setBusy(true);
    setError(null);
    try {
      const result = await importRenewals(file, apply);
      if (apply) {
        setDone(result);
        setPreview(null);
      } else {
        setPreview(result);
        setDone(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  return (
    <div className="bg-surface border border-line rounded-xl p-6 space-y-4">
      <div>
        <h3 className="text-base font-bold text-ink-primary">Import renewals from Manak Online</h3>
        <p className="text-sm text-ink-secondary mt-1">
          Upload a &quot;List of Licences&quot; report (.xlsx) downloaded from Manak Online. Clients whose
          licence now shows a later validity date are moved to that date and marked renewed, so they are
          skipped by renewal emails and follow-ups. Nothing changes until you confirm.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept=".xlsx"
          data-testid="renewals-file-input"
          onChange={(e) => {
            setFile(e.target.files?.[0] || null);
            setPreview(null);
            setDone(null);
            setError(null);
          }}
          className="text-sm text-ink-secondary"
        />
        <button
          type="button"
          onClick={() => run(false)}
          disabled={!file || busy}
          className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
        >
          Check report
        </button>
      </div>

      {error && (
        <div role="alert" className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {done && (
        <p className="text-sm text-ink-primary bg-surface-page border border-line rounded-lg px-4 py-2">
          ✅ Marked {plural(done.renewed, "client")} as renewed.
        </p>
      )}

      {preview && (
        <div className="space-y-3">
          <p className="text-sm text-ink-secondary">
            {plural(preview.report_rows, "licence")} in the report · {preview.matched} matched your clients ·{" "}
            {preview.already_current} already up to date · {preview.not_found} not in your roster
            {preview.unreadable > 0 && ` · ${preview.unreadable} rows could not be read`}
          </p>

          {preview.renewed === 0 ? (
            <p className="text-sm text-ink-primary">No renewals found in this report.</p>
          ) : (
            <>
              <p className="text-sm font-semibold text-ink-primary">
                {plural(preview.renewed, "client")} {preview.renewed === 1 ? "has" : "have"} renewed:
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-ink-muted">
                      <th className="py-1 pr-4">Client</th>
                      <th className="py-1 pr-4">Licence</th>
                      <th className="py-1">Expiry</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.renewed_sample.map((r) => (
                      <tr key={r.client_id} className="border-t border-line">
                        <td className="py-1 pr-4">
                          <div className="font-medium text-ink-primary">{r.name}</div>
                          <div className="text-xs text-ink-muted">{r.company}</div>
                        </td>
                        <td className="py-1 pr-4 tabular-nums">{r.cert_id}</td>
                        <td className="py-1 tabular-nums">{r.old_expiry} → {r.new_expiry} ({r.new_status})</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.renewed > preview.renewed_sample.length && (
                <p className="text-xs text-ink-muted">
                  Showing the first {preview.renewed_sample.length} of {preview.renewed}.
                </p>
              )}
            </>
          )}

          <div className="flex gap-3">
            {preview.renewed > 0 && (
              <button
                type="button"
                onClick={() => run(true)}
                disabled={busy}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Apply {plural(preview.renewed, "renewal")}
              </button>
            )}
            <button
              type="button"
              onClick={reset}
              disabled={busy}
              className="px-4 py-2 rounded-full text-sm font-semibold text-ink-primary border border-line hover:bg-surface-page transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
