import { describe, expect, it } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { LocateResult } from "../contracts";
import {
  FIXTURE_ROOM_LABELS,
  chooseLocate,
  landingFromLocate,
  landingLine,
  landingNote,
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

  it("is placed (taken here, no camera angle) when located in the claimed building without a pose", () => {
    const s = landingFromLocate(locate, "l2", FIXTURE_ROOM_LABELS);
    expect(s).toEqual({ kind: "placed", photoId: "l2", roomLabel: null });
    expect(landingLine(s)).toBe("Taken here: this building");
    expect(landingNote(s)).toBe("No camera angle for this photo");
  });

  it("is not found for an unknown photo", () => {
    expect(landingFromLocate(locate, "nope", FIXTURE_ROOM_LABELS).kind).toBe("not_found");
  });

  // All four LocateStatus values in src/snapback/contracts.py, each with a pose present.
  it.each([
    ["located_in_claimed", "match", "Taken here: Living room"],
    ["located_elsewhere", "elsewhere", "Not taken here"],
    ["not_located", "not_found", "Not found in this building"],
    ["not_indexed", "not_found", "Not found in this building"],
  ])("status %s reads %s", (status, kind, line) => {
    const l: LocateResult = {
      ...locate,
      photos: [{ photo_id: "l1", status, model_id: "fx-model-a" }],
    };
    const s = landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS);
    expect(s.kind).toBe(kind);
    expect(landingLine(s)).toBe(line);
  });

  it("located_elsewhere never says Taken here, even with a pose and a room label", () => {
    const l: LocateResult = {
      ...locate,
      photos: [{ photo_id: "l1", status: "located_elsewhere", model_id: "other" }],
    };
    expect(landingLine(landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS))).not.toMatch(/^Taken here/);
  });

  it("a claimed-building photo in a model other than the chosen one is not taken here", () => {
    const l: LocateResult = {
      ...locate,
      photos: [{ photo_id: "l1", status: "located_in_claimed", model_id: "fx-model-b" }],
    };
    expect(landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS).kind).toBe("elsewhere");
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
      landingLine({ kind: "elsewhere" }),
      landingLine({ kind: "placed", photoId: "l2", roomLabel: null }),
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
