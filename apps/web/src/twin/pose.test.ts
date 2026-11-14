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
