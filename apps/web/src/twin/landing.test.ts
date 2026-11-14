import { describe, expect, it } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { LocateResult } from "../contracts";
import {
  FIXTURE_ROOM_LABELS,
  hasDifferentHome,
  chooseLocate,
  floorOf,
  landingFromLocate,
  landingLine,
  landingNote,
  viewAngles,
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
    expect(landingLine(s)).toBe("Taken here: this home");
    expect(landingNote(s)).toBe("No camera angle for this photo");
  });

  it("is not found for an unknown photo", () => {
    expect(landingFromLocate(locate, "nope", FIXTURE_ROOM_LABELS).kind).toBe("not_found");
  });

  // All four LocateStatus values in src/snapback/contracts.py, each with a pose present.
  it.each([
    ["located_in_claimed", "match", "Taken here: Living room"] as const,
    ["located_elsewhere", "elsewhere", "Taken in a different home"] as const,
    ["not_located", "not_found", "Could not place this photo"] as const,
    ["not_indexed", "not_found", "Could not place this photo"] as const,
  ])("status %s reads %s", (status, kind, line) => {
    const l: LocateResult = {
      ...locate,
      photos: [
        {
          photo_id: "l1",
          status,
          model_id: "fx-model-a",
          // only an elsewhere photo names the other home
          matched_property_id: status === "located_elsewhere" ? "fx-prop-9" : null,
        },
      ],
    };
    const s = landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS);
    expect(s.kind).toBe(kind);
    expect(landingLine(s)).toBe(line);
  });

  it("located_elsewhere never says Taken here, even with a pose and a room label", () => {
    const l: LocateResult = {
      ...locate,
      photos: [
        {
          photo_id: "l1",
          status: "located_elsewhere",
          model_id: "other",
          matched_property_id: "p9",
        },
      ],
    };
    expect(landingLine(landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS))).not.toMatch(/^Taken here/);
  });

  it("a photo in the claimed property's second twin (not the chosen model) reads Taken here", () => {
    const l: LocateResult = {
      ...locate,
      photos: [
        {
          photo_id: "l1",
          status: "located_in_claimed",
          model_id: "fx-model-b",
          matched_model_id: "fx-model-b",
          matched_property_id: "fx-prop-1",
        },
      ],
    };
    const s = landingFromLocate(l, "l1", {});
    expect(s.kind).toBe("match");
    expect(landingLine(s)).toMatch(/^Taken here/);
  });

  it("a located_elsewhere photo whose matched property is the claimed one is Taken here", () => {
    const l: LocateResult = {
      ...locate,
      photos: [
        {
          photo_id: "l2",
          status: "located_elsewhere",
          matched_model_id: "fx-model-b",
          matched_property_id: "fx-prop-1",
        },
      ],
    };
    expect(landingLine(landingFromLocate(l, "l2", {}))).toBe("Taken here: this home");
  });

  it("located_elsewhere with no matched_property_id never says different home", () => {
    const l: LocateResult = {
      ...locate,
      photos: [{ photo_id: "l1", status: "located_elsewhere", model_id: "other" }],
    };
    const line = landingLine(landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS));
    expect(line).toBe("Could not place this photo");
    expect(line).not.toMatch(/different home|elsewhere/i);
  });

  it("located_elsewhere with no claimed property id cannot say different home either", () => {
    const l: LocateResult = {
      ...locate,
      claimed_property_id: null,
      photos: [{ photo_id: "l1", status: "located_elsewhere", matched_property_id: "fx-prop-9" }],
    };
    expect(landingLine(landingFromLocate(l, "l1", {}))).toBe("Could not place this photo");
  });

  it("not_located and not_indexed never read elsewhere, even with a stray matched property", () => {
    for (const status of ["not_located", "not_indexed"] as const) {
      const l: LocateResult = {
        ...locate,
        photos: [{ photo_id: "l1", status, matched_property_id: "fx-prop-9" }],
      };
      expect(landingLine(landingFromLocate(l, "l1", {}))).toBe("Could not place this photo");
    }
  });

  it("uses the photo's room_label, and it beats the fixture map", () => {
    const l: LocateResult = {
      ...locate,
      photos: [{ photo_id: "l1", status: "located_in_claimed", room_label: "Kitchen" }],
    };
    const s = landingFromLocate(l, "l1", FIXTURE_ROOM_LABELS);
    expect(s.kind === "match" && s.roomLabel).toBe("Kitchen");
    expect(landingLine(s)).toBe("Taken here: Kitchen");
  });

  it("falls back to this home when the photo has no room_label and there is no pose", () => {
    const l: LocateResult = {
      ...locate,
      poses: {},
      photos: [{ photo_id: "l1", status: "located_in_claimed" }],
    };
    expect(landingLine(landingFromLocate(l, "l1", {}))).toBe("Taken here: this home");
  });

  it("leaves the room label null when the contract has none", () => {
    const s = landingFromLocate(locate, "l1", {});
    expect(s.kind === "match" && s.roomLabel).toBeNull();
  });
});

describe("hasDifferentHome", () => {
  const withPhotos = (photos: LocateResult["photos"], claimed: string | null = "fx-prop-1") =>
    ({ ...locate, claimed_property_id: claimed, photos }) as LocateResult;
  it("is true only for located_elsewhere with a known property that differs from the claimed one", () => {
    expect(
      hasDifferentHome(
        withPhotos([{ photo_id: "a", status: "located_elsewhere", matched_property_id: "p9" }]),
      ),
    ).toBe(true);
  });
  it("is false for elsewhere in the claimed property's other twin", () => {
    expect(
      hasDifferentHome(
        withPhotos([
          { photo_id: "a", status: "located_elsewhere", matched_property_id: "fx-prop-1" },
        ]),
      ),
    ).toBe(false);
  });
  it("is false for elsewhere with no matched property, or with no claimed property", () => {
    expect(
      hasDifferentHome(
        withPhotos([{ photo_id: "a", status: "located_elsewhere", matched_property_id: null }]),
      ),
    ).toBe(false);
    expect(
      hasDifferentHome(
        withPhotos(
          [{ photo_id: "a", status: "located_elsewhere", matched_property_id: "p9" }],
          null,
        ),
      ),
    ).toBe(false);
  });
  it("is false for not_located and not_indexed even with a stray matched property", () => {
    expect(
      hasDifferentHome(
        withPhotos([
          { photo_id: "a", status: "not_located", matched_property_id: "p9" },
          { photo_id: "b", status: "not_indexed", matched_property_id: "p9" },
        ]),
      ),
    ).toBe(false);
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
  it("says Could not place this photo on a failed match", () => {
    expect(landingLine({ kind: "not_found" })).toBe("Could not place this photo");
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

describe("one camera direction for every surface (#244 follow-up)", () => {
  it("floorOf keeps (x, z) for y-up and gives (x, -y) for a z-up scan position", () => {
    expect(floorOf([1, 2, 3], "y")).toEqual([1, 3]);
    expect(floorOf([1, 2, 3], "z")).toEqual([1, -2]);
  });

  it("viewAngles prefers the locator's angles over the quaternion", () => {
    expect(
      viewAngles({ rotation_quat: [0.5, 0.5, 0.5, 0.5], yaw_deg: -175.3, pitch_deg: -13.2 }),
    ).toEqual({
      yaw: -175.3,
      pitch: -13.2,
    });
    expect(viewAngles({ rotation_quat: null })).toBeNull();
  });

  it("landingFromLocate on a live z-up pose uses its angles and its viewer floor point", () => {
    const locate = structuredClone(hold.locate) as unknown as LocateResult;
    const id = locate.photos.find((p) => p.status === "located_in_claimed")!.photo_id;
    locate.poses[id] = {
      ...locate.poses[id]!,
      position: [4, 5, 1.4],
      yaw_deg: 30,
      pitch_deg: -5,
    };
    const s = landingFromLocate(locate, id, {}, "z");
    expect(s.kind).toBe("match");
    if (s.kind !== "match") return;
    expect([s.yaw, s.pitch]).toEqual([30, -5]);
    expect(s.floor).toEqual([4, -5]);
  });
});
