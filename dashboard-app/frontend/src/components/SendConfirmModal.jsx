import { useEffect, useRef, useState } from "react";

export default function SendConfirmModal({ client, channel = "whatsapp", onConfirm, onCancel }) {
  const [confirming, setConfirming] = useState(false);
  const cancelButtonRef = useRef(null);
  const confirmButtonRef = useRef(null);

  useEffect(() => {
    if (client) {
      setConfirming(false);
      cancelButtonRef.current?.focus();
    }
  }, [client]);

  useEffect(() => {
    if (!client) return;
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
  }, [client, onCancel]);

  if (!client) return null;

  function handleConfirmClick() {
    if (confirming) return;
    setConfirming(true);
    onConfirm();
  }

  return (
    <div
      className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50"
      data-testid="send-confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="send-confirm-title"
    >
      <div className="bg-surface rounded-2xl shadow-xl p-6 max-w-sm w-full border border-line">
        <h3 id="send-confirm-title" className="text-lg font-bold text-ink-primary mb-2">Send renewal alert?</h3>
        <p className="text-sm text-ink-secondary mb-6">
          {channel === "email"
            ? <>Send a renewal email to <strong>{client.name}</strong> at <strong>{client.company}</strong>?</>
            : <>Send a real WhatsApp renewal alert to <strong>{client.name}</strong> at <strong>{client.company}</strong>?</>}
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
            Confirm Send
          </button>
        </div>
      </div>
    </div>
  );
}
