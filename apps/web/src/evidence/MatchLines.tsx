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
const MINI_LINES = 14;

interface Pane {
  x: number;
  y: number;
}

// A team-made stand-in for a room picture: a wall, a floor, a window and a counter. `shift`
// moves the pieces a little so the scan view reads as the same room from a nearby spot.
function StandIn({ at, shift }: { at: Pane; shift: number }) {
  const { x, y } = at;
  return (
    <g className="ml-standin" aria-hidden="true">
      <rect className="ml-wall" x={x} y={y} width={PANE_W} height={PANE_H} />
      <rect className="ml-floor" x={x} y={y + 236} width={PANE_W} height={PANE_H - 236} />
      <rect className="ml-window" x={x + 52 + shift} y={y + 48} width={118} height={104} />
      <rect className="ml-sill" x={x + 44 + shift} y={y + 152} width={134} height={8} />
      <rect className="ml-cabinet" x={x + 232 + shift} y={y + 40} width={150} height={58} />
      <rect className="ml-counter" x={x + 214 + shift} y={y + 168} width={190} height={100} />
      <rect className="ml-top" x={x + 206 + shift} y={y + 158} width={206} height={12} />
    </g>
  );
}

// The ad photo and the scan view with the matched points joined across the gutter. The points
// are a sample: the caption always says how many are drawn out of how many matched.
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
  const total = photo.points?.n_total ?? 0;
  const a: Pane = { x: 0, y: 0 };
  const b: Pane = stacked ? { x: 0, y: PANE_H + GAP } : { x: PANE_W + GAP, y: 0 };
  const width = stacked ? PANE_W : PANE_W * 2 + GAP;
  const height = stacked ? PANE_H * 2 + GAP : PANE_H;
  const weak = Boolean(photo.bar_failed) || photo.status === "not_located";
  const caption = `${all.length} of ${total} matched points drawn`;

  return (
    <figure
      className={`ml${mini ? " ml-mini" : ""}`}
      data-testid="match-lines"
      data-motion={reduced ? "reduced" : "full"}
      data-layout={stacked ? "stacked" : "side"}
      data-weak={weak ? "true" : undefined}
    >
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
        <g className="ml-lines">
          {pairs.map(([ax, ay, bx, by], i) => {
            const x1 = a.x + ax * PANE_W;
            const y1 = a.y + ay * PANE_H;
            const x2 = b.x + bx * PANE_W;
            const y2 = b.y + by * PANE_H;
            return (
              <g
                key={i}
                className={`ml-pair ${i % 2 === 0 ? "ml-pair-a" : "ml-pair-b"}`}
                data-testid="match-pair"
                style={reduced ? undefined : { animationDelay: `${i * 18}ms` }}
              >
                <line
                  className="ml-line"
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  pathLength={1}
                  style={reduced ? undefined : { animationDelay: `${i * 18}ms` }}
                />
                <rect className="ml-dot" x={x1 - 3} y={y1 - 3} width={6} height={6} />
                <rect className="ml-dot" x={x2 - 3} y={y2 - 3} width={6} height={6} />
              </g>
            );
          })}
        </g>
      </svg>
      {!mini && (
        <figcaption className="ml-caption">
          <span className="ml-pane-label">
            Ad photo <span className="mono">{photo.alias}</span>
            {!adSrc && <span className="ml-note"> (stand-in drawing)</span>}
          </span>
          <span className="ml-count mono" data-testid="match-count">
            {caption}
          </span>
          <span className="ml-pane-label ml-pane-label-b">
            Scan view{photo.scan_alias ? " " : ""}
            {photo.scan_alias && <span className="mono">{photo.scan_alias}</span>}
            {!scanSrc && <span className="ml-note"> (stand-in drawing)</span>}
          </span>
        </figcaption>
      )}
    </figure>
  );
}
