// The isometric house, drawn inline with the shared drawing kit (draw/kit.ts) so nothing loads
// from another host and it shares one light with every other drawn scene. Every fill is a
// token, so it follows the light and dark sets. It is decoration: aria-hidden, and it never
// carries a word. At small sizes (`detail="low"`, as in the wordmark) the fine detail (siding,
// shingles, mullions, door panels) is dropped and the big shapes carry it.
import { Parts } from "../draw/Parts";
import { makeScene, part, type Part, type Prim } from "../draw/kit";

const s = makeScene({ ox: 0, oy: 0 });

const W = 100; // along x: the long wall faces +y
const D = 80; // along y: the gable end with the door faces +x
const H = 55; // wall height
const RISE = 40; // ridge above the walls

// Window glass keeps the `house-window` class so the lit state can warm it.
const lit = (parts: Part[]): Part[] =>
  parts.map((p) => ({
    ...p,
    prims: p.prims.map((x): Prim =>
      x.c.startsWith("dk-glass") ? { ...x, c: `${x.c} house-window` } : x,
    ),
  }));

const HOUSE: Part[] = [
  part("lawn", [s.onZ("dk-lawn", 0, -26, -26, 152, 132)]),
  part("ground-shadow", [s.contact(0, 0, W, D, 18)]),
  // The walk from the street to the stoop, with two paving joints.
  part("path", [s.onZ("dk-path", 0.1, W, 46, 26, 22)]),
  part("path-joints", s.tile(W, 46, 26, 22, 9, 0.2), true),
  part("walls", s.box("white", 0, 0, 0, W, D, H)),
  part("foundation", [
    s.onY("house-plinth-left", D + 0.1, 0, W, 0, 4),
    s.onX("house-plinth-right", W + 0.1, 0, D, 0, 4),
  ]),
  part(
    "siding",
    [...s.coursesY(D + 0.2, 0, W, 4, H, 5.5), ...s.coursesX(W + 0.2, 0, D, 4, H, 5.5)],
    true,
  ),
  part(
    "corner-boards",
    [s.onY("dk-trim", D + 0.3, 0, 3, 4, H), s.onY("dk-trim", D + 0.3, W - 3, W, 4, H)],
    true,
  ),
  ...lit(s.windowY(D, 12, 36, 20, 42, 1.8)),
  ...lit(s.windowY(D, 62, 86, 20, 42, 1.8)),
  part(
    "shutters",
    [
      s.onY("dk-door", D + 0.3, 6, 10, 19, 43),
      s.onY("dk-door", D + 0.3, 38, 42, 19, 43),
      s.onY("dk-door", D + 0.3, 56, 60, 19, 43),
      s.onY("dk-door", D + 0.3, 88, 92, 19, 43),
    ],
    true,
  ),
  ...lit(s.windowX(W, 10, 32, 20, 42, 1.8)),
  ...s.doorX(W, 47, 67, 36, 1.8),
  // The stoop: a slab, a step and a small roof over the door.
  part("stoop", [
    s.contact(W, 43, 12, 28, 4),
    ...s.box("white", W, 43, 0, 12, 28, 4),
    ...s.box("white", W + 12, 47, 0, 5, 20, 2),
  ]),
  part("porch-roof", [
    ...s.box("slate", W, 43, 40, 11, 28, 2.5),
    ...s.box("white", W + 8, 44, 4, 2, 2, 36),
    ...s.box("white", W + 8, 68, 4, 2, 2, 36),
  ]),
  ...s.gableRoof("slate", 0, 0, H, W, D, RISE, 6),
  part("gable-vent", [s.onX("dk-trim-shade", W + 0.2, 35, 45, 66, 76)], true),
  part("chimney", [
    ...s.box("wood", 20, 46, 76, 11, 11, 28),
    ...s.box("dark", 19, 45, 104, 13, 13, 2.5),
  ]),
  // Planting: shrubs under the windows, a hedge by the path and a tree on the lawn.
  s.shrub(8, D + 2, 30, 7, 7),
  s.shrub(60, D + 2, 30, 7, 7),
  s.shrub(W + 2, 8, 7, 30, 6),
  s.tree(-8, 66, 2),
];

interface Props {
  className?: string;
  // Lit windows. Off for empty and error states.
  lit?: boolean;
  // "low" drops the fine detail, for small sizes such as the wordmark.
  detail?: "full" | "low";
}

export function HouseGlyph({ className, lit: isLit = true, detail = "full" }: Props) {
  return (
    <svg
      className={`house${isLit ? " house-lit" : ""}${className ? ` ${className}` : ""}`}
      viewBox="-120 -86 256 206"
      data-detail={detail === "low" ? "low" : undefined}
      aria-hidden="true"
      focusable="false"
    >
      <Parts parts={HOUSE} />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="wordmark">
      <HouseGlyph className="wordmark-house" detail="low" />
      SNAPBACK
    </span>
  );
}
