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

  it("shows the no-email skip count when job.skipped_no_email is a number", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} channel="email" onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, skipped_no_email: 3, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.getByText(/3 no email/)).toBeInTheDocument();
  });

  it("omits the no-email skip count when job.skipped_no_email is absent (WhatsApp job)", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.queryByText(/no email/)).not.toBeInTheDocument();
  });

  it("shows the no-template skip count when job.skipped_no_template is a number", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, skipped_no_template: 2, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.getByText(/2 no template/)).toBeInTheDocument();
  });

  it("omits the no-template skip count when job.skipped_no_template is absent (email job)", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} channel="email" onConfirm={() => {}} onCancel={() => {}}
        job={{ total: 10, sent: 4, skipped: 1, skipped_no_email: 0, failed: 0, done: false }}
      />
    );
    expect(screen.getByText(/4 sent, 1 skipped, 0 failed/)).toBeInTheDocument();
    expect(screen.queryByText(/no template/)).not.toBeInTheDocument();
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
    expect(screen.getByText(/Send a renewal email to:/)).toBeInTheDocument();
    expect(screen.getByTestId("send-all-confirm-modal-email")).toBeInTheDocument();
  });

  it("defaults to WhatsApp text and testid when channel is omitted", () => {
    render(
      <SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByText(/Send a real WhatsApp renewal alert to:/)).toBeInTheDocument();
    expect(screen.getByTestId("send-all-confirm-modal-whatsapp")).toBeInTheDocument();
  });

  it("shows the filtered count and defaults to the 'all eligible' scope", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    expect(screen.getByLabelText(/All eligible clients/)).toBeChecked();
    expect(screen.getByLabelText(/Currently filtered view/)).not.toBeChecked();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("passes 'all' to onConfirm when the default scope is confirmed", () => {
    const onConfirm = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={onConfirm} onCancel={() => {}}
      />
    );
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalledWith("all");
  });

  it("passes 'filtered' to onConfirm after switching scope", () => {
    const onConfirm = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={onConfirm} onCancel={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalledWith("filtered");
  });

  it("disables Confirm when the filtered scope is selected and its count is 0", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={0} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    expect(screen.getByText("Confirm Send All")).toBeDisabled();
  });

  it("defaults filteredCount to 0 when the prop is omitted", () => {
    render(<SendAllConfirmModal open={true} eligibleCount={5} onConfirm={() => {}} onCancel={() => {}} />);
    fireEvent.click(screen.getByLabelText(/Currently filtered view/));
    expect(screen.getByText("Confirm Send All")).toBeDisabled();
  });

  it("Tabs forward through both scope radios and the Cancel/Confirm buttons, then wraps", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    const allRadio = screen.getByLabelText(/All eligible clients/);
    const filteredRadio = screen.getByLabelText(/Currently filtered view/);
    const cancelButton = screen.getByText("Cancel");
    const confirmButton = screen.getByText("Confirm Send All");

    // Initial focus lands on Cancel (existing behavior, unchanged).
    expect(document.activeElement).toBe(cancelButton);

    // Move focus onto the first radio to start the forward walk from the
    // top of the idle view's visual order.
    allRadio.focus();
    expect(document.activeElement).toBe(allRadio);

    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(filteredRadio);

    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(cancelButton);

    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(confirmButton);

    // Tab from the last element wraps back around to the first radio.
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(allRadio);
  });

  it("Shift+Tab from the first radio wraps back to Confirm in the idle view", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    const allRadio = screen.getByLabelText(/All eligible clients/);
    const confirmButton = screen.getByText("Confirm Send All");

    allRadio.focus();
    expect(document.activeElement).toBe(allRadio);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirmButton);
  });

  it("Shift+Tab walks backward from Cancel into the filtered radio in the idle view", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={5} filteredCount={2} onConfirm={() => {}} onCancel={() => {}}
      />
    );
    const filteredRadio = screen.getByLabelText(/Currently filtered view/);
    const cancelButton = screen.getByText("Cancel");

    expect(document.activeElement).toBe(cancelButton);

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(filteredRadio);
  });

  it("shows the notice label in the title and body when noticeLabel is given", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} filteredCount={4} onConfirm={() => {}} onCancel={() => {}}
        noticeLabel="Transition Facilitation Order 2026" singleScope
      />
    );
    expect(screen.getByText('Send "Transition Facilitation Order 2026"?')).toBeInTheDocument();
    expect(screen.getByText(/Send "Transition Facilitation Order 2026" via WhatsApp/)).toBeInTheDocument();
  });

  it("hides the scope radio choice and shows a single count when singleScope is set", () => {
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} filteredCount={4} onConfirm={() => {}} onCancel={() => {}}
        noticeLabel="Transition Facilitation Order 2026" singleScope
      />
    );
    expect(screen.queryByText(/All eligible clients/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Currently filtered view/)).not.toBeInTheDocument();
    expect(screen.getByText(/4 clients matching your current filters/)).toBeInTheDocument();
  });

  it("calls onConfirm with no scope argument when singleScope is set", () => {
    const onConfirm = vi.fn();
    render(
      <SendAllConfirmModal
        open={true} eligibleCount={10} filteredCount={4} onConfirm={onConfirm} onCancel={() => {}}
        noticeLabel="Transition Facilitation Order 2026" singleScope
      />
    );
    fireEvent.click(screen.getByText("Confirm Send All"));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("defaults to today's exact renewal-alert wording when noticeLabel is not given", () => {
    render(<SendAllConfirmModal open={true} eligibleCount={10} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("Send bulk renewal alerts?")).toBeInTheDocument();
    expect(screen.getByText(/Send a real WhatsApp renewal alert to:/)).toBeInTheDocument();
  });
});
