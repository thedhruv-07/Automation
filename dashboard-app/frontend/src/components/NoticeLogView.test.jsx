import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NoticeLogView from "./NoticeLogView";

const entries = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", phone: "919876543210",
    notice_id: "meity_series_guidelines_2026", notice_label: "MeitY Series Guidelines — IS/IEC 62368-1:2023",
    channel: "whatsapp", message_id: "wamid.ABC", sent_at: "2026-07-18T10:00:00" },
  { client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", phone: "919812345678",
    notice_id: "meity_series_guidelines_2026", notice_label: "MeitY Series Guidelines — IS/IEC 62368-1:2023",
    channel: "email", message_id: "brevo.DEF", sent_at: "2026-07-17T09:00:00" },
];

describe("NoticeLogView", () => {
  it("fetches and displays log entries on mount", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => expect(screen.getByText("Rahul Sharma")).toBeInTheDocument());
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
    expect(fetchLog).toHaveBeenCalledTimes(1);
  });

  it("shows an error message when the fetch fails", async () => {
    const fetchLog = vi.fn().mockRejectedValue(new Error("Failed to load notice log: 500"));
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => expect(screen.getByTestId("notice-log-error")).toBeInTheDocument());
  });

  it("filters entries by search term", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.change(screen.getByLabelText("Search notice log"), { target: { value: "priya" } });
    expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument();
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
  });

  it("re-fetches when Refresh Log is clicked", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    fireEvent.click(screen.getByText("Refresh Log"));
    await waitFor(() => expect(fetchLog).toHaveBeenCalledTimes(2));
  });

  it("shows each client's phone number", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    expect(screen.getByText(/919876543210/)).toBeInTheDocument();
    expect(screen.getByText(/919812345678/)).toBeInTheDocument();
  });

  it("shows the notice label and channel for every entry", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    expect(screen.getAllByText("MeitY Series Guidelines — IS/IEC 62368-1:2023")).toHaveLength(2);
    expect(screen.getByText("whatsapp")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
  });

  it("shows a Sent status badge for every entry", async () => {
    const fetchLog = vi.fn().mockResolvedValue(entries);
    render(<NoticeLogView fetchLog={fetchLog} />);
    await waitFor(() => screen.getByText("Rahul Sharma"));
    expect(screen.getAllByText("Sent")).toHaveLength(2);
  });
});
