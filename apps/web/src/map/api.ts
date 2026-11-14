import { apiBase, apiFetch } from "../api";
import { fixturePlacesMap, fixtureSheet } from "./fixture";
import { passesOwnFilters, toBrief } from "./types";
import type { Criteria, PlaceSheetData, PlacesMap } from "./types";

// The feed for the map. With no API it is the FIXTURE city. With the API, CoStar's fields go as
// the brief and the API sets fits_brief; the map's own two filters are then applied here.
export async function fetchPlacesMap(c: Criteria, signal?: AbortSignal): Promise<PlacesMap> {
  if (!apiBase()) return fixturePlacesMap(c);
  const res = await apiFetch("/places/map", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toBrief(c)),
    signal,
  });
  if (!res.ok) throw new Error(`The places feed answered ${res.status}.`);
  const feed = (await res.json()) as PlacesMap;
  const features = feed.features.map((f) => ({
    ...f,
    properties: {
      ...f.properties,
      fits_brief: f.properties.fits_brief && passesOwnFilters(f.properties, c),
    },
  }));
  return { ...feed, features, n_fit: features.filter((f) => f.properties.fits_brief).length };
}

export async function fetchPlaceSheet(pid: string, signal?: AbortSignal): Promise<PlaceSheetData> {
  if (!apiBase()) {
    const sheet = fixtureSheet(pid);
    if (!sheet) throw new Error("This place is not in the sample city.");
    return sheet;
  }
  const res = await apiFetch(`/places/${encodeURIComponent(pid)}`, { signal });
  if (!res.ok) throw new Error(`The place sheet answered ${res.status}.`);
  return (await res.json()) as PlaceSheetData;
}

// The aerial image comes from our own API route; null in fixture mode, where the sheet shows a
// drawn stand-in instead.
export function aerialSrc(sheet: PlaceSheetData): string | null {
  const base = apiBase();
  const path = sheet.aerial?.image_path;
  return base && path ? `${base}${path}` : null;
}
