// Reusable drawn parts for the stand-in room: every fixture is a small list of flat shapes in
// room units (x down-right, y down-left, z up), projected once. Team-made drawings only. One
// light direction throughout: tops are lightest, faces toward +y are mid, faces toward +x are
// darkest. Colours come from the tone classes in walk.css, never from here.
import {
  between,
  makeScene,
  part,
  type Origin,
  type Part,
  type Prim,
  type Tone,
} from "../draw/kit";

export type { Part, Prim, Tone };

export const O: Origin = { ox: 400, oy: 196 };
export const SIZE = 300;
export const WALL_H = 150;

const scene = makeScene(O);
export const { poly, line, onX, onY, onZ, box, contact } = scene;
const steps = between;

// ---------- The shell: floor, walls with thickness, baseboard ----------

export function shell(floor: "planks" | "tile"): Part[] {
  const T = 9; // wall thickness
  const marks = floor === "planks" ? scene.planks(0, 0, SIZE, SIZE) : scene.tile(0, 0, SIZE, SIZE);
  return [
    part("floor", [onZ("rs-floor", 0, 0, 0, SIZE, SIZE)]),
    part("floor-marks", marks, true),
    part("walls", [
      onX("rs-wall-left", 0, 0, SIZE, 0, WALL_H),
      onY("rs-wall-right", 0, 0, SIZE, 0, WALL_H),
      // Wall tops and cut ends, so the walls read as solid.
      onZ("rs-wall-cap", WALL_H, -T, -T, T, SIZE + T),
      onZ("rs-wall-cap", WALL_H, 0, -T, SIZE, T),
      onY("rs-wall-end-left", SIZE, -T, 0, 0, WALL_H),
      onX("rs-wall-end-right", SIZE, -T, 0, 0, WALL_H),
    ]),
    part("baseboard", [
      onX("rs-base-left", 0.2, 0, SIZE, 0, 7),
      onY("rs-base-right", 0.2, 0, SIZE, 0, 7),
    ]),
  ];
}

/** Wall tile up to a height, as a grid on both walls (bathrooms). */
export function wallTile(top: number): Part[] {
  const marks: Prim[] = [];
  for (let z = 20; z <= top; z += 20) {
    marks.push(line("dk-seam", [0, 0, z], [0, SIZE, z]));
    marks.push(line("dk-seam", [0, 0, z], [SIZE, 0, z]));
  }
  for (let v = 30; v < SIZE; v += 30) {
    marks.push(line("dk-seam", [0, v, 0], [0, v, top]));
    marks.push(line("dk-seam", [v, 0, 0], [v, 0, top]));
  }
  return [
    part("wall-tile", [
      onX("rs-tile-left", 0.1, 0, SIZE, 0, top),
      onY("rs-tile-right", 0.1, 0, SIZE, 0, top),
    ]),
    part("wall-tile-marks", marks, true),
  ];
}

export const rug = (x: number, y: number, w: number, d: number): Part =>
  part("rug", [
    onZ("rs-rug", 0.2, x, y, w, d),
    onZ("rs-rug-inner", 0.3, x + 8, y + 8, w - 16, d - 16),
  ]);

/** Keeps a floor point inside the room. */
const fit = (v: number) => Math.min(SIZE - 3, v);

// ---------- Openings on the right wall (the plane y = 0) ----------

/** A window with trim, a sill, mullions and half-drawn blinds, plus its light on the floor. */
export function windowRight(x0: number, x1: number, z0: number, z1: number): Part[] {
  const mid = (x0 + x1) / 2;
  const blinds = steps(z1, z0 + (z1 - z0) * 0.45, 5).map((z) =>
    line("rs-blind", [x0 + 2, 0.6, z], [x1 - 2, 0.6, z]),
  );
  return [
    part("window-light", [
      poly(
        "rs-light",
        [fit(x0 + 14), 34, 0.15],
        [fit(x1 + 14), 34, 0.15],
        [fit(x1 + 64), 150, 0.15],
        [fit(x0 + 64), 150, 0.15],
      ),
    ]),
    part("window", [
      onY("rs-trim", 0.3, x0 - 5, x1 + 5, z0 - 5, z1 + 5),
      onY("rs-glass", 0.4, x0, x1, z0, z1),
      onY("rs-blind-band", 0.5, x0, x1, z1 - (z1 - z0) * 0.5, z1),
      ...box("white", x0 - 7, 0, z0 - 8, x1 - x0 + 14, 5, 3),
    ]),
    part("window-detail", [line("rs-mullion", [mid, 0.6, z0], [mid, 0.6, z1]), ...blinds], true),
  ];
}

/** A door in its frame, with two panels and a handle. */
export function doorRight(x0: number, x1: number, h: number): Part[] {
  const inset = 8;
  return [
    part("door", [
      onY("rs-trim", 0.3, x0 - 6, x1 + 6, 0, h + 6),
      onY("rs-door", 0.4, x0, x1, 0, h),
    ]),
    part(
      "door-detail",
      [
        onY("rs-door-panel", 0.5, x0 + inset, x1 - inset, h * 0.52, h - inset),
        onY("rs-door-panel", 0.5, x0 + inset, x1 - inset, inset, h * 0.46),
        ...box("metal", x1 - 9, 0.5, h * 0.47, 5, 3, 3),
      ],
      true,
    ),
  ];
}

// ---------- Cabinets ----------

interface RunOpts {
  d?: number;
  h?: number;
  doors?: number;
  tone?: Tone;
}

/** Base cabinets along the right wall: toe kick, body, doors with handles, a counter on top. */
export function cabinetsRight(x0: number, x1: number, o: RunOpts = {}): Part[] {
  const { d = 42, h = 56, doors = 2, tone = "slate" } = o;
  const seams = steps(x0, x1, doors - 1);
  const mids = [x0, ...seams].map((x, i) => (x + ([...seams, x1][i] ?? x1)) / 2);
  return [
    part("cabinet", [
      contact(x0, 0, x1 - x0, d),
      ...box("dark", x0, 0, 0, x1 - x0, d - 4, 6),
      ...box(tone, x0, 0, 6, x1 - x0, d, h - 10),
      ...box("white", x0 - 1, 0, h - 4, x1 - x0 + 2, d + 3, 4),
    ]),
    part(
      "cabinet-detail",
      [
        ...seams.map((x) => line("dk-seam", [x, d + 0.2, 8], [x, d + 0.2, h - 6])),
        ...mids.map((x) => onY("rs-handle", d + 0.3, x - 5, x + 5, h - 13, h - 11)),
      ],
      true,
    ),
  ];
}

/** Base cabinets along the left wall. Their fronts face +x. */
export function cabinetsLeft(y0: number, y1: number, o: RunOpts = {}): Part[] {
  const { d = 40, h = 56, doors = 3, tone = "slate" } = o;
  const seams = steps(y0, y1, doors - 1);
  const mids = [y0, ...seams].map((y, i) => (y + ([...seams, y1][i] ?? y1)) / 2);
  return [
    part("cabinet", [
      contact(0, y0, d, y1 - y0),
      ...box("dark", 0, y0, 0, d - 4, y1 - y0, 6),
      ...box(tone, 0, y0, 6, d, y1 - y0, h - 10),
      ...box("white", 0, y0 - 1, h - 4, d + 3, y1 - y0 + 2, 4),
    ]),
    part(
      "cabinet-detail",
      [
        ...seams.map((y) => line("dk-seam", [d + 0.2, y, 8], [d + 0.2, y, h - 6])),
        ...mids.map((y) => onX("rs-handle", d + 0.3, y - 5, y + 5, h - 13, h - 11)),
      ],
      true,
    ),
  ];
}

/** Wall cabinets hung on the right wall. */
export function upperRight(x0: number, x1: number, doors = 2, z0 = 96, z1 = 140): Part[] {
  const d = 22;
  const seams = steps(x0, x1, doors - 1);
  return [
    part("upper-cabinet", box("slate", x0, 0, z0, x1 - x0, d, z1 - z0)),
    part(
      "upper-detail",
      [
        ...seams.map((x) => line("dk-seam", [x, d + 0.2, z0 + 2], [x, d + 0.2, z1 - 2])),
        ...[x0, ...seams].map((x) => onY("rs-handle", d + 0.3, x + 4, x + 6, z0 + 5, z0 + 15)),
      ],
      true,
    ),
  ];
}

/** A sink set into a counter on the right wall, with its faucet. */
export function sinkRight(xc: number, top = 56, d = 42): Part[] {
  return [
    part("sink", [
      onZ("rs-basin", top + 0.2, xc - 17, 12, 34, d - 20),
      ...box("metal", xc - 2, 4, top, 4, 4, 13),
      ...box("metal", xc - 2, 4, top + 11, 4, 12, 2),
    ]),
  ];
}

/** A range between cabinets: cooktop with burners, an oven door with a window and a handle. */
export function rangeRight(x0: number, w = 50, d = 43, h = 56): Part[] {
  const burners = [
    [x0 + 8, 6],
    [x0 + w - 20, 6],
    [x0 + 8, d - 20],
    [x0 + w - 20, d - 20],
  ] as const;
  return [
    part("range", [
      contact(x0, 0, w, d),
      ...box("metal", x0, 0, 0, w, d, h),
      onZ("rs-cooktop", h + 0.2, x0 + 3, 2, w - 6, d - 5),
      ...box("metal", x0, 0, h, w, 5, 9),
    ]),
    part(
      "range-detail",
      [
        ...burners.map(([x, y]) => onZ("rs-burner", h + 0.3, x, y, 12, 12)),
        onY("rs-oven", d + 0.2, x0 + 6, x0 + w - 6, 12, h - 16),
        onY("rs-handle", d + 0.3, x0 + 6, x0 + w - 6, h - 12, h - 10),
      ],
      true,
    ),
    part("hood", [
      ...box("metal", x0 + 2, 0, 104, w - 4, 30, 8),
      ...box("metal", x0 + 14, 0, 112, w - 28, 16, 30),
    ]),
  ];
}

/** A fridge: a tall box with a freezer drawer line and two handles. */
export function fridgeRight(x0: number, w = 54, d = 50, h = 128): Part[] {
  const split = h * 0.34;
  return [
    part("fridge", [contact(x0, 0, w, d), ...box("metal", x0, 0, 0, w, d, h)]),
    part(
      "fridge-detail",
      [
        line("dk-seam", [x0, d + 0.2, split], [x0 + w, d + 0.2, split]),
        onY("rs-handle", d + 0.3, x0 + 6, x0 + 8, split + 8, split + 44),
        onY("rs-handle", d + 0.3, x0 + 10, x0 + w - 10, split - 8, split - 6),
      ],
      true,
    ),
  ];
}

/** A kitchen island with an overhanging top and two stools. */
export function island(x: number, y: number, w: number, d: number): Part[] {
  const stool = (sx: number): Prim[] => [
    ...box("dark", sx + 5, y + d + 15, 0, 3, 3, 30),
    ...box("wood", sx, y + d + 10, 30, 14, 14, 4),
  ];
  return [
    part("island", [
      contact(x, y, w, d),
      ...box("dark", x + 3, y + 3, 0, w - 6, d - 6, 6),
      ...box("pale", x, y, 6, w, d, 46),
      ...box("white", x - 4, y - 3, 52, w + 8, d + 12, 4),
    ]),
    part("stools", [...stool(x + 22), ...stool(x + w - 38)], true),
  ];
}

// ---------- Bathroom ----------

/** A bathtub along the left wall, with water-coloured basin and a tap. */
export function tubLeft(y0: number, y1: number): Part[] {
  return [
    part("tub", [
      contact(0, y0, 62, y1 - y0),
      ...box("white", 0, y0, 0, 62, y1 - y0, 44),
      onZ("rs-basin", 44.2, 7, y0 + 7, 48, y1 - y0 - 14),
      onZ("rs-water", 44.3, 11, y0 + 11, 40, y1 - y0 - 22),
      ...box("metal", 4, y0 + 10, 44, 4, 4, 10),
      ...box("metal", 4, y0 + 10, 52, 10, 4, 2),
    ]),
  ];
}

export function toilet(x: number): Part[] {
  return [
    part("toilet", [
      contact(x, 0, 34, 54),
      ...box("white", x, 0, 0, 34, 16, 62),
      ...box("white", x + 4, 16, 0, 26, 38, 28),
      onZ("rs-basin", 28.2, x + 8, 22, 18, 26),
      ...box("metal", x + 14, 4, 62, 6, 4, 2),
    ]),
  ];
}

/** A mirror hung on the right wall. */
export const mirrorRight = (x0: number, x1: number, z0: number, z1: number): Part =>
  part("mirror", [
    onY("rs-trim", 0.3, x0 - 3, x1 + 3, z0 - 3, z1 + 3),
    onY("rs-mirror", 0.4, x0, x1, z0, z1),
    poly(
      "rs-shine",
      [x0 + 8, 0.5, z0 + 6],
      [x0 + 20, 0.5, z0 + 6],
      [x0 + 40, 0.5, z1 - 6],
      [x0 + 28, 0.5, z1 - 6],
    ),
  ]);

// ---------- Bedroom ----------

export function bed(x: number, w = 150, len = 176): Part[] {
  const pillow = (px: number): Prim[] => box("white", px, 16, 32, w / 2 - 14, 30, 9);
  return [
    part("bed", [
      contact(x - 4, 0, w + 8, len + 10),
      ...box("wood", x - 4, 0, 0, w + 8, 10, 80),
      ...box("wood", x - 4, 10, 0, w + 8, len, 14),
      ...box("white", x, 10, 14, w, len - 4, 18),
      ...pillow(x + 8),
      ...pillow(x + w / 2 + 6),
      ...box("cloth", x - 1, 66, 30, w + 2, len - 60, 6),
      ...box("white", x - 1, 58, 32, w + 2, 12, 5),
    ]),
  ];
}

export function nightstand(x: number): Part[] {
  return [
    part("nightstand", [contact(x, 0, 34, 32), ...box("wood", x, 0, 0, 34, 32, 38)]),
    part(
      "lamp",
      [
        line("dk-seam", [x, 32.2, 20], [x + 34, 32.2, 20]),
        ...box("metal", x + 15, 12, 38, 4, 4, 12),
        ...box("white", x + 9, 6, 50, 16, 16, 14),
      ],
      true,
    ),
  ];
}

/** Sliding closet doors set flat on the left wall. */
export function closetLeft(y0: number, y1: number, h = 128): Part[] {
  const mid = (y0 + y1) / 2;
  return [
    part("closet", [
      onX("rs-trim", 0.3, y0 - 5, y1 + 5, 0, h + 5),
      onX("rs-closet", 0.4, y0, y1, 0, h),
    ]),
    part(
      "closet-detail",
      [
        line("dk-seam", [0.5, mid, 0], [0.5, mid, h]),
        onX("rs-handle", 0.6, mid - 8, mid - 6, h * 0.4, h * 0.56),
        onX("rs-handle", 0.6, mid + 6, mid + 8, h * 0.4, h * 0.56),
      ],
      true,
    ),
  ];
}

// ---------- Living room and hall ----------

export function sofa(x: number, w = 180): Part[] {
  const seat = (w - 28) / 2;
  return [
    part("sofa", [
      contact(x, 0, w, 62),
      ...box("slate", x, 0, 0, w, 16, 74),
      ...box("slate", x, 16, 0, 14, 46, 56),
      ...box("slate", x + 14, 16, 0, w - 28, 46, 30),
      ...box("pale", x + 15, 17, 30, seat - 1, 44, 9),
      ...box("pale", x + 15 + seat, 17, 30, seat - 1, 44, 9),
      ...box("pale", x + 16, 16, 39, seat - 3, 10, 30),
      ...box("pale", x + 16 + seat, 16, 39, seat - 3, 10, 30),
      ...box("slate", x + w - 14, 16, 0, 14, 46, 56),
    ]),
  ];
}

export function coffeeTable(x: number, y: number, w = 92, d = 50): Part[] {
  const leg = (lx: number, ly: number): Prim[] => box("dark", lx, ly, 0, 4, 4, 22);
  return [
    part("coffee-table", [
      contact(x, y, w, d),
      ...leg(x + 3, y + 3),
      ...leg(x + w - 7, y + 3),
      ...leg(x + 3, y + d - 7),
      ...leg(x + w - 7, y + d - 7),
      ...box("wood", x, y, 22, w, d, 5),
    ]),
    part(
      "table-things",
      [
        ...box("teal", x + 20, y + 14, 27, 26, 18, 3),
        ...box("white", x + 58, y + 20, 27, 12, 12, 8),
      ],
      true,
    ),
  ];
}

/** A low media unit along the left wall with a screen on it. */
export function tvUnitLeft(y0: number, y1: number): Part[] {
  return [
    part("tv-unit", [
      contact(0, y0, 34, y1 - y0),
      ...box("wood", 0, y0, 0, 34, y1 - y0, 38),
      ...box("dark", 10, y0 + 30, 38, 8, y1 - y0 - 60, 3),
      ...box("dark", 12, y0 + 8, 41, 4, y1 - y0 - 16, 46),
    ]),
    part("tv-detail", [line("dk-seam", [34.2, (y0 + y1) / 2, 4], [34.2, (y0 + y1) / 2, 34])], true),
  ];
}

export function plant(x: number, y: number): Part[] {
  return [
    part("plant", [
      contact(x, y, 22, 22),
      ...box("white", x, y, 0, 22, 22, 24),
      ...box("green", x + 3, y + 3, 24, 16, 16, 26),
      ...box("green", x - 3, y + 7, 40, 14, 10, 24),
      ...box("green", x + 10, y - 2, 46, 12, 12, 26),
    ]),
  ];
}

export function floorLamp(x: number, y: number): Part[] {
  return [
    part("floor-lamp", [
      ...box("dark", x - 6, y - 6, 0, 16, 16, 2),
      ...box("dark", x, y, 2, 3, 3, 104),
      ...box("white", x - 8, y - 8, 106, 19, 19, 20),
    ]),
  ];
}

export function armchair(x: number, y: number): Part[] {
  return [
    part("armchair", [
      contact(x, y, 60, 56),
      ...box("slate", x, y, 0, 60, 14, 64),
      ...box("slate", x, y + 14, 0, 10, 42, 46),
      ...box("slate", x + 10, y + 14, 0, 40, 42, 28),
      ...box("pale", x + 11, y + 15, 28, 38, 40, 8),
      ...box("slate", x + 50, y + 14, 0, 10, 42, 46),
    ]),
  ];
}

/** A sideboard or console along the right wall. */
export function sideboardRight(x0: number, x1: number, h = 46): Part[] {
  const seams = steps(x0, x1, 2);
  return [
    part("sideboard", [
      contact(x0, 0, x1 - x0, 34),
      ...box("dark", x0 + 4, 4, 0, x1 - x0 - 8, 26, 8),
      ...box("wood", x0, 0, 8, x1 - x0, 34, h - 8),
    ]),
    part(
      "sideboard-detail",
      [
        ...seams.map((x) => line("dk-seam", [x, 34.2, 10], [x, 34.2, h - 2])),
        ...box("white", x0 + 12, 8, h, 14, 14, 16),
        ...box("teal", x1 - 44, 10, h, 28, 16, 4),
      ],
      true,
    ),
  ];
}

/** A hall bench with shoes under it, and a row of hooks with coats above. */
export function hallBench(x0: number, x1: number): Part[] {
  return [
    part("bench", [
      contact(x0, 0, x1 - x0, 34),
      ...box("dark", x0 + 2, 6, 0, 4, 26, 30),
      ...box("dark", x1 - 6, 6, 0, 4, 26, 30),
      ...box("wood", x0, 0, 30, x1 - x0, 34, 6),
    ]),
    part(
      "bench-detail",
      [
        ...box("slate", x0 + 14, 10, 0, 16, 22, 8),
        ...box("white", x0 + 36, 10, 0, 16, 22, 8),
        onY("rs-handle", 0.4, x0, x1, 104, 107),
        ...box("slate", x0 + 10, 0.5, 62, 18, 5, 42),
        ...box("teal", x0 + 40, 0.5, 70, 16, 5, 34),
      ],
      true,
    ),
  ];
}
