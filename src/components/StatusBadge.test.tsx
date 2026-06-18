import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders 'Normal' for the normal status", () => {
    render(<StatusBadge status="normal" />);
    expect(screen.getByText("Normal")).toBeInTheDocument();
  });

  it("renders 'High' for the warning status", () => {
    render(<StatusBadge status="warning" />);
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("renders 'Critical' for the danger status", () => {
    render(<StatusBadge status="danger" />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });

  it("renders 'Low' for the low status", () => {
    render(<StatusBadge status="low" />);
    expect(screen.getByText("Low")).toBeInTheDocument();
  });
});
