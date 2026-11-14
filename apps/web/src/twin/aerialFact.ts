import type { AerialTile as AerialTileData, PropertyRecord } from "../contracts";

// The one neutral fact: what the record says about the building, next to when the tile was taken.
// Never a neighbourhood, crime or safety score.
export function aerialFact(record: PropertyRecord, tile: AerialTileData): string {
  const floors =
    record.floors != null
      ? `${record.floors} ${record.floors === 1 ? "floor" : "floors"} on record`
      : "floors not on record";
  const built =
    record.year_built != null ? `built ${record.year_built}` : "year built not on record";
  const taken = tile.captured_on ? `photo taken ${tile.captured_on}` : "capture date unknown";
  return `${floors}, ${built}. Aerial ${taken}.`;
}
