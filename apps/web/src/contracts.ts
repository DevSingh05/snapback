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

// A7 (#67) and D7 proofs. Mirrors UnitStatus, PhoneMatch, LinkDomain, ForSaleStatus, ForSaleMatch,
// PriceResult, AuthorityResult and FloorPlanRent in src/snapback/contracts.py.
export type PriceStatus = "within_range" | "below_range" | "not_checked";
export type UnitStatus = "on_record" | "not_on_record" | "beds_mismatch" | "not_checked";
export type PhoneMatch = "yes" | "no" | "not_checked";
export type LinkDomain = "matches" | "lookalike" | "other" | "not_checked";
export type ForSaleStatus = "active" | "recently_rented" | "none";

export interface ForSaleMatch {
  status: ForSaleStatus;
  site: string;
  listed_on?: string | null; // ISO date
  changed_on?: string | null;
}

export interface FloorPlanRent {
  name?: string | null;
  beds?: number | null;
  rent_min?: number | null;
  rent_max?: number | null;
  per_bed: boolean;
}

export interface PriceResult {
  status: PriceStatus;
  listed_rent?: number | null;
  record_median?: number | null;
  record_min?: number | null;
  record_max?: number | null;
  n_floor_plans?: number | null;
  unit: UnitStatus;
  per_bed: boolean;
}

export interface AuthorityResult {
  status: string; // AuthorityStatus: matches_record, mismatch, unknown
  manager_on_record?: string | null; // company name only
  poster_said?: string | null;
  office_phone_match: PhoneMatch;
  link_domain: LinkDomain;
}

export interface Card {
  for_sale?: ForSaleMatch | null; // D7; null or missing means not looked up
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

// Mirrors LocateStatus (contracts.py).
export type LocateStatus =
  "located_in_claimed" | "located_elsewhere" | "not_located" | "not_indexed";

// Mirrors PhotoLocation.
export interface LocatedPhoto {
  photo_id: string;
  status: LocateStatus;
  model_id?: string | null;
  pano_id?: string | null;
  inliers?: number | null;
  inlier_ratio?: number | null;
  // The twin the photo was placed in, claimed or not; for located_elsewhere these name the OTHER building.
  matched_model_id?: string | null;
  matched_property_id?: string | null;
  room_label?: string | null; // Matterport's room classification, e.g. "Kitchen"
}

// Mirrors FloorPlanCandidate.
export interface FloorPlanCandidate {
  property_id: string;
  model_id: string;
  floor_plan?: string | null;
  photos_located: number;
  total_inliers: number;
}

export interface LocateResult {
  case_id: string;
  photos: LocatedPhoto[];
  claimed_property_id?: string | null;
  chosen?: FloorPlanCandidate | null;
  alternatives?: FloorPlanCandidate[];
  poses: Record<string, Pose>; // photo_id -> pose, located photos only
  thresholds_version: string;
}

// Mirrors PropertyRecord and AerialTile in src/snapback/contracts.py.
export interface PropertyRecord {
  property_id: string;
  source: DataSource;
  market?: string | null;
  property_type?: string | null;
  floors?: number | null;
  year_built?: number | null;
  lat?: number | null;
  lon?: number | null;
  model_ids: string[];
  floor_plans: string[];
  manager_company?: string | null;
  rent_min?: number | null;
  rent_median?: number | null;
  rent_max?: number | null;
}

export interface AerialTile {
  property_id: string;
  source: DataSource;
  direction: string; // "north", "east", "south", "west" or "nadir"
  captured_on?: string | null;
  path: string;
}

// Mirrors AerialSideOut and AerialProofResponse in src/snapback/contracts.py (GET /cases/{id}/aerial).
export interface AerialSideOut {
  tile: AerialTile | null;
  record: PropertyRecord | null;
  image_url?: string | null;
}

export interface AerialProofResponse {
  case_id: string;
  source: DataSource;
  claimed: AerialSideOut;
  matched: AerialSideOut | null;
  distance_m: number | null;
}
