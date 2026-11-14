// What the walk screens draw beyond the tour plan: the evidence file, the trace events, the
// coverage line and (case b) the two-buildings mismatch. In a live walk these come from the API
// (E3 routes, the trace stream, W1 coverage, X1 walk mode) and this file passes them through.
// In FIXTURE mode, until those land, it reads the local stubs so the screens can be seen.
import type { TourPlan, TourStop, TraceEvent, WalkCoverage } from "../contracts";
import { EVIDENCE_STUB_A, EVIDENCE_STUB_B } from "../evidence/evidenceStub";
import type { EvidenceFile, EvidencePhoto } from "../evidence/types";
import { RAIL_STUB_A, RAIL_STUB_B } from "./railStub";

export interface Mismatch {
  officeLine: string;
  officeName: string | null;
  namedCapturedOn: string | null;
  picturedCapturedOn: string | null;
  banner: string;
}

export interface WalkLook {
  evidence: EvidenceFile | null;
  events: TraceEvent[];
  coverage: WalkCoverage | null;
  mismatch: Mismatch | null;
}

// Section 7 copy guards: "the home in these photos", never an address, and no claim that the
// home can be rented. Lane A's card line replaces this text when X1-card lands.
export const OFFICE_LINE =
  "The home in these photos is listed by its office on CoStar's record. We can't tell you whether it can be rented, or at this price.";
export const MISMATCH_BANNER =
  "You are in the home in the ad's photos. It is not the home the ad names.";

const same = (a?: string | null, b?: string | null) =>
  Boolean(a && b && a.trim().toLowerCase() === b.trim().toLowerCase());

const isPlaced = (p: EvidencePhoto) =>
  (p.status === "located_in_claimed" || p.status === "located_elsewhere") && !p.bar_failed;

/** The placed ad photo that belongs to a stop: by the walk's own stop alias (W1), else by the
 *  room label both files carry. */
export function photoAt(stop: TourStop, evidence: EvidenceFile | null): EvidencePhoto | null {
  if (!evidence || (stop.kind !== "room" && stop.kind !== "stop")) return null;
  const placed = evidence.photos.filter(isPlaced);
  return (
    placed.find((p) => p.stop_alias === stop.key) ??
    placed.find((p) => same(p.room_label, stop.room_label)) ??
    null
  );
}

/** Whether the ad showed this room. The plan's own field wins; "unknown" stays unknown unless
 *  an evidence file is there to answer it. */
export function adViewOf(
  stop: TourStop,
  evidence: EvidenceFile | null,
  mismatch: boolean,
): TourStop["ad_view"] {
  if (stop.ad_view !== "unknown") return stop.ad_view;
  if (stop.photos.length > 0) return "placed";
  if (!evidence || stop.kind !== "room") return "unknown";
  if (photoAt(stop, evidence)) return "placed";
  // In the walk through the pictured building, rooms without a photo are not counted against
  // the home the ad names.
  return mismatch ? "unknown" : "none_placed";
}

function coverageOf(plan: TourPlan, evidence: EvidenceFile): WalkCoverage {
  const rooms = plan.stops.filter((s) => s.kind === "room");
  const shown = rooms.filter((s) => adViewOf(s, evidence, false) === "placed").length;
  const count = (status: EvidencePhoto["status"]) =>
    evidence.photos.filter((p) => p.status === status).length;
  return {
    counted: "rooms",
    total: rooms.length,
    with_photo: shown,
    placed: count("located_in_claimed"),
    elsewhere: count("located_elsewhere"),
    unplaced: count("not_located"),
    line: `The ad showed ${shown} of the ${rooms.length} rooms in this scan.`,
  };
}

/** `search` is the page's query string. In FIXTURE mode `?case=b` shows the copied-ad case. */
export function walkLook(plan: TourPlan, search: string): WalkLook {
  if (plan.source !== "fixture")
    return { evidence: null, events: [], coverage: plan.coverage ?? null, mismatch: null };
  const caseB = new URLSearchParams(search).get("case") === "b";
  if (caseB)
    return {
      evidence: EVIDENCE_STUB_B,
      events: RAIL_STUB_B,
      coverage: null,
      mismatch: {
        officeLine: OFFICE_LINE,
        officeName: "Fixture Leasing Office",
        namedCapturedOn: plan.aerial?.captured_on ?? null,
        picturedCapturedOn: plan.aerial?.captured_on ?? null,
        banner: MISMATCH_BANNER,
      },
    };
  return {
    evidence: EVIDENCE_STUB_A,
    events: RAIL_STUB_A,
    coverage: plan.coverage ?? coverageOf(plan, EVIDENCE_STUB_A),
    mismatch: null,
  };
}
