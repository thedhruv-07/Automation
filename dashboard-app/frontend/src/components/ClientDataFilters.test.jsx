import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientDataFilters from "./ClientDataFilters";

describe("ClientDataFilters", () => {
  it("calls onCertTypeChange when a cert type is selected", () => {
    const onCertTypeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={["ISO 9001", "OSHA"]}
        certType="ALL"
        onCertTypeChange={onCertTypeChange}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by certification type"), { target: { value: "OSHA" } });
    expect(onCertTypeChange).toHaveBeenCalledWith("OSHA");
  });

  it("calls onExpiryBeforeChange when the date input changes", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by expiry before date"), { target: { value: "2026-12-31" } });
    expect(onExpiryBeforeChange).toHaveBeenCalledWith("2026-12-31");
  });

  it("only shows Clear All when a filter is active", () => {
    const { rerender } = render(
      <ClientDataFilters
        certOptions={[]}
        certType="ALL"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.queryByText("Clear All")).not.toBeInTheDocument();

    rerender(
      <ClientDataFilters
        certOptions={[]}
        certType="ISO 9001"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.getByText("Clear All")).toBeInTheDocument();
  });

  it("calls onClearAll when Clear All is clicked", () => {
    const onClearAll = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType="ISO 9001"
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={onClearAll}
      />
    );
    fireEvent.click(screen.getByText("Clear All"));
    expect(onClearAll).toHaveBeenCalled();
  });
});
