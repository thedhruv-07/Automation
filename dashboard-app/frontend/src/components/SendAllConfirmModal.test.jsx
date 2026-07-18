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
});
