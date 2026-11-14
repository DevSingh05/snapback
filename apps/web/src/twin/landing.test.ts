import { describe, expect, it } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { LocateResult } from "../contracts";
import {
  FIXTURE_ROOM_LABELS,
  chooseLocate,
  landingFromLocate,
  landingLine,
  viewCone,
} from "./landing";

const locate = hold.locate as unknown as LocateResult;

describe("landingFromLocate", () => {
  it("builds a match from a located photo with a pose", () => {
    const s = landingFromLocate(locate, "l1", FIXTURE_ROOM_LABELS);
    expect(s.kind).toBe("match");
    if (s.kind !== "match") return;
    expect(s.sweepId).toBe("fx-sweep-03");
    expect(s.roomLabel).toBe("Living room");
    expect(s.fovDeg).toBe(70);
    expect(s.yaw).toBeCloseTo(44.7, 0);
  });

  it("is not found when the photo has no pose, or is unknown", () => {
    expect(landingFromLocate(locate, "l2", FIXTURE_ROOM_LABELS).kind).toBe("not_found");
    expect(landingFromLocate(locate, "nope", FIXTURE_ROOM_LABELS).kind).toBe("not_found");
  });

  it("is not found when the photo status says it was not placed, even with a pose", () => {
    const l: LocateResult = {
      ...locate,
      photos: [{ photo_id: "l1", status: "not_found" }],
    };
    expect(landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS).kind).toBe("not_found");
  });

  it("leaves the room label null when the contract has none", () => {
    const s = landingFromLocate(locate, "l1", {});
    expect(s.kind === "match" && s.roomLabel).toBeNull();
  });
});

describe("landingLine", () => {
  it("says Taken here with the room", () => {
    const s = landingFromLocate(locate, "l1", FIXTURE_ROOM_LABELS);
    expect(landingLine(s)).toBe("Taken here: Living room");
  });
  it("says only Taken here without a room", () => {
    expect(landingLine(landingFromLocate(locate, "l1", {}))).toBe("Taken here");
  });
  it("says Not found in this building on a failed match", () => {
    expect(landingLine({ kind: "not_found" })).toBe("Not found in this building");
  });
  it("never says in this unit", () => {
    const lines = [
      landingLine(landingFromLocate(locate, "l1", FIXTURE_ROOM_LABELS)),
      landingLine({ kind: "not_found" }),
      landingLine({ kind: "loading" }),
    ];
    for (const l of lines) expect(l.toLowerCase()).not.toContain("in this unit");
  });
});

describe("viewCone", () => {
  const rightEdgeX = (d: string) => {
    const nums = d.match(/-?\d+(\.\d+)?/g) ?? [];
    return Number(nums[nums.length - 2]);
  };
  it("is identical for the same fov, so geometry is built once", () => {
    expect(viewCone(70, 40)).toBe(viewCone(70, 40));
  });
  it("is wider for a wider fov", () => {
    expect(rightEdgeX(viewCone(100, 40))).toBeGreaterThan(rightEdgeX(viewCone(50, 40)));
  });
  it("falls back to a default fov when none is given", () => {
    expect(viewCone(null, 40)).toBe(viewCone(70, 40));
  });
});

describe("chooseLocate", () => {
  const live = { ...locate, case_id: "live" };
  it("uses the fixture unless the flag is on and a live result exists", () => {
    expect(chooseLocate(false, live, locate)).toBe(locate);
    expect(chooseLocate(true, undefined, locate)).toBe(locate);
    expect(chooseLocate(true, live, locate)).toBe(live);
  });
});
