// "See how it worked": one card per member, from what the API already sent. When the deep agent
// ran, a card is the member's own trace (GET /cases/{id}/timeline `members`): what it was
// asked, the tools it called in order, what it said back, its time and model calls. When no
// model ran a member, its card says so and lists what code checked, from the timeline's steps.
// Pure functions. Nothing here works out a result, and nothing is invented: a card with no
// trace behind it shows only the desk's recorded steps.
import type { CardTone, CaseTimeline, MemberTrace, TimelineTodo } from "../contracts";
import type { Finding } from "../case/answer";
import type { Desk, DeskState, Roster, TeamView } from "./model";

export interface TraceStep {
  label: string;
  result: string | null;
  tool: string | null; // the tool's own name when a model called one
}

export interface TraceCard {
  deskId: string;
  name: string;
  role: string;
  model: string; // "code", or the model's name
  byModel: boolean;
  state: DeskState;
  tone: CardTone | "none";
  asked: string | null;
  steps: TraceStep[];
  said: string | null;
  findings: Finding[];
  tookMs: number | null;
  modelCalls: number | null; // null when code ran it: there were none to count
  // The Planner's own: its to-do list as last written, and who it handed work to.
  todos: TimelineTodo[];
  sentTo: string[];
}

const deskIdOf = (roster: Roster, kind: string): string | null =>
  kind === "planner"
    ? (roster.agents.find((a) => a.team === "planner")?.id ?? null)
    : (roster.agents.find((a) => a.kinds.includes(kind))?.id ?? null);

/** The cards in the order the team shows: the Planner, the members as they acted, the Decider. */
export function traceCards(
  roster: Roster,
  team: TeamView,
  timeline: CaseTimeline | null,
): TraceCard[] {
  if (!timeline) return [];
  const traces = new Map<string, MemberTrace>();
  for (const m of timeline.members ?? []) {
    const id = deskIdOf(roster, m.kind);
    if (id && !traces.has(id)) traces.set(id, m);
  }
  const nameOf = (kind: string) => {
    const id = deskIdOf(roster, kind);
    return roster.agents.find((a) => a.id === id)?.name ?? kind;
  };
  return team.shown.map((desk: Desk): TraceCard => {
    const trace = traces.get(desk.card.id);
    const planner = desk.card.team === "planner";
    const base = {
      deskId: desk.card.id,
      name: desk.card.name,
      role: desk.card.role,
      state: desk.state,
      tone: desk.tone,
      findings: desk.findings,
      todos: planner ? timeline.todos : [],
      sentTo: planner ? [...new Set(timeline.plan)].map(nameOf) : [],
    };
    if (trace) {
      return {
        ...base,
        model: trace.model,
        byModel: trace.model !== "code",
        asked: trace.asked ?? null,
        steps: trace.tools.map((t) => ({ label: t.label, result: t.result, tool: t.tool })),
        said: trace.said ?? null,
        tookMs: trace.took_ms ?? null,
        modelCalls: trace.model_calls,
      };
    }
    // No model ran this member: code checked it. Its steps are the timeline's own labels.
    return {
      ...base,
      model: "code",
      byModel: false,
      asked: null,
      steps: desk.evidence.map((label) => ({ label, result: null, tool: null })),
      said: null,
      tookMs: desk.tookMs,
      modelCalls: null,
    };
  });
}

/** How many things a replay reveals, one at a time: each card, then each of its steps. */
export function traceLength(cards: TraceCard[]): number {
  return cards.reduce((n, c) => n + 1 + c.steps.length, 0);
}

/** For a replay at position `at`: is this card (step -1) or this step of it on show yet? */
export function revealed(cards: TraceCard[], card: number, step: number, at: number): boolean {
  let before = 0;
  for (let i = 0; i < card; i++) before += 1 + cards[i]!.steps.length;
  return before + 1 + step < at;
}

/** A LangSmith address is shown only if it is a plain https page there: no query, no fragment. */
export function safeTraceUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    const host = u.hostname;
    const ok =
      u.protocol === "https:" &&
      (host === "smith.langchain.com" || host.endsWith(".smith.langchain.com")) &&
      !u.search &&
      !u.hash &&
      !u.username &&
      !u.password &&
      !/(lsv2_|sk-)/i.test(u.pathname); // a key pasted into the path is still a key
    return ok ? url : null;
  } catch {
    return null;
  }
}
