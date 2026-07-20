export async function getClients() {
  const res = await fetch("/api/clients");
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
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

export function downloadClientTemplate() {
  const link = document.createElement("a");
  link.href = "/api/client-template";
  link.download = "clients_certifications_template.xlsx";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
