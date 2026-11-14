import type { CSSProperties } from "react";

import { STEP_MS, drawMs, pairTiers } from "./match";
import type { EvidencePhoto } from "./types";

interface Props {
  photo: EvidencePhoto;
  /** Real images come from our own server (E3). With none, team-made stand-ins are drawn. */
  adSrc?: string | null;
  scanSrc?: string | null;
  reduced: boolean;
  /** Stack the ad photo over the scan view (phones): the lines then run downward. */
  stacked?: boolean;
  /** A small still for the agent rail: fewer lines, no captions. */
  mini?: boolean;
}

const PANE_W = 440;
const PANE_H = 330;
const GAP = 120;
const GAP_STACKED = 64;
const MINI_LINES = 14;

interface Pane {
  x: number;
  y: number;
}

// A team-made stand-in for a room picture: wall, floor boards, a paned window, wall cabinets, a
// counter with doors and a lamp. `shift` moves the pieces a little so the scan view reads as the
// same room from a nearby spot.
function StandIn({ at, shift }: { at: Pane; shift: number }) {
  const { x, y } = at;
  const boards = [252, 272, 296];
  return (
    <g className="ml-standin" aria-hidden="true">
      <rect className="ml-wall" x={x} y={y} width={PANE_W} height={PANE_H} />
      <rect className="ml-floor" x={x} y={y + 236} width={PANE_W} height={PANE_H - 236} />
      {boards.map((b) => (
        <rect key={b} className="ml-board" x={x} y={y + b} width={PANE_W} height={2} />
      ))}
      <rect className="ml-skirt" x={x} y={y + 230} width={PANE_W} height={6} />
      <rect className="ml-window" x={x + 52 + shift} y={y + 48} width={118} height={104} />
      <rect className="ml-sill" x={x + 109 + shift} y={y + 48} width={4} height={104} />
      <rect className="ml-sill" x={x + 52 + shift} y={y + 98} width={118} height={4} />
      <rect className="ml-sill" x={x + 44 + shift} y={y + 152} width={134} height={8} />
      <rect className="ml-cabinet" x={x + 232 + shift} y={y + 40} width={150} height={58} />
      <rect className="ml-seam" x={x + 281 + shift} y={y + 40} width={2} height={58} />
      <rect className="ml-seam" x={x + 331 + shift} y={y + 40} width={2} height={58} />
      <rect className="ml-counter" x={x + 214 + shift} y={y + 168} width={190} height={100} />
      <rect className="ml-seam" x={x + 276 + shift} y={y + 176} width={2} height={86} />
      <rect className="ml-seam" x={x + 340 + shift} y={y + 176} width={2} height={86} />
      <rect className="ml-top" x={x + 206 + shift} y={y + 158} width={206} height={12} />
      <rect className="ml-cabinet" x={x + 372 + shift} y={y + 120} width={22} height={38} />
      <rect className="ml-shadow" x={x + 214 + shift} y={y + 268} width={190} height={8} />
    </g>
  );
}

// The ad photo and the scan view on one dark table, with the matched points joined across the
// gutter. Each pair draws in one by one, shaded by how closely it agrees with the rest. The
// points are a sample: the caption always says how many are drawn out of how many matched.
export function MatchLines({
  photo,
  adSrc,
  scanSrc,
  reduced,
  stacked = false,
  mini = false,
}: Props) {
  const all = photo.points?.sampled ?? [];
  const pairs = mini ? all.slice(0, MINI_LINES) : all;
  const tiers = pairTiers(pairs);
  const total = photo.points?.n_total ?? 0;
  const gap = stacked ? GAP_STACKED : GAP;
  const a: Pane = { x: 0, y: 0 };
  const b: Pane = stacked ? { x: 0, y: PANE_H + gap } : { x: PANE_W + gap, y: 0 };
  const width = stacked ? PANE_W : PANE_W * 2 + gap;
  const height = stacked ? PANE_H * 2 + gap : PANE_H;
  const weak = Boolean(photo.bar_failed) || photo.status === "not_located";
  const caption = `${all.length} of ${total} matched points drawn`;
  const still = reduced || mini;

  return (
    <figure
      className={`ml${mini ? " ml-mini" : ""}`}
      data-testid="match-lines"
      data-motion={reduced ? "reduced" : "full"}
      data-layout={stacked ? "stacked" : "side"}
      data-weak={weak ? "true" : undefined}
      style={
        {
          "--draw-ms": `${drawMs(pairs.length)}ms`,
          "--b-left": `${(b.x / width) * 100}%`,
          "--b-top": `${(b.y / height) * 100}%`,
        } as CSSProperties
      }
    >
      <div className="ml-table">
        <svg
          className="ml-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${caption}, joining the ad photo to the scan view`}
        >
          {adSrc ? (
            <image
              href={adSrc}
              x={a.x}
              y={a.y}
              width={PANE_W}
              height={PANE_H}
              preserveAspectRatio="xMidYMid slice"
            />
          ) : (
            <StandIn at={a} shift={0} />
          )}
          {scanSrc ? (
            <image
              href={scanSrc}
              x={b.x}
              y={b.y}
              width={PANE_W}
              height={PANE_H}
              preserveAspectRatio="xMidYMid slice"
            />
          ) : (
            <StandIn at={b} shift={-18} />
          )}
          <rect
            className={adSrc ? "ml-scrim-real" : "ml-scrim"}
            x={a.x}
            y={a.y}
            width={PANE_W}
            height={PANE_H}
          />
          <rect
            className={scanSrc ? "ml-scrim-real" : "ml-scrim"}
            x={b.x}
            y={b.y}
            width={PANE_W}
            height={PANE_H}
          />
          {!still && (
            <rect
              className="ml-sweep"
              x={b.x}
              y={b.y}
              width={stacked ? PANE_W : 3}
              height={stacked ? 3 : PANE_H}
              aria-hidden="true"
            />
          )}
          <g className="ml-lines">
            {pairs.map(([ax, ay, bx, by], i) => {
              const x1 = a.x + ax * PANE_W;
              const y1 = a.y + ay * PANE_H;
              const x2 = b.x + bx * PANE_W;
              const y2 = b.y + by * PANE_H;
              const delay = still ? undefined : { animationDelay: `${i * STEP_MS}ms` };
              return (
                <g
                  key={i}
                  className={`ml-pair ml-${tiers[i]}`}
                  data-testid="match-pair"
                  data-tier={tiers[i]}
                  style={delay}
                >
                  <line className="ml-case" x1={x1} y1={y1} x2={x2} y2={y2} />
                  <line
                    className="ml-line"
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    pathLength={1}
                    style={delay}
                  />
                  <rect className="ml-dot" x={x1 - 3.5} y={y1 - 3.5} width={7} height={7} />
                  <rect className="ml-dot" x={x2 - 3.5} y={y2 - 3.5} width={7} height={7} />
                </g>
              );
            })}
          </g>
        </svg>
        {!mini && (
          <>
            <span className="ml-tag ml-tag-a">
              Ad photo <span className="mono">{photo.alias}</span>
              {!adSrc && <span className="ml-note"> (stand-in drawing)</span>}
            </span>
            <span className="ml-tag ml-tag-b">
              Scan view{photo.scan_alias ? " " : ""}
              {photo.scan_alias && <span className="mono">{photo.scan_alias}</span>}
              {!scanSrc && <span className="ml-note"> (stand-in drawing)</span>}
            </span>
          </>
        )}
      </div>
      {!mini && (
        <figcaption className="ml-caption">
          <span className="ml-legend" aria-hidden="true">
            <span className="ml-key ml-key-strong" />
            <span className="ml-key ml-key-mid" />
            <span className="ml-key ml-key-faint" />
          </span>
          <span className="ml-legend-text">Brighter lines agree most closely with the rest.</span>
          <span className="ml-count mono" data-testid="match-count">
            {caption}
          </span>
        </figcaption>
      )}
    </figure>
  );
}
