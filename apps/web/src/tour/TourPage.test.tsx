import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { fakeSdk, sweepIds, reducedRef } = vi.hoisted(() => ({
  sweepIds: {
    current: ["fx-sweep-00", "fx-sweep-01", "fx-sweep-03", "fx-sweep-04", "fx-sweep-06"],
  },
  reducedRef: { current: false },
  fakeSdk: {
    disconnect: vi.fn(),
    Sweep: { moveTo: vi.fn().mockResolvedValue(undefined), data: { subscribe: vi.fn() } },
  },
}));

vi.mock("../twin/showcase", async (orig) => ({
  ...(await orig<typeof import("../twin/showcase")>()),
  connectShowcase: vi.fn().mockResolvedValue(fakeSdk),
  watchSweeps: (_s: unknown, on: (ids: string[]) => void) => {
    on(sweepIds.current);
    return () => {};
  },
}));
vi.mock("../twin/useReducedMotion", () => ({ usePrefersReducedMotion: () => reducedRef.current }));

import { TwinView } from "../twin/TwinPage";
import { FIXTURE_TOUR } from "./fixtureTour";
import { AUTOPLAY_MS, TourView, evenStops } from "./TourPage";

beforeEach(() => {
  fakeSdk.Sweep.moveTo.mockClear();
  sweepIds.current = ["fx-sweep-00", "fx-sweep-01", "fx-sweep-03", "fx-sweep-04", "fx-sweep-06"];
  reducedRef.current = false;
});
afterEach(() => vi.useRealTimers());

const title = () => screen.getByRole("heading", { level: 1 }).textContent;

describe("TourView in fixture mode (no SDK)", () => {
  it("shows FIXTURE, the exact scan label and a placeholder, and steps with Next and Back", async () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    const chips = screen.getAllByTestId("source-chip").map((c) => c.textContent);
    expect(chips.every((c) => c?.includes("FIXTURE"))).toBe(true);
    expect(
      screen.getByText(
        /a 3D scan in this building \(it may be a model unit, not the one you'd rent\)/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("tour-placeholder")).toBeInTheDocument();
    expect(title()).toBe("Arrive outside");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(title()).toBe("Front door");
    expect(screen.getByText(/Check this in person:/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(title()).toBe("Arrive outside");
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();
  });

  it("shows every fact with its source and the progress rail jumps to a room", async () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    expect(screen.getByText(/Built in 1998/).parentElement).toHaveTextContent("CoStar record");
    await userEvent.setup().click(screen.getByRole("button", { name: "Kitchen" }));
    expect(title()).toBe("Kitchen");
    expect(screen.getByRole("button", { name: "Kitchen" })).toHaveAttribute("aria-current", "step");
    expect(screen.getByText(/Your ad photo photo-1 was placed in this room/)).toBeInTheDocument();
    expect(screen.getByText(/automatic labels/)).toBeInTheDocument();
  });

  it("ends on the outro with the tour-prep link", async () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    const rail = screen.getByRole("navigation", { name: "Tour progress" });
    await userEvent.setup().click(rail.querySelector("li:last-child button")!);
    expect(title()).toBe("Now see it in person");
    expect(screen.getByTestId("tour-prep-link")).toHaveAttribute(
      "href",
      "/prep/place/fixture-bldg-1",
    );
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("autoplays about every 6 s, pauses on any interaction, and stops at the end", () => {
    vi.useFakeTimers();
    render(<TourView plan={FIXTURE_TOUR} />);
    fireEvent.click(screen.getByRole("button", { name: /Autoplay off/ }));
    expect(AUTOPLAY_MS).toBe(6000);
    act(() => void vi.advanceTimersByTime(5900));
    expect(title()).toBe("Arrive outside");
    act(() => void vi.advanceTimersByTime(200));
    expect(title()).toBe("Front door");
    // Any interaction on the page pauses it.
    fireEvent.pointerDown(screen.getByRole("heading", { level: 1 }));
    expect(screen.getByRole("button", { name: /Autoplay off/ })).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(20000));
    expect(title()).toBe("Front door");
    // Resume and run to the end: it switches itself off on the last step.
    fireEvent.click(screen.getByRole("button", { name: /Autoplay off/ }));
    for (let i = 0; i < FIXTURE_TOUR.stops.length; i++)
      act(() => void vi.advanceTimersByTime(AUTOPLAY_MS));
    expect(title()).toBe("Now see it in person");
    expect(screen.getByRole("button", { name: /Autoplay off/ })).toBeDisabled();
  });
});

describe("TourView with a mocked Showcase SDK", () => {
  it("moves the 3D view to each stop's own sweep on Next and Back", async () => {
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" />);
    await waitFor(() => expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("LIVE"));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(fakeSdk.Sweep.moveTo).toHaveBeenLastCalledWith(
        "fx-sweep-00",
        expect.objectContaining({ transition: "transition.fly" }),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(fakeSdk.Sweep.moveTo).toHaveBeenLastCalledWith("fx-sweep-01", expect.anything()),
    );
    await user.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() =>
      expect(fakeSdk.Sweep.moveTo).toHaveBeenLastCalledWith("fx-sweep-00", expect.anything()),
    );
  });

  it("moves instantly when the viewer prefers reduced motion", async () => {
    reducedRef.current = true;
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" />);
    await waitFor(() => expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("LIVE"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(fakeSdk.Sweep.moveTo).toHaveBeenCalledWith(
        "fx-sweep-00",
        expect.objectContaining({ transition: "transition.instant", transitionTime: 0 }),
      ),
    );
  });

  it("does not fly to a stand-in when one sweep is missing from the model", async () => {
    sweepIds.current = ["fx-sweep-00", "fx-sweep-01", "fx-sweep-04"]; // no sweep-03 (Kitchen)
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" />);
    await waitFor(() => expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("LIVE"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Kitchen" }));
    await screen.findByText("This stop is not in the loaded 3D model");
    expect(fakeSdk.Sweep.moveTo).not.toHaveBeenCalledWith("fx-sweep-03", expect.anything());
  });

  it("walks the model's own sweeps, unlabelled, when none of the plan's sweeps are in it", async () => {
    sweepIds.current = ["real-1", "real-2", "real-3", "real-4"];
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" />);
    await screen.findByRole("button", { name: "Stop 1" });
    expect(screen.queryByRole("button", { name: "Kitchen" })).toBeNull();
    await userEvent.setup().click(screen.getByRole("button", { name: "Front door" }));
    expect(screen.getByText("Start of the 3D scan")).toBeInTheDocument();
    expect(screen.getByText(/Rooms are not labelled/)).toBeInTheDocument();
  });
});

describe("evenStops", () => {
  it("starts at the scan start and spaces the rest evenly, capped at 8", () => {
    const ids = Array.from({ length: 30 }, (_, i) => `s${i}`);
    const stops = evenStops(ids);
    expect(stops).toHaveLength(9);
    expect(stops[0]).toMatchObject({ kind: "door", sweep_id: "s0" });
    expect(stops[1]!.sweep_id).toBe("s1");
    expect(stops.at(-1)!.sweep_id).toBe("s29");
    expect(evenStops([])).toEqual([]);
  });
});

describe("links to the tour", () => {
  it("the twin page links to the claimed building's tour with its case", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByTestId("walk-it-first-link")).toHaveAttribute(
      "href",
      "/tour/fx-prop-1?case=fx-7Q2M",
    );
  });
});
