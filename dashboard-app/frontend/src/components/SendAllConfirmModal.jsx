import { useEffect, useRef, useState } from "react";

export default function SendAllConfirmModal({ open, eligibleCount, onConfirm, onCancel }) {
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
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full">
        <h3 id="send-all-confirm-title" className="text-lg font-bold text-slate-800 mb-2">
          Send bulk renewal alerts?
        </h3>
        <p className="text-sm text-slate-600 mb-6">
          Send a real WhatsApp renewal alert to all <strong>{eligibleCount}</strong> eligible
          client{eligibleCount === 1 ? "" : "s"} (Critical, Urgent, or Due Soon, not yet sent today)?
        </p>
        <div className="flex justify-end gap-3">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200"
          >
            Cancel
          </button>
          <button
            ref={confirmButtonRef}
            type="button"
            onClick={handleConfirmClick}
            disabled={confirming}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 disabled:opacity-50"
          >
            Confirm Send All
          </button>
        </div>
      </div>
    </div>
  );
}
