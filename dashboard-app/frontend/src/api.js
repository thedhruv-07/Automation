export async function getClients(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set("page", params.page);
  if (params.pageSize) query.set("page_size", params.pageSize);
  if (params.status && params.status !== "ALL") query.set("status", params.status);
  if (params.certType && params.certType !== "ALL") query.set("cert_type", params.certType);
  if (params.expiryBefore) query.set("expiry_before", params.expiryBefore);
  if (params.search) query.set("search", params.search);
  if (params.sortKey) query.set("sort_key", params.sortKey);
  if (params.sortDir) query.set("sort_dir", params.sortDir);
  const qs = query.toString();
  const res = await fetch(qs ? `/api/clients?${qs}` : "/api/clients");
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
  return res.json();
}

export async function getStats() {
  const res = await fetch("/api/stats");
  if (!res.ok) throw new Error(`Failed to load stats: ${res.status}`);
  return res.json();
}

export async function getEmailPreview(clientId) {
  const res = await fetch(`/api/email-preview/${clientId}`);
  if (!res.ok) throw new Error(`Failed to load email preview: ${res.status}`);
  return res.json();
}

export async function getSettingsInfo() {
  const res = await fetch("/api/settings-info");
  if (!res.ok) throw new Error(`Failed to load settings info: ${res.status}`);
  return res.json();
}

export async function getMessageLog() {
  const res = await fetch("/api/message-log");
  if (!res.ok) throw new Error(`Failed to load message log: ${res.status}`);
  return res.json();
}

export async function sendAlert(clientId) {
  const res = await fetch(`/api/send/${clientId}`, { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Send failed: ${res.status}`);
  }
  return data;
}

export async function sendAllAlerts() {
  const res = await fetch("/api/send-all", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Send-all failed: ${res.status}`);
  }
  return data;
}

export async function getSendAllStatus(jobId) {
  const res = await fetch(`/api/send-all/status/${jobId}`);
  if (!res.ok) throw new Error(`Failed to load send-all status: ${res.status}`);
  return res.json();
}

export function clientsExportUrl({ status, certType, expiryBefore, search } = {}) {
  const query = new URLSearchParams();
  if (status && status !== "ALL") query.set("status", status);
  if (certType && certType !== "ALL") query.set("cert_type", certType);
  if (expiryBefore) query.set("expiry_before", expiryBefore);
  if (search) query.set("search", search);
  const qs = query.toString();
  return qs ? `/api/clients/export?${qs}` : "/api/clients/export";
}

export async function uploadClientsFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/upload-clients", { method: "POST", body: formData });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Upload failed: ${res.status}`);
  }
  return data;
}

export async function mergeClientsFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/merge-clients", { method: "POST", body: formData });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error((data && data.detail) || `Merge failed: ${res.status}`);
  }
  return data;
}

export function downloadClientTemplate() {
  const link = document.createElement("a");
  link.href = "/api/client-template";
  link.download = "clients_certifications_template.xlsx";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
