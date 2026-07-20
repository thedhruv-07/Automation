import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SendSelectedConfirmModal from "./SendSelectedConfirmModal";

const clients = [
  { client_id: "CLT001", name: "Rahul Sharma" },
  { client_id: "CLT002", name: "Priya Mehta" },
];

describe("SendSelectedConfirmModal", () => {
  it("renders nothing when clients is empty", () => {
    const { container } = render(
      <SendSelectedConfirmModal clients={[]} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the selected count when open", () => {
    render(<SendSelectedConfirmModal clients={clients} onConfirm={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("calls onConfirm when Confirm Send Selected is clicked", () => {
    const onConfirm = vi.fn();
    render(<SendSelectedConfirmModal clients={clients} onConfirm={onConfirm} onCancel={() => {}} />);
    fireEvent.click(screen.getByText("Confirm Send Selected"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(<SendSelectedConfirmModal clients={clients} onConfirm={() => {}} onCancel={onCancel} />);
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("only calls onConfirm once when clicked twice in quick succession", () => {
    const onConfirm = vi.fn();
    render(<SendSelectedConfirmModal clients={clients} onConfirm={onConfirm} onCancel={() => {}} />);
    const button = screen.getByText("Confirm Send Selected");
    fireEvent.click(button);
    fireEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
