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
// floor plans are on record. `boost` exaggerates it at city zoom so the skyline reads.
export function columnHeight(nPlans: number, boost: number): number {
  return (40 + Math.min(nPlans, 6) * 26) * boost;
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
          cap: h + 14 * boost,
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
