import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SendFollowupsModal from "./SendFollowupsModal";

const base = {
  open: true, eligible: 5, remainingQuota: 300, separateKey: false, job: null,
  onConfirm: () => {}, onCancel: () => {},
};

describe("SendFollowupsModal", () => {
  it("renders nothing when closed", () => {
    render(<SendFollowupsModal {...base} open={false} />);
    expect(screen.queryByTestId("send-followups-modal")).not.toBeInTheDocument();
  });

  it("explains who gets a follow-up and how many", () => {
    render(<SendFollowupsModal {...base} />);
    expect(screen.getByText(/5 clients/)).toBeInTheDocument();
    expect(screen.getByText(/4\+ days ago/)).toBeInTheDocument();
  });

  it("uses the singular for one client", () => {
    render(<SendFollowupsModal {...base} eligible={1} />);
    expect(screen.getByText(/1 client\b/)).toBeInTheDocument();
  });

  it("warns when the daily limit will cut the send short", () => {
    render(<SendFollowupsModal {...base} eligible={5} remainingQuota={2} />);
    expect(screen.getByText(/Only 2 can go out today/)).toBeInTheDocument();
  });

  it("does not warn when the whole batch fits", () => {
    render(<SendFollowupsModal {...base} />);
    expect(screen.queryByText(/can go out today/)).not.toBeInTheDocument();
  });

  it("notes when a separate Brevo account is used", () => {
    render(<SendFollowupsModal {...base} separateKey />);
    expect(screen.getByText(/separate Brevo account/)).toBeInTheDocument();
  });

  it("calls onConfirm once, even if clicked twice", () => {
    const onConfirm = vi.fn();
    render(<SendFollowupsModal {...base} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByText("Send Follow-ups"));
    fireEvent.click(screen.getByText("Send Follow-ups"));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel from the Cancel button and on Escape", () => {
    const onCancel = vi.fn();
    render(<SendFollowupsModal {...base} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it("shows live progress while the job runs", () => {
    render(<SendFollowupsModal {...base} job={{ total: 5, sent: 2, skipped_no_email: 1, failed: 0, done: false }} />);
    expect(screen.getByText(/2 sent, 1 no email, 0 failed \(of 5\)/)).toBeInTheDocument();
    expect(screen.queryByText("Close")).not.toBeInTheDocument();
  });

  it("shows a Close button once the job is done", () => {
    const onCancel = vi.fn();
    render(
      <SendFollowupsModal
        {...base} onCancel={onCancel}
        job={{ total: 5, sent: 5, skipped_no_email: 0, failed: 0, done: true }}
      />,
    );
    fireEvent.click(screen.getByText("Close"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("shows a job error", () => {
    render(
      <SendFollowupsModal
        {...base}
        job={{ total: 0, sent: 0, skipped_no_email: 0, failed: 0, done: true, error: "boom" }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
  });
});
