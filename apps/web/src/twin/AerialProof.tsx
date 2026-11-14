import { useState } from "react";

import { SourceChip } from "../components/SourceChip";
import type { AerialTile, PropertyRecord } from "../contracts";
import { distanceAway } from "./distance";
import { canGoLive, useLiveAerial } from "./useLiveAerial";

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

function facts(record: PropertyRecord | null): string {
  if (!record) return "";
  return [
    record.manager_company,
    record.floors ? `${record.floors} floors` : null,
    record.year_built ? `built ${record.year_built}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function Tile({
  side,
  caption,
  showFacts,
}: {
  side: AerialSide;
  caption?: string;
  showFacts?: boolean;
}) {
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
        <div className="aerial-missing">No aerial image for this building yet</div>
      )}
      {caption ? <figcaption className="aerial-caption">{caption}</figcaption> : null}
      {showFacts && facts(side.record) ? (
        <p className="aerial-facts">{facts(side.record)}</p>
      ) : null}
    </figure>
  );
}

interface Props {
  matched: AerialSide;
  claimed: AerialSide;
  /** The photo was taken in a different building than the one the listing claims. */
  mismatch: boolean;
  /** With a read token for this case in the browser, the proof comes from the live route instead. */
  caseId?: string;
}

interface ViewProps {
  matched: AerialSide;
  claimed: AerialSide;
  mismatch: boolean;
  live?: boolean;
  /** Chip override for the live path (follows the response). */
  chip?: "live" | "fixture";
}

function ProofView({ matched, claimed, mismatch, live = false, chip }: ViewProps) {
  const shown = mismatch ? [claimed, matched] : [matched];
  // Fixture path: LIVE only when every tile and record on show is live; anything else reads FIXTURE.
  const allLive = shown.every((s) => s.tile?.source === "live" && s.record?.source === "live");
  const away = mismatch ? distanceAway(claimed.record ?? {}, matched.record ?? {}) : null;
  return (
    <section className="aerial-proof" aria-label="Aerial view">
      <div className="aerial-head">
        <span className="mono">Aerial</span>
        <SourceChip source={chip ?? (allLive ? "live" : "fixture")} />
      </div>
      <div className={mismatch ? "aerial-pair" : "aerial-single"}>
        {mismatch ? (
          <Tile side={claimed} caption="The listing says here." showFacts={live} />
        ) : null}
        <Tile
          side={matched}
          caption={mismatch ? "This photo was taken here." : undefined}
          showFacts={live}
        />
      </div>
      {away ? (
        <p className="aerial-distance" data-testid="aerial-distance">
          {away} away
        </p>
      ) : null}
    </section>
  );
}

function LiveAerialProof({ caseId }: { caseId: string }) {
  const aerial = useLiveAerial(caseId, true);
  if (aerial.status === "loading") {
    return (
      <section className="aerial-proof" aria-label="Aerial view" aria-busy="true">
        <div className="aerial-head">
          <span className="mono">Aerial</span>
        </div>
        <div className="aerial-skeleton" data-testid="aerial-skeleton" />
      </section>
    );
  }
  if (aerial.status === "error") {
    return (
      <section className="aerial-proof" aria-label="Aerial view">
        <div className="aerial-head">
          <span className="mono">Aerial</span>
        </div>
        <p className="aerial-distance">The aerial view could not load. Try again in a moment.</p>
      </section>
    );
  }
  const { claimed, matched, source } = aerial;
  const parts = [claimed, matched].filter((s): s is AerialSide => s !== null);
  // The response decides, and a fixture tile or record anywhere on show pulls it to FIXTURE.
  const anyFixture = parts.some(
    (s) => s.tile?.source === "fixture" || s.record?.source === "fixture",
  );
  return (
    <ProofView
      live
      mismatch={matched !== null}
      claimed={claimed}
      matched={matched ?? claimed}
      chip={source === "live" && !anyFixture ? "live" : "fixture"}
    />
  );
}

export function AerialProof({ caseId, ...rest }: Props) {
  if (canGoLive(caseId)) return <LiveAerialProof caseId={caseId} />;
  return <ProofView {...rest} />;
}
