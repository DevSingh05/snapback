import type { DataSource, PlaceMatch, RenterBrief } from "../contracts";

// The map feed (M1, POST /places/map): one point per place CoStar has researched. The feed never
// carries an address, an office or a name; the sheet (M2) is where the record lines live.
export interface PlaceProps {
  pid: string;
  kind: "apartment" | "house";
  has_scan: boolean;
  n_plans: number; // priced floor plans on record; 1 for a house
  rent_from: number | null; // lowest asking price a month, whole dollars
  units_reported: number | null; // null for a house, or when the record does not say
  fits_brief: boolean;
  source: DataSource;
  as_of: string;
}

export interface PlaceFeature {
  type: "Feature";
  id?: string | number;
  geometry: { type: "Point"; coordinates: [number, number] }; // [lon, lat]
  properties: PlaceProps;
}

export interface PlacesMap {
  type: "FeatureCollection";
  source: DataSource;
  as_of: string;
  n_places: number;
  n_fit: number;
  n_unlocated: number;
  features: PlaceFeature[];
}

export interface SheetAerial {
  source: DataSource;
  captured_on?: string | null; // ISO date
  line?: string | null; // "Aerial photo captured Mar 14, 2025 (Vexcel)"
  image_path?: string | null; // our own route; the Vexcel key never leaves the server
}

// The place sheet (M2, GET /places/{pid}), as the API sends it. Every plan carries the same
// lines search builds, so a price on the pin and a price in the walk cannot differ.
export interface PlaceSheetData {
  property_id: string;
  kind: "apartment" | "house";
  source: DataSource;
  as_of: string;
  office_on_record?: string | null; // company name only
  has_3d_scan: boolean;
  scan_text?: string | null;
  walk_path?: string | null; // Walk it first, when a scan is on record
  plans: PlaceMatch[];
  aerial?: SheetAerial | null;
}

// What the renter asked for. The first five are CoStar's fields (they travel as the RenterBrief);
// the next two are the map's own filters over the feed; `own` is the renter's own words, kept as
// notes for the visit and never checked against the record.
export interface Criteria {
  max_rent: number | null;
  beds_min: number | null;
  no_walkup: boolean;
  parking: boolean;
  pets: boolean;
  scan_only: boolean;
  units_only: boolean;
  own: string[];
}

export const EMPTY_CRITERIA: Criteria = {
  max_rent: null,
  beds_min: null,
  no_walkup: false,
  parking: false,
  pets: false,
  scan_only: false,
  units_only: false,
  own: [],
};

export function toBrief(c: Criteria): RenterBrief {
  return {
    max_rent_month: c.max_rent,
    beds_min: c.beds_min,
    needs_no_walkup: c.no_walkup,
    needs_parking: c.parking,
    pets: c.pets,
  };
}

export function criteriaCount(c: Criteria): number {
  return (
    Number(c.max_rent != null) +
    Number(c.beds_min != null) +
    Number(c.no_walkup) +
    Number(c.parking) +
    Number(c.pets) +
    Number(c.scan_only) +
    Number(c.units_only) +
    c.own.length
  );
}

// The map's own filters run in the browser over the feed, in both data modes.
export function passesOwnFilters(p: PlaceProps, c: Criteria): boolean {
  if (c.scan_only && !p.has_scan) return false;
  if (c.units_only && !(p.units_reported != null && p.units_reported > 0)) return false;
  return true;
}

// One thing the renter did on the map. These are real and live in this browser; M8 sends them to
// the event bus.
export interface RenterEvent {
  id: number;
  kind: "opened" | "passed" | "criteria" | "remembered";
  pid?: string;
  text: string;
}
