import { Parts } from "../draw/Parts";
import { between, makeScene, part } from "../draw/kit";
import type { Part, Scene, Tone } from "../draw/kit";

// Drawn stand-ins for a place, built with the shared drawing kit (draw/kit.ts) so they share its
// one light and its detail: an apartment community is a flat-roofed block with window bands, a
// rental home is a gabled house. They are team-made and generic, never a picture of a real place,
// and the sheet labels them as drawn. Decoration only: aria-hidden.

const FLOOR = 13;
const floorsFor = (plans: number) => Math.max(2, Math.min(5, plans + 1));

/** A flat-roofed block with window bands on both visible faces. `lantern` is the lit box on the
 *  roof that marks a 3D scan on record, the same white cap the map puts on a column. */
function block(
  s: Scene,
  x: number,
  y: number,
  w: number,
  d: number,
  floors: number,
  tone: Tone,
  lantern: boolean,
): Part[] {
  const h = floors * FLOOR + 4;
  const glass: Part[] = [];
  for (let f = 0; f < floors; f += 1) {
    const z0 = 6 + f * FLOOR;
    for (const cx of between(x, x + w, Math.max(2, Math.round(w / 22))))
      glass.push(...s.windowY(y + d, cx - 5, cx + 5, z0, z0 + 7, 0.8));
    for (const cy of between(y, y + d, Math.max(2, Math.round(d / 22))))
      glass.push(...s.windowX(x + w, cy - 5, cy + 5, z0, z0 + 7, 0.8));
  }
  return [
    part("block", [s.contact(x, y, w, d, 6 + floors * 4), ...s.box(tone, x, y, 0, w, d, h)]),
    part(
      "floor-bands",
      [
        ...s.coursesY(y + d + 0.2, x, x + w, 2, h, FLOOR),
        ...s.coursesX(x + w + 0.2, y, y + d, 2, h, FLOOR),
      ],
      true,
    ),
    ...glass.map((p) => ({ ...p, fine: true })),
    ...s.doorX(x + w, y + d * 0.42, y + d * 0.58, 11, 1).map((p) => ({ ...p, fine: true })),
    ...s.flatRoof("slate", x - 1, y - 1, h, w + 2, d + 2, 3),
    part(
      "roof-units",
      [
        ...s.box("metal", x + w * 0.16, y + d * 0.2, h + 2, w * 0.14, d * 0.2, 5),
        ...s.box("metal", x + w * 0.6, y + d * 0.55, h + 2, w * 0.12, d * 0.2, 4),
      ],
      true,
    ),
    ...(lantern
      ? [
          part("lantern", [
            ...s.box("white", x + w * 0.36, y + d * 0.3, h + 2, w * 0.22, d * 0.34, 9),
          ]),
        ]
      : []),
  ];
}

/** A small gabled house; `lantern` lights a dormer box on the roof for a 3D scan on record. */
function house(
  s: Scene,
  x: number,
  y: number,
  w: number,
  d: number,
  h: number,
  tone: Tone,
  lantern: boolean,
): Part[] {
  return [
    part("house", [s.contact(x, y, w, d, 10), ...s.box(tone, x, y, 0, w, d, h)]),
    part("siding", s.coursesY(y + d + 0.2, x, x + w, 2, h, 4), true),
    ...s.windowY(y + d, x + w * 0.14, x + w * 0.4, h * 0.38, h * 0.8, 1),
    ...s.windowY(y + d, x + w * 0.6, x + w * 0.86, h * 0.38, h * 0.8, 1),
    ...s.doorX(x + w, y + d * 0.55, y + d * 0.8, h * 0.68, 1),
    ...s.gableRoof("slate", x, y, h, w, d, h * 0.7, 3, tone),
    ...(lantern
      ? [part("lantern", [...s.box("white", x + w * 0.4, y + d * 0.42, h * 1.5, 10, 8, 7)])]
      : []),
  ];
}

function streetAlongX(s: Scene, y: number, x0: number, x1: number): Part[] {
  return [
    part("pavement", [s.onZ("dk-path", 0.05, x0, y + 34, x1 - x0, 9)]),
    part("street", [s.onZ("dk-asphalt", 0.05, x0, y, x1 - x0, 34)]),
    part(
      "street-lines",
      between(x0, x1, 12).map((x) => s.line("dk-paint", [x, y + 17, 0.2], [x + 12, y + 17, 0.2])),
      true,
    ),
  ];
}

function apartmentSite(plans: number, scan: boolean): Part[] {
  const s = makeScene({ ox: 196, oy: 96 });
  const floors = floorsFor(plans);
  return [
    part("ground", [s.onZ("dk-lawn", 0, -260, -260, 620, 620)]),
    ...streetAlongX(s, -118, -260, 360),
    s.tree(-86, -62, 1.1),
    s.tree(-30, -66, 0.9),
    s.tree(112, -64, 1.2),
    // a lower neighbour behind, in the pale glass tone the map gives every other building
    ...block(s, -122, -40, 54, 46, 2, "pale", false),
    ...block(s, -40, -44, 124, 62, floors, "white", scan),
    part("forecourt", [s.onZ("dk-path", 0.05, 84, -18, 30, 14)]),
    ...s.parking(-44, 36, 132, 30, 9),
    s.car("teal", -24, 40),
    s.car("slate", 5, 40),
    s.car("white", 49, 40),
    s.car("dark", 64, 40),
    s.shrub(-44, 22, 60, 5),
    s.shrub(30, 22, 54, 5),
    s.tree(112, 30, 1),
    s.tree(-78, 46, 1.2),
  ];
}

function houseSite(scan: boolean): Part[] {
  const s = makeScene({ ox: 204, oy: 92 });
  return [
    part("ground", [s.onZ("dk-lawn", 0, -260, -260, 620, 620)]),
    ...streetAlongX(s, -112, -260, 360),
    s.tree(-70, -56, 1.2),
    ...house(s, -128, -34, 52, 38, 22, "pale", false),
    s.tree(92, -52, 1),
    ...house(s, -30, -30, 78, 48, 27, "white", scan),
    part("path", [s.onZ("dk-path", 0.05, 48, 2, 44, 9)]),
    part("drive", [s.onZ("dk-asphalt", 0.05, 62, -60, 22, 34)]),
    s.car("slate", 68, -52),
    s.shrub(-30, 22, 34, 5),
    s.shrub(14, 22, 30, 5),
    s.tree(-62, 34, 1.1),
    s.tree(104, 30, 0.9),
  ];
}

/** The sheet's drawn site, shown when no aerial photo is to hand. */
export function PlaceSite({
  kind,
  plans,
  scan,
}: {
  kind: "apartment" | "house";
  plans: number;
  scan: boolean;
}) {
  const parts = kind === "house" ? houseSite(scan) : apartmentSite(plans, scan);
  return (
    <svg
      className="place-site"
      viewBox="-26 -34 486 224"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <Parts parts={parts} />
    </svg>
  );
}

/** The small mark in a ledger card and in the sheet's corner: this place as one building.
 *  More floor plans on record make a taller block, as on the map; teal means it fits the brief. */
export function PlaceMark({
  kind,
  plans,
  fits,
  scan,
}: {
  kind: "apartment" | "house";
  plans: number;
  fits: boolean;
  scan: boolean;
}) {
  const s = makeScene({ ox: 0, oy: 0 });
  const tone: Tone = fits ? "teal" : "pale";
  const parts =
    kind === "house"
      ? house(s, -17, -13, 34, 26, 15, tone, scan)
      : block(s, -15, -13, 30, 26, floorsFor(plans), tone, scan);
  return (
    <svg
      className={`placemark${fits ? " placemark-fit" : ""}`}
      viewBox="-32 -104 64 128"
      data-detail="low"
      aria-hidden="true"
      focusable="false"
    >
      <ellipse className="placemark-glow" cx="0" cy="4" rx="29" ry="15" />
      <Parts parts={parts} />
    </svg>
  );
}
