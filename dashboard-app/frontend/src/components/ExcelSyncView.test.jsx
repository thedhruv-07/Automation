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
});
