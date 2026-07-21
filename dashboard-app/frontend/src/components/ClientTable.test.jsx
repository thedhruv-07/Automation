import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientTable from "./ClientTable";

const pageOf = (rows, total = rows.length, page = 1) => ({ rows, total, page, page_size: 8 });

const oneClient = {
  client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp", email: "rahul@techcorp.com",
  cert_name: "ISO 9001", cert_id: "ISO-1", expiry_date: "24-07-2026", status: "CRITICAL",
  alert_sent_today: false,
};

describe("ClientTable", () => {
  it("renders rows from the given page", () => {
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
  });

  it("shows a loading message while the page is loading and no rows are cached yet", () => {
    render(
      <ClientTable
        page={pageOf([])} loading={true} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Loading clients…")).toBeInTheDocument();
  });

  it("shows the total row count from the server, not just the rendered page", () => {
    render(
      <ClientTable
        page={pageOf([oneClient], 137, 1)} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText(/of 137 clients/)).toBeInTheDocument();
  });

  it("calls onPageChange with the next page number", () => {
    const onPageChange = vi.fn();
    render(
      <ClientTable
        page={pageOf([oneClient], 20, 1)} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={onPageChange} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("shows a Send Alert button for eligible, not-yet-sent clients", () => {
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Send Alert")).toBeInTheDocument();
  });

  it("shows Preview Email for any status with an email on file", () => {
    const activeWithEmail = { ...oneClient, status: "ACTIVE", alert_sent_today: null };
    render(
      <ClientTable
        page={pageOf([activeWithEmail])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Preview Email")).toBeInTheDocument();
  });

  it("selects a row and calls onSendSelected with the selected client objects", () => {
    const onSendSelected = vi.fn();
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={onSendSelected} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    fireEvent.click(screen.getByText("Send Reminder to Selected"));
    expect(onSendSelected).toHaveBeenCalledWith([oneClient]);
  });

  it("calls onSort with the clicked column key", () => {
    const onSort = vi.fn();
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={onSort} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByText("Full Name"));
    expect(onSort).toHaveBeenCalledWith("name");
  });

  it("renders cached rows instead of the loading placeholder when a refetch is in flight but rows are already present", () => {
    render(
      <ClientTable
        page={pageOf([oneClient])} loading={true} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.queryByText("Loading clients…")).not.toBeInTheDocument();
  });

  it("keeps the displayed selected count accurate when a previously selected id is no longer on the page", () => {
    const { rerender } = render(
      <ClientTable
        page={pageOf([oneClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Select Rahul Sharma"));
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    // Simulate a filter change that doesn't move currentPage/sortKey/sortAsc (so the
    // selection-clearing effect doesn't fire) but replaces the rows entirely — the
    // previously-selected client_id is now stale.
    const otherClient = { ...oneClient, client_id: "CLT999", name: "Priya Mehta" };
    rerender(
      <ClientTable
        page={pageOf([otherClient])} loading={false} sortKey={null} sortAsc={true}
        onSort={() => {}} onPageChange={() => {}} onSendClick={() => {}}
        onSendSelected={() => {}} onPreviewEmail={() => {}}
      />
    );
    expect(screen.getByText("0 selected")).toBeInTheDocument();
  });
});
