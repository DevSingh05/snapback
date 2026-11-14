// The two drawn aerial stand-ins for the copied-ad case, built with the drawing kit: a house on
// a residential street (the home the ad names) and an apartment block with its car park (the
// home in its photos). Team-made and generic: they stand in until our server gives the real
// Vexcel tiles, and the pane says so.
import { between, makeScene, part, type Part, type Tone } from "../draw/kit";

const s = makeScene({ ox: 200, oy: 62 });

const ground = (): Part => part("ground", [s.onZ("dk-lawn", 0, -80, -80, 420, 420)]);

/** A road along x with a kerbside pavement and a dashed centre line. */
function streetAlongX(y: number): Part[] {
  const dashes = between(-80, 340, 13).map((x) =>
    s.line("dk-paint", [x, y + 20, 0.2], [x + 14, y + 20, 0.2]),
  );
  return [
    part("pavement", [s.onZ("dk-path", 0.05, -80, y - 10, 420, 10)]),
    part("street", [s.onZ("dk-asphalt", 0.05, -80, y, 420, 40)]),
    part("street-lines", dashes, true),
  ];
}

/** A small gabled house: walls, windows, a door on the gable end and a shingled roof. */
function house(
  x: number,
  y: number,
  w: number,
  d: number,
  h: number,
  tone: Tone = "white",
): Part[] {
  return [
    part("house", [s.contact(x, y, w, d, 10), ...s.box(tone, x, y, 0, w, d, h)]),
    ...s.windowY(y + d, x + w * 0.16, x + w * 0.4, h * 0.4, h * 0.78, 1),
    ...s.windowY(y + d, x + w * 0.6, x + w * 0.84, h * 0.4, h * 0.78, 1),
    ...s.doorX(x + w, y + d * 0.55, y + d * 0.8, h * 0.66, 1),
    ...s.gableRoof("slate", x, y, h, w, d, h * 0.7, 3, tone),
  ];
}

/** A flat-roofed block with window bands on both visible faces and plant on the roof. */
function block(x: number, y: number, w: number, d: number, floors: number, tone: Tone): Part[] {
  const fh = 13;
  const h = floors * fh + 4;
  const glassY: Part[] = [];
  const glassX: Part[] = [];
  for (let f = 0; f < floors; f++) {
    const z0 = 6 + f * fh;
    for (const cx of between(x, x + w, Math.max(2, Math.round(w / 22))))
      glassY.push(...s.windowY(y + d, cx - 5, cx + 5, z0, z0 + 7, 0.8));
    for (const cy of between(y, y + d, Math.max(2, Math.round(d / 22))))
      glassX.push(...s.windowX(x + w, cy - 5, cy + 5, z0, z0 + 7, 0.8));
  }
  return [
    part("block", [s.contact(x, y, w, d, 6 + floors * 4), ...s.box(tone, x, y, 0, w, d, h)]),
    part(
      "floor-bands",
      [
        ...s.coursesY(y + d + 0.2, x, x + w, 2, h, fh),
        ...s.coursesX(x + w + 0.2, y, y + d, 2, h, fh),
      ],
      true,
    ),
    ...glassY.map((p) => ({ ...p, fine: true })),
    ...glassX.map((p) => ({ ...p, fine: true })),
    ...s.flatRoof("slate", x - 1, y - 1, h, w + 2, d + 2, 3),
    part(
      "roof-units",
      [
        ...s.box("metal", x + w * 0.18, y + d * 0.2, h + 2, 14, 12, 6),
        ...s.box("metal", x + w * 0.55, y + d * 0.24, h + 2, 12, 12, 5),
        ...s.box("white", x + w * 0.3, y + d * 0.6, h + 2, 18, 14, 9),
      ],
      true,
    ),
  ];
}

const lot = (x: number, y: number, w: number, d: number): Part =>
  part("lot", [s.onZ("ma-lot", 0.3, x, y, w, d)]);

/** The home the ad names: a house on its lot, on a street of houses. */
export const NAMED_SCENE: Part[] = [
  ground(),
  ...house(-30, -20, 60, 46, 22, "wood"),
  s.tree(48, -14, 1.5),
  ...house(84, -34, 62, 46, 24),
  s.tree(170, -30, 1.7),
  ...house(196, -28, 60, 46, 22, "pale"),
  ...house(-58, 76, 56, 48, 22),
  lot(60, 58, 122, 124),
  part("drive", [s.onZ("dk-path", 0.35, 150, 122, 18, 60)]),
  s.tree(74, 70, 1.6),
  ...house(82, 78, 70, 54, 26),
  s.shrub(88, 136, 26, 6, 5),
  s.car("slate", 154, 142),
  s.tree(70, 152, 1.3),
  ...house(214, 78, 58, 48, 22, "wood"),
  s.tree(196, 150, 1.5),
  ...streetAlongX(196),
  s.car("pale", 40, 202),
  s.tree(-10, 250, 1.8),
  s.tree(120, 248, 1.5),
  ...house(180, 244, 60, 46, 22),
];

/** The home in its photos: an apartment block with a car park, between other blocks. */
export const PICTURED_SCENE: Part[] = [
  ground(),
  ...block(-44, -30, 70, 60, 3, "pale"),
  s.tree(44, -10, 1.6),
  ...block(170, -44, 70, 64, 4, "pale"),
  s.tree(-30, 80, 1.7),
  lot(52, 52, 150, 172),
  part("forecourt", [s.onZ("dk-path", 0.35, 60, 60, 134, 112)]),
  part("forecourt-joints", s.tile(60, 60, 134, 112, 16, 0.4), true),
  ...block(74, 70, 96, 86, 6, "white"),
  part("entrance", [
    ...s.doorX(170, 104, 122, 14, 1).flatMap((p) => p.prims),
    ...s.box("slate", 170, 100, 16, 12, 26, 2),
  ]),
  s.shrub(74, 160, 40, 6, 5),
  s.shrub(124, 160, 40, 6, 5),
  s.tree(182, 82, 1.5),
  s.tree(182, 140, 1.5),
  ...s.parking(60, 178, 134, 40, 8),
  s.car("slate", 64, 182),
  s.car("pale", 98, 182),
  s.car("white", 148, 182),
  s.car("teal", 181, 182),
  ...block(232, 96, 60, 70, 3, "pale"),
  ...streetAlongX(236),
  s.tree(20, 222, 1.6),
];
