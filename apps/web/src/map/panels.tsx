import { useState } from "react";
import type { ReactNode } from "react";

import { HouseGlyph } from "../components/HouseGlyph";
import { PlaceMark } from "./placeArt";
import { S } from "./strings";
import { EMPTY_CRITERIA, criteriaCount } from "./types";
import type { Criteria, PlaceFeature, RenterEvent } from "./types";

export function Pane({
  title,
  sub,
  collapsed,
  onToggle,
  className,
  aside,
  children,
}: {
  title: string;
  sub?: string;
  collapsed: boolean;
  onToggle: () => void;
  className?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={`pane${className ? ` ${className}` : ""}`} aria-label={title}>
      <header className="pane-head">
        <div>
          <h2 className="pane-title">{title}</h2>
          {sub && !collapsed ? <p className="pane-sub">{sub}</p> : null}
        </div>
        {aside}
        <button
          type="button"
          className="pane-toggle"
          aria-expanded={!collapsed}
          aria-label={collapsed ? S.expand(title) : S.collapse(title)}
          onClick={onToggle}
        >
          <svg viewBox="0 0 12 12" aria-hidden="true">
            <path d={collapsed ? "M2 4l4 4 4-4" : "M2 8l4-4 4 4"} />
          </svg>
        </button>
      </header>
      {collapsed ? null : children}
    </section>
  );
}

const BEDS: [string, number | null][] = [
  [S.any, null],
  [S.studio, 0],
  ["1", 1],
  ["2", 2],
  ["3+", 3],
];
const RENT_MIN = 800;
const RENT_MAX = 3200; // the top of the slider means "Any"

export function CriteriaPanel({
  value,
  onChange,
  collapsed,
  onToggle,
}: {
  value: Criteria;
  onChange: (next: Criteria) => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const [own, setOwn] = useState("");
  const set = (patch: Partial<Criteria>) => onChange({ ...value, ...patch });
  const count = criteriaCount(value);
  const toggle = (
    key: "no_walkup" | "parking" | "pets" | "scan_only" | "units_only",
    label: string,
  ) => (
    <label className={`tog${value[key] ? " tog-on" : ""}`}>
      <input
        type="checkbox"
        checked={value[key]}
        onChange={(e) => set({ [key]: e.target.checked })}
      />
      <span className="tog-box" aria-hidden="true" />
      {label}
    </label>
  );
  const addOwn = () => {
    const t = own.trim().slice(0, 60);
    if (t && !value.own.includes(t)) set({ own: [...value.own, t] });
    setOwn("");
  };
  return (
    <Pane
      title={S.criteria}
      collapsed={collapsed}
      onToggle={onToggle}
      className="pane-criteria"
      aside={count > 0 ? <span className="pane-count mono">{count} set</span> : null}
    >
      <div className="crit">
        <p className="crit-group mono">{S.criteriaCoStar}</p>
        <label className="crit-range">
          <span className="crit-label">{S.budget}</span>
          <output className="crit-out">
            {value.max_rent == null ? S.any : `$${value.max_rent.toLocaleString("en-US")}`}
          </output>
          <input
            type="range"
            min={RENT_MIN}
            max={RENT_MAX}
            step={50}
            value={value.max_rent ?? RENT_MAX}
            aria-valuetext={
              value.max_rent == null ? S.any : `$${value.max_rent.toLocaleString("en-US")} a month`
            }
            onChange={(e) => {
              const v = Number(e.target.value);
              set({ max_rent: v >= RENT_MAX ? null : v });
            }}
          />
        </label>
        <fieldset className="crit-beds">
          <legend className="crit-label">{S.beds}</legend>
          <div className="seg">
            {BEDS.map(([label, v]) => (
              <label key={label} className={`seg-opt${value.beds_min === v ? " seg-on" : ""}`}>
                <input
                  type="radio"
                  name="beds"
                  checked={value.beds_min === v}
                  onChange={() => set({ beds_min: v })}
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="togs">
          {toggle("no_walkup", S.noWalkup)}
          {toggle("parking", S.parking)}
          {toggle("pets", S.pets)}
        </div>
        <p className="crit-group mono">{S.criteriaMap}</p>
        <div className="togs">
          {toggle("scan_only", S.scanOnly)}
          {toggle("units_only", S.unitsOnly)}
        </div>
        <p className="crit-group mono">{S.criteriaOwn}</p>
        <form
          className="own"
          onSubmit={(e) => {
            e.preventDefault();
            addOwn();
          }}
        >
          <label className="sr-only" htmlFor="own-must">
            {S.ownLabel}
          </label>
          <input
            id="own-must"
            type="text"
            value={own}
            maxLength={60}
            placeholder={S.ownPlaceholder}
            onChange={(e) => setOwn(e.target.value)}
          />
          <button type="submit" className="own-add" disabled={!own.trim()}>
            {S.ownAdd}
          </button>
        </form>
        {value.own.length > 0 ? (
          <ul className="own-list">
            {value.own.map((t) => (
              <li key={t}>
                {t}
                <button
                  type="button"
                  className="own-drop"
                  aria-label={S.ownDrop(t)}
                  onClick={() => set({ own: value.own.filter((x) => x !== t) })}
                >
                  <svg viewBox="0 0 12 12" aria-hidden="true">
                    <path d="M3 3l6 6M9 3l-6 6" />
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <p className="crit-hint">{S.ownHint}</p>
        {count > 0 ? (
          <button type="button" className="crit-clear" onClick={() => onChange(EMPTY_CRITERIA)}>
            {S.clear}
          </button>
        ) : null}
      </div>
    </Pane>
  );
}

export interface Proposal {
  count: number;
}

// The corner panel (the Fish Market picture-in-picture): what the renter did on the map, live in
// this browser, and the one thing the finder offers to remember. Until the finder crew (M9)
// lands, the offer is picked by code and stamped as policy.
export function FinderPip({
  events,
  proposal,
  onYes,
  onNo,
  collapsed,
  onToggle,
}: {
  events: RenterEvent[];
  proposal: Proposal | null;
  onYes: () => void;
  onNo: () => void;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <Pane
      title={S.finder}
      sub={S.finderSub}
      collapsed={collapsed}
      onToggle={onToggle}
      className="pane-finder"
      aside={
        <span className="pane-count mono">
          <span className="live-dot" aria-hidden="true" />
          {events.length} {events.length === 1 ? "event" : "events"}
        </span>
      }
    >
      <div className="finder" aria-live="polite">
        {proposal ? (
          <div className="proposal" data-testid="proposal">
            <span className="stamp mono">{S.proposalStamp}</span>
            <p>{S.proposal(proposal.count)}</p>
            <div className="proposal-acts">
              <button type="button" className="btn-press" onClick={onYes}>
                {S.proposalYes}
              </button>
              <button type="button" className="btn-quiet" onClick={onNo}>
                {S.proposalNo}
              </button>
            </div>
          </div>
        ) : null}
        {events.length === 0 ? (
          <p className="finder-empty">{S.finderEmpty}</p>
        ) : (
          <ol className="finder-log">
            {events.slice(0, 4).map((e) => (
              <li key={e.id} className={`ev ev-${e.kind}`}>
                <span className="ev-kind mono">{S.finderStamp}</span>
                {e.text}
              </li>
            ))}
          </ol>
        )}
      </div>
    </Pane>
  );
}

// The ledger under the stage, and the list view for keyboards and screen readers: every place
// on the map is a button here, in the same order for everyone.
export function PlaceLedger({
  places,
  passed,
  selectedPid,
  onPick,
}: {
  places: PlaceFeature[];
  passed: ReadonlySet<string>;
  selectedPid: string | null;
  onPick: (pid: string) => void;
}) {
  const rank = (f: PlaceFeature) =>
    (passed.has(f.properties.pid) ? 2 : 0) + (f.properties.fits_brief ? 0 : 1);
  const sorted = [...places].sort(
    (a, b) =>
      rank(a) - rank(b) ||
      (a.properties.rent_from ?? Infinity) - (b.properties.rent_from ?? Infinity) ||
      a.properties.pid.localeCompare(b.properties.pid),
  );
  if (sorted.length === 0) return <p className="ledger-empty">{S.ledgerEmpty}</p>;
  return (
    <ul className="ledger" data-testid="place-list">
      {sorted.map((f) => {
        const p = f.properties;
        const isPassed = passed.has(p.pid);
        return (
          <li key={p.pid}>
            <button
              type="button"
              className={`lcard${p.fits_brief ? " lcard-fit" : ""}${isPassed ? " lcard-passed" : ""}`}
              data-pid={p.pid}
              aria-pressed={selectedPid === p.pid}
              onClick={() => onPick(p.pid)}
            >
              <span className="lcard-art">
                <PlaceMark
                  kind={p.kind}
                  plans={p.n_plans}
                  fits={p.fits_brief && !isPassed}
                  scan={p.has_scan}
                />
              </span>
              <span className="lcard-body">
                <span className="lcard-kicker mono">
                  {S.kindShort(p.kind)} · {S.plansShort(p.n_plans)}
                </span>
                <span className="lcard-rent">
                  {p.rent_from != null ? <small>{S.rentLead} </small> : null}
                  {S.rentFrom(p.rent_from)}
                  {p.rent_from != null ? <small> {S.rentTail}</small> : null}
                </span>
                <span className="lcard-meta">
                  {S.units(p.units_reported)}, {S.cardAsOf(p.source)}
                </span>
              </span>
              {p.has_scan ? (
                <span className="lcard-inset">
                  <HouseGlyph className="lcard-house" />
                  <span className="mono">{S.scanTag}</span>
                </span>
              ) : null}
              {isPassed ? <span className="lcard-flag mono">{S.passedTag}</span> : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
