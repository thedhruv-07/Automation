import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ExcelSyncView from "./ExcelSyncView";

function makeFile(name = "clients.xlsx") {
  return new File(["dummy"], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

function selectFormat(value) {
  fireEvent.change(screen.getByLabelText("Import format"), { target: { value } });
}

describe("ExcelSyncView", () => {
  it("shows the selected file name after choosing a file", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile("renewals.xlsx")] } });
    expect(screen.getByText("renewals.xlsx")).toBeInTheDocument();
  });

  it("does not show an Upload button until a file is chosen", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    expect(screen.queryByText("Upload and Replace Client Data")).not.toBeInTheDocument();
  });

  it("lists Roster, BIS ISI, and CRS as selectable, and FMCS as disabled", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const select = screen.getByLabelText("Import format");
    const options = Array.from(select.querySelectorAll("option"));
    const fmcsOption = options.find((o) => o.value === "fmcs");
    expect(options.map((o) => o.value)).toEqual(expect.arrayContaining(["roster", "bis_isi", "crs", "fmcs"]));
    expect(fmcsOption.disabled).toBe(true);
  });

  it("keeps the Upload button disabled until both a file and a format are set", () => {
    render(<ExcelSyncView onUpload={vi.fn()} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    expect(screen.getByText("Upload and Replace Client Data")).toBeDisabled();
    selectFormat("roster");
    expect(screen.getByText("Upload and Replace Client Data")).not.toBeDisabled();
  });

  it("calls onUpload with the chosen file and format, and shows a success result", async () => {
    const onUpload = vi.fn().mockResolvedValue({ status: "ok", row_count: 4, format: "roster" });
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(file, "roster"));
    await waitFor(() => expect(screen.getByText(/Import succeeded — 4 rows loaded/)).toBeInTheDocument());
  });

  it("shows the converted-export summary for a CRS upload", async () => {
    const onUpload = vi.fn().mockResolvedValue({
      status: "ok", row_count: 2, format: "crs",
      stats: { sheets_used: 1, sheets_empty: 0, rows_written: 2, rows_skipped_missing_key: 0 },
    });
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    selectFormat("crs");
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() =>
      expect(screen.getByText(/Converted CRS registration export — 2 rows loaded from 1 sheet/)).toBeInTheDocument()
    );
  });

  it("shows an inline error message when the upload fails", async () => {
    const onUpload = vi.fn().mockRejectedValue(new Error("Column headers don't match"));
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: Column headers don't match")).toBeInTheDocument()
    );
  });

  it("calls onMerge with the chosen file and format, and shows an added/skipped summary", async () => {
    const onMerge = vi.fn().mockResolvedValue({
      status: "ok", row_count: 5, added: 2, skipped_duplicates: 3, format: "roster", stats: null,
    });
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() => expect(onMerge).toHaveBeenCalledWith(file, "roster"));
    await waitFor(() =>
      expect(screen.getByText(/added 2 new clients, skipped 3 already on file \(5 total now\)/)).toBeInTheDocument()
    );
  });

  it("shows an inline error message when the merge fails", async () => {
    const onMerge = vi.fn().mockRejectedValue(new Error("File must be an .xlsx spreadsheet"));
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    selectFormat("roster");
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: File must be an .xlsx spreadsheet")).toBeInTheDocument()
    );
  });
});
