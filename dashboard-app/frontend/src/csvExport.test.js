import { describe, it, expect } from "vitest";
import { clientsToCsv, messageLogToCsv } from "./csvExport";

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
  it("builds a header row plus one row per log entry", () => {
    const csv = messageLogToCsv([
      { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
        status_tier: "CRITICAL", phone: "919876543210", sent_at: "2026-07-18T10:00:00", message_id: "wamid.ABC" },
    ]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe("Client ID,Full Name,Company,Certification,Alert Tier,Phone,Sent At,Message ID");
    expect(lines[1]).toBe("CLT001,Rahul Sharma,TechCorp,ISO 9001,CRITICAL,919876543210,2026-07-18T10:00:00,wamid.ABC");
  });
});
