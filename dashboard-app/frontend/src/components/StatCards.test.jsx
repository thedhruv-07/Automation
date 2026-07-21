import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatCards from "./StatCards";

describe("StatCards", () => {
  it("shows counts from the given stats object", () => {
    const stats = { status_counts: { total: 5, CRITICAL: 1, URGENT: 2, "DUE SOON": 1 } };
    render(<StatCards stats={stats} />);
    expect(screen.getByTestId("stat-total")).toHaveTextContent("5");
    expect(screen.getByTestId("stat-CRITICAL")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-URGENT")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-DUE SOON")).toHaveTextContent("1");
  });

  it("shows zero for a status with no matching clients", () => {
    const stats = { status_counts: { total: 0 } };
    render(<StatCards stats={stats} />);
    expect(screen.getByTestId("stat-CRITICAL")).toHaveTextContent("0");
  });
});
