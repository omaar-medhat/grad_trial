import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AlertSummary } from "./AlertSummary";

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("AlertSummary", () => {
  it("renders the all-clear state when no alerts exist", () => {
    renderWithRouter(<AlertSummary alerts={[]} />);
    expect(screen.getByText(/all clear today/i)).toBeInTheDocument();
    expect(screen.getByText(/no alerts have been raised/i)).toBeInTheDocument();
  });

  it("renders the newest alert message and a critical count", () => {
    renderWithRouter(
      <AlertSummary
        alerts={[
          { risk_level: "high", message: "Heart rate critical", timestamp: Date.now() },
          { risk_level: "warning", message: "SpO2 slightly low", timestamp: Date.now() - 1000 },
        ]}
      />
    );
    expect(screen.getByText("Heart rate critical")).toBeInTheDocument();
    expect(screen.getByText(/1 critical/i)).toBeInTheDocument();
    expect(screen.getByText(/1 watch/i)).toBeInTheDocument();
  });

  it("links to the alerts page", () => {
    renderWithRouter(
      <AlertSummary
        alerts={[{ risk_level: "warning", message: "Mild change", timestamp: Date.now() }]}
      />
    );
    const link = screen.getByRole("link", { name: /view all/i });
    expect(link).toHaveAttribute("href", "/alerts");
  });
});
