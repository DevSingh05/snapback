import type { Pose } from "../contracts";

export interface YawPitch {
  yaw: number; // degrees, counter-clockwise seen from above
  pitch: number; // degrees, positive looks up
}

/** Camera forward is -Z in the model frame (y up); rotate it by the quaternion, read yaw/pitch. */
export function quatToYawPitch(q: [number, number, number, number]): YawPitch {
  const [x, y, z, w] = q;
  // Rotate v = (0, 0, -1): the third column of the rotation matrix, negated.
  const fx = -(2 * (x * z + w * y));
  const fy = -(2 * (y * z - w * x));
  const fz = -(1 - 2 * (x * x + y * y));
  const deg = 180 / Math.PI;
  return {
    yaw: Math.atan2(-fx, -fz) * deg,
    pitch: Math.asin(Math.max(-1, Math.min(1, fy))) * deg,
  };
}

export interface SdkMoveTo {
  sweepId: string;
  /** Second argument of sdk.Sweep.moveTo(sweepId, options). */
  options: {
    transition: "transition.fly" | "transition.instant";
    transitionTime: number;
    rotation: { x: number; y: number };
  };
  fovDeg: number | null;
  position: [number, number, number];
}

export function poseToSdkCall(pose: Pose): SdkMoveTo {
  // The locator's own viewer angles when present (they account for the scan's z-up frame).
  const fromQuat = quatToYawPitch(pose.rotation_quat);
  const yaw = typeof pose.yaw_deg === "number" ? pose.yaw_deg : fromQuat.yaw;
  const pitch = typeof pose.pitch_deg === "number" ? pose.pitch_deg : fromQuat.pitch;
  return {
    sweepId: pose.sweep_id ?? "",
    options: {
      transition: "transition.fly",
      transitionTime: 2000,
      rotation: { x: pitch, y: yaw },
    },
    fovDeg: pose.fov_deg ?? null,
    position: pose.position,
  };
}

/** Use the pose's sweep if the loaded model has it; otherwise the first sweep, flagged as stand-in. */
export function pickSweep(
  wanted: string,
  available: string[],
): { id: string; stand: boolean } | null {
  if (available.includes(wanted)) return { id: wanted, stand: false };
  const first = available[0];
  return first ? { id: first, stand: true } : null;
}
