import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import MultiSelectDropdown from "./MultiSelectDropdown";

const OPTIONS = ["ISO 9001", "OSHA", "GMP"];

describe("MultiSelectDropdown", () => {
  it("shows the label when nothing is selected", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    expect(screen.getByLabelText("Filter by certification type")).toHaveTextContent("All Cert Types");
  });

  it("shows a count when items are selected", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA", "GMP"]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    expect(screen.getByLabelText("Filter by certification type")).toHaveTextContent("2 selected");
  });

  it("opens the panel and lists all options on click", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    expect(screen.getByText("OSHA")).toBeInTheDocument();
    expect(screen.getByText("GMP")).toBeInTheDocument();
  });

  it("filters the option list by the search box", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.change(screen.getByLabelText("Search Filter by certification type"), { target: { value: "osh" } });
    expect(screen.getByText("OSHA")).toBeInTheDocument();
    expect(screen.queryByText("ISO 9001")).not.toBeInTheDocument();
  });

  it("calls onChange with the option added when an unselected checkbox is clicked", () => {
    const onChange = vi.fn();
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA"]} onChange={onChange} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("GMP"));
    expect(onChange).toHaveBeenCalledWith(["OSHA", "GMP"]);
  });

  it("calls onChange with the option removed when a selected checkbox is clicked", () => {
    const onChange = vi.fn();
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA", "GMP"]} onChange={onChange} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("OSHA"));
    expect(onChange).toHaveBeenCalledWith(["GMP"]);
  });

  it("calls onChange with an empty array when Clear is clicked", () => {
    const onChange = vi.fn();
    render(
      <MultiSelectDropdown options={OPTIONS} selected={["OSHA", "GMP"]} onChange={onChange} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("Clear"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("closes the panel on outside click", () => {
    render(
      <div>
        <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
        <div data-testid="outside">outside</div>
      </div>
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId("outside"));
    expect(screen.queryByText("ISO 9001")).not.toBeInTheDocument();
  });

  it("closes the panel on Escape", () => {
    render(
      <MultiSelectDropdown options={OPTIONS} selected={[]} onChange={() => {}} label="All Cert Types" ariaLabel="Filter by certification type" />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    expect(screen.getByText("ISO 9001")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText("ISO 9001")).not.toBeInTheDocument();
  });
});
