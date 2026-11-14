// Pure reads of the trace for the agent rail. Every rail item is one parsed TraceEvent; nothing
// is added, merged or reworded here, so the rail can never show a step the stream did not carry.
import type { TourStop, TraceEvent } from "../contracts";
import type { AgentFile } from "../evidence/FilesTree";
import { optionPlain, pointsSentence } from "../evidence/match";
import { placeLine } from "../evidence/read";
import type { EvidencePhoto } from "../evidence/types";

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

/** One step in one plain line, for a closed row and the phone sheet. Only the event's own words,
 *  with a search option put in a renter's words (evidence/match optionPlain). */
export function plainLine(e: TraceEvent): string {
  const kind: string = e.kind;
  if (kind === "choice" && e.pick) return `Picked: ${optionPlain(e.pick)}`;
  if (kind === "file" && e.pick) return `Saved ${e.pick}`;
  return lastLine(e);
}

const lower = (s?: string | null) => (s ?? "").trim().toLowerCase();

/**
 * The agent step behind a walk stop, as the step's seq. Outside is the record agent's first step,
 * a stop with an ad photo is the place agent's search that placed that photo, and every other
 * stop is the walk agent's step (the one that names this room, else its first). Read only from
 * the trace, the stop and the photo's evidence row. Null when the trace is empty.
 */
export function stepForStop(
  items: RailItem[],
  stop: TourStop,
  photo: EvidencePhoto | null = null,
): number | null {
  if (items.length === 0) return null;
  const lane = (name: string) => {
    const own = items.filter((i) => i.agent === name);
    return own.length > 0 ? own : items;
  };
  const kindIs = (i: RailItem, kind: string) => (i.event.kind as string) === kind;
  if (stop.kind === "arrive") return lane("record")[0]!.event.seq;
  if (stop.kind === "outro") return items.at(-1)!.event.seq;
  if (stop.photos.length > 0) {
    const pool = lane("place");
    const won = [...(photo?.searches ?? [])]
      .reverse()
      .find((s) => s.result === "placed" || s.result === "elsewhere");
    const picked =
      photo && won
        ? pool.find((i) => kindIs(i, "choice") && i.event.pick === won.option)
        : undefined;
    const named = photo ? pool.find((i) => i.alias === photo.alias) : undefined;
    const base = pool.find((i) => kindIs(i, "tool"));
    return (picked ?? (won?.option === "base" ? base : named) ?? named ?? base ?? pool[0]!).event
      .seq;
  }
  const pool = lane("walk");
  const names = [lower(stop.room_label), lower(stop.title)].filter(Boolean);
  const named = pool.find((i) => kindIs(i, "choice") && names.includes(lower(i.event.pick)));
  return (named ?? pool[0]!).event.seq;
}

export const NO_PHOTO_LINE = "The ad showed no photo of this room.";

/**
 * What the lit step means at this stop, in one plain sentence: the matched points of the ad photo
 * placed here against the bar, or that the ad showed no photo of this room. Every number is the
 * evidence file's own. Null when there is nothing to add for this stop.
 */
export function stopLine(
  stop: TourStop,
  photo: EvidencePhoto | null,
  bars: Record<string, number>,
): string | null {
  if (stop.photos.length > 0)
    return photo
      ? `Ad photo ${photo.alias}: ${pointsSentence(photo, bars) ?? placeLine(photo)}`
      : null;
  if (stop.ad_view === "none_placed" && (stop.kind === "room" || stop.kind === "stop"))
    return NO_PHOTO_LINE;
  return null;
}
