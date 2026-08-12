import { useEffect, useRef, useState } from "react";
import SendAllConfirmModal from "./SendAllConfirmModal";

const JOB_POLL_MS = 500;

export default function AdhocNoticeBroadcast({
  listAdhocNotices, getAdhocNoticeCount, sendAdhocNotice, getAdhocNoticeSendStatus,
}) {
  const [notices, setNotices] = useState([]);
  const [counts, setCounts] = useState({});
  const [error, setError] = useState(null);
  const [modalNoticeId, setModalNoticeId] = useState(null);
  const [job, setJob] = useState(null);
  const jobPollRef = useRef(null);

  function loadCounts(noticeList) {
    noticeList.forEach((n) => {
      getAdhocNoticeCount(n.id)
        .then((count) => setCounts((prev) => ({ ...prev, [n.id]: count })))
        .catch(() => {});
    });
  }

  useEffect(() => {
    listAdhocNotices()
      .then((data) => {
        setNotices(data);
        loadCounts(data);
      })
      .catch((err) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listAdhocNotices]);

  useEffect(() => {
    return () => {
      if (jobPollRef.current) clearInterval(jobPollRef.current);
    };
  }, []);

  function openModal(noticeId) {
    setModalNoticeId(noticeId);
  }

  function closeModal() {
    if (jobPollRef.current) clearInterval(jobPollRef.current);
    setJob(null);
    setModalNoticeId(null);
    if (modalNoticeId) {
      getAdhocNoticeCount(modalNoticeId)
        .then((count) => setCounts((prev) => ({ ...prev, [modalNoticeId]: count })))
        .catch(() => {});
    }
  }

  async function handleConfirm() {
    try {
      const { job_id: jobId } = await sendAdhocNotice(modalNoticeId);
      setJob({ total: 0, sent: 0, skipped: 0, failed: 0, done: false });
      jobPollRef.current = setInterval(async () => {
        try {
          const jobStatus = await getAdhocNoticeSendStatus(modalNoticeId, jobId);
          setJob(jobStatus);
          if (jobStatus.done) {
            clearInterval(jobPollRef.current);
          }
        } catch (err) {
          clearInterval(jobPollRef.current);
          setJob(null);
          setModalNoticeId(null);
          setError(err.message);
        }
      }, JOB_POLL_MS);
    } catch (err) {
      setModalNoticeId(null);
      setError(err.message);
    }
  }

  if (notices.length === 0 && !error) return null;

  const activeNotice = notices.find((n) => n.id === modalNoticeId);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-bold text-ink-primary">Ad-Hoc WhatsApp Broadcasts</h3>
        <p className="text-ink-secondary text-sm mt-1">
          One-time sends to an imported phone list — no roster filtering, since these numbers have no client record.
        </p>
      </div>

      {error && (
        <div className="text-sm text-ink-primary bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2">
          {error}
        </div>
      )}

      {notices.map((n) => {
        const count = counts[n.id];
        return (
          <div key={n.id} className="bg-surface border border-line rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="font-semibold text-ink-primary">{n.label}</p>
              {count && (
                <p className="text-sm text-ink-secondary mt-1">
                  {count.not_yet_sent} of {count.total} haven't received this yet
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => openModal(n.id)}
              disabled={!count || count.not_yet_sent === 0}
              className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
            >
              Send via WhatsApp
            </button>
          </div>
        );
      })}

      <SendAllConfirmModal
        open={modalNoticeId !== null}
        eligibleCount={counts[modalNoticeId]?.not_yet_sent || 0}
        filteredCount={counts[modalNoticeId]?.not_yet_sent || 0}
        channel="whatsapp"
        job={job}
        noticeLabel={activeNotice?.label}
        singleScope
        onConfirm={handleConfirm}
        onCancel={closeModal}
      />
    </div>
  );
}
