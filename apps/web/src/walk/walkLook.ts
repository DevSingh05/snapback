// What the walk screens draw beyond the tour plan: the evidence file, its real images, the
// trace events and (copied-ad case) the two-buildings view. A live case passes its own data
// through (walk/useWalkLive). In FIXTURE mode the evidence is the E0 fixture and the rail reads
// a local stub until the recorded runs land.
import type { TourPlan, TourStop, TraceEvent } from "../contracts";
import { EVIDENCE_FIXTURE_A, EVIDENCE_FIXTURE_B } from "../evidence/fixture";
import type { EvidenceFile, EvidencePhoto } from "../evidence/types";
import { RAIL_STUB_A, RAIL_STUB_B } from "./railStub";
import type { EvidenceImages, WalkLive } from "./useWalkLive";

export interface Mismatch {
  officeLine: string;
  officeName: string | null;
  /** Shown only when the plan itself does not already say which building this walk is in. */
  banner: string | null;
}

export interface WalkLook {
  evidence: EvidenceFile | null;
  images: EvidenceImages;
  events: TraceEvent[];
  mismatch: Mismatch | null;
}

// Section 7 copy guards: never an address, and no claim that the home can be rented. The plan's
// own mode line (written by code in tour.py) is used when it is set; this is the fallback.
export const OFFICE_LINE = "We can't tell you if it is offered, or at this price.";

/** The line under the two aerials: the plan's own words when it has them. */
export const officeLineOf = (plan: TourPlan): string => plan.mode_line || OFFICE_LINE;
export const MISMATCH_BANNER =
  "You are in the home in the ad's photos. It is not the home the ad names.";

const same = (a?: string | null, b?: string | null) =>
  Boolean(a && b && a.trim().toLowerCase() === b.trim().toLowerCase());

const isPlaced = (p: EvidencePhoto) =>
  (p.status === "located_in_claimed" || p.status === "located_elsewhere") && !p.bar_failed;

/** The evidence row of the ad photo the plan placed at this stop: by the walk's own stop alias
 *  (W1), else by the room label both files carry. Null when the plan placed no photo here. */
export function photoAt(stop: TourStop, evidence: EvidenceFile | null): EvidencePhoto | null {
  if (!evidence || stop.photos.length === 0) return null;
  const placed = evidence.photos.filter(isPlaced);
  return (
    placed.find((p) => p.stop_alias === stop.key) ??
    placed.find((p) => same(p.room_label, stop.room_label)) ??
    null
  );
}

/** `search` is the page's query string. In FIXTURE mode `?demo=b` shows the copied-ad case. */
export function walkLook(plan: TourPlan, search: string, live?: WalkLive | null): WalkLook {
  const elsewhere = plan.mode === "elsewhere";
  if (plan.source !== "fixture")
    return {
      evidence: live?.evidence ?? null,
      images: live?.images ?? {},
      events: live?.events ?? [],
      // The office line and name come from the card (X1-card, lane A); not wired yet.
      mismatch: elsewhere
        ? { officeLine: officeLineOf(plan), officeName: null, banner: null }
        : null,
    };
  const caseB = elsewhere || new URLSearchParams(search).get("demo") === "b";
  return caseB
    ? {
        evidence: EVIDENCE_FIXTURE_B,
        images: {},
        events: RAIL_STUB_B,
        mismatch: {
          officeLine: officeLineOf(plan),
          officeName: "Fixture Leasing Office",
          banner: elsewhere ? null : MISMATCH_BANNER,
        },
      }
    : { evidence: EVIDENCE_FIXTURE_A, images: {}, events: RAIL_STUB_A, mismatch: null };
}
