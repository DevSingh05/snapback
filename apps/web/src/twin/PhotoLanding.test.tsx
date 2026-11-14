import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PhotoLanding } from "./PhotoLanding";
import type { LandingState } from "./landing";

const match: LandingState = {
  kind: "match",
  photoId: "l1",
  sweepId: "fx-sweep-03",
  roomLabel: "Living room",
  yaw: 44.7,
  pitch: 0,
  fovDeg: 70,
  position: [1.2, 1.5, -3.4],
};

const base = {
  photoSrc: "data:image/png;base64,AA==",
  opacity: 0.6,
  phase: "landed" as const,
  sdk: "ready" as const,
  reduced: false,
};

describe("PhotoLanding states", () => {
  it("match: shows the Taken here line, the photo, the marker and the cone", () => {
    render(<PhotoLanding {...base} state={match} />);
    expect(screen.getByText("Taken here: Living room")).toBeInTheDocument();
    expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0.6" });
    expect(screen.getByTestId("camera-marker")).toBeInTheDocument();
    expect(screen.getByTestId("view-cone")).toBeInTheDocument();
  });

  it("not found: says Not found in this building and shows no photo, marker or cone", () => {
    render(<PhotoLanding {...base} state={{ kind: "not_found" }} />);
    expect(screen.getByText("Not found in this building")).toBeInTheDocument();
    expect(screen.queryByTestId("photo-overlay")).toBeNull();
    expect(screen.queryByTestId("camera-marker")).toBeNull();
    expect(screen.queryByTestId("view-cone")).toBeNull();
  });

  it("placed: says Taken here with a no-camera-angle note and draws no cone or photo", () => {
    render(<PhotoLanding {...base} state={{ kind: "placed", photoId: "l2", roomLabel: null }} />);
    expect(screen.getByText("Taken here: this building")).toBeInTheDocument();
    expect(screen.getByText("No camera angle for this photo")).toBeInTheDocument();
    expect(screen.queryByTestId("view-cone")).toBeNull();
    expect(screen.queryByTestId("photo-overlay")).toBeNull();
  });

  it("elsewhere: says Not taken here and shows no cone", () => {
    render(<PhotoLanding {...base} state={{ kind: "elsewhere" }} />);
    expect(screen.getByText("Not taken here")).toBeInTheDocument();
    expect(screen.queryByTestId("view-cone")).toBeNull();
  });

  it("loading: announces it politely and shows no result line", () => {
    render(<PhotoLanding {...base} state={{ kind: "loading" }} phase="idle" />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(/Placing the photo/);
    expect(status).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText(/Taken here/)).toBeNull();
    expect(screen.queryByText(/Not found/)).toBeNull();
  });

  it("SDK unavailable: falls back to a static plan that still shows the cone and the photo", () => {
    render(<PhotoLanding {...base} state={match} sdk="unavailable" />);
    expect(screen.getByTestId("static-plan")).toBeInTheDocument();
    expect(screen.getByTestId("view-cone")).toBeInTheDocument();
    expect(screen.getByTestId("photo-overlay")).toBeInTheDocument();
    expect(screen.getByText("Taken here: Living room")).toBeInTheDocument();
    expect(screen.getByText("Schematic")).toBeInTheDocument();
  });

  it("with the SDK ready there is no static plan", () => {
    render(<PhotoLanding {...base} state={match} />);
    expect(screen.queryByTestId("static-plan")).toBeNull();
  });
});

describe("PhotoLanding motion", () => {
  it("normal motion: the photo card flies while the phase is flying", () => {
    render(<PhotoLanding {...base} state={match} phase="flying" opacity={0} />);
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-motion", "full");
    expect(screen.getByTestId("photo-overlay")).toHaveAttribute("data-flying", "true");
  });

  it("reduced motion: marks the root reduced and never marks the photo as flying", () => {
    render(<PhotoLanding {...base} state={match} phase="flying" reduced />);
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-motion", "reduced");
    expect(screen.getByTestId("photo-overlay")).not.toHaveAttribute("data-flying");
  });

  it("does not rebuild the cone path when only the opacity changes", () => {
    const { rerender } = render(<PhotoLanding {...base} state={match} opacity={0.2} />);
    const first = screen.getByTestId("view-cone-path").getAttribute("d");
    rerender(<PhotoLanding {...base} state={match} opacity={0.9} />);
    expect(screen.getByTestId("view-cone-path").getAttribute("d")).toBe(first);
  });

  it("turns the cone with a transform, not with new geometry", () => {
    const { rerender } = render(<PhotoLanding {...base} state={match} />);
    const d = screen.getByTestId("view-cone-path").getAttribute("d");
    rerender(<PhotoLanding {...base} state={{ ...match, yaw: 90 }} />);
    expect(screen.getByTestId("view-cone-path").getAttribute("d")).toBe(d);
    expect(screen.getByTestId("view-cone")).toHaveStyle({ transform: "rotate(-90deg)" });
  });
});

describe("TraceStrip", () => {
  afterEach(() => vi.useRealTimers());

  it("is collapsed by default and toggles with aria-expanded", async () => {
    const { TraceStrip } = await import("./TraceStrip");
    render(
      <TraceStrip>
        <p>trace body</p>
      </TraceStrip>,
    );
    const btn = screen.getByRole("button", { name: /Agent trace/ });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("trace-slot")).toHaveAttribute("hidden");
    act(() => {
      fireEvent.click(btn);
    });
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("trace-slot")).not.toHaveAttribute("hidden");
    expect(screen.getByText("trace body")).toBeInTheDocument();
  });
});
