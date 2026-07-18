export default function SendConfirmModal({ client, onConfirm, onCancel }) {
  if (!client) return null;
  return (
    <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center z-50" data-testid="send-confirm-modal">
      <div className="bg-white rounded-2xl shadow-xl p-6 max-w-sm w-full">
        <h3 className="text-lg font-bold text-slate-800 mb-2">Send renewal alert?</h3>
        <p className="text-sm text-slate-600 mb-6">
          Send a real WhatsApp renewal alert to <strong>{client.name}</strong> at{" "}
          <strong>{client.company}</strong>?
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500"
          >
            Confirm Send
          </button>
        </div>
      </div>
    </div>
  );
}
