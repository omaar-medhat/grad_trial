import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TelemetrySourceBadge } from "./TelemetrySourceBadge";

describe("TelemetrySourceBadge", () => {
  it("renders the Firebase live label for a firebase source", () => {
    render(<TelemetrySourceBadge source="firebase" stale={false} lastUpdate={Date.now()} />);
    expect(screen.getByText(/firebase live/i)).toBeInTheDocument();
  });

  it("renders 'Simulator demo' for the simulator source", () => {
    render(<TelemetrySourceBadge source="simulator" stale={false} lastUpdate={Date.now()} />);
    expect(screen.getByText(/simulator demo/i)).toBeInTheDocument();
  });

  it("switches to a Stale label when stale", () => {
    render(<TelemetrySourceBadge source="firebase" stale={true} lastUpdate={Date.now()} />);
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
  });

  it("shows Disconnected when the device is disconnected", () => {
    render(
      <TelemetrySourceBadge
        source="firebase" stale lastUpdate={Date.now()} deviceStatus="disconnected"
      />,
    );
    expect(screen.getByText(/disconnected/i)).toBeInTheDocument();
  });

  it("shows the seconds-ago hint when fresh", () => {
    const fiveSecondsAgo = Date.now() - 5_000;
    render(<TelemetrySourceBadge source="firebase" stale={false} lastUpdate={fiveSecondsAgo} />);
    expect(screen.getByText(/s ago/i)).toBeInTheDocument();
  });
});
