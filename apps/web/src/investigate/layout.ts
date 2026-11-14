import type { GraphNode } from "./types";

export interface Placed extends GraphNode {
  x: number;
  y: number;
}

// Ads sit on a circle in posting order (earliest at the top, clockwise). A phone, photo-set or
// wording node sits inside the circle, at the middle of the ads that share it, pulled toward the
// centre so lines from different nodes do not run on top of each other. Deterministic: the same
// ring always draws the same picture.
export function layoutGraph(
  nodes: GraphNode[],
  edges: { source: string; target: string }[],
  size: number,
): Map<string, Placed> {
  const centre = size / 2;
  const radius = size * 0.4;
  const ads = nodes
    .filter((n) => n.type === "ad")
    .sort(
      (a, b) => (a.date ?? "").localeCompare(b.date ?? "") || Number(a.label) - Number(b.label),
    );
  const placed = new Map<string, Placed>();
  ads.forEach((node, i) => {
    const angle = -Math.PI / 2 + (i / Math.max(ads.length, 1)) * Math.PI * 2;
    placed.set(node.id, {
      ...node,
      x: centre + radius * Math.cos(angle),
      y: centre + radius * Math.sin(angle),
    });
  });
  const members = new Map<string, string[]>();
  for (const e of edges) {
    const list = members.get(e.target) ?? [];
    list.push(e.source);
    members.set(e.target, list);
  }
  for (const node of nodes.filter((n) => n.type !== "ad")) {
    const around = (members.get(node.id) ?? [])
      .map((id) => placed.get(id))
      .filter((p): p is Placed => p !== undefined);
    const mx = around.length ? around.reduce((s, p) => s + p.x, 0) / around.length : centre;
    const my = around.length ? around.reduce((s, p) => s + p.y, 0) / around.length : centre;
    placed.set(node.id, {
      ...node,
      x: centre + (mx - centre) * 0.62,
      y: centre + (my - centre) * 0.62,
    });
  }
  return placed;
}

// Weekly bars and event ticks on one time axis, 0 to 1 across the ring's span plus a week each side.
export function timeScale(first: string, last: string): (day: string) => number {
  const day = 86_400_000;
  const start = Date.parse(first) - 7 * day;
  const end = Date.parse(last) + 14 * day;
  return (d: string) => (Date.parse(d) - start) / (end - start);
}
