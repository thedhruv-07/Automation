import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MessageLogView from "./MessageLogView";

const entries = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
    status_tier: "CRITICAL", phone: "919876543210", message_id: "wamid.ABC", sent_at: "2026-07-18T10:00:00" },
  { client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", cert_name: "OSHA",
    status_tier: "URGENT", phone: "919812345678", message_id: "wamid.DEF", sent_at: "2026-07-17T09:00:00" },
];

describe("MessageLogView", () => {
  it("fetches and displays log entries on mount", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<MessageLogView fetchLog={fetchLog} />);
    await waitFor(() => expect(screen.getByText("Rahul Sharma")).toBeInTheDocument());
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
    expect(fetchLog).toHaveBeenCalledTimes(1);
  });

  it("shows an error message when the fetch fails", async () => {
    const fetchLog = vi.fn().mockRejectedValue(new Error("Failed to load message log: 500"));
    render(<MessageLogView fetchLog={fetchLog} />);
    await waitFor(() => expect(screen.getByTestId("message-log-error")).toBeInTheDocument());
  });

  it("filters entries by search term", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<MessageLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.change(screen.getByLabelText("Search message log"), { target: { value: "priya" } });
    expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument();
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
  });

  it("re-fetches when Refresh Log is clicked", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<MessageLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Refresh Log"));
    await waitFor(() => expect(fetchLog).toHaveBeenCalledTimes(2));
  });

  it("shows a Sent status badge for every entry", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<MessageLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    expect(screen.getAllByText("Sent")).toHaveLength(2);
  });
});
