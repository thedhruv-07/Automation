import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import LoginScreen from "./LoginScreen";
import * as api from "../api";

vi.mock("../api");

beforeEach(() => {
  vi.resetAllMocks();
});

describe("LoginScreen", () => {
  it("calls onSuccess once verification succeeds", async () => {
    api.verifyCredentials.mockResolvedValue(true);
    const onSuccess = vi.fn();
    render(<LoginScreen onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByText("Sign in"));

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(api.verifyCredentials).toHaveBeenCalledWith("Basic " + btoa("admin:s3cret"));
  });

  it("shows an error and does not call onSuccess when verification fails", async () => {
    api.verifyCredentials.mockResolvedValue(false);
    const onSuccess = vi.fn();
    render(<LoginScreen onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrong" } });
    fireEvent.click(screen.getByText("Sign in"));

    await waitFor(() => expect(screen.getByText("Invalid username or password.")).toBeInTheDocument());
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("toggles the password field between hidden and visible text", () => {
    render(<LoginScreen onSuccess={vi.fn()} />);

    const passwordInput = screen.getByLabelText("Password");
    expect(passwordInput).toHaveAttribute("type", "password");

    fireEvent.click(screen.getByLabelText("Show password"));
    expect(passwordInput).toHaveAttribute("type", "text");

    fireEvent.click(screen.getByLabelText("Hide password"));
    expect(passwordInput).toHaveAttribute("type", "password");
  });
});
