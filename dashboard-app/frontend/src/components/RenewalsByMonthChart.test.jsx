import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RenewalsByMonthChart from "./RenewalsByMonthChart";

describe("RenewalsByMonthChart", () => {
  it("renders a bar with the count and month label for each bucket", () => {
    render(
      <RenewalsByMonthChart
        clients={[{ expiry_date: "24-07-2026" }, { expiry_date: "02-07-2026" }, { expiry_date: "15-09-2026" }]}
      />
    );
    expect(screen.getByText("Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("Sep 2026")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shows an empty state when there are no clients", () => {
    render(<RenewalsByMonthChart clients={[]} />);
    expect(screen.getByText("No certification expiry dates to chart yet.")).toBeInTheDocument();
  });
});
