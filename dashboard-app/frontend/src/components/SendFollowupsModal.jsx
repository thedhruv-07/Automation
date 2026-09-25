import { useEffect, useState } from "react";

export default function SendFollowupsModal({
  open, eligible, remainingQuota, separateKey, job, onConfirm, onCancel,
}) {
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (open) setConfirming(false);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm();
  }

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50"
      data-testid="send-followups-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="send-followups-title"
    >
      <div className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full border border-line">
        <h3 id="send-followups-title" className="text-lg font-bold text-ink-primary mb-2">
          Send follow-up emails?
        </h3>
        {job ? (
          <div className="mb-2">
            <p className="text-sm text-ink-secondary mb-3">
              {job.sent} sent, {job.skipped_no_email} no email, {job.failed} failed
              {job.total ? ` (of ${job.total})` : ""}
            </p>
            {job.error && (
              <div
                role="alert"
                className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2 mb-3"
              >
                Send failed: {job.error}
              </div>
            )}
            {job.done ? (
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={onCancel}
                  className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors"
                >
                  Close
                </button>
              </div>
            ) : (
              <div className="w-full bg-surface-page rounded-full h-2 overflow-hidden">
                <div
                  className="h-full bg-accent transition-all"
                  style={{ width: `${job.total ? Math.round(((job.sent + job.skipped_no_email + job.failed) / job.total) * 100) : 0}%` }}
                />
              </div>
            )}
          </div>
        ) : (
          <>
            <p className="text-sm text-ink-secondary mb-3">
              Send a follow-up to <strong>{eligible} client{eligible === 1 ? "" : "s"}</strong> who
              were emailed 4+ days ago and still haven't renewed.
            </p>
            {remainingQuota < eligible && (
              <p className="text-sm text-ink-secondary mb-3">
                Only {remainingQuota} can go out today (daily Brevo limit) — the rest stay due for tomorrow.
              </p>
            )}
            {separateKey && (
              <p className="text-xs text-ink-muted mb-3">Sent through the separate Brevo account set up for follow-ups.</p>
            )}
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={onCancel}
                className="px-4 py-2 rounded-full text-sm font-semibold text-ink-primary border border-line hover:bg-surface-page transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                data-confirm
                onClick={handleConfirmClick}
                disabled={confirming}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Send Follow-ups
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
