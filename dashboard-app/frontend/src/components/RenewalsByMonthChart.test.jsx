import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RenewalsByMonthChart from "./RenewalsByMonthChart";

describe("RenewalsByMonthChart", () => {
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
});
