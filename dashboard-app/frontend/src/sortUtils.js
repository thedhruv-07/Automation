export function initialsFor(company) {
  const str = String(company || "").trim();
  if (!str) return "";
  let words = str.split(/\s+/).filter(Boolean);
  if (words.length === 1) {
    const camelParts = str.match(/[A-Z][a-z0-9]*|[a-z0-9]+/g);
    if (camelParts && camelParts.length > 1) words = camelParts;
  }
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("");
}

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

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function monthlyGroups(clients) {
  const buckets = new Map();
  for (const c of clients) {
    const d = parseDate(c.expiry_date);
    if (Number.isNaN(d.getTime())) continue;
    const key = `${d.getFullYear()}-${d.getMonth()}`;
    if (!buckets.has(key)) {
      buckets.set(key, {
        key,
        label: `${MONTH_LABELS[d.getMonth()]} ${d.getFullYear()}`,
        year: d.getFullYear(),
        month: d.getMonth(),
        count: 0,
      });
    }
    buckets.get(key).count += 1;
  }
  return Array.from(buckets.values()).sort((a, b) => a.year - b.year || a.month - b.month);
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

export function isoDateMonthsFromToday(monthsAhead) {
  // Date.setMonth rolls overflow days into the following month (e.g. 31 Jan +
  // 1 month -> 3 Mar, not a clamped 28/29 Feb) -- that's the native JS
  // behavior and is treated as an acceptable approximation for a quick
  // "N months from now" filter preset, not exact calendar-month arithmetic.
  const d = new Date();
  d.setMonth(d.getMonth() + monthsAhead);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
