// Pure reads of the evidence file: which chip a photo gets, its three gauges and the words
// beside them. No number is made here; each comes from the photo row or from `bars`.
import type { BarFailed, EvidenceFile, EvidencePhoto, PlaceStep } from "./types";

export type ChipState = "strong" | "placed" | "not_placed";

const placed = (p: EvidencePhoto) =>
  (p.status === "located_in_claimed" || p.status === "located_elsewhere") && !p.bar_failed;

/** Strong match needs every bar passed and at least `stop_at_inliers` matched points. When the
 *  evidence file does not carry that bar, no photo is called strong. */
export function chipState(p: EvidencePhoto, bars: Record<string, number>): ChipState {
  if (!placed(p)) return "not_placed";
  const strongAt = bars.stop_at_inliers;
  return typeof strongAt === "number" && (p.inliers ?? 0) >= strongAt ? "strong" : "placed";
}

export const CHIP_LABEL: Record<ChipState, string> = {
  strong: "Strong match",
  placed: "Placed",
  not_placed: "Could not place",
};

const elsewhere = (p: EvidencePhoto) => p.status === "located_elsewhere";

/** The bar each measure was held to. A photo placed in another building is held to the
 *  stricter bars. */
export function barsFor(p: EvidencePhoto, bars: Record<string, number>) {
  return {
    inliers: elsewhere(p) ? bars.elsewhere_min_inliers : bars.min_inliers,
    spread: elsewhere(p) ? bars.elsewhere_min_spread : bars.claimed_min_spread,
    rival: bars.ambiguity_ratio,
  };
}

const num = (v: number) => (Number.isInteger(v) ? String(v) : String(Number(v.toFixed(2))));

/** Names the bar a photo missed, with its own number. Null when no bar failed. */
export function failedLine(p: EvidencePhoto, bars: Record<string, number>): string | null {
  const b = barsFor(p, bars);
  const failed: BarFailed | null | undefined = p.bar_failed;
  if (!failed) return null;
  if (failed === "inliers" && p.inliers != null && b.inliers != null)
    return `${p.inliers} matched points, the bar is ${num(b.inliers)}`;
  if (failed === "ratio" && p.inlier_ratio != null && bars.min_inlier_ratio != null)
    return `${num(p.inlier_ratio)} of its points agreed, the bar is ${num(bars.min_inlier_ratio)}`;
  if (failed === "spread" && p.spread != null && b.spread != null)
    return `the points cover ${num(p.spread)} of the photo, the bar is ${num(b.spread)}`;
  if (failed === "ambiguity") return "another building matched far more strongly";
  return "one bar was not met";
}

export interface Gauge {
  key: "points" | "spread" | "rival";
  label: string;
  value: number;
  bar: number;
  /** Where the fill ends and where the bar sits, 0 to 1 of the track. */
  fill: number;
  mark: number;
  pass: boolean;
  valueText: string;
  barText: string;
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

function gauge(
  key: Gauge["key"],
  label: string,
  value: number,
  bar: number,
  lowerIsBetter: boolean,
  valueText: string,
  barText: string,
): Gauge {
  // The track runs to twice the bar, or just past the value when it is larger.
  const top = Math.max(bar * 2, value * 1.15, Number.EPSILON);
  return {
    key,
    label,
    value,
    bar,
    fill: clamp01(value / top),
    mark: clamp01(bar / top),
    pass: lowerIsBetter ? value < bar : value >= bar,
    valueText,
    barText,
  };
}

/** The three gauges, in order. A measure the row does not carry is left out, never drawn as 0. */
export function gauges(p: EvidencePhoto, bars: Record<string, number>): Gauge[] {
  const b = barsFor(p, bars);
  const out: Gauge[] = [];
  if (p.inliers != null && b.inliers != null)
    out.push(
      gauge(
        "points",
        "Matched points",
        p.inliers,
        b.inliers,
        false,
        String(p.inliers),
        `bar ${num(b.inliers)}`,
      ),
    );
  if (p.spread != null && b.spread != null)
    out.push(
      gauge(
        "spread",
        "Spread across the photo",
        p.spread,
        b.spread,
        false,
        num(p.spread),
        `bar ${num(b.spread)}`,
      ),
    );
  if (p.rival_ratio != null && b.rival != null)
    out.push(
      gauge(
        "rival",
        "Best other building",
        p.rival_ratio,
        b.rival,
        true,
        `${num(p.rival_ratio)}x`,
        `blocks at ${num(b.rival)}x`,
      ),
    );
  return out;
}

const OPTION_LABEL: Record<string, string> = {
  base: "base search",
  wider_index: "wider search of every building",
  deeper_claimed: "deeper search of this home",
  stop: "stopped",
};

export function optionLabel(option: string): string {
  const focus = /^focus_scan:(.+)$/.exec(option);
  if (focus) return `scan ${focus[1]} on its own`;
  return OPTION_LABEL[option] ?? option;
}

/** Same words as the trace panel's stamps (trace/TracePanel.tsx byLabel). */
export const stampLabel = (by: "model" | "policy") =>
  by === "model" ? "picked by model" : "picked by rules";

export function searchLine(s: PlaceStep, i: number): string {
  const secs = typeof s.seconds === "number" ? `, ${num(s.seconds)} s` : "";
  return `${i + 1} ${optionLabel(s.option)} (${stampLabel(s.chosen_by)}${secs})`;
}

export function findPhoto(file: EvidenceFile, alias: string): EvidencePhoto | undefined {
  return file.photos.find((p) => p.alias === alias);
}

/** "Taken here: Bedroom", or the words for the other outcomes. Never "your unit". */
export function placeLine(p: EvidencePhoto): string {
  if (p.status === "located_elsewhere") return "Taken in a different building";
  if (p.status === "located_in_claimed" && !p.bar_failed)
    return p.room_label ? `Taken here: ${p.room_label}` : "Taken in this scan";
  return "Not placed in this scan";
}
