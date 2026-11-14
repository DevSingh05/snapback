import type { CSSProperties } from "react";

import { gauges } from "./read";
import type { EvidencePhoto } from "./types";

interface Props {
  photo: EvidencePhoto;
  bars: Record<string, number>;
  thresholdsVersion: string;
}

// Three measures, each drawn against the bar it was held to. The bar values come from the
// evidence file's `bars`, and the line under the gauges says which thresholds file that was.
export function BarGauges({ photo, bars, thresholdsVersion }: Props) {
  const rows = gauges(photo, bars);
  if (rows.length === 0) return null;
  return (
    <div className="bg" data-testid="bar-gauges">
      <ul className="bg-list" aria-label="What was measured, and the bar for each">
        {rows.map((g) => (
          <li
            key={g.key}
            className="bg-row"
            data-testid={`gauge-${g.key}`}
            data-pass={g.pass ? "true" : "false"}
          >
            <span className="bg-label">{g.label}</span>
            <span
              className="bg-track"
              aria-hidden="true"
              style={{ "--fill": g.fill, "--mark": g.mark } as CSSProperties}
            >
              <span className="bg-fill" />
              <span className="bg-mark" />
            </span>
            <span className="bg-value mono">{g.valueText}</span>
            <span className="bg-bar mono">
              {g.barText}
              <span className="bg-verdict">{g.pass ? " · met" : " · not met"}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="bg-source mono">Bars read from thresholds {thresholdsVersion}</p>
    </div>
  );
}
