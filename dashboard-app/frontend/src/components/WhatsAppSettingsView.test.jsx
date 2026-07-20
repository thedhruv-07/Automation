import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import WhatsAppSettingsView from "./WhatsAppSettingsView";

const info = {
  template_name: "cert_renewal_alert",
  template_lang: "en",
  phone_number_id: "1128915266981927",
  scheduled_run_time: "09:30 (Asia/Kolkata)",
  critical_days: 7,
  urgent_days: 30,
};

describe("WhatsAppSettingsView", () => {
  it("fetches and displays the settings info on mount", async () => {
    const fetchInfo = vi.fn().mockResolvedValue(info);
    render(<WhatsAppSettingsView fetchInfo={fetchInfo} />);
    await waitFor(() => expect(screen.getByText("cert_renewal_alert")).toBeInTheDocument());
    expect(screen.getByText("≤ 7 days")).toBeInTheDocument();
    expect(screen.getByText("≤ 30 days")).toBeInTheDocument();
    expect(screen.getByText("09:30 (Asia/Kolkata)")).toBeInTheDocument();
  });

  it("shows an error message when the fetch fails", async () => {
    const fetchInfo = vi.fn().mockRejectedValue(new Error("Failed to load settings info: 500"));
    render(<WhatsAppSettingsView fetchInfo={fetchInfo} />);
    await waitFor(() => expect(screen.getByTestId("settings-info-error")).toBeInTheDocument());
  });

  it("does not render any editable form controls", async () => {
    const fetchInfo = vi.fn().mockResolvedValue(info);
    render(<WhatsAppSettingsView fetchInfo={fetchInfo} />);
    await waitFor(() => screen.getByText("cert_renewal_alert"));
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});
