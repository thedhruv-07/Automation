import { describe, it, expect } from "vitest";
import { daysUntil, formatDaysLeft, sortClients, monthlyGroups, initialsFor } from "./sortUtils";

function futureDateStr(offsetDays) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}-${mm}-${d.getFullYear()}`;
}

describe("daysUntil", () => {
  it("computes positive day difference for future dates", () => {
    expect(daysUntil(futureDateStr(5))).toBe(5);
  });

  it("computes negative day difference for past dates", () => {
    expect(daysUntil(futureDateStr(-3))).toBe(-3);
  });
});

describe("formatDaysLeft", () => {
  it("returns 'today' for zero days", () => {
    expect(formatDaysLeft(futureDateStr(0))).toBe("today");
  });

  it("returns singular 'day' for exactly 1 day out", () => {
    expect(formatDaysLeft(futureDateStr(1))).toBe("in 1 day");
  });

  it("returns plural 'days' for multiple days out", () => {
    expect(formatDaysLeft(futureDateStr(6))).toBe("in 6 days");
  });

  it("returns 'ago' phrasing for past dates", () => {
    expect(formatDaysLeft(futureDateStr(-10))).toBe("10 days ago");
  });
});

describe("sortClients", () => {
  const clients = [
    { client_id: "A", name: "Charlie", expiry_date: "15-10-2026" },
    { client_id: "B", name: "Alice", expiry_date: "13-01-2027" },
    { client_id: "C", name: "Bob", expiry_date: "15-09-2026" },
  ];

  it("sorts expiry_date chronologically ascending, not lexicographically", () => {
    const sorted = sortClients(clients, "expiry_date", true);
    expect(sorted.map((c) => c.client_id)).toEqual(["C", "A", "B"]);
  });

  it("sorts expiry_date chronologically descending", () => {
    const sorted = sortClients(clients, "expiry_date", false);
    expect(sorted.map((c) => c.client_id)).toEqual(["B", "A", "C"]);
  });

  it("sorts by name ascending using localeCompare", () => {
    const sorted = sortClients(clients, "name", true);
    expect(sorted.map((c) => c.name)).toEqual(["Alice", "Bob", "Charlie"]);
  });

  it("returns original order unchanged when sortKey is null", () => {
    const sorted = sortClients(clients, null, true);
    expect(sorted.map((c) => c.client_id)).toEqual(["A", "B", "C"]);
  });
});

describe("initialsFor", () => {
  it("takes the first letter of each of two space-separated words", () => {
    expect(initialsFor("BuildRight Construction")).toBe("BC");
  });

  it("splits a single camelCase word into pseudo-words", () => {
    expect(initialsFor("TechCorp")).toBe("TC");
  });

  it("returns an empty string for empty input", () => {
    expect(initialsFor("")).toBe("");
    expect(initialsFor(undefined)).toBe("");
  });
});

describe("monthlyGroups", () => {
  it("buckets clients by expiry month/year, sorted chronologically, with counts", () => {
    const clients = [
      { expiry_date: "24-07-2026" },
      { expiry_date: "02-07-2026" },
      { expiry_date: "13-01-2027" },
      { expiry_date: "15-09-2026" },
    ];
    const groups = monthlyGroups(clients);
    expect(groups).toEqual([
      { key: "2026-6", label: "Jul 2026", year: 2026, month: 6, count: 2 },
      { key: "2026-8", label: "Sep 2026", year: 2026, month: 8, count: 1 },
      { key: "2027-0", label: "Jan 2027", year: 2027, month: 0, count: 1 },
    ]);
  });
});
