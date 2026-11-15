import { memo, useEffect, useMemo, useState } from "react";

import {
  KIND_NAME,
  KIND_UNIT,
  KINDS,
  caseFile,
  caseFileText,
  clampDay,
  dateOf,
  dayNo,
  frameAt,
  groupRadius,
  layoutStream,
  linksOf,
  otherDots,
  playFrom,
  signalRows,
  stepDay,
} from "./stream";
import type { Point, SignalKind, StreamGroup, StreamTimeline } from "./stream";
import "./stream.css";

const TICK_MS = 210;
const NARROW = "(max-width: 760px)";

function useNarrow(): boolean {
  const query = useMemo(
    () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(NARROW) : null),
    [],
  );
  const [narrow, setNarrow] = useState(query?.matches ?? false);
  useEffect(() => {
    if (!query) return;
    const on = () => setNarrow(query.matches);
    query.addEventListener("change", on);
    return () => query.removeEventListener("change", on);
  }, [query]);
  return narrow;
}

function n(x: number): string {
  return x.toLocaleString("en-US");
}

function days(x: number | null): string {
  if (x === null) return "not flagged";
  return x === 1 ? "1 day" : `${x} days`;
}

// One day's unlinked ads. Memoised: scrubbing flips `on` for a few days, not 2,700 dots.
const DayDots = memo(function DayDots({ dots, on }: { dots: Point[]; on: boolean }) {
  return (
    <g className={on ? "sw-day sw-day-on" : "sw-day"}>
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={1.7} />
      ))}
    </g>
  );
});

function Stage({
  data,
  pos,
  selected,
  onSelect,
  narrow,
}: {
  data: StreamTimeline;
  pos: number;
  selected: string | null;
  onSelect: (id: string) => void;
  narrow: boolean;
}) {
  const layout = useMemo(() => layoutStream(data, narrow), [data, narrow]);
  const dots = useMemo(
    () => otherDots(data, layout.width, layout.height),
    [data, layout.width, layout.height],
  );
  const links = useMemo(() => new Map(data.groups.map((g) => [g.id, linksOf(g)])), [data]);
  const frame = frameAt(data, pos);
  return (
    <svg
      className="sw-stage"
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role="img"
      aria-label={`Day ${frame.pos} of ${data.days}: ${n(frame.adsPosted)} synthetic ads posted, ${frame.groupsFlagged} groups flagged`}
    >
      <g className="sw-noise" aria-hidden="true">
        {dots.map((d, i) => (
          <DayDots key={i} dots={d} on={i < pos} />
        ))}
      </g>
      {data.groups.map((g, gi) => {
        const f = frame.groups[gi];
        if (!f?.started) return null;
        const c = layout.centres.get(g.id) as Point;
        const r = groupRadius(f.shown);
        return (
          <g
            key={g.id}
            className="sw-group"
            data-flagged={f.flagged}
            data-selected={selected === g.id}
            data-dim={selected !== null && selected !== g.id}
          >
            {f.flagged ? (
              <>
                <circle className="sw-ping" cx={c.x} cy={c.y} r={r} />
                <circle className="sw-halo" cx={c.x} cy={c.y} r={r} />
              </>
            ) : null}
            <g className="sw-links">
              {(links.get(g.id) ?? [])
                .filter((l) => l.day < pos)
                .map((l) => {
                  const a = layout.ads.get(l.from) as Point;
                  const b = layout.ads.get(l.to) as Point;
                  return (
                    <line
                      key={`${l.kind}-${l.key}-${l.to}`}
                      className={`sw-link sw-link-${l.kind}`}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                    />
                  );
                })}
            </g>
            <g>
              {g.ads
                .filter((a) => a.day < pos)
                .map((a) => {
                  const p = layout.ads.get(a.id) as Point;
                  return (
                    <circle
                      key={a.id}
                      className="sw-ad"
                      data-linked={a.flag_day < pos}
                      cx={p.x}
                      cy={p.y}
                      r={4.2}
                    />
                  );
                })}
            </g>
            {f.flagged ? (
              <text className="sw-label" x={c.x} y={c.y - r - 10} textAnchor="middle">
                <tspan className="sw-label-name">{g.label}</tspan>
                <tspan dx="8">caught in {days(g.gap_days)}</tspan>
              </text>
            ) : null}
            <circle
              className="sw-hit"
              cx={c.x}
              cy={c.y}
              r={Math.max(r, 34)}
              role="button"
              tabIndex={0}
              aria-label={`${g.label}: ${f.shown} ads by day ${frame.pos}. Show the evidence.`}
              onClick={() => onSelect(g.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(g.id);
                }
              }}
            />
          </g>
        );
      })}
    </svg>
  );
}

function Lanes({
  data,
  pos,
  selected,
  onSelect,
}: {
  data: StreamTimeline;
  pos: number;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const frame = frameAt(data, pos);
  const pct = (index: number) => `${(index / data.days) * 100}%`;
  return (
    <section className="sw-lanes" aria-label="Time to detect, per group">
      <header>
        <h2>Time to detect</h2>
        <p className="sw-key">
          <span className="sw-key-gap" /> posting, not yet linked
          <span className="sw-key-on" /> flagged
        </p>
      </header>
      <ol>
        {data.groups.map((g, gi) => {
          const f = frame.groups[gi];
          if (!f) return null;
          const last = Math.max(...g.ads.map((a) => a.day)) + 1;
          const flag = g.flag_day ?? data.days;
          return (
            <li key={g.id}>
              <button
                type="button"
                className="sw-lane"
                aria-pressed={selected === g.id}
                data-started={f.started}
                data-flagged={f.flagged}
                onClick={() => onSelect(g.id)}
              >
                <strong>{g.label}</strong>
                <span className="sw-track" aria-hidden="true">
                  <span
                    className="sw-seg sw-seg-gap"
                    style={{ left: pct(g.first_day), width: pct(flag - g.first_day) }}
                  />
                  <span
                    className="sw-seg sw-seg-on"
                    style={{ left: pct(flag), width: pct(Math.max(0, last - flag)) }}
                  />
                  <span className="sw-head" style={{ left: pct(pos) }} />
                </span>
                <span className="sw-lane-gap">
                  {f.flagged ? days(g.gap_days) : f.started ? "not yet" : ""}
                </span>
                <span className="sw-lane-sub">
                  first ad day {dayNo(g.first_day)}
                  {g.flag_day === null ? "" : ` · flagged day ${dayNo(g.flag_day)}`} ·{" "}
                  {g.ads_before_flag} ads before flag
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="sw-fine">
        Flagged = the first day the ring finder, seeing only the ads posted so far, reports a group
        with at least {data.min_ads} of these ads.
      </p>
    </section>
  );
}

function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function printPage(): void {
  document.body.classList.add("sw-printing");
  const done = () => document.body.classList.remove("sw-printing");
  window.addEventListener("afterprint", done, { once: true });
  window.print();
}

export function EvidencePanel({
  data,
  group,
  pos,
  onClose,
}: {
  data: StreamTimeline;
  group: StreamGroup;
  pos: number;
  onClose: () => void;
}) {
  const rows = signalRows(group, pos);
  const shown = group.ads.filter((a) => a.day < pos).length;
  const flagged = group.flag_day !== null && group.flag_day < pos;
  const file = caseFile(data, group, pos);
  const mix = Object.entries(group.answer_key).sort((a, b) => b[1] - a[1]);
  return (
    <section className="sw-panel" aria-label={`${group.label}: evidence`}>
      <header>
        <div>
          <h2>{group.label}</h2>
          <p className="sw-fine">
            {shown} of its {group.n_ads} ads posted by day {pos} · {group.n_phones} numbers by day{" "}
            {data.days}
          </p>
        </div>
        <button type="button" className="sw-close" onClick={onClose}>
          Close
        </button>
      </header>

      <dl className="sw-facts">
        <div>
          <dt>First ad</dt>
          <dd>
            day {dayNo(group.first_day)}
            <small>{dateOf(data.start, dayNo(group.first_day))}</small>
          </dd>
        </div>
        <div>
          <dt>Flagged</dt>
          <dd>
            {group.flag_day === null ? "no" : `day ${dayNo(group.flag_day)}`}
            <small>
              {group.flag_day === null
                ? ""
                : flagged
                  ? dateOf(data.start, dayNo(group.flag_day))
                  : "not yet"}
            </small>
          </dd>
        </div>
        <div>
          <dt>Time to detect</dt>
          <dd>{days(group.gap_days)}</dd>
        </div>
        <div>
          <dt>Up before the flag</dt>
          <dd>
            {group.ads_before_flag} ads
            <small>{group.ad_days_before_flag} ad-days</small>
          </dd>
        </div>
      </dl>
      <p className="sw-estimate">
        <strong>About {n(group.renters_est)} renters</strong> may have seen those ads before the
        flag. <span className="sw-tag">SYNTHETIC ESTIMATE</span> {group.ad_days_before_flag} ad-days
        times {data.views_per_ad_day} renters per ad per day, an assumption and not a measurement.
      </p>

      <h3>Why these ads are linked</h3>
      {rows.length === 0 ? (
        <p className="sw-fine">No two of its ads share anything by day {pos}.</p>
      ) : (
        <ul className="sw-signals">
          {rows.map((r) => (
            <li key={r.kind} data-kind={r.kind}>
              <div className="sw-signal-head">
                <span className={`sw-swatch sw-swatch-${r.kind}`} aria-hidden="true" />
                <strong>{KIND_NAME[r.kind]}</strong>
                <span className="sw-weight" title="The weight the ring finder gives one such link">
                  {r.weight === 0 ? "context · weight 0" : `weight ${r.weight}`}
                </span>
              </div>
              <p>
                <b>{r.values}</b> {KIND_UNIT[r.kind]} shared, linking <b>{r.ads}</b> of {shown} ads
              </p>
              <span className="sw-bar" aria-hidden="true">
                <span style={{ width: `${shown ? (r.ads / shown) * 100 : 0}%` }} />
              </span>
              <details>
                <summary>Show each one</summary>
                <ol>
                  {r.top.slice(0, 12).map((t) => (
                    <li key={t.key}>
                      <span>{t.label}</span>
                      <b>{t.n} ads</b>
                    </li>
                  ))}
                  {r.top.length > 12 ? (
                    <li className="sw-fine">and {r.top.length - 12} more, all in the case file</li>
                  ) : null}
                </ol>
              </details>
            </li>
          ))}
        </ul>
      )}
      <p className="sw-fine">
        Ads that ask for money first are joined when they share a number (weight{" "}
        {data.weights.phone}), a wording ({data.weights.wording}) or two or more photo-sets (
        {data.weights.photo}). A group is reported at {data.min_ads} ads under 2 numbers. One number
        with many ads is a property manager, not a ring.
      </p>

      <h3>Checked against the answer key</h3>
      <p className="sw-fine">
        Ads in this group by seeded ring: {mix.map(([name, k]) => `${name} ${k}`).join(", ")}.
        {mix.length > 1
          ? " The group blends more than one seeded ring: the ads are caught, the operators are not yet told apart."
          : ""}
      </p>

      <div className="sw-actions">
        <button
          type="button"
          className="sw-btn"
          onClick={() =>
            download(
              `snapback-case-file-ring-${group.id}-SYNTHETIC.json`,
              JSON.stringify(file, null, 2),
              "application/json",
            )
          }
        >
          Download case file (JSON)
        </button>
        <button type="button" className="sw-btn sw-btn-quiet" onClick={printPage}>
          Print summary
        </button>
      </div>
      <pre className="sw-print" data-testid="case-print">
        {caseFileText(file)}
      </pre>
    </section>
  );
}

export function StreamView({
  data,
  initialPos,
  initialRing = null,
}: {
  data: StreamTimeline;
  initialPos?: number;
  initialRing?: string | null;
}) {
  const [pos, setPos] = useState(() => clampDay(initialPos ?? data.days, data.days));
  const [playing, setPlaying] = useState(false);
  const [ring, setRing] = useState<string | null>(initialRing);
  const narrow = useNarrow();

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setPos((p) => {
        const next = stepDay(p, data.days);
        if (!next.playing) setPlaying(false);
        return next.pos;
      });
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [playing, data.days]);

  const frame = frameAt(data, pos);
  const key = data.answer_key;
  const group = data.groups.find((g) => g.id === ring) ?? null;
  const toggle = (id: string) => setRing((r) => (r === id ? null : id));
  const kinds = KINDS as SignalKind[];

  return (
    <div className="sw" data-playing={playing}>
      <header className="sw-top">
        <div>
          <p className="inv-eyebrow">Investigator view · 90-day stream</p>
          <h1>Watch rings form, and how fast we catch them</h1>
          <p className="inv-sub">
            {n(data.n_ads)} synthetic rental ads over {data.days} days, with {key.n_seeded} seeded
            rings hidden among honest ones. The ring finder runs once per day on only the ads posted
            so far.
          </p>
        </div>
        <div className="inv-chips">
          <span className="inv-chip inv-chip-synth">SYNTHETIC DATA</span>
          <span className="inv-chip">FIXTURE</span>
        </div>
      </header>

      <section className="sw-strip" aria-label="Measured on the synthetic stream">
        <div className="sw-tile sw-tile-hero">
          <b>
            {key.seeded_flagged} of {key.n_seeded}
          </b>
          <span>seeded rings flagged</span>
          <small>
            {frame.seededFlagged} of {key.n_seeded} by day {pos}
          </small>
        </div>
        <div className="sw-tile sw-tile-hero">
          <b>{days(key.median_gap_days)}</b>
          <span>median time to detect</span>
          <small>
            first ad to first flag, n = {key.n_gap} seeded rings · as grouped:{" "}
            {days(data.summary.median_gap_days)}, n = {data.summary.n_gap}
          </small>
        </div>
        <div className="sw-tile">
          <b>
            {key.ring_ads_flagged} of {key.ring_ads}
          </b>
          <span>ring ads flagged</span>
          <small>
            {key.honest_flagged} of {n(key.n_honest)} honest ads flagged
          </small>
        </div>
        <div className="sw-tile sw-tile-limit">
          <b>
            {key.seeded_separated} of {key.n_seeded}
          </b>
          <span>rings told apart</span>
          <small>
            Limit: {data.summary.groups_found} groups for {key.n_seeded} rings. Rings that share
            wording blend into one group.
          </small>
        </div>
      </section>

      <div className="sw-main" data-open={group !== null}>
        <div className="sw-board">
          <div className="sw-stage-wrap">
            <Stage data={data} pos={pos} selected={ring} onSelect={toggle} narrow={narrow} />
            <div className="sw-board-chips" aria-hidden="true">
              <span>SYNTHETIC DATA</span>
              <span>FIXTURE</span>
            </div>
          </div>
          <ul className="sw-legend">
            <li>
              <svg className="sw-dot sw-dot-other" viewBox="0 0 10 10" aria-hidden="true">
                <circle cx="5" cy="5" r="5" />
              </svg>{" "}
              ad, not linked
            </li>
            <li>
              <svg className="sw-dot sw-dot-ring" viewBox="0 0 10 10" aria-hidden="true">
                <circle cx="5" cy="5" r="5" />
              </svg>{" "}
              ad in a flagged group
            </li>
            {kinds.map((k) => (
              <li key={k}>
                <span className={`sw-swatch sw-swatch-${k}`} /> {KIND_NAME[k].toLowerCase()}
              </li>
            ))}
          </ul>
          <div className="sw-controls">
            <button
              type="button"
              className="sw-play"
              onClick={() => {
                if (playing) {
                  setPlaying(false);
                } else {
                  setPos((p) => playFrom(p, data.days));
                  setPlaying(true);
                }
              }}
            >
              {playing ? "Pause" : pos >= data.days ? "Play 90 days" : "Play"}
            </button>
            <label className="sw-slider">
              <span className="sw-day-read">
                Day <b>{pos}</b> of {data.days}
                <small>{pos === 0 ? "before the first ad" : dateOf(data.start, pos)}</small>
              </span>
              <input
                type="range"
                min={0}
                max={data.days}
                step={1}
                value={pos}
                aria-label="Day of the stream"
                onChange={(e) => {
                  setPlaying(false);
                  setPos(clampDay(Number(e.target.value), data.days));
                }}
              />
            </label>
            <p className="sw-live" aria-live="off">
              <span>
                <b>{n(frame.adsPosted)}</b> ads posted
              </span>
              <span>
                <b>{n(frame.adsFlagged)}</b> flagged
              </span>
              <span>
                <b>{frame.groupsFlagged}</b> groups caught
              </span>
            </p>
          </div>
        </div>

        <div className="sw-side">
          <Lanes data={data} pos={pos} selected={ring} onSelect={toggle} />
          {group ? (
            <EvidencePanel data={data} group={group} pos={pos} onClose={() => setRing(null)} />
          ) : (
            <p className="sw-hint">
              Select a group on the board or in the list to see which shared signals link its ads,
              and to export a case file.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
