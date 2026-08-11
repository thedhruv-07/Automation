import { describe, it, expect } from "vitest";
import { clientsToCsv, messageLogToCsv, noticeLogToCsv } from "./csvExport";
import { formatSentAt } from "./sortUtils";

describe("clientsToCsv", () => {
  it("builds a header row plus one row per client", () => {
    const csv = clientsToCsv([
      { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
        cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL" },
    ]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("Client ID,Full Name,Company,Certification,Cert ID,Expiry Date,Status");
    expect(lines[1]).toBe("CLT001,Rahul Sharma,TechCorp,ISO 9001,ISO-1,24-07-2026,CRITICAL");
  });

  it("quotes and escapes values containing commas or quotes", () => {
    const csv = clientsToCsv([
      { client_id: "CLT002", name: 'Priya "PJ" Mehta', company: "BuildRight, Inc",
        cert_name: "OSHA", cert_id: "OSHA-1", expiry_date: "11-08-2026", status: "URGENT" },
    ]);
    const lines = csv.split("\n");
    expect(lines[1]).toBe('CLT002,"Priya ""PJ"" Mehta","BuildRight, Inc",OSHA,OSHA-1,11-08-2026,URGENT');
  });

  it("returns just the header for an empty client list", () => {
    const csv = clientsToCsv([]);
    expect(csv).toBe("Client ID,Full Name,Company,Certification,Cert ID,Expiry Date,Status");
  });
});

describe("messageLogToCsv", () => {
  it("builds a header row plus one row per log entry, with Sent At formatted for readability", () => {
    const csv = messageLogToCsv([
      { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
        status_tier: "CRITICAL", phone: "919876543210", sent_at: "2026-07-18T10:00:00", message_id: "wamid.ABC" },
    ]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("Client ID,Full Name,Company,Certification,Alert Tier,Phone,Sent At,Message ID");
    const formatted = formatSentAt("2026-07-18T10:00:00");
    expect(lines[1]).toContain(formatted.includes(",") ? `"${formatted}"` : formatted);
    // the raw ISO timestamp (with its literal "T" separator) must not leak into the export
    expect(lines[1]).not.toContain("2026-07-18T10:00:00");
  });
});

describe("noticeLogToCsv", () => {
  it("builds a header row plus one row per log entry, with Sent At formatted for readability", () => {
    const csv = noticeLogToCsv([
      { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", phone: "919876543210",
        notice_label: "MeitY Series Guidelines — IS/IEC 62368-1:2023", channel: "whatsapp",
        sent_at: "2026-07-18T10:00:00", message_id: "wamid.ABC" },
    ]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("Client ID,Full Name,Company,Phone,Notice,Channel,Sent At,Message ID");
    const formatted = formatSentAt("2026-07-18T10:00:00");
    expect(lines[1]).toContain(formatted.includes(",") ? `"${formatted}"` : formatted);
    expect(lines[1]).not.toContain("2026-07-18T10:00:00");
  });
});
