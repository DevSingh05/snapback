import { useEffect, useMemo, useState } from "react";

import "./lab.css";
import { apiBase, apiFetch } from "../api";
import { SourceChip } from "../components/SourceChip";
import type { DataSource } from "../contracts";
import {
  calibrationLabel,
  conditionLabel,
  heldOutFrozenAt,
  type CalibrationPoint,
  ResultsError,
  calibrationSeries,
  memoryCatch,
  niceTicks,
  curveBars,
  linearScale,
  parseResults,
  pct,
  type ResultRow,
} from "./results";

const W = 760;
const H = 290;
const M = { top: 12, right: 16, bottom: 72, left: 52 };

function CurveChart({ bars }: { bars: ResultRow[] }) {
  const tickVals = niceTicks(Math.max(0.05, ...bars.map((b) => b.ci_high)));
  const max = tickVals[tickVals.length - 1]!;
  const y = linearScale([0, max], [H - M.bottom, M.top]);
  const slot = (W - M.left - M.right) / bars.length;
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-labelledby="curve-title"
      className="lab-svg"
      data-testid="curve-chart"
    >
      <title id="curve-title">
        Forged-reply false-accept rate by condition, with 95% interval and n
      </title>
      {tickVals.map((t) => (
        <g key={t}>
          <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className="lab-grid" />
          <text x={M.left - 8} y={y(t)} className="lab-tick" textAnchor="end" dy="0.32em">
            {pct(t)}
          </text>
        </g>
      ))}
      <text
        transform={`translate(12 ${(M.top + H - M.bottom) / 2}) rotate(-90)`}
        className="lab-axis"
        textAnchor="middle"
      >
        False-accept rate
      </text>
      {bars.map((b, i) => {
        const cx = M.left + slot * (i + 0.5);
        const bw = Math.min(56, slot * 0.6);
        return (
          <g key={b.condition} data-testid="curve-bar">
            <rect
              x={cx - bw / 2}
              y={y(b.rate)}
              width={bw}
              height={Math.max(0, H - M.bottom - y(b.rate))}
              className="lab-bar"
            />
            <line x1={cx} x2={cx} y1={y(b.ci_low)} y2={y(b.ci_high)} className="lab-whisker" />
            <line
              x1={cx - 6}
              x2={cx + 6}
              y1={y(b.ci_low)}
              y2={y(b.ci_low)}
              className="lab-whisker"
            />
            <line
              x1={cx - 6}
              x2={cx + 6}
              y1={y(b.ci_high)}
              y2={y(b.ci_high)}
              className="lab-whisker"
            />
            <text x={cx} y={H - M.bottom + 16} className="lab-tick" textAnchor="middle">
              {conditionLabel(b.condition)}
            </text>
            <text
              x={cx}
              y={H - M.bottom + 30}
              className="lab-tick lab-n"
              textAnchor="middle"
              data-testid="bar-n"
            >
              {`n = ${b.n}`}
            </text>
            <text
              x={cx}
              y={H - M.bottom + 44}
              className="lab-tick"
              textAnchor="middle"
              data-testid="bar-ci"
            >
              {`95% CI ${pct(b.ci_low)} to ${pct(b.ci_high)}`}
            </text>
            <text
              x={cx}
              y={H - M.bottom + 58}
              className="lab-axis"
              textAnchor="middle"
              data-testid="bar-rate"
            >
              {`${pct(b.rate)} (${b.k} of ${b.n})`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

const SERIES_CLASS = ["lab-s0", "lab-s1", "lab-s2"];

function CalibrationChart({ series }: { series: Map<string, CalibrationPoint[]> }) {
  const S = 280;
  const m = { top: 12, right: 16, bottom: 40, left: 48 };
  const x = linearScale([0, 1], [m.left, S - m.right]);
  const y = linearScale([0, 1], [S - m.bottom, m.top]);
  const entries = [...series.entries()];
  return (
    <div className="lab-cal">
      <svg
        viewBox={`0 0 ${S} ${S}`}
        role="img"
        aria-labelledby="cal-title"
        className="lab-svg lab-svg-square"
        data-testid="calibration-chart"
      >
        <title id="cal-title">
          Reliability diagram: locate score against how often the place check was right
        </title>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={m.left} x2={S - m.right} y1={y(t)} y2={y(t)} className="lab-grid" />
            <text x={m.left - 6} y={y(t)} className="lab-tick" textAnchor="end" dy="0.32em">
              {pct(t)}
            </text>
            <text x={x(t)} y={S - m.bottom + 14} className="lab-tick" textAnchor="middle">
              {pct(t)}
            </text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} className="lab-diagonal" />
        <text x={(m.left + S - m.right) / 2} y={S - 6} className="lab-axis" textAnchor="middle">
          Locate score
        </text>
        <text
          transform={`translate(10 ${(m.top + S - m.bottom) / 2}) rotate(-90)`}
          className="lab-axis"
          textAnchor="middle"
        >
          Right this often
        </text>
        {entries.map(([cond, pts], si) => (
          <g key={cond} className={SERIES_CLASS[si % SERIES_CLASS.length]} data-testid="cal-series">
            <polyline
              points={pts.map((p) => `${x(p.x)},${y(p.rate)}`).join(" ")}
              className="lab-line"
              fill="none"
            />
            {pts.map((p) => (
              <g key={`${p.condition}${p.metric}`} data-testid="cal-point">
                <line
                  x1={x(p.x)}
                  x2={x(p.x)}
                  y1={y(p.ci_low)}
                  y2={y(p.ci_high)}
                  className="lab-whisker"
                />
                <circle cx={x(p.x)} cy={y(p.rate)} r={4} className="lab-dot">
                  <title>{`${pct(p.rate)} right, n = ${p.n}, 95% CI ${pct(p.ci_low)} to ${pct(p.ci_high)}`}</title>
                </circle>
              </g>
            ))}
          </g>
        ))}
      </svg>
      <ul className="lab-legend" data-testid="cal-legend">
        {entries.map(([cond], si) => (
          <li key={cond} className={SERIES_CLASS[si % SERIES_CLASS.length]}>
            <span className="lab-swatch" aria-hidden="true" />
            {calibrationLabel(cond)}
            <span className="lab-n" data-testid="cal-legend-n">
              {` (n per bin: ${(series.get(cond) ?? []).map((p) => p.n).join(", ")})`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LabPanel({ csv, source }: { csv: string; source: DataSource }) {
  const parsed = useMemo(() => {
    try {
      return { rows: parseResults(csv), error: null as string | null };
    } catch (err) {
      return {
        rows: [] as ResultRow[],
        error: err instanceof ResultsError ? err.message : "results.csv could not be read",
      };
    }
  }, [csv]);

  const bars = curveBars(parsed.rows);
  const cal = calibrationSeries(parsed.rows);
  const mem = memoryCatch(parsed.rows);
  const calN = [...cal.values()].flat().reduce((a, p) => a + p.n, 0);
  const frozen = heldOutFrozenAt(parsed.rows);

  return (
    <section className="lab-panel" aria-labelledby="lab-title" data-testid="lab-panel">
      <header className="lab-head">
        <h2 id="lab-title">Lab</h2>
        <SourceChip source={source} />
      </header>
      <p className="lab-sub">
        Every number comes from eval/results.csv, with n and a 95% interval. Small n means wide
        intervals.{frozen ? ` Held-out set frozen ${frozen}.` : ""}
      </p>

      {parsed.error ? (
        <p role="alert" className="lab-note lab-error">
          {parsed.error}
        </p>
      ) : parsed.rows.length === 0 ? (
        <p className="lab-note" data-testid="lab-empty">
          No results yet. Run the eval to fill this in.
        </p>
      ) : (
        <>
          <div className="lab-block">
            <h3>Forged replies we let through, on the held-out set</h3>
            {bars.length > 0 ? (
              <div className="lab-scroll">
                <CurveChart bars={bars} />
              </div>
            ) : (
              <p className="lab-note" data-testid="curve-empty">
                No forged-reply rows in this file.
              </p>
            )}
          </div>
          {mem ? (
            <p className="lab-memory" data-testid="memory-catch">
              {`Memory catches ${mem.k} of ${mem.n} (${pct(mem.rate)}, 95% CI ${pct(mem.ci_low)} to ${pct(mem.ci_high)})`}
            </p>
          ) : null}
          <div className="lab-block">
            <h3>Locate score calibration (renders of our scans)</h3>
            {cal.size > 0 ? (
              <>
                <p className="lab-note" data-testid="cal-chip">
                  {`Measured on renders of our scans, n=${calN}`}
                </p>
                <CalibrationChart series={cal} />
              </>
            ) : (
              <p className="lab-note" data-testid="calibration-empty">
                No calibration rows in this file.
              </p>
            )}
          </div>
        </>
      )}
      <p className="lab-rule">
        Learned models can stop a pass. They can never call anyone a scammer.
      </p>
    </section>
  );
}

type Load =
  | { status: "loading" }
  | { status: "ready"; csv: string; source: DataSource }
  | { status: "error" };

// VITE_API_URL unset means fixture mode, same as the card: the synthetic sample is shown
// and labelled FIXTURE. With an API, the CSV is served at /eval/results.csv and labelled LIVE.
export function LabSection() {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  useEffect(() => {
    const ctrl = new AbortController();
    const base = apiBase();
    const run = async () => {
      const sample = async () => {
        const mod = await import("../../../../fixtures/contracts/results_sample.csv?raw");
        return { csv: mod.default, source: "fixture" as const };
      };
      if (!base) return sample();
      const res = await apiFetch("/eval/results.csv", { signal: ctrl.signal });
      // The API does not serve results yet: show the synthetic sample, labelled FIXTURE.
      if (res.status === 404) return sample();
      if (!res.ok) throw new Error(String(res.status));
      const csv = await res.text();
      // A committed synthetic file starts with "# FIXTURE": never label that LIVE.
      const first = csv.split(/\r?\n/, 1)[0] ?? "";
      return {
        csv,
        source: /^#\s*FIXTURE/i.test(first) ? ("fixture" as const) : ("live" as const),
      };
    };
    run()
      .then((r) => setLoad({ status: "ready", ...r }))
      .catch(() => {
        if (!ctrl.signal.aborted) setLoad({ status: "error" });
      });
    return () => ctrl.abort();
  }, []);

  if (load.status === "ready") return <LabPanel csv={load.csv} source={load.source} />;
  return (
    <section className="lab-panel" aria-labelledby="lab-title">
      <h2 id="lab-title">Lab</h2>
      <p className="lab-note" role="status">
        {load.status === "loading" ? "Loading results…" : "Results are not available right now."}
      </p>
    </section>
  );
}
