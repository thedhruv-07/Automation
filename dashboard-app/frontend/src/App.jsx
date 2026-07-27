import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
  getClients, getStats, sendAlert, sendAllAlerts, getSendAllStatus, uploadClientsFile,
  mergeClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
} from "./api";

const ALERT_ELIGIBLE_STATUSES = new Set(["CRITICAL", "URGENT", "DUE SOON", "EXPIRED"]);
const PAGE_SIZE = 8;
const SEARCH_DEBOUNCE_MS = 300;
const BULK_JOB_POLL_MS = 500;

export default function App({ onLogout } = {}) {
  const [activeView, setActiveView] = useState("clientData");
  const [page, setPage] = useState({ rows: [], total: 0, page: 1, page_size: PAGE_SIZE });
  const [clientsLoading, setClientsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [stats, setStats] = useState(null);
  const [activeStatus, setActiveStatus] = useState("ALL");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [certType, setCertType] = useState("ALL");
  const [scheme, setScheme] = useState("ALL");
  const [expiryBefore, setExpiryBefore] = useState("");
  const [pageNum, setPageNum] = useState(1);
  const [sortKey, setSortKey] = useState(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [pendingClient, setPendingClient] = useState(null);
  const [toast, setToast] = useState(null);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [sendAllJob, setSendAllJob] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingSelected, setPendingSelected] = useState([]);
  const [bulkSelectedSending, setBulkSelectedSending] = useState(false);
  const [previewClientId, setPreviewClientId] = useState(null);
  const [pendingEmailClient, setPendingEmailClient] = useState(null);
  const [emailBulkModalOpen, setEmailBulkModalOpen] = useState(false);
  const [sendAllEmailJob, setSendAllEmailJob] = useState(null);
  const [filteredEligibleCount, setFilteredEligibleCount] = useState({ whatsapp: 0, email: 0 });

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchTerm), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  useEffect(() => {
    setPageNum(1);
  }, [activeStatus, debouncedSearch, certType, scheme, expiryBefore, sortKey, sortAsc]);

  const queryParams = useMemo(() => ({
    page: pageNum, pageSize: PAGE_SIZE, status: activeStatus, certType, scheme,
    expiryBefore, search: debouncedSearch, sortKey, sortDir: sortAsc ? "asc" : "desc",
  }), [pageNum, activeStatus, certType, scheme, expiryBefore, debouncedSearch, sortKey, sortAsc]);

  const requestIdRef = useRef(0);

  const loadClients = useCallback(() => {
    const requestId = ++requestIdRef.current;
    setClientsLoading(true);
    return getClients(queryParams)
      .then((data) => {
        if (requestId !== requestIdRef.current) return; // a newer request has since been issued — ignore this stale response
        setPage(data);
        setLoadError(null);
      })
      .catch((err) => {
        if (requestId !== requestIdRef.current) return;
        setLoadError(err.message);
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setClientsLoading(false);
      });
  }, [queryParams]);

  const loadStats = useCallback(() => {
    return getStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    loadClients();
  }, [loadClients]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const eligibleCountRequestIdRef = useRef(0);

  useEffect(() => {
    if (!bulkModalOpen && !emailBulkModalOpen) return;
    const requestId = ++eligibleCountRequestIdRef.current;
    getEligibleCount({ status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch })
      .then((data) => {
        if (requestId !== eligibleCountRequestIdRef.current) return; // a newer request has since been issued — ignore this stale response
        setFilteredEligibleCount(data);
      })
      .catch(() => {});
  }, [bulkModalOpen, emailBulkModalOpen, activeStatus, certType, scheme, expiryBefore, debouncedSearch]);

  const certOptions = stats?.cert_types || [];
  const schemeOptions = stats?.schemes || [];

  function handleRefreshClick() {
    setRefreshing(true);
    Promise.all([loadClients(), loadStats()]).finally(() => setRefreshing(false));
  }

  function handleClearAllFilters() {
    setActiveStatus("ALL");
    setCertType("ALL");
    setScheme("ALL");
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
      loadStats();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    }
  }

  async function handleConfirmSendEmail() {
    const client = pendingEmailClient;
    setPendingEmailClient(null);
    try {
      await sendEmailAlert(client.client_id);
      setToast({ type: "success", message: `Emailed ${client.name}` });
      loadClients();
      loadStats();
    } catch (err) {
      setToast({ type: "error", message: err.message });
    }
  }

  const eligibleCount = stats?.eligible_not_sent_today || 0;
  const jobPollRef = useRef(null);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);

  async function handleConfirmSendAll(sendScope) {
    try {
      const filters = sendScope === "filtered"
        ? { status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch }
        : {};
      const { job_id: jobId } = await sendAllAlerts(filters);
      setSendAllJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
      jobPollRef.current = setInterval(async () => {
        try {
          const status = await getSendAllStatus(jobId);
          setSendAllJob(status);
          if (status.done) {
            clearInterval(jobPollRef.current);
            loadClients();
            loadStats();
          }
        } catch (err) {
          clearInterval(jobPollRef.current);
          setSendAllJob(null);
          setBulkModalOpen(false);
          setToast({ type: "error", message: err.message });
        }
      }, BULK_JOB_POLL_MS);
    } catch (err) {
      setBulkModalOpen(false);
      setToast({ type: "error", message: err.message });
    }
  }

  function handleCloseSendAllModal() {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    setSendAllJob(null);
    setBulkModalOpen(false);
  }

  const eligibleEmailCount = stats?.eligible_not_emailed_today || 0;
  const emailJobPollRef = useRef(null);

  useEffect(() => {
    return () => {
      if (emailJobPollRef.current) clearInterval(emailJobPollRef.current);
    };
  }, []);

  async function handleConfirmSendAllEmails(sendScope) {
    try {
      const filters = sendScope === "filtered"
        ? { status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch }
        : {};
      const { job_id: jobId } = await sendAllEmailAlerts(filters);
      setSendAllEmailJob({ total: 0, sent: 0, skipped: 0, skipped_no_email: 0, failed: 0, done: false });
      emailJobPollRef.current = setInterval(async () => {
        try {
          const status = await getSendAllEmailsStatus(jobId);
          setSendAllEmailJob(status);
          if (status.done) {
            clearInterval(emailJobPollRef.current);
            loadClients();
            loadStats();
          }
        } catch (err) {
          clearInterval(emailJobPollRef.current);
          setSendAllEmailJob(null);
          setEmailBulkModalOpen(false);
          setToast({ type: "error", message: err.message });
        }
      }, BULK_JOB_POLL_MS);
    } catch (err) {
      setEmailBulkModalOpen(false);
      setToast({ type: "error", message: err.message });
    }
  }

  function handleCloseSendAllEmailsModal() {
    if (emailJobPollRef.current) clearInterval(emailJobPollRef.current);
    setSendAllEmailJob(null);
    setEmailBulkModalOpen(false);
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
    loadStats();
    setBulkSelectedSending(false);
  }

  async function handleUploadClients(file, importFormat) {
    try {
      const result = await uploadClientsFile(file, importFormat);
      setToast({
        type: "success",
        message: `Imported ${result.row_count} client${result.row_count === 1 ? "" : "s"}.`,
      });
      loadClients();
      loadStats();
      return result;
    } catch (err) {
      setToast({ type: "error", message: err.message });
      throw err;
    }
  }

  async function handleMergeClients(file, importFormat) {
    try {
      const result = await mergeClientsFile(file, importFormat);
      setToast({
        type: "success",
        message: `Merged — added ${result.added} new client${result.added === 1 ? "" : "s"}, `
          + `skipped ${result.skipped_duplicates} already on file (${result.row_count} total).`,
      });
      loadClients();
      loadStats();
      return result;
    } catch (err) {
      setToast({ type: "error", message: err.message });
      throw err;
    }
  }

  return (
    <div className="min-h-screen bg-surface-page flex">
      <Sidebar activeView={activeView} onNavigate={setActiveView} onLogout={onLogout} />

      <div className="flex-1 min-w-0">
        <header className="h-16 sticky top-0 z-10 bg-surface border-b border-line flex items-center justify-between px-6">
          <h1 className="text-lg font-bold text-ink-primary">Certification Manager</h1>
          <div className="flex items-center gap-3">
            {activeView === "clientData" && (
              <input
                type="text"
                value={searchTerm}
                onChange={(e
                  
                ) => setSearchTerm(e.target.value)}
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
                disabled={(sendAllJob !== null && !sendAllJob.done) || eligibleCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
              >
                Send All Eligible
              </button>
            )}
            {activeView === "clientData" && (
              <button
                type="button"
                onClick={() => setEmailBulkModalOpen(true)}
                disabled={(sendAllEmailJob !== null && !sendAllEmailJob.done) || eligibleEmailCount === 0}
                className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/10 transition-colors disabled:opacity-50"
              >
                Send All Emails
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
              <StatCards stats={stats} />
              <RenewalsByMonthChart renewalsByMonth={stats?.renewals_by_month || []} />
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
                schemeOptions={schemeOptions}
                scheme={scheme}
                onSchemeChange={setScheme}
                expiryBefore={expiryBefore}
                onExpiryBeforeChange={setExpiryBefore}
                onClearAll={handleClearAllFilters}
              />
              <ClientTable
                page={page}
                loading={clientsLoading}
                sortKey={sortKey}
                sortAsc={sortAsc}
                onSort={handleSort}
                onPageChange={setPageNum}
                onSendClick={setPendingClient}
                onSendSelected={bulkSelectedSending ? () => {} : setPendingSelected}
                onPreviewEmail={setPreviewClientId}
                onSendEmailClick={setPendingEmailClient}
                exportFilters={{ status: activeStatus, certType, scheme, expiryBefore, search: debouncedSearch }}
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
        channel="whatsapp"
        onConfirm={handleConfirmSend}
        onCancel={() => setPendingClient(null)}
      />
      <SendAllConfirmModal

open={bulkModalOpen}
        eligibleCount={eligibleCount}
        filteredCount={filteredEligibleCount.whatsapp}
        channel="whatsapp"
        job={sendAllJob}
        onConfirm={handleConfirmSendAll}
        onCancel={sendAllJob ? handleCloseSendAllModal : () => setBulkModalOpen(false)}
      />
      <SendConfirmModal
        client={pendingEmailClient}
        channel="email"
        onConfirm={handleConfirmSendEmail}
        onCancel={() => setPendingEmailClient(null)}
      />
      <SendAllConfirmModal
        open={emailBulkModalOpen}
        eligibleCount={eligibleEmailCount}
        filteredCount={filteredEligibleCount.email}
        channel="email"
        job={sendAllEmailJob}
        onConfirm={handleConfirmSendAllEmails}
        onCancel={sendAllEmailJob ? handleCloseSendAllEmailsModal : () => setEmailBulkModalOpen(false)}
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
