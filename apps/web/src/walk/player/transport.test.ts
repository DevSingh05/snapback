import { describe, expect, it } from "vitest";

import { FIXTURE_TOUR } from "../../tour/fixtureTour";
import {
  ARRIVE_MS,
  LAND_MS,
  OUTSIDE_MS,
  PAN_DEG,
  PAN_MS,
  buildChapters,
  locate,
  totalMs,
} from "./timeline";
import { Transport, fakeClock, type Cue } from "./transport";

const STOPS = FIXTURE_TOUR.stops;
const PLAIN = ARRIVE_MS + PAN_MS; // a stop with no ad photo
const KITCHEN = STOPS.findIndex((s) => s.photos.length > 0);

function setup(options: { reduced?: boolean; ready?: boolean } = {}) {
  const clock = fakeClock();
  const cues: Cue[] = [];
  const transport = new Transport(STOPS, { clock, onCue: (c) => cues.push(c), ...options });
  const stopsSent = () => cues.filter((c) => c.type === "stop").map((c) => c.index);
  return { clock, cues, transport, stopsSent, at: () => transport.getState() };
}

describe("the timeline", () => {
  it("opens with a short beat outside, and a stop with an ad photo holds for its photo", () => {
    const chapters = buildChapters(STOPS);
    expect(chapters.map((c) => c.title)).toEqual(STOPS.map((s) => s.title));
    expect(chapters[0]!).toMatchObject({ duration: OUTSIDE_MS, outside: true });
    expect(OUTSIDE_MS).toBeGreaterThanOrEqual(2000);
    expect(OUTSIDE_MS).toBeLessThanOrEqual(3000);
    expect(chapters[1]!.duration).toBe(PLAIN);
    expect(chapters[KITCHEN]!.duration).toBe(PLAIN + LAND_MS);
    expect(LAND_MS).toBe(1500);
    expect(totalMs(chapters)).toBe(OUTSIDE_MS + (STOPS.length - 1) * PLAIN + LAND_MS);
  });

  it("finds the stop and the time inside it for any point", () => {
    const chapters = buildChapters(STOPS);
    expect(locate(chapters, 0)).toEqual({ index: 0, t: 0 });
    expect(locate(chapters, OUTSIDE_MS + 1200)).toEqual({ index: 1, t: 1200 });
    expect(locate(chapters, -50)).toEqual({ index: 0, t: 0 });
    expect(locate(chapters, 1e9).index).toBe(STOPS.length - 1);
  });
});

describe("the transport", () => {
  it("starts paused, plays through the stops in order, and stops at the end", () => {
    const { clock, transport, stopsSent, at } = setup();
    expect(at().mode).toBe("paused");
    clock.advance(10_000);
    expect(at()).toMatchObject({ index: 0, t: 0 });

    transport.play();
    clock.advance(OUTSIDE_MS - 100);
    expect(at().index).toBe(0);
    clock.advance(200);
    expect(at()).toMatchObject({ index: 1, mode: "playing" });

    clock.advance(transport.total);
    expect(at()).toMatchObject({ index: STOPS.length - 1, mode: "paused", ended: true });
    expect(stopsSent()).toEqual([1, 2, 3, 4, 5, 6]);
    expect(transport.position()).toBe(transport.total);

    // Play again starts over from the first stop.
    transport.play();
    expect(at()).toMatchObject({ index: 0, t: 0, mode: "playing", ended: false });
  });

  it("pauses and picks up where it left off", () => {
    const { clock, transport, at } = setup();
    transport.jumpTo(1);
    transport.play();
    clock.advance(3000);
    transport.pause();
    clock.advance(60_000);
    expect(at()).toMatchObject({ index: 1, t: 3000, mode: "paused" });
    transport.toggle();
    clock.advance(1000);
    expect(at()).toMatchObject({ index: 1, t: 4000, mode: "playing" });
  });

  it("plays the beat outside while the real 3D view loads, then holds at the door", () => {
    const { clock, transport, at } = setup({ ready: false });
    transport.play();
    clock.advance(1000);
    expect(at()).toMatchObject({ index: 0, t: 1000 });
    clock.advance(10_000);
    expect(at()).toMatchObject({ index: 0, t: OUTSIDE_MS - 1 });
    transport.setReady(true);
    clock.advance(1001);
    expect(at()).toMatchObject({ index: 1, t: 1000 });
  });

  it("never moves a stop inside the building while the real 3D view loads", () => {
    const { clock, transport, at } = setup({ ready: false });
    transport.jumpTo(2);
    transport.play();
    clock.advance(5000);
    expect(at()).toMatchObject({ index: 2, t: 0 });
  });

  it("plays one and a half times as fast at 1.5x", () => {
    const { clock, transport, at } = setup();
    transport.setSpeed(1.5);
    transport.jumpTo(1);
    transport.play();
    clock.advance(2000);
    expect(at().t).toBe(3000);
  });

  it("seeks to a stop and a point in its dwell, with the camera already turned that far", () => {
    const { transport, cues, at } = setup();
    const intoPan = ARRIVE_MS + PAN_MS / 2;
    transport.seek(transport.chapters[2]!.start + intoPan);
    expect(at()).toMatchObject({ index: 2, t: intoPan, mode: "paused" });
    expect(cues.at(-1)).toEqual({
      type: "stop",
      index: 2,
      panDeg: PAN_DEG / 2,
      instant: false,
      speed: 1,
    });
  });

  it("keeps playing from the new point when sought while playing", () => {
    const { clock, transport, at } = setup();
    transport.play();
    transport.seek(transport.chapters[4]!.start);
    clock.advance(500);
    expect(at()).toMatchObject({ index: 4, t: 500, mode: "playing" });
  });

  it("scrubbing shows the stop under the thumb and leaves the camera for the release", () => {
    const { transport, cues } = setup();
    transport.scrub(transport.chapters[3]!.start + 10);
    transport.scrub(transport.chapters[3]!.start + 900);
    expect(cues).toEqual([{ type: "index", index: 3 }]);
    transport.seek(transport.chapters[3]!.start + 900);
    expect(cues.at(-1)).toMatchObject({ type: "stop", index: 3 });
  });

  it("steps by chapter: next, and previous restarts the chapter before leaving it", () => {
    const { clock, transport, at } = setup();
    transport.jumpTo(2);
    transport.next();
    expect(at()).toMatchObject({ index: 3, t: 0 });
    transport.previous();
    expect(at().index).toBe(2);
    transport.play();
    clock.advance(3000);
    transport.previous();
    expect(at()).toMatchObject({ index: 2, t: 0 });
    transport.jumpTo(STOPS.length - 1);
    transport.next();
    expect(at().index).toBe(STOPS.length - 1);
  });

  it("pans the camera in half-second turns that add up to the whole sweep", () => {
    const { clock, transport, cues } = setup();
    transport.jumpTo(1);
    transport.play();
    clock.advance(ARRIVE_MS - 100);
    expect(cues.filter((c) => c.type === "pan")).toEqual([]);
    clock.advance(PAN_MS);
    const pans = cues.filter((c) => c.type === "pan");
    expect(pans.every((c) => c.index === 1 && c.ms === 500)).toBe(true);
    expect(pans.reduce((sum, c) => sum + c.deg, 0)).toBeCloseTo(PAN_DEG);
  });

  it("lands the ad photo: pins it for a second and a half, then lets it go as the pan starts", () => {
    const { clock, transport, cues, at } = setup();
    transport.jumpTo(KITCHEN);
    transport.play();
    clock.advance(ARRIVE_MS - 100);
    expect(at().landing).toBe(false);
    clock.advance(200);
    expect(at().landing).toBe(true);
    expect(cues.at(-1)).toEqual({ type: "photo", index: KITCHEN, shown: true });
    expect(cues.some((c) => c.type === "pan")).toBe(false);
    clock.advance(LAND_MS);
    expect(at().landing).toBe(false);
    expect(cues).toContainEqual({ type: "photo", index: KITCHEN, shown: false });
    expect(cues.some((c) => c.type === "pan")).toBe(true);
  });

  it("explore stops the tour and sends nothing until resume", () => {
    const { clock, transport, cues, at } = setup();
    transport.play();
    clock.advance(OUTSIDE_MS + 1000);
    transport.explore();
    const sent = cues.length;
    clock.advance(120_000);
    expect(at()).toMatchObject({ mode: "exploring", index: 1 });
    expect(cues.length).toBe(sent);

    // Picking a room in explore changes what is shown, with no camera move.
    transport.exploreGoto(4);
    expect(cues.at(-1)).toEqual({ type: "index", index: 4 });
    expect(cues.filter((c) => c.type === "stop" || c.type === "pan").length).toBe(
      cues.slice(0, sent).filter((c) => c.type === "stop" || c.type === "pan").length,
    );
  });

  it("resume returns to the timeline at the start of the nearest stop, playing", () => {
    const { clock, transport, cues, at } = setup();
    transport.play();
    clock.advance(3000);
    transport.explore();
    transport.resume(5);
    expect(at()).toMatchObject({ mode: "playing", index: 5, t: 0 });
    expect(cues.at(-1)).toMatchObject({ type: "stop", index: 5, panDeg: 0 });
    clock.advance(700);
    expect(at().t).toBe(700);

    // With no nearest stop known, it resumes at the stop it was on.
    transport.explore();
    transport.resume(null);
    expect(at()).toMatchObject({ mode: "playing", index: 5, t: 0 });
  });

  it("a jump from outside ends explore, paused at that stop", () => {
    const { transport, at } = setup();
    transport.explore();
    transport.jumpTo(3);
    expect(at()).toMatchObject({ mode: "paused", index: 3, t: 0 });
  });

  it("reduced motion: paused, stops change in instant jumps, and no pan is ever sent", () => {
    const { clock, transport, cues, at } = setup({ reduced: true });
    expect(at()).toMatchObject({ mode: "paused", reduced: true });
    transport.play();
    clock.advance(PLAIN * 2 + 100);
    expect(at().index).toBe(2);
    expect(cues.some((c) => c.type === "pan")).toBe(false);
    expect(cues.filter((c) => c.type === "stop").every((c) => c.instant && c.panDeg === 0)).toBe(
      true,
    );
    // Resuming from explore does not start playing by itself.
    transport.explore();
    transport.resume();
    expect(at().mode).toBe("paused");
  });

  it("turning reduced motion on mid-play pauses the tour", () => {
    const { clock, transport, at } = setup();
    transport.play();
    clock.advance(1000);
    transport.setReduced(true);
    expect(at()).toMatchObject({ mode: "paused", reduced: true });
  });
});
