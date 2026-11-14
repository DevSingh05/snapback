import { describe, expect, it } from "vitest";

import type { TourStop } from "../contracts";
import { YAW_SIGN, sdkRotation, stopMove } from "./walkMove";

const base: TourStop = {
  kind: "room",
  key: "room-1",
  title: "Kitchen",
  sweep_id: "s1",
  sweep_count: 1,
  sweep_ids: ["s1"],
  photos: [],
  ad_view: "unknown",
  claims: [],
  facts: [],
};
const s = Math.SQRT1_2;

describe("sdkRotation (the one place the rotation sign lives)", () => {
  it("is zero for the identity pose", () => {
    const r = sdkRotation([0, 0, 0, 1]);
    expect(r.x).toBeCloseTo(0);
    expect(Math.abs(r.y)).toBeCloseTo(0);
  });

  it("turns a quarter turn about Y into a 90 degree yaw whose sign is YAW_SIGN", () => {
    // Camera looks down -Z; a +90 degree turn about Y (counter-clockwise seen from above) is yaw +90.
    const r = sdkRotation([0, s, 0, s]);
    expect(Math.abs(r.y)).toBeCloseTo(90);
    expect(Math.sign(r.y)).toBe(YAW_SIGN);
    // Flipping the constant would mirror it: this pins the current choice, so a flip is visible.
    expect(YAW_SIGN).toBe(1);
  });
});

describe("stopMove", () => {
  it("goes to the stop's own sweep", () => {
    expect(stopMove(base, false)).toMatchObject({
      sweepId: "s1",
      options: { transition: "transition.fly", transitionTime: 2000 },
    });
  });

  it("faces the way the ad photo faced when one is placed here", () => {
    const m = stopMove(
      {
        ...base,
        photos: [{ photo_id: "p", sweep_id: "s2", rotation_quat: [0, s, 0, s] }],
      },
      false,
    )!;
    expect(m.sweepId).toBe("s2");
    expect(Math.abs(m.options.rotation.y)).toBeCloseTo(90);
  });

  it("moves instantly under reduced motion and has no move for a stop without a sweep", () => {
    expect(stopMove(base, true)?.options).toMatchObject({
      transition: "transition.instant",
      transitionTime: 0,
    });
    expect(stopMove({ ...base, kind: "arrive", sweep_id: null }, false)).toBeNull();
  });
});
