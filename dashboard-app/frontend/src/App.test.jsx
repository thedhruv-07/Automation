import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "./App";
import * as api from "./api";

vi.mock("./api");

const sampleClients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
    cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL", alert_sent_today: false },
];

beforeEach(() => {
  vi.resetAllMocks();
  api.getClients.mockResolvedValue(sampleClients);
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
});
