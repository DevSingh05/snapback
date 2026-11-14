// The drawing kit: every drawn 3D scene in the app (walk rooms, the house glyph, the aerial
// stand-ins, map buildings) is built from these parts so they share one light and one look.
//
// HOW TO USE
//   const s = makeScene({ ox: 200, oy: 80 });          // where room point (0,0,0) sits in the SVG
//   const parts: Part[] = [
//     part("lawn", [s.onZ("dk-lawn", 0, -20, -20, 140, 140)]),
//     part("house", [s.contact(0, 0, 60, 40), ...s.box("white", 0, 0, 0, 60, 40, 30)]),
//     part("siding", s.sidingY(40, 0, 60, 0, 30), true),  // fine detail: hidden when small
//     ...s.gableRoof("slate", 0, 0, 30, 60, 40, 18),
//     ...s.house(80, 0, 60, 46, 24),                      // or a whole small house in one call
//   ];
//   <svg viewBox="..."><Parts parts={parts} /></svg>        // draw/Parts.tsx; import draw/draw.css
//
// AXES   x runs down-right, y runs down-left, z is up (2:1 isometric). The viewer stands at
//        +x, +y, so list parts far to near: smaller x + y first, and lower before higher.
// LIGHT  one direction everywhere. Tops are lightest, faces toward +y are mid, faces toward +x
//        are darkest; `contact` casts a soft floor shadow toward +x, +y.
// COLOUR nothing here names a colour. Each shape carries classes from draw.css (`dk-top`,
//        `dk-left`, `dk-right` plus a tone such as `dk-slate`), and every fill there is a token
//        from styles/tokens.css, so light and dark follow for free. No red, no amber.
// DETAIL mark small detail `fine` (third argument of `part`). Put `data-detail="low"` on any
//        ancestor (or use it at small sizes) and draw.css hides fine parts.
// Team-made drawings only: never trace or embed sponsor imagery here.

export const K = 0.866;
export type P3 = [number, number, number];

export interface Origin {
  ox: number;
  oy: number;
}

export type Tone =
  | "slate" // roofs, dark cabinets, sofas
  | "pale" // light blue: glass-like blocks, neighbours
  | "white" // walls, porcelain, bedding
  | "green" // planting
  | "wood" // warm timber, siding shade
  | "dark" // near-ink: legs, plinths, screens
  | "metal" // appliances, taps, rooftop units
  | "teal" // the one accent: doors, small objects
  | "cloth"; // soft teal-blue fabric

export type Prim =
  | { k: "poly"; pts: string; c: string }
  | { k: "line"; x1: number; y1: number; x2: number; y2: number; c: string };

/** One named thing in a scene. `fine` parts are small detail, dropped at small sizes. */
export interface Part {
  name: string;
  fine?: boolean;
  prims: Prim[];
}

export const part = (name: string, prims: Prim[], fine = false): Part => ({ name, prims, fine });

/** n evenly spaced values strictly between `from` and `to`. */
export const between = (from: number, to: number, n: number): number[] =>
  Array.from({ length: Math.max(0, n) }, (_, i) => from + ((to - from) * (i + 1)) / (n + 1));

export function project([x, y, z]: P3, { ox, oy }: Origin): [number, number] {
  return [ox + (x - y) * K, oy + (x + y) * 0.5 - z];
}

export type Scene = ReturnType<typeof makeScene>;

export function makeScene(o: Origin) {
  const str = (ps: P3[]) =>
    ps
      .map((p) => project(p, o))
      .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
      .join(" ");

  /** Any flat shape from its corners. */
  const poly = (c: string, ...ps: P3[]): Prim => ({ k: "poly", pts: str(ps), c });

  const line = (c: string, a: P3, b: P3): Prim => {
    const [x1, y1] = project(a, o);
    const [x2, y2] = project(b, o);
    return { k: "line", x1, y1, x2, y2, c };
  };

  /** A rectangle on the plane y = const (it faces +y, the mid-lit side). */
  const onY = (c: string, y: number, x0: number, x1: number, z0: number, z1: number) =>
    poly(c, [x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]);

  /** A rectangle on the plane x = const (it faces +x, the shaded side). */
  const onX = (c: string, x: number, y0: number, y1: number, z0: number, z1: number) =>
    poly(c, [x, y0, z0], [x, y1, z0], [x, y1, z1], [x, y0, z1]);

  /** A rectangle lying flat at height z. */
  const onZ = (c: string, z: number, x: number, y: number, w: number, d: number) =>
    poly(c, [x, y, z], [x + w, y, z], [x + w, y + d, z], [x, y + d, z]);

  /** The three visible faces of a box, shaded by the one light. */
  const box = (tone: Tone, x: number, y: number, z: number, w: number, d: number, h: number) => [
    onY(`dk-left dk-${tone}`, y + d, x, x + w, z, z + h),
    onX(`dk-right dk-${tone}`, x + w, y, y + d, z, z + h),
    onZ(`dk-top dk-${tone}`, z + h, x, y, w, d),
  ];

  /** A soft contact shadow on the ground for a footprint, cast away from the light. `reach`
   *  grows with the height of the thing casting it. */
  const contact = (x: number, y: number, w: number, d: number, reach = 9, z = 0.1): Prim =>
    poly(
      "dk-contact",
      [x + 4, y + d, z],
      [x + w, y + 4, z],
      [x + w + reach, y + reach, z],
      [x + w + reach, y + d + reach, z],
      [x + reach, y + d + reach, z],
    );

  // ---- Materials: fine line work laid over a surface ----

  /** Floor boards running along x, with staggered board ends. */
  const planks = (x: number, y: number, w: number, d: number, step = 25): Prim[] => {
    const out: Prim[] = [];
    for (let row = 0; row * step < d; row++) {
      const v = y + row * step;
      if (row > 0) out.push(line("dk-seam", [x, v, 0], [x + w, v, 0]));
      for (const f of row % 2 === 0 ? [0.3, 0.77] : [0.13, 0.53, 0.9])
        out.push(line("dk-seam", [x + w * f, v, 0], [x + w * f, Math.min(v + step, y + d), 0]));
    }
    return out;
  };

  /** A square grid on the floor (tile, paving). */
  const tile = (x: number, y: number, w: number, d: number, step = 30, z = 0): Prim[] => {
    const out: Prim[] = [];
    for (let v = step; v < d; v += step)
      out.push(line("dk-seam", [x, y + v, z], [x + w, y + v, z]));
    for (let v = step; v < w; v += step)
      out.push(line("dk-seam", [x + v, y, z], [x + v, y + d, z]));
    return out;
  };

  /** Horizontal courses on a wall facing +y (siding, brick courses, wall tile). */
  const coursesY = (y: number, x0: number, x1: number, z0: number, z1: number, step = 5): Prim[] =>
    between(z0, z1, Math.floor((z1 - z0) / step) - 1).map((z) =>
      line("dk-seam", [x0, y, z], [x1, y, z]),
    );

  /** Horizontal courses on a wall facing +x. */
  const coursesX = (x: number, y0: number, y1: number, z0: number, z1: number, step = 5): Prim[] =>
    between(z0, z1, Math.floor((z1 - z0) / step) - 1).map((z) =>
      line("dk-seam", [x, y0, z], [x, y1, z]),
    );

  // ---- Openings: framed, with glass and mullions ----

  /** A window on a wall facing +y: trim, glass, a sill and (fine) mullions. */
  const windowY = (y: number, x0: number, x1: number, z0: number, z1: number, t = 1.2): Part[] => [
    part("window", [
      onY("dk-trim", y + 0.1, x0 - t, x1 + t, z0 - t, z1 + t),
      onY("dk-glass", y + 0.2, x0, x1, z0, z1),
      onY("dk-trim", y + 0.3, x0 - t * 1.6, x1 + t * 1.6, z0 - t * 1.8, z0 - t * 0.6),
    ]),
    part(
      "window-detail",
      [
        line("dk-mullion", [(x0 + x1) / 2, y + 0.3, z0], [(x0 + x1) / 2, y + 0.3, z1]),
        line("dk-mullion", [x0, y + 0.3, (z0 + z1) / 2], [x1, y + 0.3, (z0 + z1) / 2]),
      ],
      true,
    ),
  ];

  /** A window on a wall facing +x. */
  const windowX = (x: number, y0: number, y1: number, z0: number, z1: number, t = 1.2): Part[] => [
    part("window", [
      onX("dk-trim-shade", x + 0.1, y0 - t, y1 + t, z0 - t, z1 + t),
      onX("dk-glass-shade", x + 0.2, y0, y1, z0, z1),
      onX("dk-trim-shade", x + 0.3, y0 - t * 1.6, y1 + t * 1.6, z0 - t * 1.8, z0 - t * 0.6),
    ]),
    part(
      "window-detail",
      [
        line("dk-mullion", [x + 0.3, (y0 + y1) / 2, z0], [x + 0.3, (y0 + y1) / 2, z1]),
        line("dk-mullion", [x + 0.3, y0, (z0 + z1) / 2], [x + 0.3, y1, (z0 + z1) / 2]),
      ],
      true,
    ),
  ];

  /** A door on a wall facing +x: trim, the door in the accent, two panels and a handle. */
  const doorX = (x: number, y0: number, y1: number, h: number, t = 1.2): Part[] => [
    part("door", [
      onX("dk-trim-shade", x + 0.1, y0 - t, y1 + t, 0, h + t),
      onX("dk-door", x + 0.2, y0, y1, 0, h),
    ]),
    part(
      "door-detail",
      [
        onX("dk-door-panel", x + 0.3, y0 + t, y1 - t, h * 0.52, h - t),
        onX("dk-door-panel", x + 0.3, y0 + t, y1 - t, t, h * 0.46),
        onX("dk-handle", x + 0.4, y1 - t * 1.6, y1 - t * 0.8, h * 0.44, h * 0.52),
      ],
      true,
    ),
  ];

  // ---- Roofs ----

  /** A gable roof over a w x d footprint whose walls end at height z. The ridge runs along x.
   *  Draws the far slope, the gable end above the +x wall, the near slope with its shingle
   *  courses and a fascia, with `over` units of overhang all round. */
  const gableRoof = (
    tone: Tone,
    x: number,
    y: number,
    z: number,
    w: number,
    d: number,
    rise: number,
    over = 2,
    wall: Tone = "white",
  ): Part[] => {
    const mid = y + d / 2;
    const drop = (rise * over) / (d / 2); // the eave sits a little below the wall top
    const x0 = x - over;
    const x1 = x + w + over;
    const yFar = y - over;
    const yNear = y + d + over;
    const eave = z - drop;
    const courses = between(0, 1, Math.max(2, Math.round(d / 7))).map((f) =>
      line(
        "dk-seam",
        [x0, mid + (yNear - mid) * f, z + rise - (z + rise - eave) * f],
        [x1, mid + (yNear - mid) * f, z + rise - (z + rise - eave) * f],
      ),
    );
    return [
      part("roof-far", [
        poly(
          `dk-right dk-${tone}`,
          [x0, yFar, eave],
          [x1, yFar, eave],
          [x1, mid, z + rise],
          [x0, mid, z + rise],
        ),
      ]),
      part("gable", [
        poly(`dk-right dk-${wall}`, [x + w, y, z], [x + w, y + d, z], [x + w, mid, z + rise]),
      ]),
      part("roof", [
        poly(
          `dk-top dk-${tone}`,
          [x0, mid, z + rise],
          [x1, mid, z + rise],
          [x1, yNear, eave],
          [x0, yNear, eave],
        ),
        // Fascia along the near eave and the roof's cut edge at the gable end.
        poly(
          `dk-left dk-${tone}`,
          [x0, yNear, eave],
          [x1, yNear, eave],
          [x1, yNear, eave - 1.4],
          [x0, yNear, eave - 1.4],
        ),
        poly(
          `dk-right dk-${tone}`,
          [x1, yNear, eave],
          [x1, mid, z + rise],
          [x1, mid, z + rise - 1.4],
          [x1, yNear, eave - 1.4],
        ),
        poly(
          `dk-right dk-${tone}`,
          [x1, yFar, eave],
          [x1, mid, z + rise],
          [x1, mid, z + rise - 1.4],
          [x1, yFar, eave - 1.4],
        ),
      ]),
      part("shingles", courses, true),
    ];
  };

  /** A flat roof with a parapet, as on an apartment block. */
  const flatRoof = (
    tone: Tone,
    x: number,
    y: number,
    z: number,
    w: number,
    d: number,
    lip = 3,
  ): Part[] => [
    part("roof", [
      ...box(tone, x, y, z, w, d, lip),
      onZ("dk-roof-deck", z + lip - 1.2, x + lip, y + lip, w - lip * 2, d - lip * 2),
      onY("dk-roof-inner-left", y + lip, x + lip, x + w - lip, z + lip - 1.2, z + lip),
      onX("dk-roof-inner-right", x + lip, y + lip, y + d - lip, z + lip - 1.2, z + lip),
    ]),
  ];

  /** A small gabled house: shaded walls with a ground shadow, two windows on the long wall, a
   *  door on the gable end and a shingled roof. `roof` picks the roof tone ("teal" lights it). */
  const house = (
    x: number,
    y: number,
    w: number,
    d: number,
    h: number,
    walls: Tone = "white",
    roof: Tone = "slate",
  ): Part[] => [
    part("house", [contact(x, y, w, d, 10), ...box(walls, x, y, 0, w, d, h)]),
    ...windowY(y + d, x + w * 0.16, x + w * 0.4, h * 0.4, h * 0.78, 1),
    ...windowY(y + d, x + w * 0.6, x + w * 0.84, h * 0.4, h * 0.78, 1),
    ...doorX(x + w, y + d * 0.55, y + d * 0.8, h * 0.66, 1),
    ...gableRoof(roof, x, y, h, w, d, h * 0.7, 3, walls),
  ];

  // ---- Outdoors ----

  /** A blocky tree: a trunk and stacked crowns. `s` scales it. */
  const tree = (x: number, y: number, s = 1): Part =>
    part("tree", [
      contact(x - 4 * s, y - 4 * s, 12 * s, 12 * s, 6 * s),
      ...box("wood", x, y, 0, 3 * s, 3 * s, 8 * s),
      ...box("green", x - 5 * s, y - 5 * s, 7 * s, 13 * s, 13 * s, 9 * s),
      ...box("green", x - 3 * s, y - 3 * s, 16 * s, 9 * s, 9 * s, 7 * s),
    ]);

  /** A low hedge or shrub. */
  const shrub = (x: number, y: number, w: number, d: number, h = 4): Part =>
    part("shrub", [contact(x, y, w, d, 3), ...box("green", x, y, 0, w, d, h)]);

  /** Painted parking bays along x: a strip of asphalt with bay lines. */
  const parking = (x: number, y: number, w: number, d: number, bays: number): Part[] => [
    part("parking", [onZ("dk-asphalt", 0.05, x, y, w, d)]),
    part(
      "parking-lines",
      [x, ...between(x, x + w, bays - 1), x + w].map((v) =>
        line("dk-paint", [v, y + 1, 0.1], [v, y + d * 0.72, 0.1]),
      ),
      true,
    ),
  ];

  /** A small parked car. */
  const car = (tone: Tone, x: number, y: number): Part =>
    part("car", [
      contact(x, y, 9, 18, 3),
      ...box(tone, x, y, 1, 9, 18, 4),
      ...box("dark", x + 1, y + 4, 5, 7, 9, 3),
    ]);

  return {
    poly,
    line,
    onX,
    onY,
    onZ,
    box,
    contact,
    planks,
    tile,
    coursesX,
    coursesY,
    windowX,
    windowY,
    doorX,
    gableRoof,
    flatRoof,
    house,
    tree,
    shrub,
    parking,
    car,
  };
}
