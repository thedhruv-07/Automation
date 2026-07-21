import { useState, useEffect, useCallback, useMemo } from "react";
import Sidebar from "./components/Sidebar";
import StatCards from "./components/StatCards";
import RenewalsByMonthChart from "./components/RenewalsByMonthChart";
import FilterBar from "./components/FilterBar";
import ClientDataFilters from "./components/ClientDataFilters";
import ClientTable from "./components/ClientTable";
import ExcelSyncView from "./components/ExcelSyncView";
import MessageLogView from "./components/MessageLogView";
import WhatsAppSettingsView from "./components/WhatsAppSettingsView";
import SendConfirmModal from "./components/SendConfirmModal";
import SendAllConfirmModal from "./components/SendAllConfirmModal";
import SendSelectedConfirmModal from "./components/SendSelectedConfirmModal";
import EmailPreviewModal from "./components/EmailPreviewModal";
import Toast from "./components/Toast";
import {
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, mergeClientsFile, getMessageLog,
  getSettingsInfo, getEmailPreview,
} from "./api";

const ALERT_ELIGIBLE_STATUSES = new Set(["CRITICAL", "URGENT", "DUE SOON", "EXPIRED"]);

export default function App() {
  const [activeView, setActiveView] = useState("clientData");
  const [clients, setClients] = useState([]);
  const [clientsLoading, setClientsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [activeStatus, setActiveStatus] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [certType, setCertType] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
  const [sortKey, setSortKey] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [pendingClient, setPendingClient] = useState(null);
  const [toast, setToast] = useState(null);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkSending, setBulkSending] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingSelected, setPendingSelected] = useState([]);
  const [bulkSelectedSending, setBulkSelectedSending] = useState(false);
  const [previewClientId, setPreviewClientId] = useState(null);

  const loadClients = useCallback(() => {
    setClientsLoading(true);
    return getClients()
      .then((data) => {
        setClients(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setClientsLoading(false));
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  const certOptions = useMemo(
    () => Array.from(new Set(clients.map((c) => c.cert_name))).sort(),
    [clients]
  );

  function handleRefreshClick() {
    setRefreshing(true);
    loadClients().finally(() => setRefreshing(false));
  }

  function handleClearAllFilters() {
    setActiveStatus("ALL");
    setCertType("ALL");
    setExpiryBefore("");
  }

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

  async function handleConfirmSendSelected() {
    const selected = pendingSelected;
    setPendingSelected([]);
    setBulkSelectedSending(true);
    let sent = 0;
    let skipped = 0;
    let failed = 0;
    for (const client of selected) {
      if (!ALERT_ELIGIBLE_STATUSES.has(client.status) || client.alert_sent_today) {
        skipped += 1;
        continue;
      }
      try {
        await sendAlert(client.client_id);
        sent += 1;
      } catch {
        failed += 1;
      }
    }
    setToast({
      type: failed > 0 ? "error" : "success",
      message: `${sent} sent, ${skipped} already sent, ${failed} failed`,
    });
    loadClients();
    setBulkSelectedSending(false);
  }

  async function handleUploadClients(file) {
    try {
      const result = await uploadClientsFile(file);
      setToast({
        type: "success",
        message: `Imported ${result.row_count} client${result.row_count === 1 ? "" : "s"}.`,
      });
      loadClients();
      return result;
    } catch (err) {
      setToast({ type: "error", message: err.message });
      throw err;
    }
  }

  async function handleMergeClients(file) {
    try {
      const result = await mergeClientsFile(file);
      setToast({
        type: "success",
        message: `Merged — added ${result.added} new client${result.added === 1 ? "" : "s"}, `
          + `skipped ${result.skipped_duplicates} already on file (${result.row_count} total).`,
      });
      loadClients();
      return result;
    } catch (err) {
      setToast({ type: "error", message: err.message });
      throw err;
    }
  }

  return (
    <div className="min-h-screen bg-surface-page flex">
      <Sidebar activeView={activeView} onNavigate={setActiveView} />

      <div className="flex-1 min-w-0">
        <header className="h-16 sticky top-0 z-10 bg-surface border-b border-line flex items-center justify-between px-6">
          <h1 className="text-lg font-bold text-ink-primary">Certification Manager</h1>
          <div className="flex items-center gap-3">
            {activeView === "clientData" && (
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search name or company..."
                aria-label="Search name or company"
                className="w-72 px-4 py-1.5 rounded-full border border-line bg-surface-page text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40 focus:border-accent"
              />
            )}
            <button
              type="button"
              onClick={handleRefreshClick}
              aria-label="Refresh"
              className="p-2 rounded-lg text-ink-secondary hover:text-ink-primary hover:bg-surface-page transition-colors"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`h-5 w-5 ${refreshing ? "animate-spin" : ""}`}
                aria-hidden="true"
              >
                <path d="M17 2l4 4-4 4M3 12a9 9 0 0115-6.7M7 22l-4-4 4-4M21 12a9 9 0 01-15 6.7" />
              </svg>
            </button>
            {activeView === "clientData" && (
              <button
                type="button"
                onClick={() => setBulkModalOpen(true)}
                disabled={bulkSending || eligibleCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Send All Eligible
              </button>
            )}
          </div>
        </header>

        <main className="p-6 space-y-6 max-w-[1400px] mx-auto">
          {loadError && (
            <div
              className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2"
              data-testid="load-error"
            >
              Could not load clients: {loadError}. Is the backend running?
            </div>
          )}

          {activeView === "dashboard" && (
            <>
              <div>
                <h2 className="text-2xl font-bold text-ink-primary">Dashboard Overview</h2>
                <p className="text-ink-secondary text-sm mt-1">
                  Real-time status of all active and upcoming certification renewals.
                </p>
              </div>
              <StatCards clients={clients} />
              <RenewalsByMonthChart clients={clients} />
            </>
          )}

          {activeView === "clientData" && (
            <>
              <div>
                <h2 className="text-2xl font-bold text-ink-primary">Client Data</h2>
                <p className="text-ink-secondary text-sm mt-1">
                  Manage and track certification statuses for all registered clients.
                </p>
              </div>
              <FilterBar activeStatus={activeStatus} onStatusChange={setActiveStatus} />
              <ClientDataFilters
                certOptions={certOptions}
                certType={certType}
                onCertTypeChange={setCertType}
                expiryBefore={expiryBefore}
                onExpiryBeforeChange={setExpiryBefore}
                onClearAll={handleClearAllFilters}
              />
              <ClientTable
                clients={clients}
                loading={clientsLoading}
                activeStatus={activeStatus}
                searchTerm={searchTerm}
                certType={certType}
                expiryBefore={expiryBefore}
                sortKey={sortKey}
                sortAsc={sortAsc}
                onSort={handleSort}
                onSendClick={setPendingClient}
                onSendSelected={bulkSelectedSending ? () => {} : setPendingSelected}
                onPreviewEmail={setPreviewClientId}
              />
            </>
          )}

          {activeView === "excelSync" && (
            <ExcelSyncView onUpload={handleUploadClients} onMerge={handleMergeClients} />
          )}

          {activeView === "messageLog" && <MessageLogView fetchLog={getMessageLog} />}

          {activeView === "whatsappSettings" && <WhatsAppSettingsView fetchInfo={getSettingsInfo} />}
        </main>
      </div>

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
      <SendSelectedConfirmModal
        clients={pendingSelected}
        onConfirm={handleConfirmSendSelected}
        onCancel={() => setPendingSelected([])}
      />
      <EmailPreviewModal
        clientId={previewClientId}
        fetchPreview={getEmailPreview}
        onClose={() => setPreviewClientId(null)}
      />
      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  );
}
