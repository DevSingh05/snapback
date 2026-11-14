import type { LocatedPhoto, LocateResult } from "../contracts";
import { quatToYawPitch } from "./pose";

export type LandingState =
  | { kind: "loading" }
  | { kind: "not_found" } // could not place the photo (not located, not indexed, or no proof of where)
  | { kind: "elsewhere" } // verified in a different home than the one claimed
  | { kind: "placed"; photoId: string; roomLabel: string | null } // in the building, no camera angle
  | {
      kind: "match";
      photoId: string;
      sweepId: string;
      roomLabel: string | null;
      yaw: number; // degrees, counter-clockwise seen from above
      pitch: number;
      fovDeg: number | null;
      position: [number, number, number];
      /** Plan-view coordinates in the viewer's frame (x, then the viewer's z): what the mini-map
       *  draws, so its cone and dot agree with the 3D view. Absent on old states: (x, z). */
      floor?: [number, number];
    };

export type UpAxis = "y" | "z";

/** Plan-view coordinates of a model position in the 3D viewer's frame. A y-up position keeps
 *  (x, z); a z-up scan-cache position (x, y, height) is (x, -y) in the viewer's y-up frame. */
export function floorOf(p: [number, number, number], up: UpAxis = "y"): [number, number] {
  return up === "z" ? [p[0], -p[1]] : [p[0], p[2]];
}

/** The camera direction for every surface: the locator's viewer angles when sent (they account
 *  for z-up scans), else read off the quaternion. */
export function viewAngles(p: {
  rotation_quat?: [number, number, number, number] | null;
  yaw_deg?: number | null;
  pitch_deg?: number | null;
}): { yaw: number; pitch: number } | null {
  if (typeof p.yaw_deg === "number" && typeof p.pitch_deg === "number")
    return { yaw: p.yaw_deg, pitch: p.pitch_deg };
  return p.rotation_quat ? quatToYawPitch(p.rotation_quat) : null;
}

/**
 * Fixture-only room names (photo id to label). A live photo carries its own `room_label`, which
 * always wins; this map only fills in for the fixture pose.
 */
export const FIXTURE_ROOM_LABELS: Record<string, string> = { l1: "Living room" };

type Placement = "here" | "different_home" | "unplaced";

/**
 * Where a listing photo was placed, from the claimed property's point of view.
 * - here: "located_in_claimed", or placed in a twin of the claimed property (a property can have two
 *   floor-plan twins, and an honest photo may sit in the one that was not chosen).
 * - different_home: "located_elsewhere" AND both property ids are known AND they differ.
 * - unplaced: everything else, including "located_elsewhere" with no matched property to name,
 *   "not_located" and "not_indexed". We never say "elsewhere" on a guess.
 */
function placementOf(locate: LocateResult, photo: LocatedPhoto): Placement {
  const claimed = locate.claimed_property_id;
  const matched = photo.matched_property_id;
  if (photo.status === "located_in_claimed") return "here";
  if (claimed && matched && matched === claimed) return "here";
  if (photo.status === "located_elsewhere" && claimed && matched) return "different_home";
  return "unplaced";
}

/** True when any photo is verified inside a different property than the claimed one. */
export function hasDifferentHome(locate: LocateResult): boolean {
  return locate.photos.some((p) => placementOf(locate, p) === "different_home");
}

/** A located photo with no pose is still taken here, just without a camera angle. */
export function landingFromLocate(
  locate: LocateResult,
  photoId: string,
  roomLabels: Record<string, string>,
  up: UpAxis = "y",
): LandingState {
  const photo = locate.photos.find((p) => p.photo_id === photoId);
  if (!photo) return { kind: "not_found" };
  const placement = placementOf(locate, photo);
  if (placement === "different_home") return { kind: "elsewhere" };
  if (placement === "unplaced") return { kind: "not_found" };
  const roomLabel = photo.room_label || roomLabels[photoId] || null;
  const pose = locate.poses[photoId];
  if (!pose) return { kind: "placed", photoId, roomLabel };
  const { yaw, pitch } = viewAngles(pose)!;
  return {
    kind: "match",
    photoId,
    sweepId: pose.sweep_id ?? photo.pano_id ?? "",
    roomLabel,
    yaw,
    pitch,
    fovDeg: pose.fov_deg ?? null,
    position: pose.position,
    floor: floorOf(pose.position, up),
  };
}

export function landingLine(s: LandingState): string {
  switch (s.kind) {
    case "loading":
      return "Placing the photo in the building";
    case "not_found":
      return "Could not place this photo";
    case "elsewhere":
      return "Taken in a different home";
    case "placed":
      return `Taken here: ${s.roomLabel ?? "this home"}`;
    case "match":
      return s.roomLabel ? `Taken here: ${s.roomLabel}` : "Taken here";
  }
}

/** A second, smaller line for a photo that is placed but has no camera angle. */
export function landingNote(s: LandingState): string | null {
  return s.kind === "placed" ? "No camera angle for this photo" : null;
}

/** The flag decides; with it off, or with no live result yet, the fixture is used. */
export function chooseLocate(
  liveFlag: boolean,
  live: LocateResult | undefined,
  fixture: LocateResult,
): LocateResult {
  return liveFlag && live ? live : fixture;
}

const DEFAULT_FOV = 70;
const r2 = (n: number) => Math.round(n * 100) / 100 + 0;

/**
 * SVG path of a view cone pointing up (yaw 0) from the origin. Built once per fov and radius;
 * the turn to a pose is a CSS rotation of the group, never new geometry.
 */
export function viewCone(fovDeg: number | null, radius: number): string {
  const half = (((fovDeg ?? DEFAULT_FOV) / 2) * Math.PI) / 180;
  const x = r2(radius * Math.sin(half));
  const y = r2(-radius * Math.cos(half));
  return `M 0 0 L ${-x} ${y} A ${radius} ${radius} 0 0 1 ${x} ${y} Z`;
}
