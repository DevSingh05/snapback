// @vitest-environment jsdom
// The crew scene's setting and its words: the plot has real ground under it and a street of
// neighbours behind it, every figure and the home cast a soft shadow, speech sits in two fixed
// slots over the sky (so it can be large and never covers a member), and the panel puts the
// scene first so it fits one screen.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Part } from "../draw/kit";
import { CrewScene } from "./CrewScene";
import { HOME, PLOT, VIEW, bubbleSlots, crewBubbles, crewCast } from "./crew";
import { PATH, crewScenery, tuftSpots } from "./crewGround";
import { bundledRoster, floorAt, schedule, teamView, type Floor } from "./model";
import { sampleCard, sampleTimeline } from "./sample";
import { TeamPanel } from "./TeamPanel";
import type { Run } from "./useRun";
import { WORDS } from "./words";

const roster = bundledRoster("en");
const beats = schedule(sampleTimeline);
const beatOf = (kind: string) => beats[sampleTimeline.steps.findIndex((s) => s.kind === kind)]!;
const floor = (at = Infinity) =>
  floorAt({ roster, card: sampleCard, timeline: sampleTimeline, at });
const whole = floor();
const named = (parts: Part[], name: string) => parts.filter((p) => p.name === name);

afterEach(cleanup);

describe("the setting", () => {
  const scene = crewScenery();

  it("is wider than it is tall, so words have room beside the plot", () => {
    expect(VIEW.w).toBeGreaterThan(VIEW.h);
  });

  it("gives the lawn mowing stripes, tufts and a paved path from the door to the street", () => {
    expect(named(scene.lawn, "stripe").length).toBeGreaterThanOrEqual(8);
    expect(named(scene.lawn, "tufts")).toHaveLength(1);
    expect(named(scene.lawn, "path")).toHaveLength(1);
    expect(named(scene.lawn, "pavers")).toHaveLength(1);
    expect(named(scene.streets, "street").length).toBeGreaterThanOrEqual(2);
    expect(named(scene.streets, "sidewalk").length).toBeGreaterThanOrEqual(2);
  });

  it("keeps the grass tufts on the grass: inside the plot, off the home and off the path", () => {
    const spots = tuftSpots();
    expect(spots.length).toBeGreaterThanOrEqual(30);
    for (const [x, y] of spots) {
      expect(x).toBeGreaterThan(0);
      expect(x).toBeLessThan(PLOT);
      expect(y).toBeGreaterThan(0);
      expect(y).toBeLessThan(PLOT);
      const onHome =
        x > HOME.x - 4 && x < HOME.x + HOME.w + 4 && y > HOME.y - 4 && y < HOME.y + HOME.d + 4;
      const onPath = x > PATH.x - 2 && y > PATH.y - 2 && y < PATH.y + PATH.d + 2;
      expect(onHome || onPath).toBe(false);
    }
    // The same lawn every time: nothing here is random.
    expect(tuftSpots()).toEqual(spots);
  });

  it("stands a street of neighbours and trees behind the plot, none of them on it", () => {
    expect(named(scene.backdrop, "neighbour").length).toBeGreaterThanOrEqual(4);
    expect(named(scene.backdrop, "backdrop-tree").length).toBeGreaterThanOrEqual(3);
    expect(scene.neighbours.length).toBeGreaterThanOrEqual(4);
    for (const n of scene.neighbours) expect(n.x + n.w < 0 || n.y + n.d < 0).toBe(true);
  });
});

describe("the scene, drawn", () => {
  const props = (f: Floor, moving = false) => ({
    floor: f,
    team: teamView(f, whole),
    w: WORDS.en,
    lang: "en" as const,
    moving,
  });

  it("draws the sky, the backdrop behind the plot and a soft shadow under the home and each member", () => {
    render(<CrewScene {...props(whole)} />);
    const svg = screen.getByTestId("crew-scene").querySelector("svg")!;
    const order = [...svg.querySelectorAll("[data-testid]")].map((e) =>
      e.getAttribute("data-testid"),
    );
    expect(order.indexOf("crew-sky")).toBe(0);
    expect(order.indexOf("crew-backdrop")).toBeLessThan(order.indexOf("crew-haze"));
    expect(order.indexOf("crew-haze")).toBeLessThan(order.indexOf("crew-home"));
    expect(screen.getByTestId("crew-home-shadow")).toBeInTheDocument();
    const staged = screen
      .getAllByTestId("crew-actor")
      .filter((a) => a.getAttribute("data-place") !== "bench");
    for (const a of staged) expect(a.querySelector(".cs-shadow")).not.toBeNull();
  });

  it("marks who is speaking, and only them", () => {
    const f = floor(beatOf("locate").start + 10);
    render(<CrewScene {...props(f)} />);
    const speaking = screen
      .getAllByTestId("crew-actor")
      .filter((a) => a.getAttribute("data-speaking") === "yes")
      .map((a) => a.getAttribute("data-who"));
    const bubbles = screen.getAllByTestId("crew-bubble").map((b) => b.getAttribute("data-agent"));
    expect(speaking.length).toBeGreaterThan(0);
    expect([...speaking].sort()).toEqual([...bubbles].sort());
  });

  it("puts each bubble in its own slot, on its speaker's side when that slot is free", () => {
    for (const at of [beatOf("locate").start + 10, beatOf("record").start + 10, Infinity]) {
      const f = floor(at);
      const cast = crewCast(f, teamView(f, whole));
      const bubbles = crewBubbles(f, cast, 2);
      const slots = bubbleSlots(bubbles, cast);
      expect(slots).toHaveLength(bubbles.length);
      expect(new Set(slots).size).toBe(slots.length);
      const first = cast.find((a) => a.id === bubbles[0]?.deskId);
      if (first && first.side !== "mid") expect(slots[0]).toBe(first.side);
    }
    render(<CrewScene {...props(floor(beatOf("locate").start + 10))} />);
    for (const b of screen.getAllByTestId("crew-bubble"))
      expect(["left", "right"]).toContain(b.getAttribute("data-slot"));
  });
});

describe("the panel, scene first", () => {
  const ready: Run = { status: "ready", card: sampleCard, timeline: sampleTimeline, listing: null };
  const after = (a: Element, b: Element) =>
    Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

  it("on Live the Decider's stamp and the view switch sit under the scene, not over it", () => {
    render(<TeamPanel caseId={sampleCard.case_id} run={ready} roster={roster} reduced />);
    const scene = screen.getByTestId("crew-scene");
    const pane = scene.closest("[role=tabpanel]")!;
    const decider = screen.getByTestId("team-decider");
    expect(pane.contains(decider)).toBe(true);
    expect(after(scene, decider)).toBe(true);
    expect(after(scene, screen.getByRole("button", { name: "Diagram" }))).toBe(true);
    expect(screen.getAllByTestId("team-decider")).toHaveLength(1);
    expect(screen.getByTestId("team-verdict")).toBeInTheDocument();
  });

  it("on the other tabs the Decider's stamp stays in the header", () => {
    render(<TeamPanel caseId={sampleCard.case_id} run={ready} roster={roster} reduced />);
    fireEvent.click(screen.getByTestId("team-tab-meet"));
    const decider = screen.getByTestId("team-decider");
    expect(decider.closest("header")).not.toBeNull();
    expect(screen.getAllByTestId("team-decider")).toHaveLength(1);
    expect(screen.getByTestId("team-verdict")).toBeVisible();
  });
});
