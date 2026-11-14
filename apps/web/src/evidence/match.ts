// Pure reads for the match picture: how each drawn pair is shaded, where the drawn points fall
// on the ad photo, how long the draw-in runs, and the plain sentences beside the meter. Every
// number shown comes from the evidence row or from `bars`; shading and the coverage picture are
// worked out from the drawn pairs themselves, never typed in.
import { useEffect, useState } from "react";

import { barsFor } from "./read";
import type { EvidencePhoto, PlaceStep, PointPair } from "./types";

export type Tier = "strong" | "mid" | "faint";

const median = (v: number[]): number => {
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length === 0 ? 0 : s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2;
};

/** Shades each pair by how closely its shift from ad to scan agrees with the typical shift of
 *  all drawn pairs: the closest third is "strong", the furthest third "faint". The evidence file
 *  carries no per-point score, so this is the one honest strength the web can read. */
export function pairTiers(pairs: PointPair[]): Tier[] {
  if (pairs.length === 0) return [];
  const dx = pairs.map(([ax, , bx]) => bx - ax);
  const dy = pairs.map(([, ay, , by]) => by - ay);
  const mx = median(dx);
  const my = median(dy);
  const off = pairs.map((_, i) => Math.hypot(dx[i]! - mx, dy[i]! - my));
  const order = off.map((_, i) => i).sort((a, b) => off[a]! - off[b]!);
  const tiers: Tier[] = new Array<Tier>(pairs.length).fill("faint");
  order.forEach((idx, rank) => {
    const share = rank / pairs.length;
    tiers[idx] = share < 1 / 3 ? "strong" : share < 2 / 3 ? "mid" : "faint";
  });
  return tiers;
}

export const HEAT_COLS = 8;
export const HEAT_ROWS = 6;

export interface Coverage {
  /** Points per cell, row by row, HEAT_COLS x HEAT_ROWS. */
  cells: number[];
  most: number;
  /** The box around the drawn points, 0 to 1 of the photo. Null with fewer than two points. */
  box: { x: number; y: number; w: number; h: number } | null;
}

/** Where the drawn points fall on the ad photo. The spread score is the area of the box around
 *  the matched points over the photo's area (thresholds.toml), so the box is what it measures. */
export function coverage(pairs: PointPair[]): Coverage {
  const cells = new Array<number>(HEAT_COLS * HEAT_ROWS).fill(0);
  let x0 = 1;
  let y0 = 1;
  let x1 = 0;
  let y1 = 0;
  for (const [ax, ay] of pairs) {
    const c = Math.min(HEAT_COLS - 1, Math.max(0, Math.floor(ax * HEAT_COLS)));
    const r = Math.min(HEAT_ROWS - 1, Math.max(0, Math.floor(ay * HEAT_ROWS)));
    cells[r * HEAT_COLS + c]! += 1;
    x0 = Math.min(x0, ax);
    y0 = Math.min(y0, ay);
    x1 = Math.max(x1, ax);
    y1 = Math.max(y1, ay);
  }
  return {
    cells,
    most: Math.max(0, ...cells),
    box: pairs.length >= 2 ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null,
  };
}

/** One pair every STEP_MS, then a short settle. */
export const STEP_MS = 40;
export const drawMs = (pairs: number): number => (pairs === 0 ? 0 : pairs * STEP_MS + 450);

/** Counts from 0 to `total` over `ms`, in step with the lines drawing in. Under reduced motion,
 *  or with nothing to draw, it is the final number from the first frame. */
export function useCountUp(total: number, ms: number, reduced: boolean): number {
  const still = reduced || ms <= 0 || total <= 0;
  const [count, setCount] = useState(still ? total : 0);
  useEffect(() => {
    if (still) {
      setCount(total);
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const tick = (now: number) => {
      start ??= now;
      const t = Math.min(1, (now - start) / ms);
      setCount(Math.round(total * t));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [total, ms, still]);
  return count;
}

const elsewhere = (p: EvidencePhoto) => p.status === "located_elsewhere";
const points = (n: number) => `${n} matching ${n === 1 ? "point" : "points"}`;

/** The words on the bar's tick. */
export function barLabel(p: EvidencePhoto, bars: Record<string, number>): string | null {
  const bar = barsFor(p, bars).inliers;
  if (bar == null) return null;
  return elsewhere(p)
    ? `${bar} needed to say it's a different building`
    : `${bar} needed to say it's this room`;
}

/** The meter in one plain sentence. Null when the row carries no count or no bar. */
export function pointsSentence(p: EvidencePhoto, bars: Record<string, number>): string | null {
  const bar = barsFor(p, bars).inliers;
  if (p.inliers == null || bar == null) return null;
  const n = points(p.inliers);
  if (p.inliers < bar) return `${n}. We need ${bar} to be sure, so we don't say it's this room.`;
  if (p.bar_failed || p.status === "not_located")
    return `${n}, past the ${bar} we need. Another check fell short, so we don't say it's this room.`;
  if (elsewhere(p))
    return `${n}. We need ${bar} to be sure it's a different building, so we say it is.`;
  return `${n}. We need ${bar} to be sure, so we say it's this room.`;
}

/** How far short of the bar, in points. 0 when the bar is met. */
export function shortBy(p: EvidencePhoto, bars: Record<string, number>): number {
  const bar = barsFor(p, bars).inliers;
  return p.inliers == null || bar == null ? 0 : Math.max(0, bar - p.inliers);
}

const OPTION_PLAIN: Record<string, string> = {
  base: "First search of this home",
  wider_index: "Search more buildings",
  deeper_claimed: "Search deeper in this home",
  stop: "Stop here",
};

/** An option the agent had, in a renter's words. An option we have no words for is shown as is. */
export function optionPlain(option: string): string {
  const focus = /^focus_scan:(.+)$/.exec(option);
  if (focus) return `Look closer at scan ${focus[1]}`;
  return OPTION_PLAIN[option] ?? option;
}

export type PickedBy = "model" | "policy" | "random";

export const PICKED_BY: Record<PickedBy, string> = {
  model: "Picked by the model",
  policy: "Picked by our rules",
  random: "Random draw",
};

const RESULT_PLAIN: Record<PlaceStep["result"], string> = {
  placed: "Placed",
  not_placed: "Still not placed",
  elsewhere: "Placed in a different building",
  skipped: "Left as not placed",
};

export const resultPlain = (r: PlaceStep["result"]): string => RESULT_PLAIN[r];

/** What a picked search led to, read from the photo's own searches. Null when the evidence file
 *  has no such search, so the card never guesses an outcome. */
export function pickOutcome(
  photo: EvidencePhoto | undefined,
  option: string | null | undefined,
): PlaceStep["result"] | null {
  if (!photo || !option) return null;
  return photo.searches.find((s) => s.option === option)?.result ?? null;
}
