// LOCAL STUB, to be deleted when W7 lands its recorded runs (fixtures/demo/replays/). The plan's
// rule is that a FIXTURE rail replays a recorded real run; until one exists these hand-written
// lines stand in so the rail can be designed. Sentences follow plan/ml-agent-plan.md section 1,
// numbers follow evidence/evidenceStub.ts. Always shown with the FIXTURE chip.
// The kinds todo, agent, file and unsure arrive with contract E0 (trace/parse.ts on lane A).
import type { TraceEvent, TraceKind } from "../contracts";

type Line = [kind: string, pick: string | null, reason: string, by?: "model", options?: string[]];

function build(caseId: string, lines: Line[]): TraceEvent[] {
  const start = Date.parse("2026-11-14T15:00:00Z");
  return lines.map(([kind, pick, reason, by, options], i) => ({
    case_id: caseId,
    seq: i,
    at: new Date(start + i * 1500).toISOString(),
    kind: kind as TraceKind,
    options: options ?? [],
    pick,
    reason,
    source: "fixture",
    chosen_by: by ?? "policy",
  }));
}

export const RAIL_STUB_A: TraceEvent[] = build("fx-demo-a", [
  ["agent", "record", "Reading CoStar's record for the home the ad names."],
  ["file", "/evidence/record.json", ""],
  ["agent", "place", "Searching the home's scan for each ad photo."],
  ["tool", "locate_photos", "Base search of 4 photos."],
  [
    "choice",
    "focus_scan:S2",
    "P3 was not placed by the base search, so search scan S2 on its own.",
    "model",
    ["focus_scan:S2", "wider_index", "stop"],
  ],
  ["unsure", null, "P4 fell short: 24 matched points, the bar is 30."],
  ["file", "/evidence/photos.json", ""],
  ["file", "/notes/place.md", "", "model"],
  ["agent", "walk", "Plan: 7 stops."],
  [
    "choice",
    "Bathroom",
    "Dwelling here: the ad showed no photo of this room.",
    "model",
    ["Bathroom", "Kitchen"],
  ],
  ["unsure", null, "Matterport's room labels can be wrong."],
  ["file", "/evidence/walk.json", ""],
]);

export const RAIL_STUB_B: TraceEvent[] = build("fx-demo-b", [
  ["agent", "place", "Searching the home's scan for each ad photo."],
  ["tool", "locate_photos", "Base search of 1 photo."],
  [
    "choice",
    "wider_index",
    "P1 was not placed in the home the ad names, so search every building.",
    "model",
    ["wider_index", "deeper_claimed", "stop"],
  ],
  ["unsure", null, "P1 was placed in another building, where it matched far more strongly."],
  ["file", "/evidence/photos.json", ""],
  ["agent", "walk", "The walk opens in the building where the photo was taken."],
  ["file", "/evidence/walk.json", ""],
]);
