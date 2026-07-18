import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatCards from "./StatCards";

const clients = [
  { client_id: "1", status: "CRITICAL" },
  { client_id: "2", status: "URGENT" },
  { client_id: "3", status: "URGENT" },
  { client_id: "4", status: "DUE SOON" },
  { client_id: "5", status: "ACTIVE" },
];

describe("StatCards", () => {
  it("shows correct counts per status and total", () => {
    render(<StatCards clients={clients} />);
    expect(screen.getByTestId("stat-total")).toHaveTextContent("5");
    expect(screen.getByTestId("stat-CRITICAL")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-URGENT")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-DUE SOON")).toHaveTextContent("1");
  });
});
