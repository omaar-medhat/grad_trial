import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Heart } from "lucide-react";
import { MetricCard } from "./MetricCard";

describe("MetricCard", () => {
  it("renders the label, value, and unit", () => {
    render(
      <MetricCard icon={Heart} label="Heart Rate" value={72} unit="bpm" status="normal" />
    );
    expect(screen.getByText("Heart Rate")).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("bpm")).toBeInTheDocument();
  });

  it("renders the status badge when a status is provided", () => {
    render(
      <MetricCard icon={Heart} label="Heart Rate" value={72} unit="bpm" status="warning" />
    );
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("renders a hint when supplied", () => {
    render(
      <MetricCard icon={Heart} label="Heart Rate" value={72} unit="bpm" hint="last 5 min average" />
    );
    expect(screen.getByText(/last 5 min average/i)).toBeInTheDocument();
  });

  it("renders a progress bar when progress is supplied", () => {
    render(
      <MetricCard icon={Heart} label="Steps" value={4500} unit="steps" progress={45} />
    );
    expect(screen.getByText(/45% of goal/)).toBeInTheDocument();
  });

  it("caps the progress bar fill at 100%", () => {
    const { container } = render(
      <MetricCard icon={Heart} label="Steps" value={20000} unit="steps" progress={250} />
    );
    const fill = container.querySelector('[style*="width:"]') as HTMLElement | null;
    expect(fill).not.toBeNull();
    expect(fill?.style.width).toBe("100%");
  });
});
