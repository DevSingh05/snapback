import type { CSSProperties } from "react";

import { HEAT_COLS, HEAT_ROWS, barLabel, coverage, pointsSentence, shortBy } from "./match";
import { gauges, type Gauge } from "./read";
import type { EvidencePhoto } from "./types";

const verdict = (g: Gauge) => (g.pass ? "Met" : "Short of the bar");

interface MeterProps {
  photo: EvidencePhoto;
  bars: Record<string, number>;
  /** The live count while the spots are circled. Left out, the meter shows the final number. */
  count?: number;
}

// The one meter that matters: matched points against the bar, with the bar's tick, the count
// and one plain sentence. The fill follows `count`, so it rises with the spots.
export function PointsMeter({ photo, bars, count }: MeterProps) {
  const g = gauges(photo, bars).find((x) => x.key === "points");
  if (!g) return null;
  const shown = count ?? g.value;
  const done = shown >= g.value;
  const short = shortBy(photo, bars);
  const top = g.value > 0 ? g.value / g.fill : 1;
  return (
    <div
      className="pm"
      data-testid="gauge-points"
      data-pass={g.pass ? "true" : "false"}
      data-crossed={shown >= g.bar ? "true" : "false"}
      data-done={done ? "true" : "false"}
      style={{ "--fill": Math.min(1, shown / top), "--mark": g.mark } as CSSProperties}
    >
      <p className="pm-count">
        <span className="pm-num" aria-hidden="true">
          {shown}
        </span>
        <span className="pm-unit">
          matching points
          <span className="pm-verdict">{verdict(g)}</span>
        </span>
      </p>
      <div className="pm-meter" aria-hidden="true">
        <span className="pm-tick-label" data-testid="bar-label">
          {barLabel(photo, bars)}
        </span>
        <span className="pm-track">
          <span className="pm-fill" />
          {!g.pass && <span className="pm-gap" />}
          <span className="pm-tick" />
        </span>
        {!g.pass && short > 0 && <span className="pm-short mono">{short} short</span>}
      </div>
      <p className="pm-sentence" data-testid="points-sentence">
        {pointsSentence(photo, bars)}
      </p>
      <span className="sr-only" data-testid="gauge-points-plain">
        {g.plain}
      </span>
    </div>
  );
}

function Head({ g }: { g: Gauge }) {
  return (
    <p className="bg-head">
      <span className="bg-label">{g.label}</span>
      <span className="bg-verdict">{verdict(g)}</span>
    </p>
  );
}

// Spread: where the drawn points fall on the ad photo, and the box around them. The spread score
// is that box's share of the photo, so the picture shows the thing that was measured.
function SpreadTile({
  g,
  photo,
  adSrc,
}: {
  g: Gauge;
  photo: EvidencePhoto;
  adSrc?: string | null;
}) {
  const pairs = photo.points?.sampled ?? [];
  const cov = coverage(pairs);
  const W = 160;
  const H = 120;
  const cw = W / HEAT_COLS;
  const ch = H / HEAT_ROWS;
  return (
    <li className="bg-tile" data-testid="gauge-spread" data-pass={g.pass ? "true" : "false"}>
      <Head g={g} />
      <div className="bg-spread">
        <svg
          className="bg-cover"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Where the ${pairs.length} drawn points fall on the ad photo`}
        >
          <rect className="bg-cover-ground" width={W} height={H} />
          {adSrc && (
            <image
              className="bg-cover-photo"
              href={adSrc}
              width={W}
              height={H}
              preserveAspectRatio="xMidYMid slice"
            />
          )}
          {cov.box && (
            <clipPath id={`bg-clip-${photo.alias}`}>
              <rect
                x={cov.box.x * W}
                y={cov.box.y * H}
                width={cov.box.w * W}
                height={cov.box.h * H}
              />
            </clipPath>
          )}
          <g clipPath={cov.box ? `url(#bg-clip-${photo.alias})` : undefined}>
            {cov.cells.map((n, i) =>
              n === 0 ? null : (
                <rect
                  key={i}
                  className="bg-cell"
                  x={(i % HEAT_COLS) * cw + 1}
                  y={Math.floor(i / HEAT_COLS) * ch + 1}
                  width={cw - 2}
                  height={ch - 2}
                  opacity={0.25 + 0.75 * (n / cov.most)}
                />
              ),
            )}
          </g>
          {cov.box && (
            <rect
              className="bg-box"
              x={cov.box.x * W}
              y={cov.box.y * H}
              width={cov.box.w * W}
              height={cov.box.h * H}
            />
          )}
        </svg>
        <div className="bg-words">
          <p className="bg-say">
            {g.pass
              ? "The points reach across the picture, not just one corner."
              : "The points sit in too small a patch of the picture."}
          </p>
          <p className="bg-plain mono" data-testid="gauge-spread-plain">
            {g.plain}
          </p>
          <p className="bg-fine">Squares: where the {pairs.length} drawn points fall.</p>
        </div>
      </div>
    </li>
  );
}

const times = (v: number) => `${Number(v.toFixed(2))} times`;

// Rivals: this building beside the next best one, as two bars on one scale.
function RivalTile({ g, photo }: { g: Gauge; photo: EvidencePhoto }) {
  const ratio = g.value;
  const scale = Math.max(1, ratio);
  const mine = photo.status === "located_elsewhere" ? "The building it matched" : "This home";
  return (
    <li className="bg-tile" data-testid="gauge-rival" data-pass={g.pass ? "true" : "false"}>
      <Head g={g} />
      <div className="bg-rivals" aria-hidden="true">
        <span className="bg-rival-name">{mine}</span>
        <span className="bg-rival-track">
          <span className="bg-rival-bar bg-rival-this" style={{ width: `${(1 / scale) * 100}%` }} />
        </span>
        <span className="bg-rival-name">Next best building</span>
        <span className="bg-rival-track">
          <span
            className="bg-rival-bar bg-rival-other"
            style={{ width: `${Math.max(0.012, ratio / scale) * 100}%` }}
          />
        </span>
      </div>
      <p className="bg-say">
        {ratio < 1
          ? `The next best building matched only ${times(ratio)} as strongly.`
          : `Another building matched ${times(ratio)} as strongly.`}{" "}
        A match is blocked at {times(g.bar)}.
      </p>
      <p className="bg-plain mono" data-testid="gauge-rival-plain">
        {g.plain}
      </p>
    </li>
  );
}

interface Props {
  photo: EvidencePhoto;
  bars: Record<string, number>;
  thresholdsVersion: string;
  adSrc?: string | null;
  /** The drawer draws the points meter on the match table itself, so it leaves it out here. */
  withPoints?: boolean;
}

// The measures, each drawn against the bar it was held to. The bar values come from the evidence
// file's `bars`, and the line under them says which thresholds file that was.
export function BarGauges({ photo, bars, thresholdsVersion, adSrc, withPoints = true }: Props) {
  const rows = gauges(photo, bars);
  if (rows.length === 0) return null;
  const spread = rows.find((g) => g.key === "spread");
  const rival = rows.find((g) => g.key === "rival");
  return (
    <div className="bg" data-testid="bar-gauges">
      {withPoints && <PointsMeter photo={photo} bars={bars} />}
      {(spread || rival) && (
        <ul className="bg-list" aria-label="What else was measured, and the bar for each">
          {spread && <SpreadTile g={spread} photo={photo} adSrc={adSrc} />}
          {rival && <RivalTile g={rival} photo={photo} />}
        </ul>
      )}
      <p className="bg-source mono">Bars read from thresholds {thresholdsVersion}</p>
    </div>
  );
}
