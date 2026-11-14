// Mirrors EvidenceFile in src/snapback/contracts.py (contract E0, plan/ml-agent-plan.md 3b):
// `/evidence/photos.json`, written by code only. Every number the drawer draws is read from a
// value of this shape; nothing is typed into the web.
import type { DataSource, LocateStatus } from "../contracts";

export type BarFailed = "inliers" | "ratio" | "spread" | "ambiguity";

export interface PlaceStep {
  option: string; // "base", "focus_scan:S2", "wider_index", "deeper_claimed" or "stop"
  chosen_by: "model" | "policy";
  seconds?: number | null;
  result: "placed" | "not_placed" | "elsewhere" | "skipped";
}

/** Pairs (ad x, ad y, scan x, scan y), each 0 to 1. A sample: n_total is how many matched. */
export type PointPair = [number, number, number, number];

export interface EvidencePoints {
  n_total: number;
  sampled: PointPair[];
}

export interface EvidencePhoto {
  alias: string;
  status: LocateStatus;
  inliers?: number | null;
  inlier_ratio?: number | null;
  spread?: number | null;
  rival_ratio?: number | null;
  bar_failed?: BarFailed | null;
  room_label?: string | null;
  scan_alias?: string | null;
  stop_alias?: string | null;
  searches: PlaceStep[];
  points?: EvidencePoints | null;
}

export interface EvidenceFile {
  case_id: string;
  source: DataSource;
  thresholds_version: string;
  bars: Record<string, number>;
  photos: EvidencePhoto[];
  written_by: "code";
}

/** A Lab calibration row to print beside the chip: always "k of n", n printed. */
export interface Calibration {
  k: number;
  n: number;
  on: string; // what the row was measured on, e.g. "renders"
}
