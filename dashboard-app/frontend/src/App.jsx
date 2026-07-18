import { useState, useEffect, useCallback } from "react";
import StatCards from "./components/StatCards";
import FilterBar from "./components/FilterBar";
import ClientTable from "./components/ClientTable";
import SendConfirmModal from "./components/SendConfirmModal";
import SendAllConfirmModal from "./components/SendAllConfirmModal";
import Toast from "./components/Toast";
import { getClients, sendAlert, sendAllAlerts } from "./api";

const ALERT_ELIGIBLE_STATUSES = new Set(["CRITICAL", "URGENT", "DUE SOON"]);

export default function App() {
  const [clients, setClients] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [activeStatus, setActiveStatus] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [sortKey, setSortKey] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [pendingClient, setPendingClient] = useState(null);
  const [toast, setToast] = useState(null);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkSending, setBulkSending] = useState(false);

  const loadClients = useCallback(() => {
    getClients()
      .then((data) => {
        setClients(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  function handleSort(key) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  async function handleConfirmSend() {
    const client = pendingClient;
    setPendingClient(null);
    try {
      await sendAlert(client.client_id);
      setToast({ type: "success", message: `Sent to ${client.name}` });
      loadClients();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    }
  }

  const eligibleCount = clients.filter(
    (c) => ALERT_ELIGIBLE_STATUSES.has(c.status) && !c.alert_sent_today
  ).length;

  async function handleConfirmSendAll() {
    setBulkModalOpen(false);
    setBulkSending(true);
    try {
      const results = await sendAllAlerts();
      const sent = results.filter((r) => r.action === "sent").length;
      const skipped = results.filter((r) => r.action === "skipped_duplicate").length;
      const failed = results.filter((r) => r.action === "failed").length;
      setToast({
        type: failed > 0 ? "error" : "success",
        message: `${sent} sent, ${skipped} already sent, ${failed} failed`,
      });
      loadClients();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    } finally {
      setBulkSending(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold bg-gradient-to-r from-sky-500 to-indigo-500 bg-clip-text text-transparent">
          Absolute Veritas
        </h1>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={loadClients}
            className="px-4 py-2 rounded-full text-sm font-semibold text-slate-600 border border-slate-200 bg-white"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setBulkModalOpen(true)}
            disabled={bulkSending || eligibleCount === 0}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-gradient-to-r from-sky-500 to-indigo-500 disabled:opacity-50"
          >
            Send All Eligible
          </button>
        </div>
      </div>

      {loadError && (
        <div className="text-sm text-rose-600" data-testid="load-error">
          Could not load clients: {loadError}. Is the backend running?
        </div>
      )}

      <StatCards clients={clients} />
      <FilterBar
        activeStatus={activeStatus}
        onStatusChange={setActiveStatus}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
      />
      <ClientTable
        clients={clients}
        activeStatus={activeStatus}
        searchTerm={searchTerm}
        sortKey={sortKey}
        sortAsc={sortAsc}
        onSort={handleSort}
        onSendClick={setPendingClient}
      />
      <SendConfirmModal
        client={pendingClient}
        onConfirm={handleConfirmSend}
        onCancel={() => setPendingClient(null)}
      />
      <SendAllConfirmModal
        open={bulkModalOpen}
        eligibleCount={eligibleCount}
        onConfirm={handleConfirmSendAll}
        onCancel={() => setBulkModalOpen(false)}
      />
      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
