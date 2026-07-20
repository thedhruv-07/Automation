import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import EmailPreviewModal from "./EmailPreviewModal";

describe("EmailPreviewModal", () => {
  it("renders nothing when clientId is null", () => {
    const { container } = render(
      <EmailPreviewModal clientId={null} fetchPreview={vi.fn()} onClose={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("fetches and displays the preview when clientId is set", async () => {
    const fetchPreview = vi.fn().mockResolvedValue({
      subject: "Renew ISO 9001 — TechCorp",
      html: "<html><body>Hello</body></html>",
    });
    render(<EmailPreviewModal clientId="CLT001" fetchPreview={fetchPreview} onClose={() => {}} />);
    await waitFor(() => expect(fetchPreview).toHaveBeenCalledWith("CLT001"));
    await waitFor(() => expect(screen.getByText(/Renew ISO 9001/)).toBeInTheDocument());
  });

  it("shows an error message when the fetch fails", async () => {
    const fetchPreview = vi.fn().mockRejectedValue(new Error("Failed to load email preview: 404"));
    render(<EmailPreviewModal clientId="CLT001" fetchPreview={fetchPreview} onClose={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText(/Could not load email preview/)).toBeInTheDocument()
    );
  });

  it("calls onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    const fetchPreview = vi.fn().mockResolvedValue({ subject: "Test Subject Line", html: "<html></html>" });
    render(<EmailPreviewModal clientId="CLT001" fetchPreview={fetchPreview} onClose={onClose} />);
    await waitFor(() => screen.getByText(/Test Subject Line/));
    fireEvent.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalled();
  });
});
