// Distance between two buildings, from the two records' lat/lon only (no geocoding, no addresses).

export interface LatLon {
  lat?: number | null;
  lon?: number | null;
}

const EARTH_RADIUS_M = 6_371_008.8;
const FEET_PER_METER = 3.28084;
const METERS_PER_MILE = 1609.344;
/** Below this many feet (after rounding) say feet, from here say miles. */
const FEET_LIMIT = 1000;

const rad = (deg: number) => (deg * Math.PI) / 180;

export function haversineMeters(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): number {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** "900 ft" below 1000 ft (nearest 50, nearest 10 under 100 ft), else "0.4 miles". */
export function formatDistance(meters: number): string {
  const feet = meters * FEET_PER_METER;
  if (feet < 100) {
    const r = Math.round(feet / 10) * 10;
    return r < 30 ? "under 30 ft" : `${r} ft`;
  }
  const rounded = Math.round(feet / 50) * 50;
  if (rounded < FEET_LIMIT) return `${rounded} ft`;
  const miles = meters / METERS_PER_MILE;
  if (miles >= 10) {
    const m = Math.round(miles);
    return `${m} ${m === 1 ? "mile" : "miles"}`;
  }
  const oneDecimal = Math.round(miles * 10) / 10;
  return oneDecimal === 1 ? "1 mile" : `${oneDecimal} miles`;
}

/** Null when either record has no lat/lon, so the caller can leave the line out. */
export function distanceAway(a: LatLon, b: LatLon): string | null {
  if (a.lat == null || a.lon == null || b.lat == null || b.lon == null) return null;
  return formatDistance(haversineMeters({ lat: a.lat, lon: a.lon }, { lat: b.lat, lon: b.lon }));
}
