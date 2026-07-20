import { useEffect, useRef, useState } from "react";

export default function EmailPreviewModal({ clientId, fetchPreview, onClose }) {
  const [preview, setPreview] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    if (!clientId) {
      setPreview(null);
      setLoadError(null);
      return;
    }
    fetchPreview(clientId)
      .then((data) => {
        setPreview(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message));
  }, [clientId, fetchPreview]);

  useEffect(() => {
    if (!clientId) return;
    closeButtonRef.current?.focus();
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [clientId, onClose]);

  if (!clientId) return null;

  return (
    <div
      className="fixed inset-0 bg-ink-primary/50 flex items-center justify-center z-50 p-6"
      data-testid="email-preview-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="email-preview-title"
    >
      <div className="bg-surface rounded-2xl shadow-xl border border-line w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-line">
          <h3 id="email-preview-title" className="text-lg font-bold text-ink-primary">Email Preview</h3>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-secondary hover:text-ink-primary transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-4 overflow-y-auto flex-1">
          {loadError && (
            <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
              Could not load email preview: {loadError}.
            </div>
          )}
          {preview && (
            <>
              <p className="text-sm text-ink-secondary mb-3">
                <span className="font-semibold text-ink-primary">Subject:</span> {preview.subject}
              </p>
              <iframe
                title="Email preview"
                srcDoc={preview.html}
                className="w-full h-[500px] border border-line rounded-lg bg-white"
              />
              <p className="text-xs text-ink-muted mt-3">
                Preview only — no email has been sent.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
