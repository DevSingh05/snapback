// Mirrors the Card shapes in src/snapback/contracts.py. Keep the two in step; the XO owns both.

export type DataSource = "live" | "fixture";
export type VerdictState = "verified" | "hold" | "dont_pay" | "unverified";
export type CardRowKind = "place" | "person" | "price" | "claims"; // claims: ad vs record, only when it has lines
export type CardTone = "ok" | "hold" | "red_flag" | "not_shown" | "not_checked";

export interface CardLine {
  label: string;
  text: string;
  tone: CardTone;
  source?: DataSource | null;
  // The label's table key ("label.payment_ask"): which check the line came from, in any language.
  key?: string | null;
  // Which source answered the line: "CoStar record", "HUD", "Census", "HCAD", "RDAP", "TREC".
  source_name?: string | null;
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
  availability_url?: string | null; // LIVE local only; the route never sends it without the flag
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
  // "costar" (the building's record) or "hud_safmr" (HUD's typical rent for the ZIP). The HUD
  // fields name the ZIP, bedroom count and rent that were compared.
  baseline_source?: "costar" | "hud_safmr" | null;
  baseline_rent?: number | null;
  baseline_zip?: string | null;
  baseline_beds?: number | null;
}

// Public data (Census Geocoder, RDAP). Mirrors PublicStatus, PlaceCheck and DomainCheck in
// src/snapback/contracts.py.
export type PublicStatus = "found" | "no_match" | "not_checked";

export interface PlaceCheck {
  status: PublicStatus;
  zip?: string | null;
  county_fips?: string | null;
  county?: string | null;
  source: DataSource;
}

export interface DomainCheck {
  host: string;
  status: PublicStatus;
  registered_on?: string | null; // ISO date
  age_days?: number | null;
  source: DataSource;
}

export interface AuthorityResult {
  status: string; // AuthorityStatus: matches_record, mismatch, unknown
  manager_on_record?: string | null; // company name only
  poster_said?: string | null;
  office_phone_match: PhoneMatch;
  link_domain: LinkDomain;
  lookalike_sender_only?: boolean; // the lookalike came from a sender address alone
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
  // Proof plan 3.2, built by code (no model), in the card's language. Missing or empty on an
  // older card. At most 3 sentences; checks_out and does_not are "label: text" strings.
  summary?: string[];
  checks_out?: string[]; // lines with tone ok
  does_not?: string[]; // red flag, hold and not-shown lines
  // Set by the API when the state's own words would mislead (a HOLD with nothing against it).
  headline?: string | null;
  // Set by GET /cases/{id}/card: false when the case has no evidence file, so the page does not
  // ask for one. Missing means not said.
  has_evidence?: boolean | null;
}

// The body of a 202 from the report's reads while the check is still running (not ready, not
// failed). Ask again after retry_after_ms.
export interface StillChecking {
  status: string; // CaseProgress
  retry_after_ms: number;
}

export type TraceKind =
  | "choice"
  | "tool"
  | "status"
  | "hitl"
  | "verdict"
  | "error"
  // The deep agent's own steps (E0): todo list, sub-agent hand-off, file written, code-raised doubt.
  | "todo"
  | "agent"
  | "file"
  | "unsure";
export type ChoiceKind =
  | "which_checks"
  | "which_floor_plan"
  | "which_spot"
  | "retry_or_stop"
  | "ask_human"
  | "next_check"
  | "next_search"
  | "which_photo"
  | "dwell_rooms"
  | "lead_checks";

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

// One step of "What your agent did" (GET /cases/{id}/timeline), in the order it happened.
// The label is plain words (en/es) with counts only: never a phone number, address or rent.
// `by` is "agent" when the language model made the step happen, "code" otherwise; the result
// is always code's. took_ms runs until the next step began (0 for the last and derived lines).
export interface TimelineStep {
  step: number;
  label: string;
  started_ms: number;
  took_ms: number;
  result: string;
  source: DataSource;
  by: "agent" | "code";
  // The check or sub-agent the step belongs to ("record", "owner", "locate", "place", ...), so a
  // reason can be tied to the step behind it. null when the step is not one check.
  kind?: string | null;
  // The plan left this check out; `result` says why.
  skipped?: boolean;
}

export interface TimelineTodo {
  content: string;
  done: boolean;
}

// GET /cases/{id}/timeline. Read token in a header; served with Cache-Control no-store.
// `todos` (the agent's last todo list) and `plan` (sub-agents it handed work to, in order)
// are empty unless the deep agent ran. `fell_back`: the agent stopped and code finished.
// One tool call on a member's trace card: the tool's own name, what it did in plain words and one
// short line of what came back. Cleaned by the API: no phone, address, rent or result word.
export interface TraceTool {
  tool: string;
  label: string;
  result: string;
}

// One member's trace card (the planner first, then each sub-agent in the order work reached it).
export interface MemberTrace {
  kind: string; // "planner", or the sub-agent's name ("record", "owner", "place", ...)
  model: string; // what ran it: "Claude Sonnet", "Claude Haiku", ...
  asked?: string | null; // the planner's instruction to it; null for the planner
  tools: TraceTool[];
  said?: string | null; // what it handed back, trimmed
  took_ms?: number | null;
  model_calls: number;
}

export interface CaseTimeline {
  case_id: string;
  source: DataSource;
  mode: "policy" | "deepagents";
  fell_back: boolean;
  // The deep agent is still working this case in the background (SNAPBACK_AGENT=deepagents_async).
  // Absent from older servers, which means "not running".
  running?: boolean;
  steps: TimelineStep[];
  todos: TimelineTodo[];
  plan: string[];
  // The trace cards when the deep agent ran; empty or absent with the policy and on older servers.
  members?: MemberTrace[];
  // The run's LangSmith project page, when the server names one. Never carries a key or token.
  trace_url?: string | null;
}

// One working note the agent wrote (GET /cases/{id}/notes). Derived text only.
export interface CaseNote {
  path: string;
  stem: string;
  agent: string;
  text: string;
  written_by: ChosenBy;
}

export interface CaseNotes {
  case_id: string;
  source: DataSource;
  notes: CaseNote[];
  footer: string;
}

// Mirrors Pose and the parts of LocateResult the twin reads (src/snapback/contracts.py).
export interface Pose {
  sweep_id?: string | null;
  position: [number, number, number];
  rotation_quat: [number, number, number, number]; // x, y, z, w
  fov_deg?: number | null;
  // The matched camera direction in the 3D viewer's frame, degrees (yaw 0 looks down -Z and
  // grows turning left; pitch positive looks up). Set by the locator; prefer these to the quat.
  yaw_deg?: number | null;
  pitch_deg?: number | null;
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

// Mirrors RealListingPlan and RealListing in src/snapback/contracts.py
// (GET /cases/{id}/real-listing; read token in a header, never in the address; no-store).
// Record figures (rents, units, building name) are null unless figures_shown. The hand-off link
// (cta_url) is not a figure: it is sent with figures_shown on or off. Words are
// built by code in the asked language (?lang=en|es). No phone digits and no street address.
export interface RealListingPlan {
  name?: string | null;
  beds?: number | null; // 0 is a studio
  baths?: number | null;
  rent_min?: number | null; // whole dollars a month
  rent_max?: number | null;
  units_available?: number | null;
  availability_host?: string | null; // host only
}

export interface RealListing {
  case_id: string;
  source: DataSource; // show the LIVE or FIXTURE chip from this
  property_id: string;
  which: "claimed" | "matched"; // matched: the building the photos were placed in
  building_name?: string | null; // only with figures_shown
  manager_company?: string | null;
  website_host?: string | null;
  plans: RealListingPlan[]; // narrowed to the ad's bedrooms; never a per-bed plan
  photos_in_scan: number;
  photos_total: number;
  ad_rent?: number | null;
  ad_asks_irreversible: boolean;
  phone_is_office: "yes" | "no" | "not_checked";
  figures_shown: boolean;
  as_of: string; // "as of CoStar's last research"
  headline: string; // the ad against the record, one paragraph
  provenance?: string | null; // "N of M of the ad's photos are in CoStar's own scan..."
  phone_line?: string | null;
  cta_label?: string | null; // "See the real listing"
  cta_url?: string | null; // availability link, else https://<website_host>; shown with figures on or off
}

// Mirrors ReportSteps and ReportResponse in src/snapback/contracts.py (GET /cases/{id}/report;
// read token in a header, never in the address). Listing facts only: no score, nothing about the
// renter, no word about any person. `platforms` carries steps only when `reportable`.
export interface ReportSteps {
  platform: "facebook" | "zillow" | "craigslist";
  name: string; // "Facebook Marketplace", "Zillow", "Craigslist"
  steps: string[]; // what to click, in order
}

export interface ReportPack {
  case_id: string;
  source: DataSource; // show the LIVE or FIXTURE chip from this
  lang: string;
  checked_at: string;
  state: VerdictState;
  reportable: boolean; // true only on proof, or a record that shows the home for sale
  proof_lines: string[]; // decide()'s own reasons, in order
  twin_url?: string | null;
  platforms?: ReportSteps[];
  not_checked: string[];
}

// Mirrors CopyAlert in src/snapback/contracts.py (GET /cases/{id}/copy-alert; read token in a
// header, never in the address; no-store). A DRAFT for the leasing office on record: nothing is
// ever sent, `sent` is always false. Show it only when `fires`. Words are in the asked language
// (?lang=en|es). No phone digits, no street address, no person named, rent as a percent only.
export interface CopyAlert {
  case_id: string;
  source: DataSource; // show the LIVE or FIXTURE chip from this
  fires: boolean;
  why_not?: "no_record" | "no_photos_in_scan" | "phone_not_checked" | "phone_is_office" | null;
  which?: "claimed" | "matched" | null;
  property_id?: string | null;
  manager_company?: string | null; // who the note is for
  website_host?: string | null;
  photos_in_scan: number;
  photos_total: number;
  phone_is_office: "yes" | "no" | "not_checked"; // "no" when it fires on the claimed building
  rent_percent_under?: number | null;
  draft_only: true;
  sent: false;
  draft_subject?: string | null;
  draft_body?: string | null; // plain text with blank lines between paragraphs
  report_url?: string | null; // GET it with the read token header: the "Report this copy" pack
  report_ready: boolean; // the pack hands out report steps only when true
  as_of: string;
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
  // GET /cases/{id}/alternatives only: where the renter goes to see this place's real listing.
  // The plan's availability page, else https://<website host>, else null. A LIVE place has none
  // unless the local demo's figures flag is on.
  handoff_url?: string | null;
  handoff_label?: string | null; // "Its listing on Apartments.com" or "The building's own site"
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
  prefer_scans?: boolean | null;
}

export interface CasePreferences {
  no_walkup: boolean;
  needs_parking: boolean;
  max_rent: number | null;
  avoid_property_ids: string[];
  prefer_scans: boolean; // M9: orders the list (3D-scan places first), never filters it
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
  alias?: string | null; // P1, P2...: the key of /cases/{id}/evidence/{alias}/photo.jpg
  sweep_id?: string | null;
  position?: [number, number, number] | null;
  rotation_quat?: [number, number, number, number] | null;
  fov_deg?: number | null;
  yaw_deg?: number | null; // the matched camera direction in the 3D viewer's frame (Pose.yaw_deg)
  pitch_deg?: number | null;
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
  ad_view: "placed" | "none_placed" | "unknown"; // whether an ad photo was placed in this room
  claims: TourFact[]; // what the ad claimed for this room
  position?: [number, number, number] | null;
  rotation_quat?: [number, number, number, number] | null;
  facts: TourFact[];
  tip?: string | null; // "check this in person"
  note?: string | null;
}

export interface WalkCoverage {
  counted: "rooms" | "spots" | "none";
  total: number;
  with_photo: number;
  placed: number;
  elsewhere: number;
  unplaced: number;
  other_scan?: number; // placed in this home, in another scan of the building: not on a stop
  plan_mismatch?: boolean;
  line?: string | null;
}

export interface TourDirector {
  dwell: string[]; // stop keys
  lead_checks: string[];
  stamp: "model" | "policy";
  reason?: string | null;
}

// GET /cases/{id}/walk: the plan with the case's placed photos, and its locate result.
export interface WalkResponse {
  plan: TourPlan;
  model_id?: string | null; // the scan the walk was built from
  locate?: LocateResult | null;
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
  up_axis?: "y" | "z"; // which model axis is vertical in the stops' positions
  mode?: "claimed" | "elsewhere"; // "elsewhere": the building the ad's photos were taken in
  mode_line?: string | null;
  coverage?: WalkCoverage | null;
  director?: TourDirector | null;
  scan_date_line?: string | null; // "Scanned Mar 2026 (Matterport)" or "Scan date not on record"
  scan_age_note?: string | null; // set when the scan is older than 12 months
  summary?: { know: string[]; see: string[] } | null; // the last screen's two columns
}

// Mirrors PackLine and TourPrepPack in src/snapback/pack.py (GET /cases/{id}/tour-prep and
// GET /places/{property_id}/tour-prep). Every word is the API's, written by code in the language
// asked for; render it as given.
export interface PackLine {
  key: string;
  text: string;
  sources: string[];
  as_of?: string | null; // "as of CoStar's last research", on lines from CoStar's research
}

export interface TourPrepPack {
  source: DataSource;
  lang: "en" | "es";
  title: string;
  subtitle: string;
  note: string;
  as_of: string;
  facts_heading: string;
  questions_heading: string;
  pay_heading: string;
  facts: PackLine[];
  questions: PackLine[];
  before_you_pay: string[];
}

// M9: the finder (src/snapback/agent/finder.py, api/finder.py). Mirrors the Finder* models in
// contracts.py. Nothing the agent learns applies until the renter accepts a proposal.
export type FinderProposalKey =
  "propose_no_walkup" | "propose_parking" | "propose_prefer_scans" | "propose_lower_budget";

export interface FinderSessionStarted {
  session_id: string;
  token: string; // shown once; send as Authorization: Bearer or X-Finder-Token, never in the address
  source: DataSource;
  mode: "policy" | "deepagents";
}

export interface FinderSignal {
  kind: "pick" | "pass" | "brief";
  place_kind?: "apartment" | "house" | null;
  has_scan?: boolean | null;
  rent_from?: number | null;
  walkup?: boolean | null;
  parking?: boolean | null;
  brief_field?: "budget" | "beds" | "parking" | "no_walkup" | "pets" | null;
  rent_max?: number | null;
}

export interface FinderMessageRequest {
  text?: string | null; // up to 500; code reads it into signals, the model sees it cleaned
  signals?: FinderSignal[];
}

export interface FinderProposal {
  id: string;
  key: FinderProposalKey;
  update: PreferencesUpdate;
  text: string; // the question for the renter, written by code
  evidence: string;
  reason: string;
  chosen_by: ChosenBy;
  status: "proposed" | "accepted" | "declined";
  at: string;
}

export interface FinderPick {
  pid: string;
  rank: number;
  kind: "apartment" | "house";
  has_scan: boolean;
  line: string; // code-built from the record, "as of CoStar's last research"
  why: string; // one sentence from the search sub-agent
  chosen_by: ChosenBy;
  as_of: string;
  // The record's facts behind the line, so a pass or pick can go back as a signal.
  rent_from?: number | null;
  walkup?: boolean | null;
  parking?: boolean | null;
}

export interface FinderNote {
  path: string;
  text: string;
  written_by: ChosenBy;
}

export interface FinderTraceEvent {
  session_id: string;
  seq: number;
  at: string;
  kind: TraceKind;
  options: string[];
  pick?: string | null;
  reason: string;
  source: DataSource;
  chosen_by: ChosenBy;
}

export interface FinderReply {
  session_id: string;
  source: DataSource;
  mode: "policy" | "deepagents";
  reply: string;
  reply_by: ChosenBy;
  proposals: FinderProposal[];
  picks: FinderPick[];
  as_of: string;
}

export interface FinderState {
  session_id: string;
  source: DataSource;
  mode: "policy" | "deepagents";
  applied: CasePreferences;
  proposals: FinderProposal[];
  picks: FinderPick[];
  learned: Record<string, string | boolean>; // "what I've learned about you"
  notes: FinderNote[];
  trace: FinderTraceEvent[];
  as_of: string;
  watch?: FinderWatchStatus | null; // set by POST /finder/{session}/watch
}

export interface FinderWatchRequest {
  channel: "imessage";
}

export interface FinderWatchStatus {
  session_id: string;
  channel: "imessage";
  kind: "brief"; // the session's brief, never one place
  event_id: string; // the watch_added event on the bus
  source: DataSource;
  at: string;
}

export interface FinderDecision {
  decision: "accept" | "decline";
}
