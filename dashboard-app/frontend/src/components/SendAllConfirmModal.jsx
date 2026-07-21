import { useEffect, useRef, useState } from "react";

export default function SendAllConfirmModal({ open, eligibleCount, onConfirm, onCancel, job = null }) {
  const [confirming, setConfirming] = useState(false);
  const cancelButtonRef = useRef(null);
  const confirmButtonRef = useRef(null);

  useEffect(() => {
    if (open) {
      setConfirming(false);
      cancelButtonRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") {
        onCancel();
      } else if (e.key === "Tab") {
        const first = cancelButtonRef.current;
        const last = confirmButtonRef.current;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
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
      data-testid="send-all-confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="send-all-confirm-title"
    >
      <div className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full border border-line">
        <h3 id="send-all-confirm-title" className="text-lg font-bold text-ink-primary mb-2">
          Send bulk renewal alerts?
        </h3>
        {job ? (
          <div className="mb-2">
            <p className="text-sm text-ink-secondary mb-3">
              {job.sent} sent, {job.skipped} skipped, {job.failed} failed
              {job.total ? ` (of ${job.total})` : ""}
            </p>
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
                  style={{ width: `${job.total ? Math.round(((job.sent + job.skipped + job.failed) / job.total) * 100) : 0}%` }}
                />
              </div>
            )}
          </div>
        ) : (
          <>
            <p className="text-sm text-ink-secondary mb-6">
              Send a real WhatsApp renewal alert to all <strong>{eligibleCount}</strong> eligible
              client{eligibleCount === 1 ? "" : "s"} (Critical, Urgent, Due Soon, or Expired, not yet sent today)?
            </p>
            <div className="flex justify-end gap-3">
              <button
                ref={cancelButtonRef}
                type="button"
                onClick={onCancel}
                className="px-4 py-2 rounded-full text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
              >
                Cancel
              </button>
              <button
                ref={confirmButtonRef}
                type="button"
                onClick={handleConfirmClick}
                disabled={confirming}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Confirm Send All
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
