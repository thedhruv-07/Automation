import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientTable from "./ClientTable";

const clients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", cert_name: "ISO 9001",
    cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL", alert_sent_today: false },
  { client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", cert_name: "OSHA",
    cert_id: "OSHA-1", expiry_date: "11-08-2026", status: "URGENT", alert_sent_today: true },
  { client_id: "CLT004", name: "Sneha Kapoor", company: "EduTech", cert_name: "ISO 27001",
    cert_id: "ISO27-1", expiry_date: "15-10-2026", status: "ACTIVE", alert_sent_today: null },
];

describe("ClientTable", () => {
  it("shows a Send Alert button for eligible, not-yet-sent clients", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Send Alert")).toBeInTheDocument();
  });

  it("shows a Sent pill for eligible clients already sent today, with no button", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("✅ Sent")).toBeInTheDocument();
  });

  it("shows a dash for non-eligible statuses", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("calls onSendClick with the client when Send Alert is clicked", () => {
    const onSendClick = vi.fn();
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={onSendClick} />
    );
    fireEvent.click(screen.getByText("Send Alert"));
    expect(onSendClick).toHaveBeenCalledWith(clients[0]);
  });

  it("filters rows by active status", () => {
    render(
      <ClientTable clients={clients} activeStatus="URGENT" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument();
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
  });

  it("filters rows by search term", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="rahul" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.queryByText("Priya Mehta")).not.toBeInTheDocument();
  });

  it("calls onSort with the column key when a header is clicked", () => {
    const onSort = vi.fn();
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={onSort} onSendClick={() => {}} />
    );
    fireEvent.click(screen.getByText("Days Left"));
    expect(onSort).toHaveBeenCalledWith("days_left");
  });
});
