import { describe, expect, it } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { Pose } from "../contracts";
import { pickSweep, poseToSdkCall, quatToYawPitch } from "./pose";

const fixturePose = hold.locate.poses.l1 as Pose;

describe("quatToYawPitch", () => {
  it("identity looks straight ahead", () => {
    const { yaw, pitch } = quatToYawPitch([0, 0, 0, 1]);
    expect(yaw).toBeCloseTo(0);
    expect(pitch).toBeCloseTo(0);
  });

  it("a quarter turn about Y gives 90 degrees of yaw and no pitch", () => {
    const s = Math.SQRT1_2;
    const { yaw, pitch } = quatToYawPitch([0, s, 0, s]);
    expect(yaw).toBeCloseTo(90);
    expect(pitch).toBeCloseTo(0);
  });

  it("tilting up about X gives positive pitch", () => {
    const s = Math.sin(Math.PI / 12); // half of 30 degrees
    const { pitch } = quatToYawPitch([s, 0, 0, Math.cos(Math.PI / 12)]);
    expect(pitch).toBeCloseTo(30);
  });
});

describe("pose frame: Y up, camera looks down -Z", () => {
  // Independent check: rotate the forward vector (0, 0, -1) by q with the quaternion sandwich product.
  type V3 = [number, number, number];
  const forward = ([x, y, z, w]: [number, number, number, number]): V3 => {
    const v: V3 = [0, 0, -1];
    const t: V3 = [2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])];
    return [
      v[0] + w * t[0] + (y * t[2] - z * t[1]),
      v[1] + w * t[1] + (z * t[0] - x * t[2]),
      v[2] + w * t[2] + (x * t[1] - y * t[0]),
    ];
  };

  it("the fixture pose looks toward -X and -Z, and its positive yaw agrees", () => {
    const f = forward(fixturePose.rotation_quat);
    expect(f[0]).toBeLessThan(0); // left in plan view (+X is right)
    expect(f[2]).toBeLessThan(0); // up in plan view (-Z is up)
    expect(Math.abs(f[1])).toBeLessThan(1e-9); // level
    const { yaw } = quatToYawPitch(fixturePose.rotation_quat);
    expect(yaw).toBeGreaterThan(0);
    // yaw counter-clockwise from above, measured from -Z: forward = (-sin yaw, 0, -cos yaw)
    const r = (yaw * Math.PI) / 180;
    expect(f[0]).toBeCloseTo(-Math.sin(r));
    expect(f[2]).toBeCloseTo(-Math.cos(r));
  });

  it("a quarter turn about +Y faces -X; the opposite turn faces +X", () => {
    const s = Math.SQRT1_2;
    expect(forward([0, s, 0, s])[0]).toBeCloseTo(-1);
    expect(quatToYawPitch([0, s, 0, s]).yaw).toBeCloseTo(90);
    expect(forward([0, -s, 0, s])[0]).toBeCloseTo(1);
    expect(quatToYawPitch([0, -s, 0, s]).yaw).toBeCloseTo(-90);
  });
});

describe("poseToSdkCall with the fixture pose", () => {
  it("maps sweep, rotation and fov to Sweep.moveTo arguments", () => {
    const call = poseToSdkCall(fixturePose);
    expect(call.sweepId).toBe("fx-sweep-03");
    expect(call.options.rotation.y).toBeCloseTo(44.7, 0);
    expect(call.options.rotation.x).toBeCloseTo(0);
    expect(call.options.transition).toBe("transition.fly");
    expect(call.fovDeg).toBe(70);
  });

  it("keeps the model-frame position for display", () => {
    expect(poseToSdkCall(fixturePose).position).toEqual([1.2, 1.5, -3.4]);
  });
});

describe("pickSweep fixture fallback", () => {
  it("uses the pose sweep when the model has it", () => {
    expect(pickSweep("fx-sweep-03", ["a", "fx-sweep-03"])).toEqual({
      id: "fx-sweep-03",
      stand: false,
    });
  });

  it("falls back to the first sweep of the loaded model and says it is a stand-in", () => {
    expect(pickSweep("fx-sweep-03", ["real-1", "real-2"])).toEqual({ id: "real-1", stand: true });
  });

  it("returns null when the model has no sweeps", () => {
    expect(pickSweep("fx-sweep-03", [])).toBeNull();
  });
});
