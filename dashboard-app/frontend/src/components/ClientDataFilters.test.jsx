import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ClientDataFilters from "./ClientDataFilters";
import { isoDateMonthsFromToday } from "../sortUtils";

describe("ClientDataFilters", () => {
  it("calls onCertTypeChange when a cert type is checked", () => {
    const onCertTypeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={["ISO 9001", "OSHA"]}
        certType={[]}
        onCertTypeChange={onCertTypeChange}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByLabelText("Filter by certification type"));
    fireEvent.click(screen.getByText("OSHA"));
    expect(onCertTypeChange).toHaveBeenCalledWith(["OSHA"]);
  });

  it("calls onSchemeChange when a scheme is selected", () => {
    const onSchemeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        schemeOptions={["ISI", "FMCS"]}
        scheme="ALL"
        onSchemeChange={onSchemeChange}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by scheme"), { target: { value: "FMCS" } });
    expect(onSchemeChange).toHaveBeenCalledWith("FMCS");
  });

  it("shows Clear All when a scheme filter is active", () => {
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        schemeOptions={["ISI", "FMCS"]}
        scheme="FMCS"
        onSchemeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={() => {}}
        onClearAll={() => {}}
      />
    );
    expect(screen.getByText("Clear All")).toBeInTheDocument();
  });

  it("calls onExpiryBeforeChange when the date input changes", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.change(screen.getByLabelText("Filter by expiry before date"), { target: { value: "2026-12-31" } });
    expect(onExpiryBeforeChange).toHaveBeenCalledWith("2026-12-31");
  });

  it("calls onExpiryBeforeChange with the correct date when '3 months' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("3 months"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(3));
  });

  it("calls onExpiryBeforeChange with the correct date when '6 months' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("6 months"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(6));
  });

  it("calls onExpiryBeforeChange with the correct date when '1 year' is clicked", () => {
    const onExpiryBeforeChange = vi.fn();
    render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
        onCertTypeChange={() => {}}
        expiryBefore=""
        onExpiryBeforeChange={onExpiryBeforeChange}
        onClearAll={() => {}}
      />
    );
    fireEvent.click(screen.getByText("1 year"));
    expect(onExpiryBeforeChange).toHaveBeenCalledWith(isoDateMonthsFromToday(12));
  });

  it("only shows Clear All when a filter is active", () => {
    const { rerender } = render(
      <ClientDataFilters
        certOptions={[]}
        certType={[]}
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
        certType={["ISO 9001"]}
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
        certType={["ISO 9001"]}
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
