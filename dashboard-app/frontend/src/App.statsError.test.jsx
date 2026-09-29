import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";

vi.mock("./api");

const stats = {
  status_counts: { total: 66743, CRITICAL: 5 }, eligible_not_sent_today: 1, eligible_not_emailed_today: 1,
  cert_types: [], renewals_by_month: [],
};

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  localStorage.setItem("activeView", "dashboard");
  api.getClients.mockResolvedValue({ rows: [], total: 0, page: 1, page_size: 50 });
  api.getEligibleCount.mockResolvedValue({ whatsapp: 0, email: 0 });
  api.getFollowupCount.mockResolvedValue({ eligible: 0, separate_key: false, remaining_quota: 300 });
});

describe("App dashboard stats failure handling", () => {
  it("retries a failed stats fetch instead of silently showing zeros", async () => {
    api.getStats.mockRejectedValueOnce(new Error("network error")).mockResolvedValueOnce(stats);
    render(<App />);
    await waitFor(() => expect(api.getStats).toHaveBeenCalledTimes(2), { timeout: 3000 });
    expect(await screen.findByText("66743")).toBeInTheDocument();
    expect(screen.queryByText(/Could not load/)).not.toBeInTheDocument();
  });

  it("shows a clear error (not misleading zeros) once retries are exhausted, with a way to retry manually", { timeout: 15000 }, async () => {
    api.getStats.mockRejectedValue(new Error("network error"));
    render(<App />);
    const alert = await screen.findByText(/Could not load dashboard stats/, {}, { timeout: 8000 });
    expect(alert).toBeInTheDocument();
    // the misleading "0" cards must not render alongside the error
    expect(screen.queryByText("Total Clients")).not.toBeInTheDocument();

    api.getStats.mockResolvedValueOnce(stats);
    screen.getByRole("button", { name: /retry/i }).click();
    expect(await screen.findByText("66743")).toBeInTheDocument();
  });
});
