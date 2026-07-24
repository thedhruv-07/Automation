import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";

vi.mock("./api");

const samplePage = (rows, total = rows.length, page = 1) => ({ rows, total, page, page_size: 50 });

const sampleClients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
    cert_name: "ISO 9001", cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL",
    alert_sent_today: false },
];

const sampleStats = {
  status_counts: { total: 1, CRITICAL: 1 },
  eligible_not_sent_today: 1,
  cert_types: ["ISO 9001"],
  renewals_by_month: [{ year_month: "2026-07", count: 1 }],
};

beforeEach(() => {
  vi.resetAllMocks();
  api.getClients.mockResolvedValue(samplePage(sampleClients));
  api.getStats.mockResolvedValue(sampleStats);
  api.getEligibleCount.mockResolvedValue({ whatsapp: 0, email: 0 });
});

describe("App", () => {
  it("renders the Absolute Veritas heading", async () => {
    render(<App />);
    expect(screen.getByText("Absolute Veritas")).toBeInTheDocument();
  });

  it("loads and displays clients on mount", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByText("Rahul Sharma")).toBeInTheDocument());
  });

  it("does not send until the confirmation modal is accepted", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send Alert"));
    expect(screen.getByTestId("send-confirm-modal")).toBeInTheDocument();
    expect(api.sendAlert).not.toHaveBeenCalled();
  });

  it("sends and shows a success toast after confirming", async () => {
    api.sendAlert.mockResolvedValue({ status: "sent", message_id: "wamid.ABC" });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Confirm Send"));
    await waitFor(() => expect(api.sendAlert).toHaveBeenCalledWith("CLT001"));
    await waitFor(() => expect(screen.getByText("Sent to Rahul Sharma")).toBeInTheDocument());
  });

  it("shows an error toast when the send fails", async () => {
    api.sendAlert.mockRejectedValue(new Error("Alert already sent today for this client/status"));
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Confirm Send"));
    await waitFor(() =>
      expect(screen.getByText("Alert already sent today for this client/status")).toBeInTheDocument()
    );
  });

  it("shows a load error message when getClients fails", async () => {
    api.getClients.mockRejectedValue(new Error("Failed to load clients: 500"));
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("load-error")).toBeInTheDocument());
  });

  it("does not send-all until the bulk confirmation modal is accepted", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    expect(screen.getByTestId("send-all-confirm-modal-whatsapp")).toBeInTheDocument();
    expect(api.sendAllAlerts).not.toHaveBeenCalled();
  });

  it("sends all and shows a summary toast once the job finishes", async () => {
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(api.sendAllAlerts).toHaveBeenCalled());
    await waitFor(() => expect(api.getSendAllStatus).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByText(/1 sent, 0 skipped, 0 failed/)).toBeInTheDocument());
  });

  it("stops polling and shows an error toast if checking send-all status fails", async () => {
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockRejectedValue(new Error("Network error"));
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(api.getSendAllStatus).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByText("Network error")).toBeInTheDocument());
    // The modal should have closed and the interval should be cleared — no further polling.
    expect(screen.queryByTestId("send-all-confirm-modal-whatsapp")).not.toBeInTheDocument();
    const callsAfterError = api.getSendAllStatus.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 700));
    expect(api.getSendAllStatus.mock.calls.length).toBe(callsAfterError);
  });

  it("sends an email and shows a success toast after confirming", async () => {
    api.sendEmailAlert.mockResolvedValue({ status: "sent", message_id: "brevo-1" });
    render(<App />);
    await waitFor(() => screen.getByText("Send Email"));
    fireEvent.click(screen.getByText("Send Email"));
    fireEvent.click(screen.getByText("Confirm Send"));
    await waitFor(() => expect(api.sendEmailAlert).toHaveBeenCalledWith("CLT001"));
    await waitFor(() => expect(screen.getByText("Emailed Rahul Sharma")).toBeInTheDocument());
  });

  it("does not send-all-emails until the bulk email confirmation modal is accepted", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
    render(<App />);
    await waitFor(() => screen.getByText("Send Email"));
    fireEvent.click(screen.getByText("Send All Emails"));
    expect(screen.getByTestId("send-all-confirm-modal-email")).toBeInTheDocument();
    expect(api.sendAllEmailAlerts).not.toHaveBeenCalled();
  });

  it("sends all emails and shows a summary toast once the job finishes", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
    api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllEmailsStatus.mockResolvedValue({
      total: 1, sent: 1, skipped: 0, skipped_no_email: 0, failed: 0, done: true,
    });
    render(<App />);
    await waitFor(() => screen.getByText("Send Email"));
    fireEvent.click(screen.getByText("Send All Emails"));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(api.sendAllEmailAlerts).toHaveBeenCalled());
    await waitFor(() => expect(api.getSendAllEmailsStatus).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByText(/1 sent, 0 skipped, 0 failed/)).toBeInTheDocument());
  });

  it("stops polling and shows an error toast if checking send-all-emails status fails", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
    api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllEmailsStatus.mockRejectedValue(new Error("Network error"));
    render(<App />);
    await waitFor(() => screen.getByText("Send Email"));
    fireEvent.click(screen.getByText("Send All Emails"));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(api.getSendAllEmailsStatus).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByText("Network error")).toBeInTheDocument());
    expect(screen.queryByTestId("send-all-confirm-modal-email")).not.toBeInTheDocument();
    const callsAfterError = api.getSendAllEmailsStatus.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 700));
    expect(api.getSendAllEmailsStatus.mock.calls.length).toBe(callsAfterError);
  });

  it("includes the header search term when 'Currently filtered view' is confirmed for Send All Emails", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, eligible_not_emailed_today: 1 });
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllEmailAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllEmailsStatus.mockResolvedValue({
      total: 1, sent: 1, skipped: 0, skipped_no_email: 0, failed: 0, done: true,
    });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Emails"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllEmailAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });

  it("ignores a stale paginated response that resolves after a newer one for a changed filter", async () => {
    const manyClients = Array.from({ length: 16 }, (_, i) => ({
      client_id: `CLT${i}`, name: `Client ${i}`, company: "Co", email: "",
      cert_name: "ISO 9001", cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL",
      alert_sent_today: false,
    }));

    // App.jsx paginates at 8 rows/page — samplePage()'s default page_size (50)
    // would leave everything on one page, so build pages with page_size: 8
    // explicitly to get a real second page to navigate to.
    const pageOf8 = (rows, total, page) => ({ rows, total, page, page_size: 8 });

    const resolvers = [];
    api.getClients.mockImplementation((params) => new Promise((resolve) => {
      resolvers.push({ params, resolve });
    }));

    render(<App />);

    // Initial load: page 1.
    await waitFor(() => expect(resolvers.length).toBe(1));
    resolvers[0].resolve(pageOf8(manyClients.slice(0, 8), 16, 1));
    await waitFor(() => screen.getByText("Client 0"));

    // Move to page 2.
    fireEvent.click(screen.getByLabelText("Next page"));
    await waitFor(() => expect(resolvers.length).toBe(2));
    resolvers[1].resolve(pageOf8(manyClients.slice(8, 16), 16, 2));
    await waitFor(() => screen.getByText("Client 8"));

    // Change a filter while on page 2 — this fires two requests: one still
    // carrying the stale page (2), and one carrying the reset page (1).
    fireEvent.click(screen.getByText("Critical"));
    await waitFor(() => expect(resolvers.length).toBe(4));

    const stale = resolvers[2]; // page 2 with the new filter — superseded
    const fresh = resolvers[3]; // page 1 with the new filter — the real answer

    // Resolve out of order: the fresh (later-issued) request answers first,
    // then the stale (earlier-issued) request answers after it.
    fresh.resolve(pageOf8([manyClients[0]], 1, 1));
    await waitFor(() => screen.getByText("Client 0"));
    stale.resolve(pageOf8(manyClients.slice(8, 16), 16, 2));

    // Give the stale response a chance to (incorrectly) clobber state.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(screen.getByText("Client 0")).toBeInTheDocument();
    expect(screen.queryByText("Client 8")).not.toBeInTheDocument();
  });

  it("filters the table via the top-bar search input", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "nobody" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "nobody" })),
      { timeout: 1000 }
    );
    await waitFor(() => expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument());
  });

  it("switches to the Dashboard view and shows the stat cards instead of the table", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Dashboard"));
    expect(screen.getByText("Dashboard Overview")).toBeInTheDocument();
    expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument();
    expect(screen.getByTestId("stat-cards")).toBeInTheDocument();
  });

  it("switches back to Client Data and shows the table again", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Dashboard"));
    fireEvent.click(screen.getByText("Client Data"));
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
  });

  it("does not send-selected until the confirmation modal is accepted", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    fireEvent.click(screen.getByText("Send Reminder to Selected"));
    expect(screen.getByTestId("send-selected-confirm-modal")).toBeInTheDocument();
    expect(api.sendAlert).not.toHaveBeenCalled();
  });

  it("sends selected clients and shows a summary toast after confirming", async () => {
    api.sendAlert.mockResolvedValue({ status: "sent", message_id: "wamid.ABC" });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    fireEvent.click(screen.getByText("Send Reminder to Selected"));
    fireEvent.click(screen.getByText("Confirm Send Selected"));
    await waitFor(() => expect(api.sendAlert).toHaveBeenCalledWith("CLT001"));
    await waitFor(() => expect(screen.getByText("1 sent, 0 already sent, 0 failed")).toBeInTheDocument());
  });

  it("navigates to Excel Sync and uploads a file, refreshing the client list", async () => {
    api.uploadClientsFile.mockResolvedValue({ status: "ok", row_count: 7 });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Excel Sync"));

    const file = new File(["dummy"], "clients.xlsx");
    fireEvent.change(screen.getByLabelText("Upload client spreadsheet"), { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));

    await waitFor(() => expect(api.uploadClientsFile).toHaveBeenCalledWith(file));
    await waitFor(() => expect(screen.getByText("Imported 7 clients.")).toBeInTheDocument());
    expect(api.getClients).toHaveBeenCalledTimes(2);
  });

  it("navigates to Excel Sync and merges a file, refreshing the client list", async () => {
    api.mergeClientsFile.mockResolvedValue({
      status: "ok", row_count: 9, added: 2, skipped_duplicates: 1, format: "roster", stats: null,
    });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Excel Sync"));

    const file = new File(["dummy"], "clients.xlsx");
    fireEvent.change(screen.getByLabelText("Upload client spreadsheet"), { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));

    await waitFor(() => expect(api.mergeClientsFile).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(screen.getByText("Merged — added 2 new clients, skipped 1 already on file (9 total).")).toBeInTheDocument()
    );
    expect(api.getClients).toHaveBeenCalledTimes(2);
  });

  it("navigates to Message Log and displays fetched entries", async () => {
    api.getMessageLog.mockResolvedValue([
      { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
        status_tier: "CRITICAL", phone: "919876543210", message_id: "wamid.ABC", sent_at: "2026-07-18T10:00:00" },
    ]);
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Message Log"));
    await waitFor(() => expect(api.getMessageLog).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText("Rahul Sharma").length).toBeGreaterThan(0));
  });

  it("navigates to WhatsApp Settings and displays fetched info", async () => {
    api.getSettingsInfo.mockResolvedValue({
      template_name: "cert_renewal_alert", template_lang: "en", phone_number_id: "1128915266981927",
      scheduled_run_time: "09:30 (Asia/Kolkata)", critical_days: 7, urgent_days: 30,
    });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("WhatsApp Settings"));
    await waitFor(() => expect(api.getSettingsInfo).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("cert_renewal_alert")).toBeInTheDocument());
  });

  it("opens the email preview modal with fetched content when Preview Email is clicked", async () => {
    api.getEmailPreview.mockResolvedValue({
      subject: "[Action Required] Renew ISO 9001 — TechCorp",
      html: "<html><body>Preview</body></html>",
    });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Preview Email"));
    await waitFor(() => expect(api.getEmailPreview).toHaveBeenCalledWith("CLT001"));
    await waitFor(() => expect(screen.getByTestId("email-preview-modal")).toBeInTheDocument());
  });

  it("fetches the eligible count for the current filters when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "",
      })
    );
  });

  it("includes the header search term in the eligible count fetched when the bulk send modal opens", async () => {
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });

  it("ignores a stale eligible-count response that resolves after a newer one", async () => {
    let resolveFirst;
    let resolveSecond;
    const firstPromise = new Promise((resolve) => { resolveFirst = resolve; });
    const secondPromise = new Promise((resolve) => { resolveSecond = resolve; });
    api.getEligibleCount
      .mockReturnValueOnce(firstPromise)
      .mockReturnValueOnce(secondPromise);

    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalledTimes(1));

    // Change the filter while the modal is still open — this fires a second,
    // newer eligible-count request without the first one having resolved yet.
    fireEvent.click(screen.getByText("Critical"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalledTimes(2));

    // Resolve out of order: the newer ("Critical") request lands first, then
    // the stale (original "ALL") request resolves after it.
    const modal = screen.getByTestId("send-all-confirm-modal-whatsapp");
    resolveSecond({ whatsapp: 2, email: 2 });
    await waitFor(() => expect(modal.textContent).toContain("Currently filtered view (2)"));

    resolveFirst({ whatsapp: 9, email: 9 });
    // Give the stale promise's .then a chance to run before asserting it was ignored.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(modal.textContent).toContain("Currently filtered view (2)");
    expect(modal.textContent).not.toContain("Currently filtered view (9)");
  });

  it("sends only the filtered scope when 'Currently filtered view' is selected and confirmed", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Critical"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith({
        status: "CRITICAL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "",
      })
    );
  });

  it("sends with no filters when the default 'all eligible' scope is confirmed, even with an active filter", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));
    fireEvent.click(screen.getByText("Critical"));
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(api.sendAllAlerts).toHaveBeenCalledWith({}));
  });

  it("includes the header search term when 'Currently filtered view' is confirmed for Send All Eligible", async () => {
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    api.getClients.mockResolvedValue(samplePage([]));
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "BuildRight" },
    });
    await waitFor(
      () => expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ search: "BuildRight" })),
      { timeout: 1000 }
    );
    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() => expect(api.getEligibleCount).toHaveBeenCalled());
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith({
        status: "ALL", certType: "ALL", scheme: "ALL", expiryBefore: "", search: "BuildRight",
      })
    );
  });

  it("selecting a scheme filters the table and flows into the eligible count and bulk-send scope", async () => {
    api.getStats.mockResolvedValue({ ...sampleStats, schemes: ["FMCS", "ISI"] });
    api.getEligibleCount.mockResolvedValue({ whatsapp: 1, email: 1 });
    api.sendAllAlerts.mockResolvedValue({ job_id: "job-1" });
    api.getSendAllStatus.mockResolvedValue({ total: 1, sent: 1, skipped: 0, failed: 0, done: true });
    render(<App />);
    await waitFor(() => screen.getByText("Send Alert"));

    fireEvent.change(screen.getByLabelText("Filter by scheme"), { target: { value: "FMCS" } });
    await waitFor(() =>
      expect(api.getClients).toHaveBeenCalledWith(expect.objectContaining({ scheme: "FMCS" }))
    );

    fireEvent.click(screen.getByText("Send All Eligible"));
    await waitFor(() =>
      expect(api.getEligibleCount).toHaveBeenCalledWith(
        expect.objectContaining({ scheme: "FMCS" })
      )
    );
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() =>
      expect(api.sendAllAlerts).toHaveBeenCalledWith(
        expect.objectContaining({ scheme: "FMCS" })
      )
    );
  });
});
