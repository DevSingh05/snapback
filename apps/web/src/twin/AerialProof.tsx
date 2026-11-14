import { useState } from "react";

import { SourceChip } from "../components/SourceChip";
import type { AerialTile, PropertyRecord } from "../contracts";
import { distanceAway } from "./distance";

export interface AerialSide {
  tile: AerialTile | null;
  record: PropertyRecord | null;
  /** Runtime image URL served by our API (the Vexcel key stays server side). Not stored past the session. */
  imageUrl?: string;
}

// Synthetic stand-in tile (team-made, not Vexcel imagery): a plain block on a plain ground.
function fixtureTileSrc(seed: string): string {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const tall = 100 + (h % 7) * 12;
  const left = 180 + (h % 5) * 20;
  return (
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#dbe8f4"/><path d="M0 300 L640 250 L640 400 L0 400Z" fill="#cfe6dd"/><rect x="${left}" y="${280 - tall}" width="180" height="${tall}" fill="#ffffff"/><text x="320" y="370" text-anchor="middle" font-family="sans-serif" font-size="22" fill="#3b5a7a">Aerial tile (fixture)</text></svg>`,
    )
  );
}

function srcFor(side: AerialSide): string | null {
  const { tile } = side;
  if (!tile) return null;
  if (tile.source === "live") return side.imageUrl ?? null;
  return fixtureTileSrc(tile.property_id);
}

function Tile({ side, caption }: { side: AerialSide; caption?: string }) {
  const [broken, setBroken] = useState(false);
  const src = srcFor(side);
  return (
    <figure className="aerial-cell">
      {src && !broken ? (
        <img
          className="aerial-img"
          src={src}
          alt={`${side.tile?.direction ?? ""}-facing aerial view of the building`}
          onError={() => setBroken(true)}
        />
      ) : (
        <div className="aerial-missing">Tile unavailable</div>
      )}
      {caption ? <figcaption className="aerial-caption">{caption}</figcaption> : null}
    </figure>
  );
}

interface Props {
  matched: AerialSide;
  claimed: AerialSide;
  /** The photo was taken in a different building than the one the listing claims. */
  mismatch: boolean;
}

export function AerialProof({ matched, claimed, mismatch }: Props) {
  const shown = mismatch ? [claimed, matched] : [matched];
  // LIVE only when every tile and record on show (the distance comes from the records) is live; anything else reads FIXTURE.
  const allLive = shown.every((s) => s.tile?.source === "live" && s.record?.source === "live");
  const away = mismatch ? distanceAway(claimed.record ?? {}, matched.record ?? {}) : null;
  return (
    <section className="aerial-proof" aria-label="Aerial view">
      <div className="aerial-head">
        <span className="mono">Aerial</span>
        <SourceChip source={allLive ? "live" : "fixture"} />
      </div>
      <div className={mismatch ? "aerial-pair" : "aerial-single"}>
        {mismatch ? <Tile side={claimed} caption="The listing says here." /> : null}
        <Tile side={matched} caption={mismatch ? "This photo was taken here." : undefined} />
      </div>
      {away ? (
        <p className="aerial-distance" data-testid="aerial-distance">
          {away} away
        </p>
      ) : null}
    </section>
  );
}
