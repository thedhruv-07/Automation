import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SendConfirmModal from "./SendConfirmModal";

describe("SendConfirmModal", () => {
  it("renders nothing when client is null", () => {
    const { container } = render(<SendConfirmModal client={null} onConfirm={() => {}} onCancel={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the client's name and company when open", () => {
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={() => {}} onCancel={() => {}} />
    );
    expect(screen.getByText("Rahul Sharma")).toBeInTheDocument();
    expect(screen.getByText("TechCorp")).toBeInTheDocument();
  });

  it("calls onConfirm when Confirm Send is clicked", () => {
    const onConfirm = vi.fn();
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={onConfirm} onCancel={() => {}} />
    );
    fireEvent.click(screen.getByText("Confirm Send"));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={() => {}} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });

  it("only calls onConfirm once when Confirm Send is clicked twice in quick succession", () => {
    const onConfirm = vi.fn();
    render(
      <SendConfirmModal client={{ name: "Rahul Sharma", company: "TechCorp" }} onConfirm={onConfirm} onCancel={() => {}} />
    );
    const confirmButton = screen.getByText("Confirm Send");
    fireEvent.click(confirmButton);
    fireEvent.click(confirmButton);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("shows email-specific text when channel is 'email'", () => {
    render(
      <SendConfirmModal
        client={{ name: "Rahul Sharma", company: "TechCorp" }}
        channel="email"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );
    expect(screen.getByText(/Send a renewal email/)).toBeInTheDocument();
  });

  it("defaults to WhatsApp text when channel is omitted", () => {
    render(
      <SendConfirmModal
        client={{ name: "Rahul Sharma", company: "TechCorp" }}
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );
    expect(screen.getByText(/Send a real WhatsApp renewal alert/)).toBeInTheDocument();
  });
});
