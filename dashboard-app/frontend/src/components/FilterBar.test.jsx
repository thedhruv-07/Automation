import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FilterBar from "./FilterBar";

describe("FilterBar", () => {
  it("calls onStatusChange with the clicked status", () => {
    const onStatusChange = vi.fn();
    render(<FilterBar activeStatus="ALL" onStatusChange={onStatusChange} />);
    fireEvent.click(screen.getByText("Critical"));
    expect(onStatusChange).toHaveBeenCalledWith("CRITICAL");
  });
});
