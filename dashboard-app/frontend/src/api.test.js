import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getClients, sendAlert, sendAllAlerts, uploadClientsFile, mergeClientsFile,
  getMessageLog, getSettingsInfo, getEmailPreview,
  getStats, getSendAllStatus, verifyCredentials,
  sendEmailAlert, sendAllEmailAlerts, getSendAllEmailsStatus, getEligibleCount,
  listNotices, getNoticeEligibleCount, sendNotice, getNoticeSendStatus,
} from "./api";
import { setStoredAuthHeader } from "./auth";

beforeEach(() => {
  global.fetch = vi.fn();
  sessionStorage.clear();
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
      "/api/clients?page=1&page_size=50&status=CRITICAL&search=tech",
      { credentials: "include", headers: {} }
    );
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getClients({})).rejects.toThrow("Failed to load clients: 500");
  });

  it("passes scheme as a query param when given", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ rows: [], total: 0, page: 1, page_size: 50 }),
    });
    await getClients({ scheme: "FMCS" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/clients?scheme=FMCS",
      { credentials: "include", headers: {} }
    );
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
    expect(global.fetch).toHaveBeenCalledWith("/api/stats", { credentials: "include", headers: {} });
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
    expect(global.fetch).toHaveBeenCalledWith("/api/email-preview/CLT001", { credentials: "include", headers: {} });
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
    expect(global.fetch).toHaveBeenCalledWith("/api/settings-info", { credentials: "include", headers: {} });
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
    expect(global.fetch).toHaveBeenCalledWith("/api/message-log", { credentials: "include", headers: {} });
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
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send/CLT001",
      { method: "POST", credentials: "include", headers: {} }
    );
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
    const result = await uploadClientsFile(file, "roster");
    expect(result).toEqual({ status: "ok", row_count: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/upload-clients",
      expect.objectContaining({ method: "POST", credentials: "include" })
    );
  });

  it("includes import_format in the request body", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ status: "ok", row_count: 1 }) });
    const file = new File(["dummy"], "clients.xlsx");
    await uploadClientsFile(file, "crs");
    const body = global.fetch.mock.calls[0][1].body;
    expect(body.get("import_format")).toBe("crs");
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Column headers don't match the expected format" }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(uploadClientsFile(file, "roster")).rejects.toThrow(
      "Column headers don't match the expected format"
    );
  });
});

describe("mergeClientsFile", () => {
  it("returns parsed JSON on success and includes import_format in the request body", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", row_count: 5, added: 2, skipped_duplicates: 0 }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    const result = await mergeClientsFile(file, "bis_isi");
    expect(result).toEqual({ status: "ok", row_count: 5, added: 2, skipped_duplicates: 0 });
    const body = global.fetch.mock.calls[0][1].body;
    expect(body.get("import_format")).toBe("bis_isi");
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Unknown format 'xyz'." }),
    });
    const file = new File(["dummy"], "clients.xlsx");
    await expect(mergeClientsFile(file, "xyz")).rejects.toThrow("Unknown format 'xyz'.");
  });
});

describe("sendAllAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("adds status/cert_type/expiry_before/search/scheme as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllAlerts({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight&scheme=ISI",
      { method: "POST", credentials: "include", headers: {} }
    );
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
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all/status/abc-123", { credentials: "include", headers: {} });
  });
});

describe("verifyCredentials", () => {
  it("returns true when the backend accepts the credentials", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const ok = await verifyCredentials("Basic dGVzdDp0ZXN0");
    expect(ok).toBe(true);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/settings-info",
      { credentials: "include", headers: { Authorization: "Basic dGVzdDp0ZXN0" } }
    );
  });

  it("returns false when the backend rejects the credentials", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 401 });
    const ok = await verifyCredentials("Basic d3Jvbmc6d3Jvbmc=");
    expect(ok).toBe(false);
  });
});

describe("authenticated requests", () => {
  it("adds the stored Authorization header to requests once set", async () => {
    setStoredAuthHeader("Basic dGVzdDp0ZXN0");
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ status_counts: { total: 1 } }) });
    await getStats();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/stats",
      { credentials: "include", headers: { Authorization: "Basic dGVzdDp0ZXN0" } }
    );
  });
});

describe("sendEmailAlert", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: "sent", message_id: "brevo-1" }),
    });
    const result = await sendEmailAlert("CLT001");
    expect(result).toEqual({ status: "sent", message_id: "brevo-1" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-email/CLT001",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 400,
      json: async () => ({ detail: "This client has no valid email on file" }),
    });
    await expect(sendEmailAlert("CLT005")).rejects.toThrow("This client has no valid email on file");
  });
});

describe("sendAllEmailAlerts", () => {
  it("returns a job id on success", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    const result = await sendAllEmailAlerts();
    expect(result).toEqual({ job_id: "abc-123" });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all-emails", { method: "POST", credentials: "include", headers: {} });
  });

  it("adds status/cert_type/expiry_before/search/scheme as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "abc-123" }) });
    await sendAllEmailAlerts({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/send-all-emails?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight&scheme=ISI",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: "A bulk email send is already in progress" }),
    });
    await expect(sendAllEmailAlerts()).rejects.toThrow("A bulk email send is already in progress");
  });
});

describe("getSendAllEmailsStatus", () => {
  it("returns parsed JSON on success", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ total: 5, sent: 2, skipped: 1, skipped_no_email: 0, failed: 0, done: false }),
    });
    const status = await getSendAllEmailsStatus("abc-123");
    expect(status).toEqual({ total: 5, sent: 2, skipped: 1, skipped_no_email: 0, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith("/api/send-all-emails/status/abc-123", { credentials: "include", headers: {} });
  });
});

describe("getEligibleCount", () => {
  it("returns parsed JSON with no query string when no filters are given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 3, email: 2 }) });
    const result = await getEligibleCount();
    expect(result).toEqual({ whatsapp: 3, email: 2 });
    expect(global.fetch).toHaveBeenCalledWith("/api/eligible-count", { credentials: "include", headers: {} });
  });

  it("passes status/cert_type/expiry_before/search/scheme as query params when given", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 1, email: 1 }) });
    await getEligibleCount({
      status: "CRITICAL", certType: "OSHA", expiryBefore: "2026-12-31", search: "BuildRight", scheme: "ISI",
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/eligible-count?status=CRITICAL&cert_type=OSHA&expiry_before=2026-12-31&search=BuildRight&scheme=ISI",
      { credentials: "include", headers: {} }
    );
  });

  it("throws when the response is not ok", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(getEligibleCount()).rejects.toThrow("Failed to load eligible count: 500");
  });
});

describe("API_BASE prefixing", () => {
  it("prefixes requests with VITE_API_BASE_URL when set", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE_URL", "https://backend.example.com");
    const { getStats: getStatsWithBase } = await import("./api");
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ status_counts: { total: 1 } }) });
    await getStatsWithBase();
    expect(global.fetch).toHaveBeenCalledWith(
      "https://backend.example.com/api/stats",
      { credentials: "include", headers: {} }
    );
    vi.unstubAllEnvs();
  });
});

describe("listNotices", () => {
  it("returns the notices list", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ([{ id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" }]),
    });
    const result = await listNotices();
    expect(result).toEqual([{ id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" }]);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices",
      { credentials: "include", headers: {} }
    );
  });
});

describe("getNoticeEligibleCount", () => {
  it("passes filters as query params", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ whatsapp: 2, email: 3 }) });
    const result = await getNoticeEligibleCount("transition_facilitation_2026", { scheme: "CRS" });
    expect(result).toEqual({ whatsapp: 2, email: 3 });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/eligible-count?scheme=CRS",
      { credentials: "include", headers: {} }
    );
  });
});

describe("sendNotice", () => {
  it("posts to the channel-specific send endpoint with filters", async () => {
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({ job_id: "job-1" }) });
    const result = await sendNotice("transition_facilitation_2026", "whatsapp", { scheme: "CRS" });
    expect(result).toEqual({ job_id: "job-1" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/send-whatsapp?scheme=CRS",
      { method: "POST", credentials: "include", headers: {} }
    );
  });

  it("throws the backend's detail message on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false, status: 404, json: async () => ({ detail: "Unknown notice_id: xyz" }),
    });
    await expect(sendNotice("xyz", "email", {})).rejects.toThrow("Unknown notice_id: xyz");
  });
});

describe("getNoticeSendStatus", () => {
  it("fetches the channel-specific job status", async () => {
    global.fetch.mockResolvedValue({
      ok: true, json: async () => ({ total: 2, sent: 1, skipped: 0, failed: 0, done: false }),
    });
    const result = await getNoticeSendStatus("transition_facilitation_2026", "whatsapp", "job-1");
    expect(result).toEqual({ total: 2, sent: 1, skipped: 0, failed: 0, done: false });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/notices/transition_facilitation_2026/send-whatsapp/status/job-1",
      { credentials: "include", headers: {} }
    );
  });
});
