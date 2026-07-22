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
    expect(screen.getByTestId("send-all-confirm-modal")).toBeInTheDocument();
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
});
