// The crew scene's setting, drawn with the app's drawing kit (draw/kit.ts): the plot's lawn with
// its mowing stripes, tufts and a paved path, the home, and behind it a street of neighbours
// and trees. Pure and fixed: nothing here is random and nothing reads the run. The scene fades
// the backdrop with distance (CrewScene.tsx, crew.css), so the crew stays the subject.
import { makeScene, part, type Part, type Prim, type Tone } from "../draw/kit";
import { HOME, ORIGIN, PLOT } from "./crew";

// The front path: from the door in the home's gable end out to the street.
const DOOR_Y = HOME.y + HOME.d * 0.675;
export const PATH = { x: HOME.x + HOME.w, y: DOOR_Y - 7, w: PLOT - HOME.x - HOME.w, d: 14 };
// The street runs along three sides of the plot: behind it on both far sides and down the
// front right, where the path meets it.
const WALK = 10; // sidewalk width
const ROAD = 30; // street width
const FAR = -112; // how far back the drawn world goes

export interface Lot {
  x: number;
  y: number;
  w: number;
  d: number;
  h: number;
  roof: Tone;
}

// The neighbours, across the street on the two far sides. Far to near.
const NEIGHBOURS: Lot[] = [
  { x: -104, y: 18, w: 46, d: 38, h: 20, roof: "slate" },
  { x: 16, y: -104, w: 40, d: 46, h: 20, roof: "wood" },
  { x: -106, y: 108, w: 48, d: 40, h: 22, roof: "wood" },
  { x: 108, y: -106, w: 40, d: 48, h: 22, roof: "slate" },
  { x: -104, y: 204, w: 46, d: 38, h: 20, roof: "slate" },
  { x: 204, y: -104, w: 38, d: 46, h: 20, roof: "wood" },
];

const TREES: [x: number, y: number, s: number][] = [
  [-96, -70, 0.9],
  [-66, -98, 0.8],
  [-60, 76, 0.8],
  [78, -60, 0.8],
  [-64, 174, 0.9],
  [176, -62, 0.9],
  [-58, 262, 1],
  [286, 60, 1],
];

/** Where the grass tufts stand: a fixed scatter over the lawn, off the home and the path. */
export function tuftSpots(): [number, number][] {
  const out: [number, number][] = [];
  let seed = 7;
  const next = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  while (out.length < 44) {
    const x = Math.round((6 + next() * (PLOT - 12)) * 10) / 10;
    const y = Math.round((6 + next() * (PLOT - 12)) * 10) / 10;
    const onHome =
      x > HOME.x - 6 && x < HOME.x + HOME.w + 14 && y > HOME.y - 6 && y < HOME.y + HOME.d + 14;
    const onPath = x > PATH.x - 4 && y > PATH.y - 4 && y < PATH.y + PATH.d + 4;
    if (!onHome && !onPath) out.push([x, y]);
  }
  return out;
}

export interface Scenery {
  streets: Part[]; // the streets and sidewalks round the plot
  backdrop: Part[]; // the neighbours across the street: behind the plot, faded with distance
  verge: Part[]; // what stands on the near side of the street, in front of the plot
  lawn: Part[]; // the plot's ground
  home: Part[]; // the home in the ad
  shadow: Prim; // the home's shadow on the lawn, drawn soft
  neighbours: Lot[];
}

export function crewScenery(): Scenery {
  const s = makeScene(ORIGIN);
  const near = PLOT + WALK + ROAD;

  // ---- behind the plot ----
  const streets: Part[] = [
    // Far left and far right: the two streets that meet behind the Planner.
    part("street", [s.onZ("dk-asphalt", 0, -WALK - ROAD, FAR, ROAD, near - FAR)]),
    part("street", [s.onZ("dk-asphalt", 0, FAR, -WALK - ROAD, near - FAR, ROAD)]),
    // Front right: the street the path leads to.
    part("street", [s.onZ("dk-asphalt", 0, PLOT + WALK, -WALK, ROAD, 340)]),
    part("sidewalk", [s.onZ("dk-path", 0, -WALK, -WALK, WALK, PLOT + WALK + 120)]),
    part("sidewalk", [s.onZ("dk-path", 0, -WALK, -WALK, PLOT + WALK * 2, WALK)]),
    part("sidewalk", [s.onZ("dk-path", 0, PLOT, 0, WALK, 330)]),
    part(
      "street-lines",
      [
        ...[-90, -62, 20, 48, 76, 104, 132, 160, 188].map((v) =>
          s.line("dk-paint", [-WALK - ROAD / 2, v, 0.1], [-WALK - ROAD / 2, v + 14, 0.1]),
        ),
        ...[-90, -62, 20, 48, 76, 104, 132, 160, 188].map((v) =>
          s.line("dk-paint", [v, -WALK - ROAD / 2, 0.1], [v + 14, -WALK - ROAD / 2, 0.1]),
        ),
        ...[10, 38, 66, 94, 150, 178, 206, 234].map((v) =>
          s.line(
            "dk-paint",
            [PLOT + WALK + ROAD / 2, v, 0.1],
            [PLOT + WALK + ROAD / 2, v + 14, 0.1],
          ),
        ),
      ],
      true,
    ),
  ];
  const far: { depth: number; parts: Part[] }[] = [
    ...NEIGHBOURS.map((n) => ({
      depth: n.x + n.y,
      parts: [
        part("neighbour-lot", [s.onZ("cs-lot", 0.02, n.x - 8, n.y - 8, n.w + 22, n.d + 22)]),
        ...s
          .house(n.x, n.y, n.w, n.d, n.h, "white", n.roof)
          .map((p) => ({ ...p, name: p.name === "house" ? "neighbour" : `neighbour-${p.name}` })),
      ],
    })),
    ...TREES.filter(([x, y]) => x < 0 || y < 0).map(([x, y, k]) => ({
      depth: x + y,
      parts: [{ ...s.tree(x, y, k), name: "backdrop-tree" }],
    })),
    { depth: -WALK - ROAD + 40, parts: [{ ...s.car("pale", -WALK - ROAD + 4, 52), name: "car" }] },
  ].sort((a, b) => a.depth - b.depth);
  const verge: Part[] = [
    { ...s.car("metal", PLOT + WALK + 17, 172), name: "car" },
    ...TREES.filter(([x, y]) => x >= 0 && y >= 0).map(([x, y, k]) => s.tree(x, y, k)),
  ];

  // ---- the plot ----
  const bands = 11;
  const band = PLOT / bands;
  const stripes = Array.from({ length: bands }, (_, i) =>
    part("stripe", [s.onZ(i % 2 === 0 ? "cs-lawn-a" : "cs-lawn-b", 0.02, i * band, 0, band, PLOT)]),
  );
  const tufts = tuftSpots().flatMap(([x, y], i): Prim[] => [
    s.line("cs-tuft", [x, y, 0], [x - 0.6, y + 0.6, 2.6]),
    s.line("cs-tuft", [x + 1.2, y - 1.2, 0], [x + 2, y - 2, i % 3 === 0 ? 3.2 : 2.2]),
  ]);
  const bed = { x: HOME.x - 5, y: HOME.y + HOME.d, w: HOME.w * 0.82, d: 7 };
  const blooms = [0.1, 0.24, 0.4, 0.55, 0.7, 0.86].map((f, i) =>
    s.dot(i % 2 === 0 ? "cs-bloom" : "cs-bloom-warm", [bed.x + bed.w * f, bed.y + 3.6, 5.4], 1.3),
  );
  const lawn: Part[] = [
    part("plot", [s.onZ("dk-lawn", 0.01, 0, 0, PLOT, PLOT)]),
    ...stripes,
    // Where the afternoon light pools, and where the tree keeps the grass dark.
    part("sun-patch", [
      s.poly(
        "cs-lawn-sun",
        [14, 128, 0.03],
        [52, 112, 0.03],
        [70, 150, 0.03],
        [44, 196, 0.03],
        [12, 178, 0.03],
      ),
      s.poly("cs-lawn-sun", [150, 18, 0.03], [196, 26, 0.03], [204, 62, 0.03], [166, 70, 0.03]),
    ]),
    part("path", [
      s.onZ("dk-path", 0.04, PATH.x, PATH.y, PATH.w, PATH.d),
      // The step at the door.
      ...s.box("white", PATH.x, PATH.y + 1, 0, 5, PATH.d - 2, 1.6),
    ]),
    part("pavers", s.tile(PATH.x + 5, PATH.y, PATH.w - 5, PATH.d, 13, 0.06), true),
    part("tufts", tufts, true),
    // A clipped hedge along the two far sides, between the lawn and the street.
    s.shrub(0, 0, PLOT, 4, 6),
    s.shrub(0, 4, 4, PLOT - 4, 6),
    s.tree(58, 58, 0.95),
  ];
  const home: Part[] = [
    ...s.house(HOME.x, HOME.y, HOME.w, HOME.d, HOME.h, "white", "slate"),
    // A chimney on the far slope.
    part(
      "chimney",
      s.box("wood", HOME.x + HOME.w * 0.22, HOME.y + HOME.d * 0.3, HOME.h, 6, 6, HOME.h * 0.78),
    ),
    part("bed", [s.onZ("cs-soil", 0.05, bed.x, bed.y, bed.w, bed.d)]),
    s.shrub(bed.x + 1, bed.y + 1.5, bed.w - 2, 4, 4.4),
    part("blooms", blooms, true),
    s.tree(158, 156, 0.72),
  ];
  // The home's shadow: longer than the kit's contact shadow, for a low warm sun.
  const reach = 20;
  const shadow = s.poly(
    "cs-cast",
    [HOME.x + 6, HOME.y + HOME.d, 0.08],
    [HOME.x + HOME.w, HOME.y + 6, 0.08],
    [HOME.x + HOME.w + reach, HOME.y + reach, 0.08],
    [HOME.x + HOME.w + reach, HOME.y + HOME.d + reach, 0.08],
    [HOME.x + reach, HOME.y + HOME.d + reach, 0.08],
  );
  return {
    streets,
    backdrop: far.flatMap((f) => f.parts),
    verge,
    lawn,
    home,
    shadow,
    neighbours: NEIGHBOURS,
  };
}
