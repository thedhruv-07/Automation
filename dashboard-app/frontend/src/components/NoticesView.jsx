import { useEffect, useRef, useState } from "react";
import ClientDataFilters from "./ClientDataFilters";
import SendAllConfirmModal from "./SendAllConfirmModal";
import EmailPreviewModal from "./EmailPreviewModal";
import NoticeClientsTable from "./NoticeClientsTable";
import AdhocNoticeBroadcast from "./AdhocNoticeBroadcast";

const JOB_POLL_MS = 500;
const FILTERS_STORAGE_KEY = "noticesFilters";

function loadStoredFilters() {
  try {
    const stored = JSON.parse(localStorage.getItem(FILTERS_STORAGE_KEY));
    if (!stored || typeof stored !== "object") return null;
    return stored;
  } catch {
    return null;
  }
}

export default function NoticesView({
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus, getNoticePreview,
  getNoticeClients,
  listAdhocNotices, getAdhocNoticeCount, sendAdhocNotice, getAdhocNoticeSendStatus,
  schemeOptions = [], certOptions = [],
}) {
  const stored = loadStoredFilters();
  const [notices, setNotices] = useState([]);
  const [selectedNoticeId, setSelectedNoticeId] = useState(stored?.selectedNoticeId || "");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [certType, setCertType] = useState(Array.isArray(stored?.certType) ? stored.certType : []);
  const [scheme, setScheme] = useState(stored?.scheme || "ALL");
  const [status, setStatus] = useState(stored?.status || "ALL");
  const [expiryBefore, setExpiryBefore] = useState(stored?.expiryBefore || "");
  const [eligibleCount, setEligibleCount] = useState({ whatsapp: 0, email: 0 });
  const [clientsPageNum, setClientsPageNum] = useState(1);
  const [clientsPage, setClientsPage] = useState({ rows: [], total: 0, page: 1, page_size: 8 });
  const [clientsLoading, setClientsLoading] = useState(false);
  const [whatsappModalOpen, setWhatsappModalOpen] = useState(false);
  const [whatsappJob, setWhatsappJob] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailJob, setEmailJob] = useState(null);
  const [error, setError] = useState(null);
  const jobPollRef = useRef(null);

  useEffect(() => {
    listNotices().then(setNotices).catch((err) => setError(err.message));
  }, [listNotices]);

  useEffect(() => {
    localStorage.setItem(
      FILTERS_STORAGE_KEY,
      JSON.stringify({ selectedNoticeId, status, certType, scheme, expiryBefore }),
    );
  }, [selectedNoticeId, status, certType, scheme, expiryBefore]);

  useEffect(() => {
    if (!selectedNoticeId) return;
    getNoticeEligibleCount(selectedNoticeId, { status, certType, scheme, expiryBefore })
      .then(setEligibleCount)
      .catch(() => {});
  }, [selectedNoticeId, status, certType, scheme, expiryBefore, getNoticeEligibleCount]);

  useEffect(() => {
    setClientsPageNum(1);
  }, [selectedNoticeId, status, certType, scheme, expiryBefore]);

  useEffect(() => {
    if (!selectedNoticeId) {
      setClientsPage({ rows: [], total: 0, page: 1, page_size: 8 });
      return;
    }
    setClientsLoading(true);
    getNoticeClients(selectedNoticeId, {
      page: clientsPageNum, pageSize: 8, status, certType, scheme, expiryBefore,
    })
      .then(setClientsPage)
      .catch(() => {})
      .finally(() => setClientsLoading(false));
  }, [selectedNoticeId, clientsPageNum, status, certType, scheme, expiryBefore, getNoticeClients]);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);

  const selectedNotice = notices.find((n) => n.id === selectedNoticeId) || null;

  function handleClearAllFilters() {
    setStatus("ALL");
    setCertType([]);
    setScheme("ALL");
    setExpiryBefore("");
  }

  function startSend(channel, setModalOpen, setJob) {
    return async function handleConfirm() {
      try {
        const { job_id: jobId } = await sendNotice(selectedNoticeId, channel, {
          status, certType, scheme, expiryBefore,
        });
        setJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
        jobPollRef.current = setInterval(async () => {
          try {
            const jobStatus = await getNoticeSendStatus(selectedNoticeId, channel, jobId);
            setJob(jobStatus);
            if (jobStatus.done) {
              clearInterval(jobPollRef.current);
            }
          } catch (err) {
            clearInterval(jobPollRef.current);
            setJob(null);
            setModalOpen(false);
            setError(err.message);
          }
        }, JOB_POLL_MS);
      } catch (err) {
        setModalOpen(false);
        setError(err.message);
      }
    };
  }

  function closeModal(setModalOpen, setJob) {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    setJob(null);
    setModalOpen(false);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-ink-primary">Notices</h2>
        <p className="text-ink-secondary text-sm mt-1">
          Send a one-time broadcast announcement to clients matching your filters.
        </p>
      </div>

      {error && (
        <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      <div>
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-2">
          Which notice?
        </label>
        <select
          value={selectedNoticeId}
          onChange={(e) => setSelectedNoticeId(e.target.value)}
          aria-label="Which notice?"
          className="min-w-[280px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="" disabled>-- Select a notice --</option>
          {notices.map((n) => (
            <option key={n.id} value={n.id}>{n.label}</option>
          ))}
        </select>
      </div>

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

      {selectedNoticeId && (
        <p className="text-sm text-ink-secondary">
          {eligibleCount.whatsapp} client{eligibleCount.whatsapp === 1 ? "" : "s"} matching your filters haven't received this via WhatsApp,{" "}
          {eligibleCount.email} client{eligibleCount.email === 1 ? "" : "s"} via Email.
        </p>
      )}

      {selectedNoticeId && (
        <NoticeClientsTable page={clientsPage} loading={clientsLoading} onPageChange={setClientsPageNum} />
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => setWhatsappModalOpen(true)}
          disabled={!selectedNoticeId || (whatsappJob !== null && !whatsappJob.done)}
          className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
        >
          Send via WhatsApp
        </button>
        <button
          type="button"
          onClick={() => setEmailModalOpen(true)}
          disabled={!selectedNoticeId || (emailJob !== null && !emailJob.done)}
          className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/10 transition-colors disabled:opacity-50"
        >
          Send via Email
        </button>
        <button
          type="button"
          onClick={() => setPreviewOpen(true)}
          disabled={!selectedNoticeId}
          className="text-sm font-semibold text-accent hover:underline disabled:opacity-50 disabled:no-underline disabled:cursor-not-allowed"
        >
          Preview Email
        </button>
      </div>

      <EmailPreviewModal
        clientId={previewOpen ? selectedNoticeId : null}
        fetchPreview={getNoticePreview}
        onClose={() => setPreviewOpen(false)}
      />

      <SendAllConfirmModal
        open={whatsappModalOpen}
        eligibleCount={eligibleCount.whatsapp}
        filteredCount={eligibleCount.whatsapp}
        channel="whatsapp"
        job={whatsappJob}
        noticeLabel={selectedNotice?.label}
        singleScope
        onConfirm={startSend("whatsapp", setWhatsappModalOpen, setWhatsappJob)}
        onCancel={() => closeModal(setWhatsappModalOpen, setWhatsappJob)}
      />
      <SendAllConfirmModal
        open={emailModalOpen}
        eligibleCount={eligibleCount.email}
        filteredCount={eligibleCount.email}
        channel="email"
        job={emailJob}
        noticeLabel={selectedNotice?.label}
        singleScope
        onConfirm={startSend("email", setEmailModalOpen, setEmailJob)}
        onCancel={() => closeModal(setEmailModalOpen, setEmailJob)}
      />

      <div className="pt-4 border-t border-line">
        <AdhocNoticeBroadcast
          listAdhocNotices={listAdhocNotices}
          getAdhocNoticeCount={getAdhocNoticeCount}
          sendAdhocNotice={sendAdhocNotice}
          getAdhocNoticeSendStatus={getAdhocNoticeSendStatus}
        />
      </div>
    </div>
  );
}
