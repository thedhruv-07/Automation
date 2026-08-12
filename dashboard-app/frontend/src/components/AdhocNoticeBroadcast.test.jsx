import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AdhocNoticeBroadcast from "./AdhocNoticeBroadcast";

function setup(overrides = {}) {
  const props = {
    listAdhocNotices: vi.fn().mockResolvedValue([
      { id: "independence_day_2026", label: "Independence Day Special Offer 2026" },
    ]),
    getAdhocNoticeCount: vi.fn().mockResolvedValue({ total: 2692, not_yet_sent: 2692 }),
    sendAdhocNotice: vi.fn().mockResolvedValue({ job_id: "job-1" }),
    getAdhocNoticeSendStatus: vi.fn().mockResolvedValue({
      total: 2692, sent: 2692, skipped: 0, failed: 0, done: true,
    }),
    ...overrides,
  };
  return { ...render(<AdhocNoticeBroadcast {...props} />), props };
}

describe("AdhocNoticeBroadcast", () => {
  it("shows the notice label and recipient counts", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("Independence Day Special Offer 2026")).toBeInTheDocument());
    expect(screen.getByText("2692 of 2692 haven't received this yet")).toBeInTheDocument();
  });

  it("renders nothing when there are no ad-hoc notices", async () => {
    const { container } = setup({ listAdhocNotices: vi.fn().mockResolvedValue([]) });
    await waitFor(() => expect(container.firstChild).toBeNull());
  });

  it("opens the confirm modal and starts a send on confirm", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByText("Send via WhatsApp"));
    fireEvent.click(screen.getByText("Send via WhatsApp"));
    await waitFor(() => screen.getByText("Confirm Send All"));
    fireEvent.click(screen.getByText("Confirm Send All"));
    await waitFor(() => expect(props.sendAdhocNotice).toHaveBeenCalledWith("independence_day_2026"));
    await waitFor(() => expect(screen.getByText(/2692 sent/)).toBeInTheDocument());
  });

  it("disables the send button when nothing is left to send", async () => {
    setup({ getAdhocNoticeCount: vi.fn().mockResolvedValue({ total: 2692, not_yet_sent: 0 }) });
    await waitFor(() => screen.getByText("Send via WhatsApp"));
    expect(screen.getByText("Send via WhatsApp")).toBeDisabled();
  });
});
