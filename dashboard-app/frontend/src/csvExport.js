import { formatSentAt } from "./sortUtils";

// Excel auto-detects long digit strings (phone numbers) as numbers, mangling
// them into scientific notation (8.67699E+12) and right-aligning them like
// other numbers. Wrapping in ="..." forces Excel to evaluate it as a formula
// that returns the literal text, which displays left-aligned and unmangled.
function forceExcelText(value) {
  const str = String(value ?? "");
  return str ? `="${str}"` : str;
}

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
  { key: "phone", header: "Phone", format: forceExcelText },
  { key: "sent_at", header: "Sent At", format: formatSentAt },
  { key: "message_id", header: "Message ID" },
];

const NOTICE_LOG_COLUMNS = [
  { key: "client_id", header: "Client ID" },
  { key: "name", header: "Full Name" },
  { key: "company", header: "Company" },
  { key: "phone", header: "Phone", format: forceExcelText },
  { key: "notice_label", header: "Notice" },
  { key: "channel", header: "Channel" },
  { key: "sent_at", header: "Sent At", format: formatSentAt },
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
  const lines = rows.map((row) => columns.map((col) => {
    const value = col.format ? col.format(row[col.key]) : row[col.key];
    return escapeCsvValue(value);
  }).join(","));
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
