import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import NoticesView from "./NoticesView";

function setup(overrides = {}) {
  const props = {
    listNotices: vi.fn().mockResolvedValue([
      { id: "transition_facilitation_2026", label: "Transition Facilitation Order 2026" },
    ]),
    getNoticeEligibleCount: vi.fn().mockResolvedValue({ whatsapp: 3, email: 3 }),
    sendNotice: vi.fn().mockResolvedValue({ job_id: "job-1" }),
    getNoticeSendStatus: vi.fn().mockResolvedValue({
      total: 3, sent: 3, skipped: 0, failed: 0, done: true,
    }),
    ...overrides,
  };
  return { ...render(<NoticesView {...props} />), props };
}

describe("NoticesView", () => {
  it("loads and shows the notice options", async () => {
    setup();
    await waitFor(() => expect(screen.getByText("Transition Facilitation Order 2026")).toBeInTheDocument());
  });

  it("fetches the eligible count once a notice is selected", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(props.getNoticeEligibleCount).toHaveBeenCalledWith(
      "transition_facilitation_2026", expect.objectContaining({ scheme: "ALL" })
    ));
  });

  it("keeps the send buttons disabled until a notice is selected", async () => {
    setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    expect(screen.getByText("Send via WhatsApp")).toBeDisabled();
    expect(screen.getByText("Send via Email")).toBeDisabled();
  });

  it("enables the send buttons once a notice is selected", async () => {
    setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(screen.getByText("Send via WhatsApp")).not.toBeDisabled());
  });

  it("sends the notice via WhatsApp and shows progress through to done", async () => {
    const { props } = setup();
    await waitFor(() => screen.getByLabelText("Which notice?"));
    fireEvent.change(screen.getByLabelText("Which notice?"), { target: { value: "transition_facilitation_2026" } });
    await waitFor(() => expect(screen.getByText("Send via WhatsApp")).not.toBeDisabled());

    fireEvent.click(screen.getByText("Send via WhatsApp"));
    await waitFor(() => screen.getByText("Confirm Send All"));
    fireEvent.click(screen.getByText("Confirm Send All"));

    await waitFor(() => expect(props.sendNotice).toHaveBeenCalledWith(
      "transition_facilitation_2026", "whatsapp", expect.objectContaining({ scheme: "ALL" })
    ));
    await waitFor(() => expect(screen.getByText(/3 sent, 0 skipped, 0 failed/)).toBeInTheDocument());
  });
});
