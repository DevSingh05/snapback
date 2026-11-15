// The crew's characters, drawn with the app's drawing kit (draw/kit.ts) so they stand in the
// same isometric world as the house: same angle, same one light, same line work. Each persona
// has its own build, hat and prop, and wears the member's own colour (the `crew` tone, set by
// --crew on the group that holds it). No faces: a head, a hat and a silhouette.
//
// A figure is drawn round its feet at (0, 0); the scene moves it into place with one transform.
// `fwd` is toward the viewer, `side` is to the right of the screen, `z` is up.
import { makeScene, type P3, type Prim, type Tone } from "../draw/kit";
import type { Persona } from "./crew";

export interface Figure {
  back: Prim[]; // furniture behind the body
  body: Prim[]; // shadow, legs, torso, head, hat, arms
  prop: Prim[]; // what the member works with: the part that moves while it works
  fx: Prim[]; // a flash, a signal: shown only while it works
  front: Prim[]; // furniture in front of the body
}

const R = Math.SQRT1_2;
const s = makeScene({ ox: 0, oy: 0 });
/** A point on the figure. */
const P = (fwd: number, side: number, z: number): P3 => [(fwd + side) * R, (fwd - side) * R, z];
// The member's own colour, and the paper white of a note: tones this scene adds to the kit's.
const CREW = "crew" as Tone;
const PAPER = "paper" as Tone;

/** A box centred on a point of the figure. */
function box(tone: Tone, fwd: number, side: number, z: number, w: number, d: number, h: number) {
  const [x, y] = P(fwd, side, 0);
  return s.box(tone, x - w / 2, y - d / 2, z, w, d, h);
}

const limb = (a: P3, b: P3): Prim => s.line("cs-limb", a, b);
const ink = (a: P3, b: P3): Prim => s.line("cs-ink", a, b);

interface Build {
  wide: number; // torso footprint
  hips: number; // where the torso starts (a long coat or a robe starts lower)
  tall: number; // shoulder height
  head: number; // head radius
}

const BUILD: Record<Persona, Build> = {
  foreman: { wide: 13, hips: 22, tall: 41, head: 6.6 },
  inspector: { wide: 9.5, hips: 13, tall: 46, head: 6 },
  photographer: { wide: 10.5, hips: 23, tall: 42, head: 6.2 },
  clerk: { wide: 11.5, hips: 22, tall: 40, head: 6.4 },
  operator: { wide: 10, hips: 23, tall: 43, head: 6.2 },
  registrar: { wide: 12, hips: 16, tall: 42, head: 6.2 },
  scout: { wide: 10, hips: 23, tall: 41, head: 6.2 },
  searcher: { wide: 10.5, hips: 23, tall: 42, head: 6.2 },
  guide: { wide: 10, hips: 23, tall: 44, head: 6 },
  judge: { wide: 14, hips: 5, tall: 43, head: 6.6 },
  helper: { wide: 10.5, hips: 23, tall: 42, head: 6.2 },
};

function shadow(reach = 10): Prim {
  const pool = Array.from({ length: 10 }, (_, i): P3 => {
    const a = (i * Math.PI) / 5;
    return [2 + Math.cos(a) * reach, 2 + Math.sin(a) * reach, 0.2];
  });
  return s.poly("dk-contact", ...pool);
}

function frame(b: Build): { legs: Prim[]; torso: Prim[]; head: Prim[]; top: number } {
  const legs =
    b.hips > 8
      ? [...box("dark", 0, -3.2, 0, 4.6, 4.6, b.hips), ...box("dark", 0, 3.2, 0, 4.6, 4.6, b.hips)]
      : [];
  const torso = box(CREW, 0, 0, b.hips, b.wide, b.wide, b.tall - b.hips);
  const hz = b.tall + b.head + 1.5;
  const head = [
    s.dot("dk-head", P(0, 0, hz), b.head),
    s.dot("dk-head-lit", P(-1, -2, hz + b.head * 0.45), b.head * 0.36),
  ];
  return { legs, torso, head, top: hz + b.head };
}

/** One character. Pure, so it can be tested and drawn anywhere. */
export function figure(persona: Persona): Figure {
  const b = BUILD[persona];
  const { legs, torso, head, top } = frame(b);
  const sh = b.tall - 2; // shoulders
  const reachL = P(2, -(b.wide / 2 + 1), sh);
  const reachR = P(2, b.wide / 2 + 1, sh);
  const hangL = limb(reachL, P(3, -(b.wide / 2 + 2), sh - 13));
  const hangR = limb(reachR, P(3, b.wide / 2 + 2, sh - 13));
  const out: Figure = { back: [], body: [], prop: [], fx: [], front: [] };
  let hat: Prim[] = [];
  let arms: Prim[] = [hangL, hangR];
  let pool = shadow();

  switch (persona) {
    case "foreman": {
      // A hard hat with a brim, a hi-vis vest with two bands, a clipboard held out in front.
      hat = [
        ...box(CREW, 1, 0, top - 5.2, 15.5, 15.5, 1.3),
        ...box(CREW, 0, 0, top - 4, 11, 11, 4.6),
        ...box("dark", 0, 0, top + 0.6, 3, 9, 1),
      ];
      torso.push(
        s.poly("cs-band", P(6.6, -6.4, 33), P(6.6, 6.4, 33), P(6.6, 6.4, 35.4), P(6.6, -6.4, 35.4)),
        s.poly("cs-band", P(6.6, -6.4, 27), P(6.6, 6.4, 27), P(6.6, 6.4, 29.4), P(6.6, -6.4, 29.4)),
      );
      arms = [limb(reachL, P(9, -5.5, 30)), limb(reachR, P(9, 5.5, 30))];
      out.prop = [
        s.poly("cs-board", P(10, -6.5, 25), P(10, 6.5, 25), P(10, 6.5, 41), P(10, -6.5, 41)),
        s.poly(
          "cs-sheet",
          P(10.2, -5, 26.5),
          P(10.2, 5, 26.5),
          P(10.2, 5, 38.5),
          P(10.2, -5, 38.5),
        ),
        s.poly(
          "cs-clip",
          P(10.4, -2.6, 38.5),
          P(10.4, 2.6, 38.5),
          P(10.4, 2.6, 41.8),
          P(10.4, -2.6, 41.8),
        ),
        ink(P(10.4, -3.4, 35), P(10.4, 3.4, 35)),
        ink(P(10.4, -3.4, 32), P(10.4, 3.4, 32)),
        ink(P(10.4, -3.4, 29), P(10.4, 0.6, 29)),
      ];
      break;
    }
    case "inspector": {
      // Tall and narrow in a long coat, a flat cap with a peak, a big magnifier held out.
      hat = [
        ...box(CREW, 0, 0, top - 3.4, 11.5, 11.5, 3),
        ...box(CREW, 5, 0, top - 3.4, 6, 9, 1.1),
      ];
      torso.push(ink(P(4.8, 0, 14), P(4.8, 0, 43)));
      arms = [hangL, limb(reachR, P(7, 9, 33))];
      out.prop = [
        ink(P(8, 9.5, 32), P(8, 12, 40)),
        s.dot("cs-lens", P(8, 13.6, 46), 7.4),
        s.dot("cs-glint", P(8, 11.4, 48.6), 1.7),
      ];
      break;
    }
    case "photographer": {
      // A backwards cap, a strap, and a camera with a long lens held up to the face.
      hat = [...box(CREW, 0, 0, top - 3.6, 11, 11, 3.2), ...box(CREW, -5, 0, top - 3.6, 5, 8, 1.1)];
      torso.push(ink(P(5.3, -5, 41), P(5.3, 4.6, 26)));
      arms = [limb(reachL, P(8, -4.5, 44)), limb(reachR, P(8, 4.5, 44))];
      out.prop = [
        ...box("dark", 8.5, 0, 41, 9.5, 9.5, 7),
        ...box("metal", 8.5, 2.4, 48, 3.4, 3.4, 1.6),
        s.dot("cs-lens-rim", P(13.5, 0, 44.4), 4.3),
        s.dot("cs-lens", P(13.5, 0, 44.4), 2.9),
        s.dot("cs-glint", P(13.5, -0.9, 45.4), 0.9),
      ];
      const c = P(14, 7, 56);
      const [cx, cy] = [c[0], c[1]];
      const ray = (dz: number, ds: number): P3 => [cx + ds * R, cy - ds * R, c[2] + dz];
      out.fx = [
        s.poly(
          "cs-flash",
          ray(9, 0),
          ray(2.2, 2.2),
          ray(0, 9),
          ray(-2.2, 2.2),
          ray(-9, 0),
          ray(-2.2, -2.2),
          ray(0, -9),
          ray(2.2, -2.2),
        ),
      ];
      break;
    }
    case "clerk": {
      // A green eyeshade and rolled sleeves, at a tall records cabinet with one drawer open.
      hat = [
        ...box(CREW, 0, 0, top - 4.4, 11.6, 11.6, 1.5),
        s.poly(
          "cs-visor",
          P(5.6, -6.6, top - 4.6),
          P(5.6, 6.6, top - 4.6),
          P(10.6, 5, top - 6.6),
          P(10.6, -5, top - 6.6),
        ),
      ];
      const [cx, cy] = P(1, 17, 0);
      out.back = [
        s.contact(cx - 7, cy - 7, 14, 14, 7),
        ...s.box("metal", cx - 7, cy - 7, 0, 14, 14, 39),
        ...[2, 14.5].map((z) => s.onY("cs-drawer", cy + 7.1, cx - 5.6, cx + 5.6, z, z + 10.5)),
        ...[6.6, 19.1].map((z) => s.onY("cs-pull", cy + 7.2, cx - 2, cx + 2, z, z + 1.5)),
      ];
      arms = [hangL, limb(reachR, P(6, 12, 33))];
      out.front = [...s.box("metal", cx - 5.8, cy + 7, 27, 11.6, 8, 10.5)];
      out.prop = [
        ...s.box(PAPER, cx - 4.6, cy + 8.4, 33, 9.2, 1.3, 8),
        ...s.box("teal", cx - 4.6, cy + 10.8, 33, 9.2, 1.3, 9.5),
        ...s.box(PAPER, cx - 4.6, cy + 13, 33, 9.2, 1.3, 7),
      ];
      break;
    }
    case "operator": {
      // A hair bun and a headset with a boom mic, one hand to the ear.
      hat = [
        s.dot("cs-hair", P(-2.5, 0, top + 1.6), 3.5),
        s.line("cs-headband", P(0, -6.4, top - 6), P(0, -3.6, top - 0.2)),
        s.line("cs-headband", P(0, -3.6, top - 0.2), P(0, 3.6, top - 0.2)),
        s.line("cs-headband", P(0, 3.6, top - 0.2), P(0, 6.4, top - 6)),
        s.dot("cs-cup", P(1, 6.6, top - 6.6), 3),
        s.dot("cs-cup", P(1, -6.6, top - 6.6), 3),
        ink(P(2, 6.6, top - 7.6), P(7.5, 3, top - 12)),
        s.dot("cs-mic", P(7.5, 3, top - 12), 1.8),
      ];
      arms = [hangL, limb(reachR, P(4, 10, sh - 5)), limb(P(4, 10, sh - 5), P(3, 8, top - 8))];
      out.fx = [
        s.dot("cs-wave", P(2, 13, top - 3), 1.5),
        s.dot("cs-wave", P(2, 17.5, top + 1), 2),
        s.dot("cs-wave", P(2, 22.5, top + 5), 2.6),
      ];
      break;
    }
    case "registrar": {
      // A pillbox hat and a long coat, at a lectern with the open register and a hand stamp.
      hat = [
        ...box(CREW, 0, 0, top - 3, 9.4, 9.4, 5),
        ...box("dark", 0, 0, top - 3.4, 10.6, 10.6, 1.2),
      ];
      arms = [limb(reachL, P(9, -6, 31)), limb(reachR, P(9, 5, 37))];
      out.front = [
        s.contact(P(12, 0, 0)[0] - 7, P(12, 0, 0)[1] - 7, 14, 14, 5),
        ...box("wood", 12, 0, 0, 9, 9, 25),
        ...box("wood", 12, 0, 25, 17, 17, 1.6),
        ...box(PAPER, 12, -4.4, 26.6, 7.6, 12, 1.6),
        ...box(PAPER, 12, 4.4, 26.6, 7.6, 12, 1.6),
        ink(P(15, -6, 28.4), P(15, -2, 28.4)),
        ink(P(13, -6, 28.4), P(13, -2, 28.4)),
      ];
      out.prop = [
        ...box("teal", 12, 4.6, 30.6, 5.6, 5.6, 2.6),
        ...box("dark", 12, 4.6, 33.2, 2.6, 2.6, 5.4),
      ];
      break;
    }
    case "scout": {
      // A bobble hat and a backpack, with a laptop open on a crate.
      hat = [
        ...box(CREW, 0, 0, top - 4, 11.2, 11.2, 4.4),
        s.dot("cs-bobble", P(0, 0, top + 2.6), 2.7),
      ];
      out.back = [...box("dark", -6.5, 0, 25, 8, 9, 14)];
      const [cx, cy] = P(3, 16, 0);
      out.front = [
        s.contact(cx - 7, cy - 7, 14, 14, 5),
        ...s.box("wood", cx - 7, cy - 7, 0, 14, 14, 21),
        ...s.box("dark", cx - 5.6, cy - 6, 21, 11.6, 12, 1.2),
        s.onX("cs-lid", cx - 5.4, cy - 6, cy + 6, 22.2, 33),
      ];
      out.prop = [
        s.onX("cs-screen", cx - 5.2, cy - 5, cy + 5, 23.2, 32),
        s.line("cs-code", [cx - 5.1, cy - 3.6, 30], [cx - 5.1, cy + 2, 30]),
        s.line("cs-code", [cx - 5.1, cy - 3.6, 27.6], [cx - 5.1, cy + 3.6, 27.6]),
        s.line("cs-code", [cx - 5.1, cy - 3.6, 25.2], [cx - 5.1, cy, 25.2]),
      ];
      arms = [hangL, limb(reachR, P(5, 12, 25))];
      break;
    }
    case "searcher": {
      // A wide-brimmed hat and an open map.
      hat = [
        ...box(CREW, 0, 0, top - 4.6, 17, 17, 1.2),
        ...box(CREW, 0, 0, top - 3.6, 9.6, 9.6, 4),
      ];
      arms = [limb(reachL, P(9, -7.5, 33)), limb(reachR, P(9, 7.5, 33))];
      out.prop = [
        s.poly("cs-sheet", P(10, -9, 27), P(10, 9, 27), P(10, 9, 40), P(10, -9, 40)),
        ink(P(10.2, -3, 27), P(10.2, -3, 40)),
        ink(P(10.2, 3, 27), P(10.2, 3, 40)),
        s.line("cs-route", P(10.3, -7, 30), P(10.3, -1, 36)),
        s.line("cs-route", P(10.3, -1, 36), P(10.3, 6, 32)),
      ];
      break;
    }
    case "guide": {
      // A peaked cap and a tall route flag.
      hat = [
        ...box(CREW, 0, 0, top - 3.4, 10.6, 10.6, 3),
        ...box("dark", 5, 0, top - 3.4, 5, 8, 1),
      ];
      arms = [hangL, limb(reachR, P(5, 10, 32))];
      out.prop = [
        ink(P(5, 10.5, 0), P(5, 10.5, 62)),
        s.poly("cs-flag", P(5, 10.5, 62), P(5, 21, 58), P(5, 10.5, 53)),
      ];
      break;
    }
    case "judge": {
      // A robe to the floor with a white collar, behind a desk; the stamp is in its hand.
      pool = shadow(12);
      hat = [
        ...box("dark", 0, 0, top - 3.6, 12.4, 12.4, 1.2),
        ...box("dark", 0, 0, top - 2.4, 8, 8, 2.6),
      ];
      torso.push(
        s.poly("cs-collar", P(7.2, -3.6, 43), P(7.2, 3.6, 43), P(7.2, 1.6, 36), P(7.2, -1.6, 36)),
      );
      arms = [limb(reachL, P(10, -9, 27)), limb(reachR, P(11, 8, 33))];
      const [cx, cy] = P(15, 0, 0);
      out.front = [
        s.contact(cx - 20, cy - 8, 40, 16, 6),
        ...s.box("wood", cx - 20, cy - 8, 0, 40, 16, 20),
        ...s.box("wood", cx - 22, cy - 9.5, 20, 44, 19, 2),
      ];
      out.prop = [...box("teal", 15, 8.5, 26, 7, 7, 3), ...box("dark", 15, 8.5, 29, 3, 3, 6.5)];
      break;
    }
    case "helper":
      hat = [...box(CREW, 0, 0, top - 3.4, 10.6, 10.6, 3)];
      break;
  }

  out.body = [pool, ...legs, ...torso, ...head, ...hat, ...arms];
  return out;
}

/** Where the Decider's desk top is, round the judge's feet: the pile of notes sits here. */
export const DESK_TOP = P(15, -8, 22);
/** How tall a figure stands, in its own units: where a bubble's tail may point. */
export const FIGURE_HEIGHT = 60;
