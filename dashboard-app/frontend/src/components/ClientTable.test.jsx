import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientTable from "./ClientTable";

const clients = [
  { client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com", cert_name: "ISO 9001",
    cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL", alert_sent_today: false },
  { client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", cert_name: "OSHA",
    cert_id: "OSHA-1", expiry_date: "11-08-2026", status: "URGENT", alert_sent_today: true },
  { client_id: "CLT004", name: "Sneha Kapoor", company: "EduTech", cert_name: "ISO 27001",
    cert_id: "ISO27-1", expiry_date: "15-10-2026", status: "ACTIVE", alert_sent_today: null },
];

function makeClients(count) {
  return Array.from({ length: count }, (_, i) => ({
    client_id: `CLT${String(i + 1).padStart(3, "0")}`,
    name: `Client ${i + 1}`,
    company: `Company ${i + 1}`,
    cert_name: "ISO 9001",
    cert_id: `ISO-${i + 1}`,
    expiry_date: "24-07-2026",
    status: "ACTIVE",
    alert_sent_today: null,
  }));
}

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

  it("shows a company-initials avatar and email subtext when available", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("TC")).toBeInTheDocument();
    expect(screen.getByText("rahul@techcorp.com")).toBeInTheDocument();
  });

  it("paginates rows, showing only the first page by default", () => {
    render(
      <ClientTable clients={makeClients(10)} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Client 1")).toBeInTheDocument();
    expect(screen.getByText("Client 8")).toBeInTheDocument();
    expect(screen.queryByText("Client 9")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1–8 of 10 clients")).toBeInTheDocument();
  });

  it("advances to the next page when Next is clicked", () => {
    render(
      <ClientTable clients={makeClients(10)} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(screen.getByText("Client 9")).toBeInTheDocument();
    expect(screen.queryByText("Client 1")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 9–10 of 10 clients")).toBeInTheDocument();
  });

  it("filters rows by certification type", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" certType="OSHA" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Priya Mehta")).toBeInTheDocument();
    expect(screen.queryByText("Rahul Sharma")).not.toBeInTheDocument();
  });

  it("filters rows by expiry-before date", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" expiryBefore="2026-08-01" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.queryByText("Priya Mehta")).not.toBeInTheDocument();
  });

  it("selects a row via checkbox and shows the bulk-send bar", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} onSendSelected={() => {}} />
    );
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });

  it("calls onSendSelected with the selected client objects", () => {
    const onSendSelected = vi.fn();
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} onSendSelected={onSendSelected} />
    );
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    fireEvent.click(screen.getByText("Send Reminder to Selected"));
    expect(onSendSelected).toHaveBeenCalledWith([clients[0]]);
  });

  it("shows a Preview Email link for alert-eligible clients with an email on file", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} onPreviewEmail={() => {}} />
    );
    expect(screen.getByText("Preview Email")).toBeInTheDocument();
  });

  it("does not show Preview Email for eligible clients without an email on file", () => {
    render(
      <ClientTable clients={clients} activeStatus="URGENT" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} onPreviewEmail={() => {}} />
    );
    expect(screen.queryByText("Preview Email")).not.toBeInTheDocument();
  });

  it("calls onPreviewEmail with the client_id when Preview Email is clicked", () => {
    const onPreviewEmail = vi.fn();
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} onPreviewEmail={onPreviewEmail} />
    );
    fireEvent.click(screen.getByText("Preview Email"));
    expect(onPreviewEmail).toHaveBeenCalledWith("CLT001");
  });

  it("selects all rows on the page via the header checkbox", () => {
    render(
      <ClientTable clients={clients} activeStatus="ALL" searchTerm="" sortKey={null} sortAsc={true}
        onSort={() => {}} onSendClick={() => {}} onSendSelected={() => {}} />
    );
    fireEvent.click(screen.getByLabelText("Select all on this page"));
    expect(screen.getByText("3 selected")).toBeInTheDocument();
  });
});
