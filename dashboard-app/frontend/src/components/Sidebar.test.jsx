import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Sidebar from "./Sidebar";

describe("Sidebar", () => {
  it("calls onNavigate with the item's view when clicked", () => {
    const onNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Client Data"));
    expect(onNavigate).toHaveBeenCalledWith("clientData");
  });

  it("calls onNavigate for Excel Sync", () => {
    const onNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Excel Sync"));
    expect(onNavigate).toHaveBeenCalledWith("excelSync");
  });

  it("calls onNavigate for Message Log", () => {
    const onNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Message Log"));
    expect(onNavigate).toHaveBeenCalledWith("messageLog");
  });

  it("calls onNavigate for WhatsApp Settings", () => {
    const onNavigate = vi.fn();
    render(<Sidebar activeView="dashboard" onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("WhatsApp Settings"));
    expect(onNavigate).toHaveBeenCalledWith("whatsappSettings");
  });

  it("marks the active view's nav item with aria-current", () => {
    render(<Sidebar activeView="clientData" onNavigate={() => {}} />);
    expect(screen.getByText("Client Data").closest("button")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Dashboard").closest("button")).not.toHaveAttribute("aria-current");
  });
});
