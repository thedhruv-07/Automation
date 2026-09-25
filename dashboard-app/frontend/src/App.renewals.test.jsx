import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";

vi.mock("./api");

const stats = {
  status_counts: { total: 1, EXPIRED: 1 }, eligible_not_sent_today: 0, eligible_not_emailed_today: 0,
  cert_types: [], renewals_by_month: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  localStorage.setItem("activeView", "excelSync");
  api.getClients.mockResolvedValue({ rows: [], total: 0, page: 1, page_size: 50 });
  api.getStats.mockResolvedValue(stats);
  api.getEligibleCount.mockResolvedValue({ whatsapp: 0, email: 0 });
  api.getFollowupCount.mockResolvedValue({ eligible: 0, separate_key: false, remaining_quota: 300 });
});

describe("App renewals import", () => {
  it("shows the renewals import on the Excel Sync screen", async () => {
    render(<App />);
    expect(await screen.findByText("Import renewals from Manak Online")).toBeInTheDocument();
  });

  it("reloads the client list and stats after renewals are applied", async () => {
    const preview = {
      applied: false, report_rows: 1, unreadable: 0, matched: 1, renewed: 1, already_current: 0, not_found: 0,
      renewed_sample: [{ client_id: "C1", name: "A", company: "B", cert_id: "1", old_expiry: "01-01-2026", new_expiry: "01-01-2031", new_status: "ACTIVE" }],
    };
    api.importRenewals.mockResolvedValueOnce(preview).mockResolvedValueOnce({ ...preview, applied: true });
    render(<App />);
    await screen.findByText("Import renewals from Manak Online");
    await waitFor(() => expect(api.getStats).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId("renewals-file-input"), { target: { files: [new File(["x"], "BIS.xlsx")] } });
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    const applyButton = await screen.findByRole("button", { name: "Apply 1 renewal" });
    const clientCalls = api.getClients.mock.calls.length;
    const statsCalls = api.getStats.mock.calls.length;
    fireEvent.click(applyButton);
    await screen.findByText(/Marked 1 client as renewed/);
    await waitFor(() => expect(api.getClients.mock.calls.length).toBeGreaterThan(clientCalls));
    await waitFor(() => expect(api.getStats.mock.calls.length).toBeGreaterThan(statsCalls));
    expect(api.importRenewals).toHaveBeenLastCalledWith(expect.any(File), true);
  });
});
