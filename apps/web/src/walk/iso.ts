// A tiny 2:1 isometric helper for the drawn fixture stage and the drawn aerial stand-ins.
// x runs down-right, y runs down-left, z is up. Team-made drawings only: no sponsor imagery.

export const K = 0.866;
export type P3 = [number, number, number];

export interface Origin {
  ox: number;
  oy: number;
}

export function project([x, y, z]: P3, { ox, oy }: Origin): [number, number] {
  return [ox + (x - y) * K, oy + (x + y) * 0.5 - z];
}

export function points(o: Origin, ...ps: P3[]): string {
  return ps
    .map((p) => project(p, o))
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
}

export interface Box {
  x: number;
  y: number;
  z?: number;
  w: number; // along x
  d: number; // along y
  h: number;
  tone?: "slate" | "pale" | "white" | "green" | "door";
}

/** The three faces of a box the viewer can see: top, the face toward +y, the face toward +x. */
export function boxFaces(b: Box, o: Origin): { top: string; left: string; right: string } {
  const z = b.z ?? 0;
  const { x, y, w, d, h } = b;
  return {
    top: points(o, [x, y, z + h], [x + w, y, z + h], [x + w, y + d, z + h], [x, y + d, z + h]),
    left: points(o, [x, y + d, z], [x + w, y + d, z], [x + w, y + d, z + h], [x, y + d, z + h]),
    right: points(o, [x + w, y, z], [x + w, y + d, z], [x + w, y + d, z + h], [x + w, y, z + h]),
  };
}
