// The Proof Room's floor, worked out from what the API already sent: the roster (GET /agents),
// the case's card, its timeline and the real-listing read. Pure functions, no fetch, no clock.
//
// Findings come from the report's own mapping (case/answer.ts): a desk shows what the card and
// the real listing already say for its checks. The timeline gives the order, the timing and
// the LIVE or FIXTURE source. Nothing here works out a result: the Decider's words are the
// card's headline and the card's reasons, and they show only once every step has played.
//
// A replay walks the recorded steps on a play clock. A step shorter than MIN_BEAT is held that
// long so a person can read it; the time printed on a desk is always the recorded one.
import type { Card, CardTone, CaseTimeline, DataSource, RealListing } from "../contracts";
import { answerView, type AnswerView, type CheckId, type Finding } from "../case/answer";
import rosterJson from "./roster.json";

export type TeamId = "planner" | "scam_check" | "listing_help" | "decider";

export interface AgentCard {
  id: string;
  name: string;
  team: TeamId;
  job: string;
  doing: string;
  tools: string[];
  model: "Claude Sonnet" | "Claude Haiku" | "code";
  never: string[];
  availability?: string | null;
  kinds: string[];
  checks: string[];
}

export interface TeamInfo {
  id: TeamId;
  name: string;
  about: string;
}

export interface Roster {
  lang: "en" | "es";
  teams: TeamInfo[];
  agents: AgentCard[];
}

export type Lang = "en" | "es";

/** The roster the app ships, for the front end that has no API. Written from roster.py. */
export function bundledRoster(lang: string): Roster {
  return (rosterJson as unknown as Record<Lang, Roster>)[lang === "es" ? "es" : "en"];
}

/** A roster read from GET /agents, or null when the body is not one. */
export function asRoster(body: unknown): Roster | null {
  const r = body as Partial<Roster> | null;
  if (!r || !Array.isArray(r.agents) || !Array.isArray(r.teams) || r.agents.length === 0)
    return null;
  const ok = r.agents.every(
    (a) =>
      typeof a?.id === "string" &&
      typeof a.name === "string" &&
      Array.isArray(a.kinds) &&
      Array.isArray(a.tools) &&
      Array.isArray(a.never),
  );
  return ok ? (r as Roster) : null;
}

// idle: nothing has reached this desk yet. working: one of its steps is under way.
// done: its steps ran. skipped: the plan left its check out, and says why.
// unused: the run is over and nothing ever reached this desk.
export type DeskState = "idle" | "working" | "done" | "skipped" | "unused";

export interface Desk {
  card: AgentCard;
  state: DeskState;
  tone: CardTone | "none";
  findings: Finding[];
  // What the desk did, as the timeline's own plain labels (counts only). The evidence line.
  evidence: string[];
  // Why the plan left it out (skipped), in the timeline's or the card's own words.
  why: string | null;
  source: DataSource | null;
  tookMs: number | null; // recorded time over its steps; null when it has none
  startedAt: number | null; // play clock, when work first reached this desk
}

export interface LogLine {
  step: number;
  deskId: string | null; // null: SNAPBACK itself (reading the ad, a wait, the result)
  who: string;
  text: string;
  source: DataSource;
  by: "agent" | "code";
  tookMs: number;
  skipped: boolean;
  // Set on a finding line: what the desk found, with the card's own tone for it.
  finding?: boolean;
  tone?: CardTone | "none";
}

export interface FloorReason {
  text: string;
  deskId: string | null;
}

export interface Floor {
  phase: "rest" | "running" | "done";
  desks: Desk[];
  log: LogLine[];
  checksDone: number;
  checksTotal: number;
  redFlags: number; // desks whose finding is a red flag
  nowDeskId: string | null; // the desk the status line names
  progress: number; // 0..1
  // The card's headline and reasons, once every step has played. Never worked out here.
  verdict: { headline: string; reasons: FloorReason[] } | null;
  fellBack: boolean;
  source: DataSource | null;
}

export const MIN_BEAT = 900;

export interface Beat {
  start: number; // play clock, ms
  end: number;
}

/** When each recorded step plays. Steps keep their order and their real gaps; a gap shorter
 *  than `minBeat` is held that long. `end` is the step's own length, held the same way. */
export function schedule(timeline: CaseTimeline, minBeat = MIN_BEAT): Beat[] {
  const steps = timeline.steps;
  const beats: Beat[] = [];
  let at = 0;
  steps.forEach((step, i) => {
    const next = steps[i + 1];
    const gap = next ? Math.max(0, next.started_ms - step.started_ms) : step.took_ms;
    beats.push({ start: at, end: at + Math.max(step.took_ms, minBeat) });
    at += Math.max(gap, minBeat);
  });
  return beats;
}

/** How long the whole replay runs on the play clock. */
export function runLength(beats: Beat[]): number {
  return beats.reduce((max, b) => Math.max(max, b.end), 0);
}

const TONE_RANK: Record<CardTone | "none", number> = {
  red_flag: 0,
  hold: 1,
  not_shown: 1,
  ok: 2,
  not_checked: 3,
  none: 3,
};

function deskOfKind(roster: Roster, kind: string | null | undefined): AgentCard | null {
  if (!kind) return null;
  return roster.agents.find((a) => a.kinds.includes(kind)) ?? null;
}

/** The desk that answers for one of the report's checks. */
export function deskOfCheck(roster: Roster, check: CheckId | string): AgentCard | null {
  return roster.agents.find((a) => a.checks.includes(check)) ?? null;
}

const restDesk = (card: AgentCard): Desk => ({
  card,
  state: "idle",
  tone: "none",
  findings: [],
  evidence: [],
  why: null,
  source: null,
  tookMs: null,
  startedAt: null,
});

export interface FloorInput {
  roster: Roster;
  card: Card | null;
  timeline: CaseTimeline | null;
  listing?: RealListing | null;
  // The play clock in ms. Infinity (the default) is the whole run.
  at?: number;
  snapback?: string; // who speaks for a step that is nobody's desk
}

/** The floor at one moment of the run. With no timeline it is the roster at rest. */
export function floorAt({
  roster,
  card,
  timeline,
  listing = null,
  at = Infinity,
  snapback = "SNAPBACK",
}: FloorInput): Floor {
  const steps = timeline?.steps ?? [];
  if (!timeline || steps.length === 0) {
    return {
      phase: "rest",
      desks: roster.agents.map(restDesk),
      log: [],
      checksDone: 0,
      checksTotal: 0,
      redFlags: 0,
      nowDeskId: null,
      progress: 0,
      verdict: null,
      fellBack: false,
      source: null,
    };
  }
  const live = (timeline as CaseTimeline & { running?: boolean }).running === true;
  const beats = schedule(timeline);
  const length = runLength(beats);
  const over = !live && at >= length;
  const started = (i: number) => beats[i]!.start <= at;
  // On a live run the newest step is the one under way; on a replay, a step whose beat is open.
  const ended = (i: number) => (live ? i < steps.length - 1 : beats[i]!.end <= at);
  const view: AnswerView | null = card ? answerView(card, timeline, listing) : null;
  const planner = roster.agents.find((a) => a.team === "planner") ?? null;
  const decider = roster.agents.find((a) => a.team === "decider") ?? null;
  const deep = timeline.mode === "deepagents";

  const desks: Desk[] = roster.agents.map((agent) => {
    const desk = restDesk(agent);
    let mine = steps
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => agent.kinds.includes(s.kind ?? ""));
    if (agent.team === "planner") {
      // The planner has no check of its own: every step the model made happen is its work.
      mine = deep ? steps.map((s, i) => ({ s, i })).filter(({ s }) => s.by === "agent") : [];
    }
    const ran = mine.filter(({ s }) => !s.skipped);
    const skipped = mine.filter(({ s }) => s.skipped);
    const begun = ran.filter(({ i }) => started(i));
    const bubbles = (view?.bubbles ?? []).filter((b) => agent.checks.includes(b.check));
    const quiet = (view?.notChecked ?? []).filter((n) => agent.checks.includes(n.check));

    if (ran.length === 0) {
      if (skipped.length > 0 || quiet.length > 0) {
        // Skipped shows from the moment the plan said so (or at once when only the card says it).
        const first = skipped[0];
        if (!first || started(first.i)) {
          desk.state = "skipped";
          desk.why = quiet[0]?.text ?? first?.s.result ?? null;
          desk.source = first?.s.source ?? null;
        }
      } else if (agent.team === "decider") {
        desk.state = over ? "done" : "idle";
      } else if (over) {
        desk.state = "unused";
      }
      if (agent.team === "decider" && over) desk.source = card?.source ?? timeline.source;
      return desk;
    }
    if (begun.length === 0) return desk;
    desk.startedAt = beats[begun[0]!.i]!.start;
    desk.source = begun[0]!.s.source;
    const allIn = begun.length === ran.length && begun.every(({ i }) => ended(i));
    // The Decider is done only when the whole run is: its stamp is the last thing to land.
    if (!allIn || (agent.team === "decider" && !over)) {
      desk.state = "working";
      return desk;
    }
    desk.state = "done";
    desk.tookMs = ran.reduce((sum, { s }) => sum + s.took_ms, 0);
    desk.evidence = ran.map(({ s }) => s.label);
    desk.findings = bubbles.flatMap((b) => b.findings);
    desk.tone = bubbles.reduce<CardTone | "none">(
      (worst, b) => (TONE_RANK[b.tone] < TONE_RANK[worst] ? b.tone : worst),
      "none",
    );
    if (bubbles[0]) desk.source = bubbles[0].source;
    if (quiet.length > 0 && bubbles.length === 0) desk.why = quiet[0]!.text;
    return desk;
  });

  // The thread: each step as it starts, and a desk's findings the moment its last step is in.
  const log: LogLine[] = [];
  steps.forEach((s, i) => {
    if (!started(i)) return;
    const owner = deskOfKind(roster, s.kind) ?? (s.by === "agent" && deep ? planner : null);
    log.push({
      step: s.step,
      deskId: owner?.id ?? null,
      who: owner?.name ?? snapback,
      text: s.label,
      source: s.source,
      by: s.by,
      tookMs: s.took_ms,
      skipped: s.skipped === true,
    });
    const desk = owner ? desks.find((d) => d.card.id === owner.id) : null;
    if (!desk || desk.state !== "done" || desk.card.team === "planner") return;
    const last = steps.reduce(
      (at, t, j) => (!t.skipped && desk.card.kinds.includes(t.kind ?? "") ? j : at),
      -1,
    );
    if (last !== i) return;
    for (const f of desk.findings) {
      log.push({
        step: s.step,
        deskId: desk.card.id,
        who: desk.card.name,
        text: f.label ? `${f.label}: ${f.text}` : f.text,
        source: desk.source ?? s.source,
        by: "code",
        tookMs: 0,
        skipped: false,
        finding: true,
        tone: desk.tone,
      });
    }
  });

  // "Checks" are the scam-check desks this case reached; the status line counts those.
  const checkDesks = desks.filter(
    (d) =>
      d.card.team === "scam_check" &&
      steps.some((s) => !s.skipped && d.card.kinds.includes(s.kind ?? "")),
  );
  const working = desks.filter((d) => d.state === "working");
  const nowDesk =
    working.find((d) => d.card.team === "scam_check") ??
    working.find((d) => d.card.team !== "planner") ??
    working[0] ??
    null;

  const verdict =
    over && card
      ? {
          headline: view?.verdict ?? "",
          reasons: (view?.reasons ?? []).map((r) => ({
            text: r.text,
            deskId: r.bubbleId ? (deskOfCheck(roster, r.bubbleId)?.id ?? null) : null,
          })),
        }
      : null;
  if (over && decider && verdict) {
    log.push({
      step: steps.length,
      deskId: decider.id,
      who: decider.name,
      text: verdict.headline,
      source: card?.source ?? timeline.source,
      by: "code",
      tookMs: 0,
      skipped: false,
    });
  }

  return {
    phase: over ? "done" : "running",
    desks,
    log,
    checksDone: checkDesks.filter((d) => d.state === "done").length,
    checksTotal: checkDesks.length,
    redFlags: desks.filter((d) => d.state === "done" && d.tone === "red_flag").length,
    nowDeskId: over ? null : (nowDesk?.card.id ?? null),
    progress: over ? 1 : live ? 0.5 : length > 0 ? Math.min(1, Math.max(0, at / length)) : 0,
    verdict: verdict && verdict.headline ? verdict : null,
    fellBack: timeline.fell_back,
    source: timeline.source,
  };
}

export interface Words {
  rest: string;
  checks: (done: number, total: number) => string;
  setBy: (headline: string) => string;
  starting: string;
}

/** The one plain status line: "3 of 6 checks done · placing the photos in the 3D scan". */
export function statusLine(floor: Floor, w: Words): string {
  if (floor.phase === "rest") return w.rest;
  const count = w.checks(floor.checksDone, floor.checksTotal);
  if (floor.phase === "done")
    return floor.verdict ? `${count} · ${w.setBy(floor.verdict.headline)}` : count;
  const now = floor.desks.find((d) => d.card.id === floor.nowDeskId);
  const doing = now ? now.card.doing.charAt(0).toLowerCase() + now.card.doing.slice(1) : w.starting;
  return `${count} · ${doing}`;
}

/** The report's one-line summary: how many desks checked, and how many found a red flag. */
export function teamSummary(floor: Floor): { checked: number; redFlags: number } {
  return { checked: floor.checksDone, redFlags: floor.redFlags };
}
