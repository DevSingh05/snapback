import { SourceChip } from "../components/SourceChip";
import type { AerialTileInfo, PropertyFacts } from "../contracts";

// Synthetic stand-in tile (team-made, not Vexcel imagery). Live tiles come from the API at runtime.
const PLACEHOLDER_TILE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#e4ecfc"/><path d="M0 300 L640 260 L640 400 L0 400Z" fill="#dff3ee"/><rect x="230" y="120" width="180" height="170" fill="#ffffff" stroke="#2457c5" stroke-width="3"/><text x="320" y="360" text-anchor="middle" font-family="sans-serif" font-size="24" fill="#2457c5">Aerial tile (fixture)</text></svg>`,
  );

// The one neutral fact: what the record says about the building, next to when the tile was taken.
// Never a neighbourhood, crime or safety score.
export function aerialFact(record: PropertyFacts, tile: AerialTileInfo): string {
  const floors =
    record.floors != null
      ? `${record.floors} ${record.floors === 1 ? "floor" : "floors"} on record`
      : "floors not on record";
  const built =
    record.year_built != null ? `built ${record.year_built}` : "year built not on record";
  const taken = tile.captured_on ? `photo taken ${tile.captured_on}` : "capture date unknown";
  return `${floors}, ${built}. Aerial ${taken}.`;
}

interface Props {
  tile: AerialTileInfo;
  record: PropertyFacts;
  /** Runtime image URL served by our API (the Vexcel key stays server side). Not stored past the session. */
  imageUrl?: string;
}

export function AerialTile({ tile, record, imageUrl }: Props) {
  const src = tile.source === "live" && imageUrl ? imageUrl : PLACEHOLDER_TILE;
  return (
    <figure className="aerial-tile" aria-label="Aerial view">
      <div className="aerial-head">
        <span className="mono">Aerial</span>
        <SourceChip source={tile.source} />
      </div>
      <img
        className="aerial-img"
        src={src}
        alt={`${tile.direction}-facing aerial view of the building`}
      />
      <figcaption className="aerial-fact" data-testid="aerial-fact">
        {aerialFact(record, tile)}
      </figcaption>
    </figure>
  );
}
