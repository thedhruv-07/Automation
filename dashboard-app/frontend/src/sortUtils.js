export function parseDate(str) {
  const [d, m, y] = String(str).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function daysUntil(expiryStr) {
  const expiry = parseDate(expiryStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  expiry.setHours(0, 0, 0, 0);
  return Math.round((expiry - today) / 86400000);
}

export function formatDaysLeft(expiryStr) {
  const diffDays = daysUntil(expiryStr);
  if (diffDays === 0) return "today";
  if (diffDays > 0) return `in ${diffDays} day${diffDays === 1 ? "" : "s"}`;
  return `${Math.abs(diffDays)} day${Math.abs(diffDays) === 1 ? "" : "s"} ago`;
}

export function sortClients(clients, sortKey, sortAsc) {
  if (!sortKey) return clients;
  const rows = clients.slice();
  rows.sort((a, b) => {
    if (sortKey === "days_left") {
      const av = daysUntil(a.expiry_date);
      const bv = daysUntil(b.expiry_date);
      return sortAsc ? av - bv : bv - av;
    }
    if (sortKey === "expiry_date") {
      const av = parseDate(a.expiry_date);
      const bv = parseDate(b.expiry_date);
      return sortAsc ? av - bv : bv - av;
    }
    const av = String(a[sortKey] ?? "");
    const bv = String(b[sortKey] ?? "");
    return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
  return rows;
}
