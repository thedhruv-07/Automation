import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ExcelSyncView from "./ExcelSyncView";

function makeFile(name = "clients.xlsx") {
  return new File(["dummy"], name, { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
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

  it("calls onUpload with the chosen file and shows a success result", async () => {
    const onUpload = vi.fn().mockResolvedValue({ status: "ok", row_count: 4 });
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(file));
    await waitFor(() => expect(screen.getByText(/Import succeeded — 4 rows loaded/)).toBeInTheDocument());
  });

  it("shows an inline error message when the upload fails", async () => {
    const onUpload = vi.fn().mockRejectedValue(new Error("Column headers don't match"));
    render(<ExcelSyncView onUpload={onUpload} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    fireEvent.click(screen.getByText("Upload and Replace Client Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: Column headers don't match")).toBeInTheDocument()
    );
  });

  it("calls onMerge with the chosen file and shows an added/skipped summary", async () => {
    const onMerge = vi.fn().mockResolvedValue({
      status: "ok", row_count: 5, added: 2, skipped_duplicates: 3, format: "roster", stats: null,
    });
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    const file = makeFile();
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() => expect(onMerge).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(screen.getByText(/added 2 new clients, skipped 3 already on file \(5 total now\)/)).toBeInTheDocument()
    );
  });

  it("shows an inline error message when the merge fails", async () => {
    const onMerge = vi.fn().mockRejectedValue(new Error("File must be an .xlsx spreadsheet"));
    render(<ExcelSyncView onUpload={vi.fn()} onMerge={onMerge} />);
    const input = screen.getByLabelText("Upload client spreadsheet");
    fireEvent.change(input, { target: { files: [makeFile()] } });
    fireEvent.click(screen.getByText("Upload and Merge with Existing Data"));
    await waitFor(() =>
      expect(screen.getByText("Import failed: File must be an .xlsx spreadsheet")).toBeInTheDocument()
    );
  });
});
