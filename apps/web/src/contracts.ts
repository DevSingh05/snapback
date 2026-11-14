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
  offices?: string[]; // listing offices on record: brokerage companies, never a person
}

export interface FloorPlanRent {
  name?: string | null;
  beds?: number | null;
  rent_min?: number | null;
  rent_max?: number | null;
  per_bed: boolean;
  baths?: number | null;
  units_available?: number | null; // reported available at CoStar's last research
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
  "which_checks" | "which_floor_plan" | "which_spot" | "retry_or_stop" | "ask_human" | "next_check";

// Who made a trace step happen: a language model picking from code-written options, or the
// code policy (also every fallback, random draw and tool code ran).
export type ChosenBy = "model" | "policy";

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
  chosen_by: ChosenBy;
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
  identified_by_scan?: boolean;
  identified_photos?: number;
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
  // Search must-haves; null or missing means the record does not say.
  is_walkup?: boolean | null;
  has_elevator?: boolean | null;
  metering?: string | null; // "individual" or "master"
  parking_ratio?: number | null;
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

// Mirrors RenterBrief, PlaceMatch, SearchResponse, AlternativesResponse, TourDraftRequest and
// TourDraft in src/snapback/contracts.py (POST /search, GET /cases/{id}/alternatives,
// POST /cases/{id}/tour-draft). Every price and availability line ends "as of CoStar's last
// research"; never render "available now".
export const AS_OF = "as of CoStar's last research";

export interface RenterBrief {
  max_rent_month?: number | null; // whole-unit rent a month
  beds_min?: number | null; // 0 is a studio
  baths_min?: number | null;
  needs_no_walkup?: boolean;
  needs_parking?: boolean;
  pets?: boolean;
  move_in_by?: string | null; // ISO date
  max_results?: number; // 1 to 50, default 10
}

export type BudgetFit = "within" | "starts_within" | "no_full_price" | "no_budget";

export interface MustHaveLine {
  key: string; // "walkup", "utilities", "parking", "pets"
  text: string;
  met?: boolean | null; // null: the record does not say, or the renter did not ask
}

export interface PlaceMatch {
  property_id: string;
  kind: "apartment" | "house";
  floor_plan?: string | null;
  plan_key?: string | null; // pick a plan by this, not by the label: many share one
  beds?: number | null;
  baths?: number | null;
  rent_min?: number | null; // the asking price as reported
  rent_max?: number | null;
  budget_fit: BudgetFit;
  price_text: string;
  availability_text: string;
  must_haves: MustHaveLine[];
  musts_met: number;
  has_3d_scan: boolean;
  scan_text?: string | null; // "a 3D scan in this building"
  office_on_record?: string | null; // company name only
  checked?: boolean; // true only for a place that got the deep check; the rest are "researched"
  check_line?: string | null; // built by code: "Checked: listed for rent by ...; ..."
  source: DataSource;
}

// One choice the search agent made. "model" only when a language model picked from options
// code wrote; a menu of one is always "policy". Show "picked by model" from chosen_by.
export interface SearchDecision {
  kind: "deep_check" | "tradeoff" | "tour_gate";
  options: string[];
  pick: string;
  reason: string;
  chosen_by: "model" | "policy";
}

export interface SearchResponse {
  source: DataSource;
  as_of: string;
  n_considered: number;
  n_matches: number;
  matches: PlaceMatch[];
  decisions?: SearchDecision[];
  question?: string | null; // the one trade-off question to put to the renter
  ask_first?: boolean; // ask it before drafting a tour request
  remembered?: string[]; // preference keys applied to this search
}

export interface AlternativesResponse {
  case_id: string;
  source: DataSource;
  as_of: string;
  matches: PlaceMatch[];
  decisions?: SearchDecision[];
  question?: string | null;
  ask_first?: boolean;
  remembered?: string[];
}

// POST /cases/{id}/preferences (write token header). Code-defined keys only.
export interface PreferencesUpdate {
  no_walkup?: boolean | null;
  needs_parking?: boolean | null;
  max_rent?: number | null;
  avoid_property_id?: string | null;
}

export interface CasePreferences {
  no_walkup: boolean;
  needs_parking: boolean;
  max_rent: number | null;
  avoid_property_ids: string[];
}

export interface TourDraftRequest {
  property_id: string;
  floor_plan?: string | null;
  plan_key?: string | null;
  brief?: RenterBrief | null;
}

// A draft for the renter to approve. Nothing is sent and no route sends it.
export interface TourDraft {
  property_id: string;
  addressee: string; // the office on record, company name only
  text: string;
  status: "draft";
  sent: false;
  source: DataSource;
}

// Mirrors TourPlan in src/snapback/tour.py (GET /places/{id}/tour and /cases/{id}/tour): the
// "Walk it first" tour, built by code. Every fact has a source line.
export interface TourFact {
  text: string;
  source: string;
}

export interface TourPhoto {
  photo_id: string;
  sweep_id?: string | null;
  position?: [number, number, number] | null;
  rotation_quat?: [number, number, number, number] | null;
  fov_deg?: number | null;
}

export interface TourStop {
  kind: "arrive" | "door" | "room" | "stop" | "outro";
  key: string;
  title: string;
  room_label?: string | null;
  sweep_id?: string | null;
  sweep_count: number;
  sweep_ids: string[];
  photos: TourPhoto[]; // the renter's own ad photos placed in this room (case tour only)
  position?: [number, number, number] | null;
  rotation_quat?: [number, number, number, number] | null;
  facts: TourFact[];
  tip?: string | null; // "check this in person"
  note?: string | null;
}

export interface TourPlan {
  property_id: string;
  kind: "apartment" | "house";
  source: DataSource;
  as_of: string;
  has_scan: boolean;
  scan_label?: string | null;
  rooms_labelled: boolean;
  rooms_note: string;
  aerial?: { source: DataSource; captured_on?: string | null; has_image: boolean } | null;
  stops: TourStop[];
  links: { tour_prep: string; tour_prep_api: string; tour_draft_hint: string };
}
