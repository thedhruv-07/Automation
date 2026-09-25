import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import RenewalsImport from "./RenewalsImport";

const file = new File(["x"], "BIS.xlsx");

const preview = {
  applied: false, report_rows: 36, unreadable: 0, matched: 5, renewed: 3, already_current: 2, not_found: 31,
  renewed_sample: [
    { client_id: "C1", name: "Rahul Sharma", company: "TechCorp", cert_id: "0009156278",
      old_expiry: "24-07-2026", new_expiry: "31-08-2031", new_status: "ACTIVE" },
  ],
};

function pick(f = file) {
  fireEvent.change(screen.getByTestId("renewals-file-input"), { target: { files: [f] } });
}

describe("RenewalsImport", () => {
  it("explains what it does and keeps Check report disabled until a file is chosen", () => {
    render(<RenewalsImport importRenewals={vi.fn()} />);
    expect(screen.getByText("Import renewals from Manak Online")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check report" })).toBeDisabled();
    pick();
    expect(screen.getByRole("button", { name: "Check report" })).not.toBeDisabled();
  });

  it("previews without applying and shows the counts and what would change", async () => {
    const importRenewals = vi.fn().mockResolvedValue(preview);
    render(<RenewalsImport importRenewals={importRenewals} />);
    pick();
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    await waitFor(() => expect(importRenewals).toHaveBeenCalledWith(file, false));
    expect(await screen.findByText(/3 clients have renewed/)).toBeInTheDocument();
    expect(screen.getByText(/36 licences in the report/)).toBeInTheDocument();
    expect(screen.getByText(/31 not in your roster/)).toBeInTheDocument();
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.getByText(/24-07-2026/)).toBeInTheDocument();
    expect(screen.getByText(/31-08-2031/)).toBeInTheDocument();
  });

  it("applies only after the Apply button is clicked, then reports the result", async () => {
    const importRenewals = vi.fn()
      .mockResolvedValueOnce(preview)
      .mockResolvedValueOnce({ ...preview, applied: true });
    render(<RenewalsImport importRenewals={importRenewals} />);
    pick();
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    fireEvent.click(await screen.findByRole("button", { name: "Apply 3 renewals" }));
    await waitFor(() => expect(importRenewals).toHaveBeenLastCalledWith(file, true));
    expect(await screen.findByText(/Marked 3 clients as renewed/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply/ })).not.toBeInTheDocument();
  });

  it("offers no Apply button when nobody in the report has renewed", async () => {
    const importRenewals = vi.fn().mockResolvedValue({ ...preview, renewed: 0, renewed_sample: [] });
    render(<RenewalsImport importRenewals={importRenewals} />);
    pick();
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    expect(await screen.findByText(/No renewals found/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply/ })).not.toBeInTheDocument();
  });

  it("mentions rows it could not read", async () => {
    const importRenewals = vi.fn().mockResolvedValue({ ...preview, unreadable: 4 });
    render(<RenewalsImport importRenewals={importRenewals} />);
    pick();
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    expect(await screen.findByText(/4 rows could not be read/)).toBeInTheDocument();
  });

  it("shows the server's error", async () => {
    const importRenewals = vi.fn().mockRejectedValue(new Error("This doesn't look like a Manak Online report"));
    render(<RenewalsImport importRenewals={importRenewals} />);
    pick();
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This doesn't look like a Manak Online report");
  });

  it("Cancel discards the preview", async () => {
    render(<RenewalsImport importRenewals={vi.fn().mockResolvedValue(preview)} />);
    pick();
    fireEvent.click(screen.getByRole("button", { name: "Check report" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/3 clients have renewed/)).not.toBeInTheDocument();
  });
});
