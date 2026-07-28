import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import NoticeClientsTable from "./NoticeClientsTable";

const pageOf = (rows, total = rows.length, page = 1) => ({ rows, total, page, page_size: 2 });

const clients = [
  {
    client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
    phone: "919876543210", notice_sent_whatsapp: true, notice_sent_email: false,
  },
  {
    client_id: "CLT002", name: "Priya Mehta", company: "BuildRight", email: null,
    phone: "919812345678", notice_sent_whatsapp: false, notice_sent_email: false,
  },
];

describe("NoticeClientsTable", () => {
  it("renders each client's identity and contact info", () => {
    render(<NoticeClientsTable page={pageOf(clients)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.getByText("TechCorp")).toBeInTheDocument();
    expect(screen.getByText("919876543210")).toBeInTheDocument();
  });

  it("shows an em dash for a missing email", () => {
    render(<NoticeClientsTable page={pageOf(clients)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("shows Sent for a client already notified via that channel, Not yet otherwise", () => {
    render(<NoticeClientsTable page={pageOf([clients[0]])} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText("Sent")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
  });

  it("shows the total row count from the server, not just the rendered page", () => {
    render(<NoticeClientsTable page={pageOf(clients, 137, 1)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByText(/of 137 clients/)).toBeInTheDocument();
  });

  it("calls onPageChange with the next page when Next is clicked", () => {
    const onPageChange = vi.fn();
    render(<NoticeClientsTable page={pageOf(clients, 10, 1)} loading={false} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("disables Previous on the first page", () => {
    render(<NoticeClientsTable page={pageOf(clients, 10, 1)} loading={false} onPageChange={() => {}} />);
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });

  it("shows a loading message while loading and no rows are cached yet", () => {
    render(<NoticeClientsTable page={pageOf([])} loading={true} onPageChange={() => {}} />);
    expect(screen.getByText("Loading clients…")).toBeInTheDocument();
  });
});
