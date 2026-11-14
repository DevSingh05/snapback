import type { MustHaveLine, PlaceMatch } from "../contracts";
import { passesOwnFilters } from "./types";
import type { Criteria, PlaceFeature, PlaceSheetData, PlacesMap } from "./types";

// The FIXTURE city: team-made stand-ins on real Houston streets. Every point is made up by a
// seeded generator; none is a real place, address, office or name, and no kit id appears here.
// The same generated record feeds the pin and the sheet, so the two cannot disagree.

// What stands where a live record says "as of CoStar's last research": these are the team's
// own sample figures, so they never borrow CoStar's name.
export const SAMPLE_AS_OF = "sample figures, made by the team";
const SAMPLE = "(sample figure)";

interface FixturePlace {
  pid: string;
  kind: "apartment" | "house";
  lon: number;
  lat: number;
  has_scan: boolean;
  units_reported: number | null;
  plans: { beds: number; baths: number; rent: number }[];
  walkup: boolean | null; // null: the record does not say
  parking: boolean | null;
  pets: boolean | null;
  company: string;
  aerial_captured: string;
}

// Rough centres of ten Houston areas; the generator scatters stand-ins around each.
const CENTRES: [number, number, number][] = [
  [-95.3698, 29.7604, 9],
  [-95.3795, 29.74, 8],
  [-95.392, 29.744, 8],
  [-95.398, 29.79, 6],
  [-95.398, 29.707, 7],
  [-95.461, 29.74, 7],
  [-95.348, 29.75, 5],
  [-95.388, 29.725, 5],
  [-95.4, 29.77, 5],
  [-95.43, 29.733, 4],
];

const COMPANIES = ["Sample Property Group", "Stand-in Residential", "Fixture Homes Management"];

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function build(): FixturePlace[] {
  const rnd = mulberry32(20261114);
  const pick = <T>(xs: T[]): T => xs[Math.floor(rnd() * xs.length)]!;
  const tri = (): boolean | null => {
    const r = rnd();
    return r < 0.5 ? true : r < 0.8 ? false : null;
  };
  const out: FixturePlace[] = [];
  let n = 0;
  for (const [lon, lat, count] of CENTRES) {
    for (let i = 0; i < count; i += 1) {
      n += 1;
      const house = rnd() < 0.18;
      const nPlans = house ? 1 : 1 + Math.floor(rnd() * 5);
      const base = 950 + Math.floor(rnd() * 14) * 50;
      const plans = Array.from({ length: nPlans }, (_, k) => {
        const beds = house ? 2 + Math.floor(rnd() * 2) : Math.min(3, k);
        return { beds, baths: beds > 1 ? 2 : 1, rent: base + beds * 280 + k * 40 };
      });
      out.push({
        pid: `fx-map-${String(n).padStart(2, "0")}`,
        kind: house ? "house" : "apartment",
        lon: +(lon + (rnd() - 0.5) * 0.024).toFixed(5),
        lat: +(lat + (rnd() - 0.5) * 0.02).toFixed(5),
        has_scan: rnd() < 0.38,
        units_reported: house ? null : rnd() < 0.15 ? null : Math.floor(rnd() * 9),
        plans,
        walkup: house ? false : tri(),
        parking: tri(),
        pets: tri(),
        company: pick(COMPANIES),
        aerial_captured: `2025-${String(3 + Math.floor(rnd() * 8)).padStart(2, "0")}-14`,
      });
    }
  }
  return out;
}

const PLACES = build();
const usd = (n: number) => `$${n.toLocaleString("en-US")}`;
const planName = (beds: number, baths: number) =>
  `${beds === 0 ? "Studio" : `${beds} bed`} / ${baths} bath`;

function fits(p: FixturePlace, c: Criteria): boolean {
  const plans = p.plans.filter(
    (pl) =>
      (c.max_rent == null || pl.rent <= c.max_rent) &&
      (c.beds_min == null || pl.beds >= c.beds_min),
  );
  if (plans.length === 0) return false;
  if (c.no_walkup && p.walkup !== false) return false;
  if (c.parking && p.parking !== true) return false;
  if (c.pets && p.pets !== true) return false;
  return true;
}

function feature(p: FixturePlace, c: Criteria): PlaceFeature {
  const properties = {
    pid: p.pid,
    kind: p.kind,
    has_scan: p.has_scan,
    n_plans: p.plans.length,
    rent_from: Math.min(...p.plans.map((pl) => pl.rent)),
    units_reported: p.units_reported,
    fits_brief: false,
    source: "fixture" as const,
    as_of: SAMPLE_AS_OF,
  };
  properties.fits_brief = fits(p, c) && passesOwnFilters(properties, c);
  return {
    type: "Feature",
    id: p.pid,
    geometry: { type: "Point", coordinates: [p.lon, p.lat] },
    properties,
  };
}

export function fixturePlacesMap(c: Criteria): PlacesMap {
  const features = PLACES.map((p) => feature(p, c));
  return {
    type: "FeatureCollection",
    source: "fixture",
    as_of: SAMPLE_AS_OF,
    n_places: features.length,
    n_fit: features.filter((f) => f.properties.fits_brief).length,
    n_unlocated: 0,
    features,
  };
}

function line(
  key: string,
  label: string,
  v: boolean | null,
  yes: string,
  no: string,
): MustHaveLine {
  return { key, text: `${label}: ${v == null ? "not on record" : v ? yes : no}`, met: v };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function fixtureSheet(pid: string): PlaceSheetData | null {
  const p = PLACES.find((x) => x.pid === pid);
  if (!p) return null;
  const must_haves = [
    line(
      "walkup",
      "Stairs",
      p.walkup == null ? null : !p.walkup,
      "reported elevator or ground-floor access",
      "reported as a walk-up",
    ),
    line("parking", "Parking", p.parking, "reported on site", "none reported"),
    line("pets", "Pets", p.pets, "reported as allowed", "reported as not allowed"),
  ];
  const availability_text =
    p.units_reported == null
      ? "Units available: not on record"
      : `${p.units_reported} ${p.units_reported === 1 ? "unit" : "units"} reported available ${SAMPLE}`;
  const plans: PlaceMatch[] = p.plans.map((pl, i) => ({
    property_id: p.pid,
    kind: p.kind,
    floor_plan: planName(pl.beds, pl.baths),
    plan_key: `${p.pid}-plan-${i + 1}`,
    beds: pl.beds,
    baths: pl.baths,
    rent_min: pl.rent,
    rent_max: pl.rent,
    budget_fit: "no_budget",
    price_text: `${usd(pl.rent)} a month ${SAMPLE}`,
    availability_text,
    must_haves,
    musts_met: must_haves.filter((m) => m.met).length,
    has_3d_scan: p.has_scan,
    scan_text: p.has_scan ? "a 3D scan in this building" : null,
    office_on_record: p.company,
    source: "fixture",
  }));
  const [y, m, d] = p.aerial_captured.split("-").map(Number) as [number, number, number];
  return {
    property_id: p.pid,
    kind: p.kind,
    source: "fixture",
    as_of: SAMPLE_AS_OF,
    office_on_record: p.company,
    has_3d_scan: p.has_scan,
    scan_text: p.has_scan ? "a 3D scan in this building" : null,
    walk_path: p.has_scan ? `/tour/${p.pid}` : null,
    plans,
    aerial: {
      source: "fixture",
      captured_on: p.aerial_captured,
      line: `Aerial photo captured ${MONTHS[m - 1]} ${d}, ${y} (fixture tile)`,
      image_path: null,
    },
  };
}

// For the policy proposal: does the fixture record call this place a walk-up?
export function fixtureIsWalkup(pid: string): boolean {
  return PLACES.find((x) => x.pid === pid)?.walkup === true;
}
