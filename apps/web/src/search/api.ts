import { apiFetch, apiFetchReadWhenReady, dataMode } from "../api";
import { AS_OF } from "../contracts";
import type {
  AlternativesResponse,
  PlaceMatch,
  RenterBrief,
  SearchResponse,
  TourDraft,
} from "../contracts";

export class NoReadToken extends Error {}

// The strip's answer: the places, which data they came from, and (when the API sends one) the
// budget trade-off question to show if nothing fits. All text is the API's, shown as given.
export interface Places {
  source: SearchResponse["source"];
  as_of: string;
  matches: PlaceMatch[];
  tradeoff_question: string | null;
}

export function briefIsEmpty(brief: RenterBrief | null | undefined): boolean {
  if (!brief) return true;
  return (
    brief.max_rent_month == null &&
    brief.beds_min == null &&
    !brief.needs_no_walkup &&
    !brief.needs_parking &&
    !brief.pets &&
    !brief.move_in_by
  );
}

// The renter's brief for a case lives in sessionStorage by case id, so the card page can ask for
// places that fit it. It holds a budget and must-haves only, never a token.
const BRIEF_PREFIX = "snapback.brief.";

export function saveBrief(caseId: string, brief: RenterBrief): void {
  try {
    window.sessionStorage.setItem(BRIEF_PREFIX + caseId.toUpperCase(), JSON.stringify(brief));
  } catch {
    // Storage blocked: the card page shows places without the budget filter.
  }
}

export function loadBrief(caseId: string): RenterBrief | null {
  try {
    const raw = window.sessionStorage.getItem(BRIEF_PREFIX + caseId.toUpperCase());
    return raw ? (JSON.parse(raw) as RenterBrief) : null;
  } catch {
    return null;
  }
}

// Synthetic sample places for fixture mode. They are labelled FIXTURE on screen, and they are
// not real listings.
const FIXTURE_PLACES: PlaceMatch[] = [
  {
    property_id: "fixture-bldg-1",
    kind: "apartment",
    floor_plan: "1 bed / 1 bath",
    plan_key: "fixture-plan-1",
    beds: 1,
    baths: 1,
    rent_min: 1450,
    rent_max: 1600,
    budget_fit: "within",
    price_text: `$1,450 to $1,600 a month ${AS_OF}`,
    availability_text: `3 units reported available ${AS_OF}`,
    must_haves: [
      { key: "walkup", text: "No walk-up: reported elevator access", met: true },
      { key: "parking", text: "Parking: the record does not say", met: null },
    ],
    musts_met: 1,
    has_3d_scan: true,
    scan_text: "a 3D scan in this building",
    office_on_record: "Sample Property Group",
    source: "fixture",
  },
  {
    property_id: "fixture-bldg-2",
    kind: "apartment",
    floor_plan: "2 bed / 1 bath",
    plan_key: "fixture-plan-2",
    beds: 2,
    baths: 1,
    rent_min: 1700,
    rent_max: 1850,
    budget_fit: "starts_within",
    price_text: `$1,700 to $1,850 a month ${AS_OF}`,
    availability_text: `1 unit reported available ${AS_OF}`,
    must_haves: [{ key: "walkup", text: "No walk-up: reported elevator access", met: true }],
    musts_met: 1,
    has_3d_scan: false,
    scan_text: null,
    office_on_record: "Example Residential Co",
    source: "fixture",
  },
];

export const FIXTURE_TOUR_TEXT =
  "Hello, I am a renter interested in a 1 bed / 1 bath, listed at $1,450 to $1,600 a month " +
  `${AS_OF}. Could I book a tour? Please reply with the times that work and what a tour covers.`;

async function failure(res: Response): Promise<Error> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = ` ${body.detail}`;
  } catch {
    // not JSON; the status is enough
  }
  return new Error(`The server answered ${res.status}.${detail}`.trim());
}

function fixturePlaces(brief: RenterBrief | null): Places {
  const cap = brief?.max_rent_month;
  const matches =
    cap == null ? FIXTURE_PLACES : FIXTURE_PLACES.filter((p) => (p.rent_min ?? 0) <= cap);
  return { source: "fixture", as_of: AS_OF, matches, tradeoff_question: null };
}

// POST /search with the brief. No case or token is needed.
export async function searchPlaces(brief: RenterBrief, signal?: AbortSignal): Promise<Places> {
  if (dataMode() === "fixture") return fixturePlaces(brief);
  const res = await apiFetch("/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(brief),
    signal,
  });
  if (!res.ok) throw await failure(res);
  const body = (await res.json()) as SearchResponse & { tradeoff_question?: string | null };
  return {
    source: body.source,
    as_of: body.as_of,
    matches: body.matches,
    tradeoff_question: body.tradeoff_question ?? null,
  };
}

// GET /cases/{id}/alternatives, with the case's read token in the Authorization header.
export async function fetchAlternatives(
  caseId: string,
  signal?: AbortSignal,
  onWaiting?: (waiting: boolean) => void,
): Promise<Places> {
  if (dataMode() === "fixture") return fixturePlaces(null);
  const res = await apiFetchReadWhenReady(
    `/cases/${encodeURIComponent(caseId)}/alternatives`,
    caseId,
    { signal },
    onWaiting,
  );
  if (!res)
    throw new NoReadToken("This browser does not hold the key to read places for this case.");
  if (!res.ok || res.status === 202) throw await failure(res);
  const body = (await res.json()) as AlternativesResponse & { tradeoff_question?: string | null };
  return {
    source: body.source,
    as_of: body.as_of,
    matches: body.matches,
    tradeoff_question: body.tradeoff_question ?? null,
  };
}

// POST /cases/{id}/tour-draft. The case's write token goes in the Authorization header only.
// The API returns a draft; no route sends it.
export async function requestTourDraft(
  caseId: string,
  place: PlaceMatch,
  brief: RenterBrief | null,
  signal?: AbortSignal,
): Promise<TourDraft> {
  if (dataMode() === "fixture") {
    return {
      property_id: place.property_id,
      addressee: place.office_on_record ?? "the leasing office",
      text: FIXTURE_TOUR_TEXT,
      status: "draft",
      sent: false,
      source: "fixture",
    };
  }
  const payload: Record<string, unknown> = { property_id: place.property_id };
  if (place.plan_key) payload.plan_key = place.plan_key;
  else if (place.floor_plan) payload.floor_plan = place.floor_plan;
  if (brief && !briefIsEmpty(brief)) payload.brief = brief;
  const res = await apiFetch(`/cases/${encodeURIComponent(caseId)}/tour-draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    tokenFor: caseId,
    signal,
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as TourDraft;
}
