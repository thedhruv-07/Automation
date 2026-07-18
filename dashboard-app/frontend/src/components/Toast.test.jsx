import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import Toast from "./Toast";

describe("Toast", () => {
  it("renders nothing when toast is null", () => {
    render(<Toast toast={null} onDismiss={() => {}} />);
    expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
  });

  it("shows the toast message when set", () => {
    render(<Toast toast={{ type: "success", message: "Sent to Rahul Sharma" }} onDismiss={() => {}} />);
    expect(screen.getByText("Sent to Rahul Sharma")).toBeInTheDocument();
  });

  it("applies the error background class for error-type toasts", () => {
    render(<Toast toast={{ type: "error", message: "Something failed" }} onDismiss={() => {}} />);
    expect(screen.getByTestId("toast")).toHaveClass("bg-rose-500");
  });

  it("calls onDismiss after 4000ms", () => {
    vi.useFakeTimers();
    const onDismiss = vi.fn();
    render(<Toast toast={{ type: "success", message: "Sent" }} onDismiss={onDismiss} />);
    vi.advanceTimersByTime(4000);
    expect(onDismiss).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("does not reset the auto-dismiss timer when onDismiss changes but toast stays the same", () => {
    vi.useFakeTimers();
    const toast = { type: "success", message: "Sent" };
    const onDismiss1 = vi.fn();
    const { rerender } = render(<Toast toast={toast} onDismiss={onDismiss1} />);

    vi.advanceTimersByTime(2000);
    const onDismiss2 = vi.fn();
    rerender(<Toast toast={toast} onDismiss={onDismiss2} />);

    vi.advanceTimersByTime(2000);
    expect(onDismiss2).toHaveBeenCalledTimes(1);
    expect(onDismiss1).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
