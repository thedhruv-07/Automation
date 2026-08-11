const CLIENT_COLUMNS = [
  { key: "client_id", header: "Client ID" },
  { key: "name", header: "Full Name" },
  { key: "company", header: "Company" },
  { key: "cert_name", header: "Certification" },
  { key: "cert_id", header: "Cert ID" },
  { key: "expiry_date", header: "Expiry Date" },
  { key: "status", header: "Status" },
];

const MESSAGE_LOG_COLUMNS = [
  { key: "client_id", header: "Client ID" },
  { key: "name", header: "Full Name" },
  { key: "company", header: "Company" },
  { key: "cert_name", header: "Certification" },
  { key: "status_tier", header: "Alert Tier" },
  { key: "phone", header: "Phone" },
  { key: "sent_at", header: "Sent At" },
  { key: "message_id", header: "Message ID" },
];

const NOTICE_LOG_COLUMNS = [
  { key: "client_id", header: "Client ID" },
  { key: "name", header: "Full Name" },
  { key: "company", header: "Company" },
  { key: "phone", header: "Phone" },
  { key: "notice_label", header: "Notice" },
  { key: "channel", header: "Channel" },
  { key: "sent_at", header: "Sent At" },
  { key: "message_id", header: "Message ID" },
];

function escapeCsvValue(value) {
  const str = String(value ?? "");
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function rowsToCsv(rows, columns) {
  const header = columns.map((c) => c.header).join(",");
  const lines = rows.map((row) => columns.map((col) => escapeCsvValue(row[col.key])).join(","));
  return [header, ...lines].join("\n");
}

function downloadCsv(csv, filename) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function clientsToCsv(clients) {
  return rowsToCsv(clients, CLIENT_COLUMNS);
}

export function downloadClientsCsv(clients, filename = `clients_export_${new Date().toISOString().slice(0, 10)}.csv`) {
  downloadCsv(clientsToCsv(clients), filename);
}

export function messageLogToCsv(entries) {
  return rowsToCsv(entries, MESSAGE_LOG_COLUMNS);
}

export function downloadMessageLogCsv(entries, filename = `message_log_export_${new Date().toISOString().slice(0, 10)}.csv`) {
  downloadCsv(messageLogToCsv(entries), filename);
}

export function noticeLogToCsv(entries) {
  return rowsToCsv(entries, NOTICE_LOG_COLUMNS);
}

export function downloadNoticeLogCsv(entries, filename = `notice_log_export_${new Date().toISOString().slice(0, 10)}.csv`) {
  downloadCsv(noticeLogToCsv(entries), filename);
}
