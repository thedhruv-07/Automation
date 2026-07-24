import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SendAllConfirmModal from "./SendAllConfirmModal";

describe("SendAllConfirmModal", () => {
  it("renders nothing when open is false", () => {
    const { container } = render(
      <SendAllConfirmModal open={false} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the eligible count when open", () => {
    render(<SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/eligible clients/)).toBeInTheDocument();
  });

  it("calls onConfirm when Confirm Send All is clicked", () => {
    const onConfirm = vi.fn();
    render(<SendAllConfirmModal open={true} eligibleCount={3} onConfirm={onConfirm} onCancel={() => {}} />);
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(<SendAllConfirmModal open={true} eligibleCount={3} onConfirm={() => {}} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("only calls onConfirm once when Confirm Send All is clicked twice in quick succession", () => {
    const onConfirm = vi.fn();
    render(<SendAllConfirmModal open={true} eligibleCount={3} onConfirm={onConfirm} onCancel={() => {}} />);
    const button = screen.getByText("Confirm Send All");
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("shows a progress bar once a job is in progress", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.getByText(/of 10/)).toBeInTheDocument();
  });

  it("shows a done summary and a Close button once the job finishes", () => {
    const onCancel = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={onCancel}
        job={{ total: 10, sent: 9, skipped: 1, failed: 0, done: true }}
      />
    );
    fireEvent.click(screen.getByText("Close"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("handles job.total === 0 without NaN or a '(of 0)' suffix", () => {
    const { container } = render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 0, sent: 0, skipped: 0, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/0 sent, 0 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.queryByText(/of 0/)).not.toBeInTheDocument();
    expect(container.innerHTML).not.toContain("NaN");
  });

  it("shows a distinct error state and Close button when the job fails", () => {
    const onCancel = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={onCancel}
        job={{ total: 0, sent: 0, skipped: 0, failed: 0, done: true, error: "database is locked" }}
      />
    );
    expect(screen.getByText(/database is locked/)).toBeInTheDocument();
    const closeButton = screen.getByText("Close");
    fireEvent.click(closeButton);
    expect(onCancel).toHaveBeenCalled();
  });

  it("does not show the error state when job.error is not set", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, failed: 0, done: false }}
      />
    );
    expect(screen.queryByText(/failed:/i)).not.toBeInTheDocument();
  });

  it("keeps Tab/Shift+Tab from leaving the dialog while a job is in progress (no interactive elements)", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, failed: 0, done: false }}
      />
    );
    // No Cancel/Confirm/Close button exists in this state — pressing Tab
    // must not throw and must not hand focus to anything outside the dialog.
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(document.body);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(document.body);
  });

  it("focuses the Close button on completion and cycles Tab/Shift+Tab back to it when the job is done", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 9, skipped: 1, failed: 0, done: true }}
      />
    );
    const closeButton = screen.getByText("Close");
    expect(document.activeElement).toBe(closeButton);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(closeButton);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(closeButton);
  });

  it("shows email-specific text and a distinct testid when channel is 'email'", () => {
    render(
      <SendAllConfirmModal
        open={true}
        eligibleCount={5}
        channel="email"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );
    expect(screen.getByText(/Send a renewal email to all/)).toBeInTheDocument();
    expect(screen.getByTestId("send-all-confirm-modal-email")).toBeInTheDocument();
  });

  it("defaults to WhatsApp text and testid when channel is omitted", () => {
    render(
      <SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByText(/Send a real WhatsApp renewal alert to all/)).toBeInTheDocument();
    expect(screen.getByTestId("send-all-confirm-modal-whatsapp")).toBeInTheDocument();
  });
});
