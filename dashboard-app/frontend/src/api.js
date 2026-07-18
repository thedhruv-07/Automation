export async function getClients() {
  const res = await fetch("/api/clients");
  if (!res.ok) throw new Error(`Failed to load clients: ${res.status}`);
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
