import type { TourStop } from "../../contracts";

// The walk as a video timeline. Every stop is one chapter: the camera arrives, an ad photo placed
// here lands and holds for a second, then the camera pans across the room and the tour moves on.
// All times are milliseconds of tour time at 1x.

export const ARRIVE_MS = 2000;
export const LAND_MS = 1000;
export const PAN_MS = 3500;
/** How far the real camera turns during one stop's pan, in degrees. */
export const PAN_DEG = 110;
/** The pan is sent to the scan in short turns, so a pause stops it within half a second. */
export const PAN_CHUNK_MS = 500;

export interface Chapter {
  index: number;
  key: string;
  title: string;
  start: number;
  duration: number;
  /** An ad photo was placed at this stop, so the chapter holds while it lands. */
  land: boolean;
}

export function hasLanding(stop: TourStop): boolean {
  return stop.photos.length > 0;
}

export function buildChapters(stops: TourStop[]): Chapter[] {
  let start = 0;
  return stops.map((stop, index) => {
    const land = hasLanding(stop);
    const duration = ARRIVE_MS + (land ? LAND_MS : 0) + PAN_MS;
    const chapter = { index, key: stop.key, title: stop.title, start, duration, land };
    start += duration;
    return chapter;
  });
}

export function totalMs(chapters: Chapter[]): number {
  const last = chapters[chapters.length - 1];
  return last ? last.start + last.duration : 0;
}

/** The chapter and the time inside it for a point on the whole timeline. */
export function locate(chapters: Chapter[], ms: number): { index: number; t: number } {
  const at = Math.max(0, Math.min(ms, totalMs(chapters)));
  for (let i = chapters.length - 1; i >= 0; i--) {
    const c = chapters[i]!;
    if (at >= c.start) return { index: i, t: Math.min(at - c.start, c.duration) };
  }
  return { index: 0, t: 0 };
}

export type Phase = "arrive" | "land" | "pan";

export interface Moment {
  phase: Phase;
  /** Tour time spent panning so far, 0 to PAN_MS. */
  panMs: number;
  /** How far the camera is through this stop, 0 to 1. It holds still while a photo lands. */
  sweep: number;
}

export function momentAt(chapter: Pick<Chapter, "land">, t: number): Moment {
  const landEnd = ARRIVE_MS + (chapter.land ? LAND_MS : 0);
  const phase: Phase = t < ARRIVE_MS ? "arrive" : t < landEnd ? "land" : "pan";
  const panMs = Math.max(0, Math.min(t - landEnd, PAN_MS));
  const moved = Math.min(t, ARRIVE_MS) + panMs;
  return { phase, panMs, sweep: moved / (ARRIVE_MS + PAN_MS) };
}

export interface DrawnPose {
  /** Shift, as a fraction of the stage. */
  x: number;
  y: number;
  zoom: number;
  /** Turn of the drawing, in degrees. */
  yaw: number;
}

export const REST_POSE: DrawnPose = { x: 0, y: 0, zoom: 1, yaw: 0 };

const smooth = (u: number) => u * u * (3 - 2 * u);

/** The drawn stage's camera: a slow push in while it glides and turns across the room. */
export function drawnPose(sweep: number): DrawnPose {
  const u = smooth(Math.max(0, Math.min(sweep, 1)));
  return {
    x: 0.035 - 0.07 * u,
    y: 0.012 - 0.03 * u,
    zoom: 1.04 + 0.18 * u,
    yaw: -7 + 14 * u,
  };
}

/** One line on what is on screen at this stop. It only says what the plan itself says. */
export function captionOf(stop: TourStop): string {
  if (stop.kind === "arrive") return "Outside the building, before you go in.";
  if (stop.kind === "outro") return "That is the whole walk. Next, see it in person.";
  if (stop.photos.length > 0) return "You are standing where the ad's photo was taken.";
  if (stop.ad_view === "none_placed") return "A room the ad left out.";
  if (stop.kind === "door") return "The way in.";
  return "A look around this room.";
}

export function clockText(ms: number): string {
  const s = Math.floor(Math.max(0, ms) / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
