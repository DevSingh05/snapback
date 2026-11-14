import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { O } from "../walk/roomParts";
import { drawRoom, type RoomKind } from "../walk/rooms";
import { HERE_SPOT } from "../walk/StopStage";
import { personPrims } from "./Person";
import { between, makeScene, project } from "./kit";

const s = makeScene({ ox: 100, oy: 50 });
const names = (kind: RoomKind) => {
  const room = drawRoom(kind);
  return [...room.base, ...room.things].map((p) => p.name);
};

describe("the drawing kit", () => {
  it("projects 2:1 isometric: x down-right, y down-left, z up", () => {
    expect(project([10, 0, 0], { ox: 0, oy: 0 })).toEqual([8.66, 5]);
    expect(project([0, 10, 0], { ox: 0, oy: 0 })).toEqual([-8.66, 5]);
    expect(project([0, 0, 10], { ox: 0, oy: 0 })).toEqual([0, -10]);
  });

  it("a box is three faces shaded by the one light: left, right, top", () => {
    const faces = s.box("slate", 0, 0, 0, 10, 10, 10);
    expect(faces.map((f) => f.c)).toEqual([
      "dk-left dk-slate",
      "dk-right dk-slate",
      "dk-top dk-slate",
    ]);
  });

  it("spaces values evenly, strictly inside the range", () => {
    expect(between(0, 30, 2)).toEqual([10, 20]);
    expect(between(0, 30, 0)).toEqual([]);
  });

  it("marks material line work and mullions as fine detail, never the big shapes", () => {
    const [win, detail] = s.windowY(0, 0, 10, 0, 10);
    expect(win!.fine).toBe(false);
    expect(detail!.fine).toBe(true);
    const roof = s.gableRoof("slate", 0, 0, 10, 20, 16, 8);
    expect(roof.find((p) => p.name === "shingles")!.fine).toBe(true);
    expect(roof.find((p) => p.name === "roof")!.fine).toBe(false);
  });

  it("names no colour: every fill and stroke in draw.css is a token", () => {
    const css = readFileSync(join(__dirname, "draw.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    expect(css.match(/#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/g)).toBeNull();
    for (const banned of ["--coral", "--v-dont-pay", "--amber", "--scan", "--warn", "--v-hold"])
      expect(css).not.toContain(banned);
  });
});

describe("the drawn rooms: real fixtures per room kind", () => {
  it("kitchen: cabinets with detail, a sink, a range with a hood, a fridge, an island", () => {
    expect(names("kitchen")).toEqual(
      expect.arrayContaining([
        "cabinet",
        "cabinet-detail",
        "upper-cabinet",
        "sink",
        "range",
        "hood",
        "fridge",
        "island",
        "window",
      ]),
    );
  });

  it("bathroom: a tub, a toilet, a vanity with a sink and a mirror, tile", () => {
    expect(names("bathroom")).toEqual(
      expect.arrayContaining(["tub", "toilet", "cabinet", "sink", "mirror", "wall-tile", "rug"]),
    );
  });

  it("bedroom: a bed, nightstands with lamps, a closet", () => {
    const n = names("bedroom");
    expect(n).toEqual(expect.arrayContaining(["bed", "lamp", "closet", "window"]));
    expect(n.filter((x) => x === "nightstand")).toHaveLength(2);
  });

  it("living room: a sofa, a rug, a coffee table, a TV unit", () => {
    expect(names("living")).toEqual(
      expect.arrayContaining(["sofa", "rug", "coffee-table", "tv-unit", "plant", "floor-lamp"]),
    );
  });

  it("entry and the fallback room are furnished too", () => {
    expect(names("entry")).toEqual(expect.arrayContaining(["door", "bench", "window", "rug"]));
    expect(names("plain")).toEqual(expect.arrayContaining(["sideboard", "armchair", "window"]));
  });

  it("every room has materials and light: floor marks, baseboard, window light, contact shadows", () => {
    for (const kind of ["kitchen", "bathroom", "bedroom", "living", "entry", "plain"] as const) {
      const room = drawRoom(kind);
      const all = [...room.base, ...room.things];
      expect(names(kind)).toEqual(
        expect.arrayContaining(["floor", "floor-marks", "walls", "baseboard", "window-light"]),
      );
      expect(all.some((p) => p.prims.some((x) => x.c === "dk-contact"))).toBe(true);
      // Fine detail is separable, so the corner window can drop it.
      expect(all.some((p) => p.fine)).toBe(true);
      expect(all.filter((p) => !p.fine).length).toBeGreaterThan(5);
    }
  });
});

describe("every CSS variable the walk, evidence, drawing and landing styles use is defined", () => {
  it("names a token from tokens.css, a local custom property, or carries a fallback", () => {
    const src = join(__dirname, "..");
    const tokens = readFileSync(join(src, "styles", "tokens.css"), "utf8");
    const defined = new Set([...tokens.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
    const files = [
      "tour/tour.css",
      "walk/walk.css",
      "evidence/evidence.css",
      "draw/draw.css",
      "landing/landing.css",
    ];
    for (const file of files) {
      const css = readFileSync(join(src, file), "utf8");
      const local = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));
      // Set from inline styles in the components.
      for (const v of ["--fill", "--mark", "--rs-x", "--rs-y"]) local.add(v);
      const missing = [...css.matchAll(/var\((--[a-z0-9-]+)(\s*,)?/g)]
        .filter((m) => !m[2] && !defined.has(m[1]) && !local.has(m[1]))
        .map((m) => m[1]);
      expect(missing, file).toEqual([]);
    }
  });
});

describe("the person in a drawn room", () => {
  const inside = (pts: [number, number][], [px, py]: [number, number]) => {
    let hit = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i]!;
      const [xj, yj] = pts[j]!;
      if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) hit = !hit;
    }
    return hit;
  };
  const kinds: RoomKind[] = ["kitchen", "bathroom", "bedroom", "living", "entry", "plain"];

  it("stands on open floor in every room: its feet clear every furniture footprint", () => {
    for (const kind of kinds) {
      const [sx, sy] = HERE_SPOT[kind];
      const feet: [number, number][] = Array.from({ length: 8 }, (_, i) => {
        const a = (i * Math.PI) / 4;
        return project([sx + Math.cos(a) * 9, sy + Math.sin(a) * 9, 0], O);
      });
      feet.push(project([sx, sy, 0], O));
      const footprints = drawRoom(kind)
        .things.flatMap((p) => p.prims)
        .filter((p) => p.k === "poly" && p.c === "dk-contact")
        .map((p) =>
          (p as { pts: string }).pts
            .split(" ")
            .map((xy) => xy.split(",").map(Number) as [number, number]),
        );
      expect(footprints.length, kind).toBeGreaterThan(0);
      for (const pt of feet)
        expect(
          footprints.some((f) => inside(f, pt)),
          `${kind} at ${sx},${sy}`,
        ).toBe(false);
    }
  });

  it("is one rigid figure: shadow first, then head, torso, legs, arms and camera, all in place", () => {
    const prims = personPrims(O, 250, 130);
    expect(prims[0]!.c).toContain("dk-contact");
    expect(prims.filter((p) => p.k === "dot" && p.c === "dk-head")).toHaveLength(1);
    expect(prims.filter((p) => p.c.includes("dk-teal"))).toHaveLength(3);
    expect(prims.filter((p) => p.c.includes("dk-dark")).length).toBe(9); // two legs, the camera
    expect(prims.filter((p) => p.k === "line")).toHaveLength(4);
    // The head sits straight over the feet.
    const head = prims.find((p) => p.k === "dot" && p.c === "dk-head") as { cx: number };
    expect(head.cx).toBeCloseTo(project([250, 130, 0], O)[0], 0);
  });
});
