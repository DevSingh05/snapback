import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TourStop, TraceEvent } from "../contracts";

// The tour patterns of Matterport and Apartments.com applied to Walk it first: open outside, the
// highlight strip of ad photos, the ad photo over the view at its pose, a scan that is late, the
// end card with one action, the person standing in the drawn room, and a live trace's rail.

const { connect, fakeSdk } = vi.hoisted(() => {
  const fakeSdk = {
    disconnect: vi.fn(),
    Sweep: {
      moveTo: vi.fn().mockResolvedValue(undefined),
      data: { subscribe: vi.fn(() => ({ cancel: () => {} })) },
    },
  };
  return { fakeSdk, connect: { resolve: null as null | ((s: unknown) => void) } };
});

vi.mock("../twin/showcase", async (orig) => ({
  ...(await orig<typeof import("../twin/showcase")>()),
  // A scan that takes as long as the test says: it connects only when `connect.resolve` runs.
  connectShowcase: vi.fn(
    () =>
      new Promise((resolve) => {
        connect.resolve = resolve;
      }),
  ),
  watchSweeps: (_s: unknown, on: (ids: string[]) => void) => {
    on(["fx-sweep-00", "fx-sweep-01", "fx-sweep-03", "fx-sweep-06"]);
    return () => {};
  },
}));

import { railItems, stepForStop } from "../walk/rail";
import { FIXTURE_TOUR } from "./fixtureTour";
import { SCAN_WAIT_MS, TourView } from "./TourPage";

beforeEach(() => {
  connect.resolve = null;
  fakeSdk.Sweep.moveTo.mockClear();
});
afterEach(() => vi.useRealTimers());

const title = () => screen.getByRole("heading", { level: 1 }).textContent;

describe("the sample walk", () => {
  it("stays on the drawn 3D view and offers the real scan only through the scan card", () => {
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" sample />);
    expect(screen.queryByTitle("Matterport 3D view")).toBeNull();
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-main", "drawing");
    expect(screen.getByTestId("scan-offer")).toBeInTheDocument();
    expect(screen.queryByText(/Loading the 3D/)).toBeNull();
    expect(screen.getByTestId("walk-player")).toHaveAttribute("data-mode", "playing");
  });
});

describe("a scan that is slow to connect", () => {
  it("opens outside at once, plays on the drawing after the wait, and switches when the scan is in", async () => {
    vi.useFakeTimers();
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" />);
    // The drawing fills the stage while the scan loads in the corner window.
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-main", "drawing");
    expect(screen.getByTitle("Matterport 3D view")).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(4000));
    // The beat outside has played; the walk holds at the door, never frozen at 0:00.
    expect(title()).toBe("Arrive outside");
    expect(screen.getByTestId("wp-time")).toHaveTextContent("0:02");
    expect(screen.getByTestId("wp-caption")).toHaveTextContent("Loading the 3D scan");
    act(() => void vi.advanceTimersByTime(SCAN_WAIT_MS));
    expect(screen.getByTestId("wp-scan-late")).toHaveTextContent("3D scan still loading");
    act(() => void vi.advanceTimersByTime(2000));
    expect(title()).toBe("Front door");
    // The scan connects: the real view takes the stage and the chip goes.
    await act(async () => {
      connect.resolve!(fakeSdk);
      await Promise.resolve();
    });
    expect(screen.queryByTestId("wp-scan-late")).toBeNull();
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-main", "real");
  });
});

describe("the highlight strip and the ad photo over the view", () => {
  it("shows the ad photos in the bar, lights the current one, and a tap jumps to its stop", () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    const shots = screen.getAllByTestId("wp-shot");
    expect(shots).toHaveLength(FIXTURE_TOUR.stops.filter((s) => s.photos.length > 0).length);
    const kitchen = screen.getByRole("button", { name: "Chapter 4: Kitchen" });
    expect(within(kitchen).getByTestId("wp-shot")).toHaveTextContent("P2");
    // Stops with no ad photo stay text-only chapters.
    expect(
      within(screen.getByRole("button", { name: "Chapter 2: Front door" })).queryByTestId(
        "wp-shot",
      ),
    ).toBeNull();
    fireEvent.click(kitchen);
    expect(title()).toBe("Kitchen");
    expect(kitchen).toHaveAttribute("aria-current", "true");
  });

  it("fades the ad photo over the view after arrival, captioned and labelled a stand-in", () => {
    vi.useFakeTimers();
    render(<TourView plan={FIXTURE_TOUR} />);
    fireEvent.click(screen.getByRole("button", { name: "Chapter 4: Kitchen" }));
    const flash = screen.getByTestId("wp-flash");
    expect(flash).not.toHaveAttribute("data-on");
    act(() => void vi.advanceTimersByTime(2200));
    expect(flash).toHaveAttribute("data-on", "true");
    expect(flash).toHaveAttribute("data-stand-in", "true");
    expect(flash).toHaveTextContent("Ad photo P2");
    expect(flash).toHaveTextContent("stand-in");
    expect(screen.getByTestId("stage-caption")).toHaveTextContent("Taken here: ad photo P2");
    act(() => void vi.advanceTimersByTime(1500));
    expect(flash).not.toHaveAttribute("data-on");
  });
});

describe("the end card", () => {
  it("gives one action, and Watch again", () => {
    vi.useFakeTimers();
    render(<TourView plan={FIXTURE_TOUR} />);
    act(() => void vi.advanceTimersByTime(120_000));
    const end = screen.getByTestId("wp-end");
    expect(within(end).getAllByRole("link")).toHaveLength(1);
    expect(within(end).getByRole("link")).toHaveTextContent("Tour prep: what to ask");
    expect(within(end).getByRole("button", { name: "Watch again" })).toBeInTheDocument();
  });
});

describe("the person in the drawn room", () => {
  it("stands at the room's spot as You are here, in the stage and the corner window alike", () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    fireEvent.click(screen.getByRole("button", { name: "Chapter 3: Living room" }));
    const here = screen.getByTestId("you-are-here");
    expect(within(here).getByTestId("person")).toBeInTheDocument();
    expect(here.querySelector("circle.dk-head")).not.toBeNull();
    expect(here.querySelector(".rs-here-cone")).not.toBeNull();
  });
});

// A recorded-style live trace: the shape a live run streams (sub-agent hand-offs, photos counted
// not named, a floor-plan pick, the verdict). Team-made text, no sponsor rows.
function ev(seq: number, kind: string, pick: string | null, reason: string, choice?: string) {
  return {
    case_id: "LIVE1",
    seq,
    at: new Date(Date.UTC(2026, 10, 14, 18, 0, seq)).toISOString(),
    kind,
    choice: choice ?? null,
    options: [],
    pick,
    reason,
    source: "live",
    chosen_by: "policy",
  } as unknown as TraceEvent;
}
const LIVE_TRACE: TraceEvent[] = [
  ev(
    0,
    "choice",
    "twin+rules+challenge",
    "The building has a scan and the ad has 3 photos.",
    "which_checks",
  ),
  ev(1, "tool", "locate", "Placing 3 listing photos in the twin."),
  ev(2, "status", "owner of record", "Skipped owner of record: none on record."),
  ev(3, "choice", "home record", "Only one option was open.", "next_check"),
  ev(
    4,
    "choice",
    "floor plan 1",
    "Plan A placed all 3 photos; Plan B placed none.",
    "which_floor_plan",
  ),
  ev(5, "verdict", "hold", "We could not confirm who may rent this unit."),
  ev(6, "agent", "sub-agent: record", "Handed the record checks to a sub-agent."),
  ev(7, "agent", "sub-agent done: record", "The record sub-agent finished."),
  ev(8, "agent", "sub-agent: place", "Handed the place checks to a sub-agent."),
  ev(9, "agent", "sub-agent done: place", "The place sub-agent finished."),
  ev(10, "file", "file: /case/LIVE1/place.md", "Note written: /case/LIVE1/place.md."),
  ev(11, "file", "file: /case/LIVE1/tour_prep.md", "Note written: /case/LIVE1/tour_prep.md."),
];

function stop(over: Partial<TourStop> & Pick<TourStop, "kind" | "key" | "title">): TourStop {
  return {
    sweep_count: 0,
    sweep_ids: [],
    photos: [],
    ad_view: "unknown",
    claims: [],
    facts: [],
    ...over,
  };
}
const photo = (alias: string, id: string) => ({
  photo_id: id,
  alias,
  sweep_id: "s",
  position: [0, 0, 0] as [number, number, number],
  rotation_quat: [0, 0, 0, 1] as [number, number, number, number],
  fov_deg: 70,
});
const LIVE_STOPS: TourStop[] = [
  stop({ kind: "arrive", key: "arrive", title: "Arrive outside" }),
  stop({ kind: "door", key: "door", title: "Front door" }),
  stop({
    kind: "room",
    key: "room-1",
    title: "Bathroom",
    room_label: "Bathroom",
    photos: [photo("P2", "l2")],
    ad_view: "placed",
  }),
  stop({
    kind: "room",
    key: "room-2",
    title: "Living Room",
    room_label: "Living Room",
    photos: [photo("P3", "l3")],
    ad_view: "placed",
  }),
  stop({
    kind: "room",
    key: "room-3",
    title: "Bedroom",
    room_label: "Bedroom",
    photos: [photo("P1", "l1")],
    ad_view: "placed",
  }),
  stop({ kind: "outro", key: "outro", title: "Now see it in person" }),
];

describe("the rail on a live trace", () => {
  it("lights a different, fitting step as the walk moves, never stuck on step 01", () => {
    const items = railItems(LIVE_TRACE);
    const lit = LIVE_STOPS.map((s) => stepForStop(items, s));
    // Outside: the record agent's step. The door: the floor plan whose rooms are walked. Each
    // photo stop: a step that placed the ad's photos. The end: the verdict.
    expect(lit[0]).toBe(6);
    expect(lit[1]).toBe(4);
    expect(lit.slice(2, 5).sort()).toEqual([1, 4, 8]);
    expect(lit[5]).toBe(5);
    expect(new Set(lit).size).toBeGreaterThanOrEqual(4);
    expect(lit.filter((n) => n === 0)).toEqual([]);
  });

  it("names agents by their short names, so hand-offs and their notes share a lane", () => {
    const items = railItems(LIVE_TRACE);
    expect(items.find((i) => i.event.seq === 10)!.agent).toBe("place");
    expect(items.find((i) => i.event.seq === 7)!.agent).toBe("record");
  });

  it("matches a photo by its id or alias when the trace names it", () => {
    const named = [...LIVE_TRACE, ev(12, "unsure", null, "Photo l3 fell short of the bar.")];
    expect(stepForStop(railItems(named), LIVE_STOPS[3]!)).toBe(12);
  });
});
