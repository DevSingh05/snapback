import type { LocateResult } from "../contracts";
import { quatToYawPitch } from "./pose";

export type LandingState =
  | { kind: "loading" }
  | { kind: "not_found" }
  | {
      kind: "match";
      photoId: string;
      sweepId: string;
      roomLabel: string | null;
      yaw: number; // degrees, counter-clockwise seen from above
      pitch: number;
      fovDeg: number | null;
      position: [number, number, number];
    };

/**
 * Adapter gap (posted on issue #28 for lane V): LocateResult.poses carries sweep id, rotation,
 * position and fov, but no room label. Until it does, room labels come from this fixture-side map
 * (photo id to label). A live result with no entry here simply reads "Taken here".
 */
export const FIXTURE_ROOM_LABELS: Record<string, string> = { l1: "Living room" };

/** A photo lands only if it has a pose and its status does not say it was left unplaced. */
export function landingFromLocate(
  locate: LocateResult,
  photoId: string,
  roomLabels: Record<string, string>,
): LandingState {
  const pose = locate.poses[photoId];
  const photo = locate.photos.find((p) => p.photo_id === photoId);
  if (!pose || (photo && !photo.status.startsWith("located"))) return { kind: "not_found" };
  const { yaw, pitch } = quatToYawPitch(pose.rotation_quat);
  return {
    kind: "match",
    photoId,
    sweepId: pose.sweep_id ?? photo?.pano_id ?? "",
    roomLabel: roomLabels[photoId] ?? null,
    yaw,
    pitch,
    fovDeg: pose.fov_deg ?? null,
    position: pose.position,
  };
}

export function landingLine(s: LandingState): string {
  if (s.kind === "loading") return "Placing the photo in the building";
  if (s.kind === "not_found") return "Not found in this building";
  return s.roomLabel ? `Taken here: ${s.roomLabel}` : "Taken here";
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
