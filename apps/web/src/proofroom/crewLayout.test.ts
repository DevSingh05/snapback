// @vitest-environment node
// Where the words go on the crew's stage: no name tag, speech slot, stamp or bench line may
// touch another, or stand on a figure, for this ad's crew and for a full stage.
import { describe, expect, it } from "vitest";

import { VIEW, crewCast } from "./crew";
import {
  BENCH_LINE,
  HOME_BOX,
  SLOTS,
  STAMP,
  collisions,
  figureBox,
  tagLayout,
  type Box,
} from "./crewLayout";
import { bundledRoster, floorAt, schedule, teamView, type Floor } from "./model";
import { sampleCard, sampleTimeline } from "./sample";

const roster = bundledRoster("en");
const beats = schedule(sampleTimeline);
const beatOf = (kind: string) => beats[sampleTimeline.steps.findIndex((s) => s.kind === kind)]!;
const floor = (at = Infinity) =>
  floorAt({ roster, card: sampleCard, timeline: sampleTimeline, at });
const whole = floor();

describe("where the words go", () => {
  const label = (cast: ReturnType<typeof crewCast>) =>
    new Map(
      cast.map((a) => [
        a.id,
        { name: a.card.name.replace(/ agent$/i, ""), model: "Claude Sonnet" },
      ]),
    );
  const everything = (cast: ReturnType<typeof crewCast>): [string, Box][] => [
    ["slot-left", SLOTS.left],
    ["slot-right", SLOTS.right],
    ["stamp", STAMP],
    ["bench-line", BENCH_LINE],
    ["home", HOME_BOX],
    ...cast
      .filter((a) => a.place !== "bench")
      .map((a): [string, Box] => [`figure-${a.id}`, figureBox(a)]),
    ...[...tagLayout(cast, label(cast))].map(([id, b]): [string, Box] => [`tag-${id}`, b]),
  ];
  // A figure may stand in front of another figure: that is depth, not a collision of words.
  const wordsOnly = (pairs: [string, string][]) =>
    pairs.filter(([a, b]) => !(a.startsWith("figure-") && b.startsWith("figure-")));

  it("no tag, slot, stamp or bench line touches another, or any figure: this ad's crew", () => {
    const cast = crewCast(whole, teamView(whole, whole));
    expect(wordsOnly(collisions(everything(cast)))).toEqual([]);
  });

  it("with everyone on stage at once (a run watched live) the tags still clear every speech slot, the stamp and the home", () => {
    const live = floor(beatOf("locate").start + 10);
    const cast = crewCast(live, { ...teamView(live, live), notNeeded: [] });
    expect(cast.filter((a) => a.place === "wing").length).toBeGreaterThan(0);
    const tags = [...tagLayout(cast, label(cast))].map(([id, b]): [string, Box] => [
      `tag-${id}`,
      b,
    ]);
    expect(tags).toHaveLength(cast.length);
    const fixed: [string, Box][] = [
      ["slot-left", SLOTS.left],
      ["slot-right", SLOTS.right],
      ["stamp", STAMP],
      ["home", HOME_BOX],
    ];
    const pairs = collisions([...fixed, ...tags]).filter(
      ([a, b]) => !(a.startsWith("tag-") && b.startsWith("tag-")),
    );
    expect(pairs).toEqual([]);
  });

  it("keeps every tag whole on the stage, and in the same place all run", () => {
    const at = (f: Floor) => {
      const cast = crewCast(f, teamView(f, whole));
      return tagLayout(cast, label(cast));
    };
    const end = at(whole);
    for (const b of end.values()) {
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.y).toBeGreaterThanOrEqual(0);
      expect(b.x + b.w).toBeLessThanOrEqual(VIEW.w);
      expect(b.y + b.h).toBeLessThanOrEqual(VIEW.h);
    }
    expect([...at(floor(beatOf("record").start + 10))]).toEqual([...end]);
  });
});
