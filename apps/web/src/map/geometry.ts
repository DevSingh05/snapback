import type { PlaceFeature } from "./types";

// Pure map geometry, kept apart from MapLibre so it can be tested without WebGL.

const M_PER_DEG_LAT = 111_320;

export function metresBetween(a: [number, number], b: [number, number]): number {
  const mLon = M_PER_DEG_LAT * Math.cos(((a[1] + b[1]) / 2) * (Math.PI / 180));
  return Math.hypot((a[0] - b[0]) * mLon, (a[1] - b[1]) * M_PER_DEG_LAT);
}

// A six-sided footprint around a point: the base of a place's column.
export function hexagon(centre: [number, number], radiusM: number): [number, number][] {
  const [lon, lat] = centre;
  const dLat = radiusM / M_PER_DEG_LAT;
  const dLon = radiusM / (M_PER_DEG_LAT * Math.cos(lat * (Math.PI / 180)));
  const ring: [number, number][] = [];
  for (let i = 0; i < 6; i += 1) {
    const t = (Math.PI / 3) * i + Math.PI / 6;
    ring.push([lon + Math.cos(t) * dLon, lat + Math.sin(t) * dLat]);
  }
  ring.push(ring[0]!);
  return ring;
}

// Column height in metres. It is a data mark, not the building: height says how many priced
// floor plans are on record, in four capped steps, so the tallest column is never more than
// about one and a half times the shortest. `boost` scales the whole set for a zoom band.
export function columnHeight(nPlans: number, boost: number): number {
  return (64 + Math.min(Math.max(nPlans, 1), 4) * 12) * boost;
}

export interface ColumnFeature {
  type: "Feature";
  id: number;
  geometry: { type: "Polygon"; coordinates: [number, number][][] };
  properties: {
    pid: string;
    fits: boolean;
    scan: boolean;
    passed: boolean;
    h: number;
    cap: number;
  };
}

export function columns(
  places: PlaceFeature[],
  radiusM: number,
  boost: number,
  passed: ReadonlySet<string>,
): { type: "FeatureCollection"; features: ColumnFeature[] } {
  return {
    type: "FeatureCollection",
    features: places.map((f, i) => {
      const h = columnHeight(f.properties.n_plans, boost);
      return {
        type: "Feature",
        id: i + 1,
        geometry: { type: "Polygon", coordinates: [hexagon(f.geometry.coordinates, radiusM)] },
        properties: {
          pid: f.properties.pid,
          fits: f.properties.fits_brief,
          scan: f.properties.has_scan,
          passed: passed.has(f.properties.pid),
          h,
          cap: h + 12 * boost,
        },
      };
    }),
  };
}

// The place a clicked building belongs to: the nearest one within `withinM` metres, else null
// ("Nothing on CoStar's record for this building").
export function nearestPlace(
  places: PlaceFeature[],
  at: [number, number],
  withinM = 40,
): PlaceFeature | null {
  let best: PlaceFeature | null = null;
  let bestD = withinM;
  for (const f of places) {
    const d = metresBetween(f.geometry.coordinates, at);
    if (d <= bestD) {
      best = f;
      bestD = d;
    }
  }
  return best;
}

type Ring = [number, number][];

function inRing(at: [number, number], ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i]!;
    const [xj, yj] = ring[j]!;
    if (yi > at[1] !== yj > at[1] && at[0] < ((xj - xi) * (at[1] - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

// One building out of what the tiles hand back. A tile feature can be a MultiPolygon that joins
// many buildings, so this keeps only the polygon that holds the place's point, or failing that
// the one with a corner nearest to it within `withinM` metres. Null when there is none.
export function pickPolygon(
  geometry: { type: string; coordinates: unknown },
  at: [number, number],
  withinM = 60,
): { type: "Polygon"; coordinates: Ring[] } | null {
  const polygons: Ring[][] =
    geometry.type === "Polygon"
      ? [geometry.coordinates as Ring[]]
      : geometry.type === "MultiPolygon"
        ? (geometry.coordinates as Ring[][])
        : [];
  let best: Ring[] | null = null;
  let bestD = withinM;
  for (const poly of polygons) {
    const outer = poly[0];
    if (!outer || outer.length < 4) continue;
    if (inRing(at, outer)) return { type: "Polygon", coordinates: poly };
    const d = Math.min(...outer.map((pt) => metresBetween(pt, at)));
    if (d <= bestD) {
      best = poly;
      bestD = d;
    }
  }
  return best ? { type: "Polygon", coordinates: best } : null;
}
