// A sample run for the front end that has no API, and for "Watch a sample run": the fixture
// card (fixtures/contracts/card_hold.json) with a team-made timeline that fits it. Synthetic,
// marked FIXTURE everywhere; the times are made up to read like a check with photos.
import cardHold from "../../../../fixtures/contracts/card_hold.json";
import deepSample from "./deepSample.json";
import type { Card, CaseTimeline, TimelineStep } from "../contracts";

export const SAMPLE_ID = "sample";

export const sampleCard = cardHold as Card;

type Row = [label: string, started: number, took: number, kind: string | null, result?: string];

const ROWS: Row[] = [
  ["Read the ad", 0, 0, null, "Read what the ad says it is."],
  ["Chose which checks to run", 40, 60, null],
  ["Compared the ad's claims with the record", 100, 120, "claims"],
  ["Found the building on CoStar's record", 220, 380, "record"],
  ["Checked the phone against the leasing office", 600, 0, "phone"],
  ["Placed 3 of 3 photos in its 3D scan", 600, 4200, "locate"],
  ["Checked the county's owner of record", 4800, 300, "owner"],
  [
    "Skipped the license lookup",
    5100,
    0,
    "license",
    "Skipped TREC license: the ad names no license.",
  ],
  ["Checked the photo that came back", 5100, 2400, "reply"],
  ["Put the report together", 7500, 200, "report"],
  [
    "Code worked out the result",
    7700,
    0,
    null,
    "Worked out by code from the evidence. No model picks it.",
  ],
];

const steps: TimelineStep[] = ROWS.map(([label, started_ms, took_ms, kind, result], step) => ({
  step,
  label,
  started_ms,
  took_ms,
  result: result ?? "Done.",
  source: "fixture",
  by: "code",
  kind,
  skipped: label.startsWith("Skipped"),
}));

export const sampleTimeline: CaseTimeline = {
  case_id: sampleCard.case_id,
  source: "fixture",
  mode: "policy",
  fell_back: false,
  steps,
  todos: [],
  plan: [],
};

// A deep-agent run, for the trace cards: a real deepagents graph (planner, sub-agents, their
// tools, the to-do list and the notes) driven by a scripted model instead of Claude, on the
// fixture kit, then saved exactly as the API served it. The words the "model" says are the
// team's; the shapes, the order and the counts are the graph's own. FIXTURE everywhere.
export const DEEP_SAMPLE_ID = "deep-sample";
export const deepCard = (deepSample as { card: Card }).card;
export const deepTimeline = (deepSample as { timeline: CaseTimeline }).timeline;
