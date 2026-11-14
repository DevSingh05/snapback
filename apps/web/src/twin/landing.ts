import type { LocateResult } from "../contracts";
import { quatToYawPitch } from "./pose";

export type LandingState =
  | { kind: "loading" }
  | { kind: "not_found" }
  | { kind: "elsewhere" } // placed in a different building than the one claimed
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
    };

/**
 * Adapter gap (posted on issue #28 for lane V): LocateResult.poses carries sweep id, rotation,
 * position and fov, but no room label. Until it does, room labels come from this fixture-side map
 * (photo id to label). A live result with no entry here simply reads "Taken here".
 */
export const FIXTURE_ROOM_LABELS: Record<string, string> = { l1: "Living room" };

/**
 * Only "located_in_claimed" in the chosen model counts as taken here. "located_elsewhere" is a
 * different building ("Not taken here"); "not_located" and "not_indexed" are "Not found in this
 * building". A located photo with no pose is still taken here, just without a camera angle.
 */
export function landingFromLocate(
  locate: LocateResult,
  photoId: string,
  roomLabels: Record<string, string>,
): LandingState {
  const photo = locate.photos.find((p) => p.photo_id === photoId);
  if (!photo) return { kind: "not_found" };
  if (photo.status === "located_elsewhere") return { kind: "elsewhere" };
  if (photo.status !== "located_in_claimed") return { kind: "not_found" };
  // The web contract type omits `chosen` (it is in contracts.py); read it without editing the contract.
  const chosenModel = (locate as LocateResult & { chosen?: { model_id?: string } | null }).chosen
    ?.model_id;
  if (chosenModel && photo.model_id && photo.model_id !== chosenModel) return { kind: "elsewhere" };
  const roomLabel = roomLabels[photoId] ?? null;
  const pose = locate.poses[photoId];
  if (!pose) return { kind: "placed", photoId, roomLabel };
  const { yaw, pitch } = quatToYawPitch(pose.rotation_quat);
  return {
    kind: "match",
    photoId,
    sweepId: pose.sweep_id ?? photo.pano_id ?? "",
    roomLabel,
    yaw,
    pitch,
    fovDeg: pose.fov_deg ?? null,
    position: pose.position,
  };
}

export function landingLine(s: LandingState): string {
  switch (s.kind) {
    case "loading":
      return "Placing the photo in the building";
    case "not_found":
      return "Not found in this building";
    case "elsewhere":
      return "Not taken here";
    case "placed":
      return `Taken here: ${s.roomLabel ?? "this building"}`;
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
