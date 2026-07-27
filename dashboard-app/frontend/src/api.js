import { getStoredAuthHeader } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

function authHeaders(extra = {}) {
  const stored = getStoredAuthHeader();
  return stored ? { ...extra, Authorization: stored } : extra;
}

export async function getClients(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.scheme && params.scheme !== "ALL") query.set("scheme", params.scheme);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.sortKey) query.set("sort_key", params.sortKey);
  if (params.sortDir) query.set("sort_dir", params.sortDir);
  const qs = query.toString();
  const res = await fetch(`${API_BASE}${qs ? `/api/clients?${qs}` : "/api/clients"}`, {
    credentials: "include",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/api/stats`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load stats: ${res.status}`);
  return res.json();
}

export async function getEmailPreview(clientId) {
  const res = await fetch(`${API_BASE}/api/email-preview/${clientId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load email preview: ${res.status}`);
  return res.json();
}

export async function getSettingsInfo() {
  const res = await fetch(`${API_BASE}/api/settings-info`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load settings info: ${res.status}`);
  return res.json();
}

export async function getMessageLog() {
  const res = await fetch(`${API_BASE}/api/message-log`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load message log: ${res.status}`);
  return res.json();
}

export async function sendAlert(clientId) {
  const res = await fetch(`${API_BASE}/api/send/${clientId}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Send failed: ${res.status}`);
  }
  return data;
}

function scopeQueryString(params = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.scheme && params.scheme !== "ALL") query.set("scheme", params.scheme);
  return query.toString();
}

export async function sendAllAlerts(params = {}) {
  const qs = scopeQueryString(params);
  const res = await fetch(`${API_BASE}${qs ? `/api/send-all?${qs}` : "/api/send-all"}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}

export async function getSendAllStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/send-all/status/${jobId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load send-all status: ${res.status}`);
  return res.json();
}

export async function sendEmailAlert(clientId) {
  const res = await fetch(`${API_BASE}/api/send-email/${clientId}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Send failed: ${res.status}`);
  }
  return data;
}

export async function sendAllEmailAlerts(params = {}) {
  const qs = scopeQueryString(params);
  const res = await fetch(`${API_BASE}${qs ? `/api/send-all-emails?${qs}` : "/api/send-all-emails"}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}

export async function getSendAllEmailsStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/send-all-emails/status/${jobId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load send-all status: ${res.status}`);
  return res.json();
}

export async function getEligibleCount(params = {}) {
  const qs = scopeQueryString(params);
  const res = await fetch(`${API_BASE}${qs ? `/api/eligible-count?${qs}` : "/api/eligible-count"}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load eligible count: ${res.status}`);
  return res.json();
}

export function clientsExportUrl({ status, certType, expiryBefore, search, scheme } = {}) {
  const query = new URLSearchParams();
  if (status && status !== "ALL") query.set("status", status);
  if (certType && certType !== "ALL") query.set("cert_type", certType);
  if (scheme && scheme !== "ALL") query.set("scheme", scheme);
  if (expiryBefore) query.set("expiry_before", expiryBefore);
  if (search) query.set("search", search);
  const qs = query.toString();
  return `${API_BASE}${qs ? `/api/clients/export?${qs}` : "/api/clients/export"}`;
}

export async function uploadClientsFile(file, importFormat) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("import_format", importFormat);
  const res = await fetch(`${API_BASE}/api/upload-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Upload failed: ${res.status}`);
  }
  return data;
}

export async function mergeClientsFile(file, importFormat) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("import_format", importFormat);
  const res = await fetch(`${API_BASE}/api/merge-clients`, {
    method: "POST", credentials: "include", headers: authHeaders(), body: formData,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Merge failed: ${res.status}`);
  }
  return data;
}

export function downloadClientTemplate() {
  const link = document.createElement("a");
  link.href = `${API_BASE}/api/client-template`;
  link.download = "clients_certifications_template.xlsx";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export async function verifyCredentials(authHeaderValue) {
  // /api/settings-info is deliberately used here instead of /api/stats (or any
  // other data-backed endpoint): it requires auth but never touches the
  // database, so login isn't blocked by an empty/missing clients.db (e.g.
  // right after a Render free-tier restart, before the roster is reloaded).
  const res = await fetch(`${API_BASE}/api/settings-info`, {
    credentials: "include",
    headers: { Authorization: authHeaderValue },
  });
  return res.ok;
}

export async function listNotices() {
  const res = await fetch(`${API_BASE}/api/notices`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load notices: ${res.status}`);
  return res.json();
}

export async function getNoticeEligibleCount(noticeId, params = {}) {
  const qs = scopeQueryString(params);
  const url = `/api/notices/${noticeId}/eligible-count${qs ? `?${qs}` : ""}`;
  const res = await fetch(`${API_BASE}${url}`, { credentials: "include", headers: authHeaders() });
  if (!res.ok) throw new Error(`Failed to load notice eligible count: ${res.status}`);
  return res.json();
}

export async function sendNotice(noticeId, channel, params = {}) {
  const qs = scopeQueryString(params);
  const url = `/api/notices/${noticeId}/send-${channel}${qs ? `?${qs}` : ""}`;
  const res = await fetch(`${API_BASE}${url}`, {
    method: "POST", credentials: "include", headers: authHeaders(),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send failed: ${res.status}`);
  }
  return data;
}

export async function getNoticeSendStatus(noticeId, channel, jobId) {
  const res = await fetch(`${API_BASE}/api/notices/${noticeId}/send-${channel}/status/${jobId}`, {
    credentials: "include", headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to load notice send status: ${res.status}`);
  return res.json();
}
