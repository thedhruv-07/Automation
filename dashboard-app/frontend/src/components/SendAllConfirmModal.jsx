import { useEffect, useRef, useState } from "react";

export default function SendAllConfirmModal({
  open, eligibleCount, filteredCount = 0, channel = "whatsapp", onConfirm, onCancel, job = null,
  noticeLabel = null, singleScope = false,
}) {
  const [confirming, setConfirming] = useState(false);
  const [scope, setScope] = useState("all");
  const cancelButtonRef = useRef(null);
  const confirmButtonRef = useRef(null);
  const closeButtonRef = useRef(null);
  const scopeAllRadioRef = useRef(null);
  const scopeFilteredRadioRef = useRef(null);

  useEffect(() => {
    if (open) {
      setConfirming(false);
      setScope("all");
      cancelButtonRef.current?.focus();
    }
  }, [open]);

  // Once the job finishes, the Cancel/Confirm buttons are long gone and the
  // Close button mounts in their place — move focus there so it doesn't get
  // silently dropped to <body>.
  useEffect(() => {
    if (open && job?.done) {
      closeButtonRef.current?.focus();
    }
  }, [open, job?.done]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") {
        onCancel();
      } else if (e.key === "Tab") {
        // Only one of these branches is ever mounted at a time (no job: the
        // two scope radios + Cancel + Confirm; job.done: Close; job in
        // progress: neither), so filtering for whichever refs currently
        // point at a live DOM node gives us the correct focusable set, in
        // visual order, for whatever is rendered now.
        //
        // The two scope radios share name="send-all-scope", which makes
        // them a single native radio group — browsers only give a Tab stop
        // to one radio per group (arrow keys move within it), so relying on
        // default Tab traversal would silently skip the unchecked radio.
        // To keep both radios individually reachable we take over every Tab
        // press here and move focus explicitly, rather than only
        // intervening at the first/last boundary.
        const focusable = [
          scopeAllRadioRef.current,
          scopeFilteredRadioRef.current,
          cancelButtonRef.current,
          confirmButtonRef.current,
          closeButtonRef.current,
        ].filter(Boolean);
        if (focusable.length === 0) {
          // Nothing focusable is currently in the dialog (e.g. progress bar
          // only) — block Tab so focus can't slip out into the page behind
          // the overlay.
          e.preventDefault();
          return;
        }
        e.preventDefault();
        const currentIndex = focusable.indexOf(document.activeElement);
        let nextIndex;
        if (e.shiftKey) {
          nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
        } else {
          nextIndex = currentIndex === -1 || currentIndex === focusable.length - 1 ? 0 : currentIndex + 1;
        }
        focusable[nextIndex].focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const selectedCount = singleScope ? filteredCount : (scope === "filtered" ? filteredCount : eligibleCount);

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm(singleScope ? undefined : scope);
  }

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50"
      data-testid={`send-all-confirm-modal-${channel}`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="send-all-confirm-title"
    >
      <div className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full border border-line">
        <h3 id="send-all-confirm-title" className="text-lg font-bold text-ink-primary mb-2">
          {noticeLabel ? `Send "${noticeLabel}"?` : "Send bulk renewal alerts?"}
        </h3>
        {job ? (
          <div className="mb-2">
            <p className="text-sm text-ink-secondary mb-3">
              {job.sent} sent, {job.skipped} skipped, {job.failed} failed
              {typeof job.skipped_no_email === "number" ? ` (${job.skipped_no_email} no email)` : ""}
              {typeof job.skipped_no_template === "number" ? ` (${job.skipped_no_template} no template)` : ""}
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
            {job.done && job.failed > 0 && (
              <div
                role="alert"
                className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2 mb-3"
              >
                ⚠ {job.failed} message{job.failed === 1 ? "" : "s"} failed to send. This can happen
                when WhatsApp holds or blocks delivery (e.g. low account quality) rather than a
                code error — check WhatsApp Business Manager for details before retrying.
              </div>
            )}
            {job.done ? (
              <div className="flex justify-end">
                <button
                  ref={closeButtonRef}
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
            <p className="text-sm text-ink-secondary mb-3">
              {noticeLabel
                ? `Send "${noticeLabel}" via ${channel === "email" ? "email" : "WhatsApp"}`
                : (channel === "email" ? "Send a renewal email" : "Send a real WhatsApp renewal alert")} to:
            </p>
            {singleScope ? (
              <p className="text-sm text-ink-secondary mb-6">
                {`${filteredCount} client${filteredCount === 1 ? "" : "s"} matching your current filters.`}
              </p>
            ) : (
              <div className="mb-6 space-y-2">
                <label className="flex items-center gap-2 text-sm text-ink-primary">
                  <input
                    ref={scopeAllRadioRef}
                    type="radio"
                    name="send-all-scope"
                    checked={scope === "all"}
                    onChange={() => setScope("all")}
                  />
                  All eligible clients (<strong>{eligibleCount}</strong>)
                </label>
                <label className="flex items-center gap-2 text-sm text-ink-primary">
                  <input
                    ref={scopeFilteredRadioRef}
                    type="radio"
                    name="send-all-scope"
                    checked={scope === "filtered"}
                    onChange={() => setScope("filtered")}
                  />
                  Currently filtered view (<strong>{filteredCount}</strong>)
                </label>
              </div>
            )}
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
                disabled={confirming || selectedCount === 0}
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
