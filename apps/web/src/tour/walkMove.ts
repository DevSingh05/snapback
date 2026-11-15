import { quatToYawPitch } from "../twin/pose";
import type { TourStop } from "../contracts";

/**
 * The one place the camera rotation sign lives. The Showcase `moveTo` rotation was never checked
 * by eye against a known pose (risk R2), so a mirrored view is a one-line fix: set this to -1.
 */
export const YAW_SIGN: 1 | -1 = 1;

export interface SdkRotation {
  x: number; // pitch, degrees, positive looks up
  y: number; // yaw, degrees
}

export function sdkRotation(q: [number, number, number, number]): SdkRotation {
  const { yaw, pitch } = quatToYawPitch(q);
  return { x: pitch, y: YAW_SIGN * yaw };
}

/** The matched view's rotation: the locator's own viewer angles when it sent them (they account
 *  for the scan's z-up frame), else angles read off the quaternion. */
export function photoRotation(p: {
  rotation_quat?: [number, number, number, number] | null;
  yaw_deg?: number | null;
  pitch_deg?: number | null;
}): SdkRotation | null {
  if (typeof p.yaw_deg === "number" && typeof p.pitch_deg === "number")
    return { x: p.pitch_deg, y: YAW_SIGN * p.yaw_deg };
  return p.rotation_quat ? sdkRotation(p.rotation_quat) : null;
}

export interface StopMove {
  sweepId: string;
  options: {
    transition: "transition.fly" | "transition.instant";
    transitionTime: number;
    rotation: SdkRotation;
  };
}

/**
 * Where the camera goes for a stop. With an ad photo placed here, it flies to that photo's sweep
 * and turns the way the photo faced, so the photo lands over the same corner. Without one it goes
 * to the stop's own sweep. A stop with no sweep (arrive, outro) has no move.
 */
export function stopMove(stop: TourStop, reduced: boolean): StopMove | null {
  const photo = stop.photos.find(
    (p) => p.sweep_id && (p.rotation_quat || typeof p.yaw_deg === "number"),
  );
  const sweepId = photo?.sweep_id ?? stop.sweep_id;
  if (!sweepId) return null;
  const rotation =
    (photo && photoRotation(photo)) ?? sdkRotation(stop.rotation_quat ?? [0, 0, 0, 1]);
  return {
    sweepId,
    options: {
      transition: reduced ? "transition.instant" : "transition.fly",
      transitionTime: reduced ? 0 : 2000,
      rotation,
    },
  };
}
