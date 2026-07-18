import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FilterBar from "./FilterBar";

describe("FilterBar", () => {
  it("calls onStatusChange with the clicked status", () => {
    const onStatusChange = vi.fn();
    render(
      <FilterBar activeStatus="ALL" onStatusChange={onStatusChange} searchTerm="" onSearchChange={() => {}} />
    );
    fireEvent.click(screen.getByText("Critical"));
    expect(onStatusChange).toHaveBeenCalledWith("CRITICAL");
  });

  it("calls onSearchChange as the user types", () => {
    const onSearchChange = vi.fn();
    render(
      <FilterBar activeStatus="ALL" onStatusChange={() => {}} searchTerm="" onSearchChange={onSearchChange} />
    );
    fireEvent.change(screen.getByPlaceholderText("Search name or company..."), {
      target: { value: "rahul" },
    });
    expect(onSearchChange).toHaveBeenCalledWith("rahul");
  });
});
