// The crew scene, worked out from the floor (model.floorAt): who each member is as a character,
// where it stands around the home, which notes pass between them and what each one says. Pure
// functions, no clock and no DOM. Nothing here works out a result: a note flies only because a
// recorded step changed a member's state, a bubble holds the roster's or the card's own words,
// and the stamp follows floor.verdict, which is held until the fresh card is in.
import { project } from "../draw/kit";
import type { CardTone } from "../contracts";
import type { AgentCard, Desk, DeskState, Floor, TeamView } from "./model";

// Who each member is. One character, one prop, one colour, everywhere the member shows.
export type Persona =
  | "foreman" // Planner: hard hat and clipboard
  | "inspector" // Rules: magnifier
  | "photographer" // Photo: camera
  | "clerk" // Record: records cabinet
  | "operator" // Phone and office: headset
  | "registrar" // Owner and licence: stamp book
  | "scout" // Web: laptop
  | "searcher" // Finder: map
  | "guide" // Tour prep: route flag
  | "judge" // Decider: desk and stamp
  | "helper"; // anyone the roster adds later

const PERSONAS: Record<string, Persona> = {
  planner: "foreman",
  rules: "inspector",
  photo: "photographer",
  record: "clerk",
  phone_office: "operator",
  owner_licence: "registrar",
  web: "scout",
  finder: "searcher",
  tour_prep: "guide",
  decider: "judge",
};

export const hasPersona = (id: string) => id in PERSONAS;
export const personaOf = (id: string): Persona => PERSONAS[id] ?? "helper";

// The stage, in SVG user units. The plot is a square lawn seen in the drawing kit's isometric
// view; scene point (0, 0) is its far corner.
// The stage is wider than the plot: speech sits in the sky over the two back corners, and the
// neighbours' street shows behind.
export const VIEW = { w: 640, h: 546 };
export const ORIGIN = { ox: 320, oy: 238 };
export const PLOT = 220;
const INSET = 20;
// The home in the ad, in the middle of the plot.
export const HOME = { x: 78, y: 84, w: 64, d: 50, h: 26 };

// lead: the Planner. ring: round the home. desk: the Decider. wing: waiting at the edge for a
// turn, when more members are in the run than the ring holds. bench: not needed for this ad.
export type Place = "lead" | "ring" | "desk" | "wing" | "bench";
// The ring holds three members a side: more would stand on each other's name tags.
export const RING_MAX = 6;

export interface CrewActor {
  id: string;
  persona: Persona;
  card: AgentCard;
  desk: Desk | null; // null on the bench
  state: DeskState;
  tone: CardTone | "none";
  place: Place;
  side: "left" | "right" | "mid";
  // Where its feet are, in stage units, and how big it is drawn.
  sx: number;
  sy: number;
  scale: number;
  // Far to near: the order to draw in.
  depth: number;
}

const r1 = (v: number) => Math.round(v * 10) / 10;

function onStage(x: number, y: number): { sx: number; sy: number; depth: number } {
  const [sx, sy] = project([x, y, 0], ORIGIN);
  return { sx: r1(sx), sy: r1(sy), depth: x + y };
}

/** A point `t` (0..1) of the way round one side of the plot, from the far corner to the near. */
function along(side: "left" | "right", t: number): [number, number] {
  const a = INSET;
  const b = PLOT - INSET;
  const corner: [number, number] = side === "left" ? [a, b] : [b, a];
  const leg = (from: [number, number], to: [number, number], f: number): [number, number] => [
    from[0] + (to[0] - from[0]) * f,
    from[1] + (to[1] - from[1]) * f,
  ];
  return t <= 0.5 ? leg([a, a], corner, t * 2) : leg(corner, [b, b], (t - 0.5) * 2);
}

/** Everyone in the scene. The Planner leads from the far corner, the Decider sits at its desk
 *  in front, the members this run needed stand round the home (the roster's order, so nobody
 *  changes place as the run plays), and the ones it did not need sit on the bench at the edge. */
export function crewCast(floor: Floor, team: TeamView): CrewActor[] {
  const benched = new Set(team.notNeeded.map((a) => a.id));
  const everyone = floor.desks.filter(
    (d) => d.card.team !== "planner" && d.card.team !== "decider" && !benched.has(d.card.id),
  );
  const members = everyone.slice(0, RING_MAX);
  const wing = everyone.slice(RING_MAX);
  const leftN = Math.ceil(members.length / 2);
  const cast: CrewActor[] = [];
  const base = (d: Desk) => ({
    id: d.card.id,
    persona: personaOf(d.card.id),
    card: d.card,
    desk: d,
    state: d.state,
    tone: d.tone,
  });
  for (const d of floor.desks) {
    if (benched.has(d.card.id)) continue;
    if (d.card.team === "planner") {
      cast.push({ ...base(d), place: "lead", side: "mid", scale: 1, ...onStage(12, 12) });
    } else if (d.card.team === "decider") {
      cast.push({
        ...base(d),
        place: "desk",
        side: "mid",
        scale: 1,
        ...onStage(PLOT - 14, PLOT - 14),
      });
    } else if (wing.includes(d)) {
      const k = wing.indexOf(d);
      cast.push({
        ...base(d),
        place: "wing",
        side: "right",
        // In the right gutter, under the plot's side corner and over the stamp.
        sx: VIEW.w - 20 - k * 27,
        sy: VIEW.h - 150,
        scale: 0.72,
        depth: 9_000 + k,
      });
    } else {
      const i = members.indexOf(d);
      const left = i < leftN;
      const n = left ? leftN : members.length - leftN;
      const k = left ? i : i - leftN;
      const [x, y] = along(left ? "left" : "right", (k + 1) / (n + 1));
      cast.push({
        ...base(d),
        place: "ring",
        side: left ? "left" : "right",
        scale: 1,
        ...onStage(x, y),
      });
    }
  }
  // The bench: one row in the near left corner of the stage, outside the plot.
  const gap = Math.min(27, 96 / Math.max(1, team.notNeeded.length - 1));
  team.notNeeded.forEach((card, i) => {
    cast.push({
      id: card.id,
      persona: personaOf(card.id),
      card,
      desk: null,
      state: "unused",
      tone: "none",
      place: "bench",
      side: "left",
      sx: r1(18 + i * gap),
      sy: VIEW.h - 64,
      scale: 0.72,
      depth: 10_000 + i,
    });
  });
  return cast.sort((a, b) => a.depth - b.depth);
}

// ---------- notes ----------

export type CrewAction =
  | { kind: "brief"; to: string } // the Planner hands a member its note
  | { kind: "report"; from: string; flag: boolean } // the member sends its note to the Decider
  | { kind: "stamp" }; // the Decider stamps the verdict

/** What happened between two looks at the floor. Only a member whose recorded state moved
 *  forward gets a note; the first look, a restart and an unchanged floor give nothing. */
export function crewActions(before: Floor | null, now: Floor): CrewAction[] {
  if (!before) return [];
  const was = new Map(before.desks.map((d) => [d.card.id, d.state]));
  const out: CrewAction[] = [];
  for (const d of now.desks) {
    if (d.card.team === "planner" || d.card.team === "decider") continue;
    const prev = was.get(d.card.id);
    if (prev === undefined || prev === d.state) continue;
    if (prev === "idle" && (d.state === "working" || d.state === "done"))
      out.push({ kind: "brief", to: d.card.id });
    if ((prev === "idle" || prev === "working") && d.state === "done")
      out.push({ kind: "report", from: d.card.id, flag: d.tone === "red_flag" });
  }
  if (!before.verdict && now.verdict && before.phase !== "rest") out.push({ kind: "stamp" });
  return out;
}

/** The notes on the Decider's desk: one for each member that has reported, red tagged for a
 *  red flag. */
export function reported(floor: Floor): { id: string; flag: boolean }[] {
  return floor.desks
    .filter((d) => d.state === "done" && d.card.team !== "planner" && d.card.team !== "decider")
    .sort((a, b) => a.order - b.order)
    .map((d) => ({ id: d.card.id, flag: d.tone === "red_flag" }));
}

// ---------- speech ----------

// Three lines of a bubble at its reading size.
export const SAY_MAX = 54;

/** A line short enough for a speech bubble, cut at a word. */
export function shortSay(text: string, max = SAY_MAX): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max + 1);
  const at = cut.lastIndexOf(" ");
  return `${(at > max * 0.5 ? cut.slice(0, at) : clean.slice(0, max)).replace(/[\s.,;:·]+$/, "")}…`;
}

export interface CrewBubble {
  deskId: string;
  text: string;
  tone: CardTone | "none";
  // working: what the member is doing (the roster's words). finding: what it found (the
  // card's words). said: a step the Planner made happen (the timeline's label).
  kind: "working" | "finding" | "said";
}

export const BUBBLES_MAX = 2;

export type BubbleSlot = "left" | "right";

/** Where each bubble sits: one of two fixed slots in the sky, over the back corners of the
 *  plot, so speech is large and never covers a member. A bubble takes the slot on its
 *  speaker's side when it is free (the newest speaker chooses first); the Planner, in the
 *  middle, takes the right. */
export function bubbleSlots(bubbles: CrewBubble[], cast: CrewActor[]): BubbleSlot[] {
  const taken = new Set<BubbleSlot>();
  return bubbles.map((b) => {
    const side = cast.find((a) => a.id === b.deskId)?.side;
    const want: BubbleSlot = side === "left" ? "left" : "right";
    const slot = taken.has(want) ? (want === "left" ? "right" : "left") : want;
    taken.add(slot);
    return slot;
  });
}

/** Who is speaking now, newest first. A member at work says what it is doing; a member that
 *  is done says its finding. Once the run is over a red flag speaks first. The Decider never
 *  speaks a verdict here: that is the stamp. */
export function crewBubbles(floor: Floor, cast: CrewActor[], max = BUBBLES_MAX): CrewBubble[] {
  if (floor.phase === "rest") return [];
  const staged = new Set(cast.filter((a) => a.place !== "bench").map((a) => a.id));
  const deskOf = new Map(floor.desks.map((d) => [d.card.id, d]));
  const out: CrewBubble[] = [];
  const add = (b: CrewBubble) => {
    if (!staged.has(b.deskId) || out.some((o) => o.deskId === b.deskId)) return;
    out.push({ ...b, text: shortSay(b.text) });
  };
  const finding = (d: Desk): CrewBubble | null => {
    const f = d.findings[0];
    if (!f) return null;
    return {
      deskId: d.card.id,
      text: f.label ? `${f.label}: ${f.text}` : f.text,
      tone: d.tone,
      kind: "finding",
    };
  };
  const doing = (d: Desk): CrewBubble => ({
    deskId: d.card.id,
    text: d.card.doing,
    tone: "none",
    kind: "working",
  });
  if (floor.phase === "done")
    for (const d of floor.desks) {
      const f = d.state === "done" && d.tone === "red_flag" ? finding(d) : null;
      if (f) add(f);
    }
  // Members at work come first, the newest to start first.
  const working = floor.desks
    .filter((d) => d.state === "working" && !d.byCode)
    .sort((a, b) => (b.startedAt ?? 0) - (a.startedAt ?? 0));
  for (const d of working) {
    if (d.card.team !== "planner") add(doing(d));
  }
  for (let i = floor.log.length - 1; i >= 0; i--) {
    const line = floor.log[i]!;
    const d = line.deskId ? deskOf.get(line.deskId) : null;
    if (!d || d.card.team === "decider") continue;
    if (line.finding) {
      const f = finding(d);
      if (f) add(f);
    } else if (d.card.team === "planner" && !d.byCode && floor.phase === "running") {
      add({ deskId: d.card.id, text: line.text, tone: "none", kind: "said" });
    }
  }
  return out.slice(0, max);
}
