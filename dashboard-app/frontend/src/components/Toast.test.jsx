import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Toast from "./Toast";

describe("Toast", () => {
  it("renders nothing when toast is null", () => {
    render(<Toast toast={null} onDismiss={() => {}} />);
    expect(screen.queryByTestId("toast")).not.toBeInTheDocument();
  });

  it("shows the toast message when set", () => {
    render(<Toast toast={{ type: "success", message: "Sent to Rahul Sharma" }} onDismiss={() => {}} />);
    expect(screen.getByText("Sent to Rahul Sharma")).toBeInTheDocument();
  });
});
