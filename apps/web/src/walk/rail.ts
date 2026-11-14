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
/** A live run names its agents as hand-offs: "sub-agent: place", "sub-agent done: place". */
const SUB_AGENT = /^sub-agent(?: done)?:\s*(.+)$/i;

/** The agent an "agent" event hands to, in the rail's own short names. */
export function agentName(pick: string): string {
  return (SUB_AGENT.exec(pick.trim())?.[1] ?? pick).trim();
}

export function railItems(events: TraceEvent[]): RailItem[] {
  let agent = MAIN_AGENT;
  return [...events]
    .sort((a, b) => a.seq - b.seq)
    .map((event) => {
      if (kindOf(event) === "agent" && event.pick) agent = agentName(event.pick);
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
 * a stop with an ad photo is the step that placed that photo, and every other stop is the step
 * that names its room. Recorded and live traces differ: a recorded run names agents and photos
 * (P1, P2) and room picks, a live run hands to sub-agents and names photos only in counts. So
 * each stop matches by the photo's alias or id, then the room's label, and falls back on the
 * step of the same kind of work (locating photos, picking the floor plan whose rooms are walked,
 * the verdict at the end). Read only from the trace, the stop and the photo's evidence row. Null
 * when the trace is empty.
 */
export function stepForStop(
  items: RailItem[],
  stop: TourStop,
  photo: EvidencePhoto | null = null,
): number | null {
  if (items.length === 0) return null;
  const own = (name: string) => items.filter((i) => i.agent === name);
  const kindIs = (i: RailItem, kind: string) => (i.event.kind as string) === kind;
  const words = (i: RailItem) => `${i.event.pick ?? ""} ${i.event.reason}`;
  const says = (i: RailItem, token: string) =>
    new RegExp(`(^|[^\\w])${token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^\\w]|$)`, "i").test(
      words(i),
    );
  const locating = (i: RailItem) => kindIs(i, "tool") && /locat|plac/i.test(words(i));
  const floorPlan = (i: RailItem) =>
    kindIs(i, "choice") && (i.event.choice === "which_floor_plan" || /floor plan/i.test(words(i)));
  const seq = (i: RailItem | undefined) => i?.event.seq ?? null;

  if (stop.kind === "arrive") {
    const record = own("record");
    return (
      seq(record[0]) ??
      seq(items.find((i) => kindIs(i, "choice") && /record/i.test(words(i)))) ??
      items[0]!.event.seq
    );
  }
  if (stop.kind === "outro")
    return seq([...items].reverse().find((i) => kindIs(i, "verdict"))) ?? items.at(-1)!.event.seq;

  if (stop.photos.length > 0) {
    const place = own("place");
    const pool = place.length > 0 ? place : items;
    const won = [...(photo?.searches ?? [])]
      .reverse()
      .find((s) => s.result === "placed" || s.result === "elsewhere");
    const picked =
      photo && won
        ? pool.find((i) => kindIs(i, "choice") && i.event.pick === won.option)
        : undefined;
    const tokens = [photo?.alias, ...stop.photos.flatMap((p) => [p.alias, p.photo_id])].filter(
      (t): t is string => Boolean(t),
    );
    const named =
      pool.find((i) => tokens.some((t) => i.alias === t || says(i, t))) ??
      items.find((i) => tokens.some((t) => i.alias === t || says(i, t)));
    const base = pool.find(locating) ?? items.find(locating);
    const exact = picked ?? (won?.option === "base" ? base : undefined) ?? named;
    if (exact) return exact.event.seq;
    // Nothing names this photo (a live run counts photos, it does not name them): spread the
    // photo stops over the steps that placed photos, in the photo's own order (P1, P2, ...), so
    // the lit step moves with the walk and is always one about placing the ad's photos.
    const placing = [
      ...new Set([base, items.find(floorPlan), ...place].filter((i): i is RailItem => Boolean(i))),
    ];
    const n = Number(/\d+/.exec(photo?.alias ?? stop.photos[0]?.alias ?? "")?.[0] ?? 1);
    return seq(placing[(Math.max(n, 1) - 1) % Math.max(placing.length, 1)] ?? pool[0]);
  }

  const walk = own("walk");
  const pool = walk.length > 0 ? walk : items;
  const names = [lower(stop.room_label), lower(stop.title)].filter(Boolean);
  const named =
    pool.find((i) => kindIs(i, "choice") && names.includes(lower(i.event.pick))) ??
    items.find((i) => names.some((n) => n.length > 3 && says(i, n)));
  if (named) return named.event.seq;
  if (walk.length > 0) return walk[0]!.event.seq;
  // A live run has no walk agent: the rooms walked are the floor plan the agent picked.
  return seq(items.find(floorPlan)) ?? seq(items.find(locating)) ?? items[0]!.event.seq;
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
