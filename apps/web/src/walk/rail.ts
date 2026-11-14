// Pure reads of the trace for the agent rail. Every rail item is one parsed TraceEvent; nothing
// is added, merged or reworded here, so the rail can never show a step the stream did not carry.
import type { TraceEvent } from "../contracts";
import type { AgentFile } from "../evidence/FilesTree";

export const MAIN_AGENT = "main";

export interface RailItem {
  event: TraceEvent;
  /** The agent holding the case when this event arrived: the last hand-off's name. */
  agent: string;
  /** A photo alias (P1, P2, ...) the event names, if any, to show its matched points. */
  alias: string | null;
}

const kindOf = (e: TraceEvent): string => e.kind;
const ALIAS = /\bP\d+\b/;

export function railItems(events: TraceEvent[]): RailItem[] {
  let agent = MAIN_AGENT;
  return [...events]
    .sort((a, b) => a.seq - b.seq)
    .map((event) => {
      if (kindOf(event) === "agent" && event.pick) agent = event.pick;
      const alias = ALIAS.exec(`${event.pick ?? ""} ${event.reason}`)?.[0] ?? null;
      return { event, agent, alias };
    });
}

/** Agents in the order they first held the case. */
export function lanes(items: RailItem[]): string[] {
  return [...new Set(items.map((i) => i.agent))];
}

export function railFiles(events: TraceEvent[]): AgentFile[] {
  const seen = new Map<string, AgentFile>();
  for (const e of events)
    if (kindOf(e) === "file" && e.pick)
      seen.set(e.pick, { path: e.pick, written_by: e.chosen_by === "model" ? "agent" : "code" });
  return [...seen.values()];
}

export function railCounts(events: TraceEvent[]): { steps: number; byModel: number } {
  return {
    steps: events.length,
    byModel: events.filter((e) => e.kind === "choice" && e.chosen_by === "model").length,
  };
}

/** Same words as the trace panel's stamps (trace/TracePanel.tsx byLabel). */
export function stampOf(e: TraceEvent): string {
  if (e.choice === "which_spot") return "random draw";
  return e.chosen_by === "model" ? "picked by model" : "picked by rules";
}

export const KIND_TAG: Record<string, string> = {
  choice: "Pick",
  tool: "Tool",
  status: "Status",
  hitl: "Your OK",
  verdict: "Result",
  error: "Error",
  todo: "Plan",
  agent: "Hand-off",
  file: "File",
  unsure: "Not sure",
};

export const summaryLine = (events: TraceEvent[]): string => {
  const { steps, byModel } = railCounts(events);
  return `${steps} ${steps === 1 ? "step" : "steps"}, ${byModel} picked by model`;
};

/** The newest step in one line, for the phone sheet. Only the event's own words. */
export function lastLine(e: TraceEvent): string {
  if (e.reason) return e.reason;
  const tag = KIND_TAG[e.kind] ?? e.kind;
  return e.pick ? `${tag}: ${e.pick}` : tag;
}
