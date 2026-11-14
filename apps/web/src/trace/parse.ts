import type { TraceEvent } from "../contracts";

const KINDS = [
  "choice",
  "tool",
  "status",
  "hitl",
  "verdict",
  "error",
  "todo",
  "agent",
  "file",
  "unsure",
];

// Returns null for anything that is not a well-formed TraceEvent, so one bad line never
// breaks the panel.
export function parseTraceEvent(raw: string): TraceEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null) return null;
  const d = data as Record<string, unknown>;
  if (
    typeof d.case_id !== "string" ||
    typeof d.seq !== "number" ||
    !Number.isInteger(d.seq) ||
    d.seq < 0 ||
    typeof d.at !== "string" ||
    typeof d.kind !== "string" ||
    !KINDS.includes(d.kind) ||
    typeof d.reason !== "string" ||
    (d.source !== "live" && d.source !== "fixture")
  ) {
    return null;
  }
  return {
    ...(d as unknown as TraceEvent),
    options: Array.isArray(d.options) ? (d.options as string[]) : [],
    // An older line with no stamp was made by the code policy (the API's own default).
    chosen_by: d.chosen_by === "model" ? "model" : "policy",
  };
}

export function parseFixtureLines(text: string): TraceEvent[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map(parseTraceEvent)
    .filter((e): e is TraceEvent => e !== null);
}

// seq is strictly increasing per case; the client drops repeats and keeps seq order.
export function mergeEvent(list: TraceEvent[], event: TraceEvent): TraceEvent[] {
  if (list.some((e) => e.seq === event.seq)) return list;
  return [...list, event].sort((a, b) => a.seq - b.seq);
}
