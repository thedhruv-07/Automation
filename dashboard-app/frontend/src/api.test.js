import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus,
} from "./api";

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("getClients", () => {
  it("returns the paginated response and passes query params", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 50 }),
    });
    const result = await getClients({ page: 1, pageSize: 50, status: "CRITICAL", search: "tech" });
    expect(result).toEqual({ rows: [{ client_id: "CLT001" }], total: 1, page: 1, page_size: 50 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/clients?page=1&page_size=50&status=CRITICAL&search=tech"
    );
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getClients({})).rejects.toThrow("Failed to load clients: 500");
  });
});

describe("getStats", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status_counts: { total: 5 }, cert_types: ["ISO 9001"] }),
    });
    const stats = await getStats();
    expect(stats).toEqual({ status_counts: { total: 5 }, cert_types: ["ISO 9001"] });
    expect(global.fetch).toHaveBeenCalledWith("/api/stats");
  });
});

describe("getEmailPreview", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ subject: "Renew ISO 9001", html: "<html></html>" }),
    });
    const preview = await getEmailPreview("CLT001");
    expect(preview).toEqual({ subject: "Renew ISO 9001", html: "<html></html>" });
    expect(global.fetch).toHaveBeenCalledWith("/api/email-preview/CLT001");
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 404 });
    await expect(getEmailPreview("NOPE")).rejects.toThrow("Failed to load email preview: 404");
  });
});

describe("getSettingsInfo", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ template_name: "cert_renewal_alert", critical_days: 7 }),
    });
    const info = await getSettingsInfo();
    expect(info).toEqual({ template_name: "cert_renewal_alert", critical_days: 7 });
    expect(global.fetch).toHaveBeenCalledWith("/api/settings-info");
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getSettingsInfo()).rejects.toThrow("Failed to load settings info: 500");
  });
});

describe("getMessageLog", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => [{ client_id: "CLT001", message_id: "wamid.ABC" }],
    });
    const log = await getMessageLog();
    expect(log).toEqual([{ client_id: "CLT001", message_id: "wamid.ABC" }]);
    expect(global.fetch).toHaveBeenCalledWith("/api/message-log");
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getMessageLog()).rejects.toThrow("Failed to load message log: 500");
  });
});

describe("sendAlert", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "sent", message_id: "wamid.ABC" }),
    });
    const result = await sendAlert("CLT001");
    expect(result).toEqual({ status: "sent", message_id: "wamid.ABC" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send/CLT001", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "Alert already sent today for this client/status" }),
    });
    await expect(sendAlert("CLT001")).rejects.toThrow(
      "Alert already sent today for this client/status"
    );
  });
});

describe("uploadClientsFile", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 3 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await uploadClientsFile(file);
    expect(result).toEqual({ status: "ok", row_count: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/upload-clients",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Column headers don't match the expected format" }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(uploadClientsFile(file)).rejects.toThrow(
      "Column headers don't match the expected format"
    );
  });
});

describe("sendAllAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all", { method: "POST" });
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk send is already in progress" }),
    });
    await expect(sendAllAlerts()).rejects.toThrow("A bulk send is already in progress");
  });
});

describe("getSendAllStatus", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ total: 5, sent: 2, skipped: 1, failed: 0, done: false }),
    });
    const status = await getSendAllStatus("abc-123");
    expect(status).toEqual({ total: 5, sent: 2, skipped: 1, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all/status/abc-123");
  });
});
