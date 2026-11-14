// Mirrors the Card shapes in src/snapback/contracts.py. Keep the two in step; the XO owns both.

export type DataSource = "live" | "fixture";
export type VerdictState = "verified" | "hold" | "dont_pay" | "unverified";
export type CardRowKind = "place" | "person" | "price";
export type CardTone = "ok" | "hold" | "red_flag" | "not_shown" | "not_checked";

export interface CardLine {
  label: string;
  text: string;
  tone: CardTone;
}

export interface CardRow {
  kind: CardRowKind;
  lines: CardLine[];
}

export interface Card {
  case_id: string;
  source: DataSource;
  state: VerdictState;
  checked_at: string;
  expires_at: string;
  rows: CardRow[];
  not_checked: string[];
  footer: string[];
  verify_url?: string | null;
  lang: string;
}

export type TraceKind = "choice" | "tool" | "status" | "hitl" | "verdict" | "error";
export type ChoiceKind =
  "which_checks" | "which_floor_plan" | "which_spot" | "retry_or_stop" | "ask_human";

// One line of the agent trace, sent as SSE `event: trace` with this JSON as `data`.
export interface TraceEvent {
  case_id: string;
  seq: number;
  at: string;
  kind: TraceKind;
  choice?: ChoiceKind | null;
  options: string[];
  pick?: string | null;
  reason: string;
  source: DataSource;
}

// Mirrors Pose and the parts of LocateResult the twin reads (src/snapback/contracts.py).
export interface Pose {
  sweep_id?: string | null;
  position: [number, number, number];
  rotation_quat: [number, number, number, number]; // x, y, z, w
  fov_deg?: number | null;
}

export interface LocatedPhoto {
  photo_id: string;
  status: string;
  model_id?: string | null;
  pano_id?: string | null;
  inliers?: number | null;
}

export interface LocateResult {
  case_id: string;
  photos: LocatedPhoto[];
  poses: Record<string, Pose>;
}

// Mirrors AerialTile and the PropertyRecord fields the aerial fact reads (src/snapback/contracts.py).
export interface AerialTileInfo {
  property_id: string;
  source: DataSource;
  direction: string;
  captured_on?: string | null;
  path: string;
}

export interface PropertyFacts {
  property_id: string;
  source: DataSource;
  floors?: number | null;
  year_built?: number | null;
}
