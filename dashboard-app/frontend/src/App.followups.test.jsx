import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";

vi.mock("./api");

const stats = {
  status_counts: { total: 1, CRITICAL: 1 }, eligible_not_sent_today: 1, eligible_not_emailed_today: 1,
  cert_types: [], renewals_by_month: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  localStorage.setItem("activeView", "clientData");
  api.getClients.mockResolvedValue({ rows: [], total: 0, page: 1, page_size: 50 });
  api.getStats.mockResolvedValue(stats);
  api.getEligibleCount.mockResolvedValue({ whatsapp: 0, email: 0 });
  api.getFollowupCount.mockResolvedValue({ eligible: 3, separate_key: false, remaining_quota: 300 });
});

async function openModal() {
  const button = await screen.findByRole("button", { name: "Send Follow-ups" });
  await waitFor(() => expect(button).not.toBeDisabled());
  fireEvent.click(button);
  return screen.getByTestId("send-followups-modal");
}

function confirm(modal) {
  fireEvent.click(modal.querySelector("[data-confirm]"));
}

describe("App follow-ups", () => {
  it("opens a confirmation modal showing the eligible count and does not send yet", async () => {
    render(<App />);
    await openModal();
    expect(screen.getByText(/3 clients/)).toBeInTheDocument();
    expect(api.sendFollowups).not.toHaveBeenCalled();
  });

  it("disables the button when nobody is due a follow-up", async () => {
    api.getFollowupCount.mockResolvedValue({ eligible: 0, separate_key: false, remaining_quota: 300 });
    render(<App />);
    const button = await screen.findByRole("button", { name: "Send Follow-ups" });
    await waitFor(() => expect(api.getFollowupCount).toHaveBeenCalled());
    expect(button).toBeDisabled();
  });

  it("starts the job on confirm and polls its status until done", async () => {
    api.sendFollowups.mockResolvedValue({ job_id: "j1" });
    api.getSendFollowupsStatus.mockResolvedValue({
      total: 3, sent: 3, skipped_no_email: 0, failed: 0, done: true, error: null,
    });
    render(<App />);
    confirm(await openModal());
    await waitFor(() => expect(api.sendFollowups).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getSendFollowupsStatus).toHaveBeenCalledWith("j1"));
    await waitFor(() => expect(screen.getByText(/3 sent/)).toBeInTheDocument());
  });

  it("shows an error toast when starting the job fails", async () => {
    api.sendFollowups.mockRejectedValue(new Error("A bulk email send is already in progress"));
    render(<App />);
    confirm(await openModal());
    await waitFor(() => expect(screen.getByText("A bulk email send is already in progress")).toBeInTheDocument());
  });
});
