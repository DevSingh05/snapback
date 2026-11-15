// Where the words go on the crew's stage, in stage units (crew.VIEW), so nothing ever sits on
// anything else: two speech slots in the sky, the stamp beside the Decider's desk, the bench's
// line in the near left corner, and one name tag per member. Every box has a fixed size here
// and the scene draws it at exactly that size (its type scales with the stage), so what is
// true of these boxes is true on screen at every width. Pure: no clock, no DOM.
import { project } from "../draw/kit";
import { HOME, ORIGIN, VIEW, type CrewActor } from "./crew";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** The two speech slots, over the sky. A bubble is never taller than its slot. */
export const SLOTS: Record<"left" | "right", Box> = {
  left: { x: 8, y: 12, w: 256, h: 124 },
  right: { x: VIEW.w - 8 - 256, y: 12, w: 256, h: 124 },
};
/** The Decider's stamp, in the near right corner beside the desk. */
export const STAMP: Box = { x: VIEW.w - 8 - 236, y: VIEW.h - 8 - 96, w: 236, h: 96 };
/** The bench's line, under the bench in the near left corner. */
export const BENCH_LINE: Box = { x: 6, y: VIEW.h - 6 - 46, w: 200, h: 46 };
const BENCH: Box = { x: 0, y: VIEW.h - 126, w: 132, h: 126 };
/** The home in the ad: nothing is written over it. */
export const HOME_BOX: Box = (() => {
  const at = (x: number, y: number, z: number) => project([x, y, z], ORIGIN);
  const left = at(HOME.x, HOME.y + HOME.d, 0)[0];
  const right = at(HOME.x + HOME.w, HOME.y, 0)[0];
  const top = at(HOME.x, HOME.y, HOME.h * 1.7)[1];
  const bottom = at(HOME.x + HOME.w, HOME.y + HOME.d, 0)[1];
  return { x: left - 2, y: top, w: right - left + 4, h: bottom - top + 2 };
})();

const GAP = 3;
// Type sizes in stage units (crew.css sets the same in cqw) and how wide a letter runs at most.
const NAME_CH = 9.1;
const MODEL_CH = 7.6;
// The state chip's line is held wide enough for its longest word, so a tag never changes size.
const CHIP_W = 92;
// A long name breaks into two lines rather than making a wide tag.
const NAME_MAX = 12;

/** A member's name as the one or two lines its tag shows. */
export function nameLines(name: string): string[] {
  if (name.length <= NAME_MAX || !name.includes(" ")) return [name];
  const words = name.split(" ");
  let best = [name];
  let bestWide = Infinity;
  for (let i = 1; i < words.length; i++) {
    const pair = [words.slice(0, i).join(" "), words.slice(i).join(" ")];
    const wide = Math.max(pair[0]!.length, pair[1]!.length);
    if (wide < bestWide) [best, bestWide] = [pair, wide];
  }
  return best;
}

/** How big a member's tag is: badge and name (one or two lines), what runs it, and its state
 *  in a word, each on its own line. */
export function tagSize(name: string, model: string): { w: number; h: number } {
  const lines = nameLines(name);
  const top = 22 + 5 + Math.max(...lines.map((l) => l.length)) * NAME_CH;
  return {
    w: Math.ceil(Math.max(top, model.length * MODEL_CH, model ? CHIP_W : 0) + 14),
    h: 66 + (lines.length - 1) * 17,
  };
}

const hit = (a: Box, b: Box, pad = 0) =>
  a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad;

/** The room a member's figure takes on the stage. */
export function figureBox(a: CrewActor): Box {
  const k = a.scale;
  return a.place === "desk"
    ? { x: a.sx - 30, y: a.sy - 66, w: 68, h: 90 }
    : { x: a.sx - 18 * k, y: a.sy - 68 * k, w: 36 * k, h: 78 * k };
}

export interface TagLabel {
  name: string;
  model: string;
}

/** A tag for every member on stage (not the bench), each clear of the speech slots, the stamp,
 *  the bench, every figure and every other tag. A tag touches its member's figure: over the
 *  head, under the feet or to a side, whichever free place is nearest the head. The answer
 *  depends only on who is on stage, so a tag never moves while a run plays. */
export function tagLayout(cast: CrewActor[], labels: Map<string, TagLabel>): Map<string, Box> {
  const staged = cast.filter((a) => a.place !== "bench");
  const fixed: Box[] = [SLOTS.left, SLOTS.right, STAMP, BENCH, BENCH_LINE, HOME_BOX];
  const figures = staged.map(figureBox);
  // Every place a member's tag could go, best first.
  const places = new Map<string, Box[]>();
  for (const a of staged) {
    const label = labels.get(a.id) ?? { name: a.card.name, model: "code" };
    // Waiting at the edge for a turn: the name is enough until it steps in.
    const { w, h } =
      a.place === "wing"
        ? { w: tagSize(label.name, "").w, h: 30 + (nameLines(label.name).length - 1) * 17 }
        : tagSize(label.name, label.model);
    const f = figureBox(a);
    const away = a.side === "left" ? -1 : 1; // which way is away from the home
    const head = { x: f.x + f.w / 2, y: f.y + 14 };
    const tries: Box[] = [];
    for (const far of [0, 12, 24, 36]) {
      for (let dx = -w; dx <= f.w; dx += 6) {
        tries.push({ x: f.x + dx, y: f.y - GAP - far - h, w, h });
        tries.push({ x: f.x + dx, y: f.y + f.h + GAP + far, w, h });
      }
      for (let dy = -h; dy <= f.h; dy += 6) {
        tries.push({ x: f.x - GAP - far - w, y: f.y + dy, w, h });
        tries.push({ x: f.x + f.w + GAP + far, y: f.y + dy, w, h });
      }
    }
    const cost = (b: Box) =>
      Math.hypot(b.x + b.w / 2 - head.x, (b.y + b.h / 2 - head.y) * 1.15) -
      (Math.sign(b.x + b.w / 2 - head.x) === away ? 6 : 0);
    places.set(
      a.id,
      tries
        .map((b) => ({ ...b, x: Math.round(b.x), y: Math.round(b.y) }))
        .filter((b) => b.x >= 3 && b.y >= 3 && b.x + w <= VIEW.w - 3 && b.y + h <= VIEW.h - 3)
        .filter((b) => !fixed.some((o) => hit(b, o, 2)) && !figures.some((o) => hit(b, o)))
        .sort((p, q) => cost(p) - cost(q)),
    );
  }
  // Search for a place for everyone: the member with the fewest free places chooses first,
  // each takes its best free place, and the search steps back when someone is left with
  // none. It is bounded, and it is the same search every time.
  const order = [...staged].sort(
    (p, q) => (places.get(p.id)?.length ?? 0) - (places.get(q.id)?.length ?? 0),
  );
  const chosen: Box[] = [];
  let budget = 60_000;
  const search = (i: number): boolean => {
    if (i === order.length) return true;
    for (const b of places.get(order[i]!.id) ?? []) {
      if (budget-- <= 0) return false;
      if (chosen.some((o) => hit(b, o, GAP))) continue;
      chosen.push(b);
      if (search(i + 1)) return true;
      chosen.pop();
    }
    return false;
  };
  const out = new Map<string, Box>();
  if (search(0)) {
    order.forEach((a, i) => out.set(a.id, chosen[i]!));
    return out;
  }
  // No clean answer (a stage more crowded than any run gives): each takes its best place.
  for (const a of staged) {
    const all = places.get(a.id) ?? [];
    const free = all.find((b) => ![...out.values()].some((o) => hit(b, o, GAP)));
    out.set(a.id, free ?? all[0] ?? { x: 3, y: 3, ...tagSize(a.card.name, "code") });
  }
  return out;
}

/** Every pair of boxes that touch: none, when the layout is right. */
export function collisions(boxes: [string, Box][]): [string, string][] {
  const out: [string, string][] = [];
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++)
      if (hit(boxes[i]![1], boxes[j]![1])) out.push([boxes[i]![0], boxes[j]![0]]);
  return out;
}
