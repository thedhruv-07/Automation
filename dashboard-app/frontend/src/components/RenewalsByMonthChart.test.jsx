import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import RenewalsByMonthChart from "./RenewalsByMonthChart";

describe("RenewalsByMonthChart", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("renders a bar with the count and month label for each bucket", () => {
    render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    expect(screen.getByText("Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("Sep 2026")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows an empty state when there are no buckets", () => {
    render(<RenewalsByMonthChart renewalsByMonth={[]} />);
    expect(screen.getByText("No certification expiry dates to chart yet.")).toBeInTheDocument();
  });

  it("does not render the jump-to-month dropdown when there are no buckets", () => {
    render(<RenewalsByMonthChart renewalsByMonth={[]} />);
    expect(screen.queryByLabelText("Jump to month")).not.toBeInTheDocument();
  });

  it("lists every month as a dropdown option with its label and count", () => {
    render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    expect(screen.getByLabelText("Jump to month")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Jul 2026 (2)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Sep 2026 (1)" })).toBeInTheDocument();
  });

  it("scrolls the selected month's bar into view when chosen from the dropdown", () => {
    const { container } = render(
      <RenewalsByMonthChart
        renewalsByMonth={[
          { year_month: "2026-07", count: 2 },
          { year_month: "2026-09", count: 1 },
        ]}
      />
    );
    const julBar = container.querySelector('[data-month="2026-07"]');
    const sepBar = container.querySelector('[data-month="2026-09"]');
    // Assign fresh mocks as own properties on each specific node (rather than
    // vi.spyOn, which resolves the inherited Element.prototype.scrollIntoView
    // and would install on the shared prototype instead of the instance).
    const julScroll = (julBar.scrollIntoView = vi.fn());
    const sepScroll = (sepBar.scrollIntoView = vi.fn());

    const select = screen.getByLabelText("Jump to month");
    fireEvent.change(select, { target: { value: "2026-09" } });

    expect(sepScroll).toHaveBeenCalledWith(
      expect.objectContaining({ inline: "center", block: "nearest" })
    );
    expect(julScroll).not.toHaveBeenCalled();
  });
});
