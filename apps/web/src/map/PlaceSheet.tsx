import { useEffect, useState } from "react";

import { HouseGlyph } from "../components/HouseGlyph";
import { SourceChip } from "../components/SourceChip";
import { aerialSrc, fetchPlaceSheet } from "./api";
import { ColumnMark } from "./panels";
import { S } from "./strings";
import type { PlaceFeature, PlaceSheetData } from "./types";

// How old the aerial is, in whole months, so the photo never passes for a live view.
export function monthsOld(iso: string, now: Date = new Date()): number | null {
  const at = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(at.getTime())) return null;
  const months = (now.getFullYear() - at.getFullYear()) * 12 + now.getMonth() - at.getMonth();
  return Math.max(0, months);
}

type Load =
  | { state: "loading" }
  | { state: "error" }
  | { state: "ready"; pid: string; sheet: PlaceSheetData };

// The place sheet: the side tab that opens when a place or its building is picked. It shows what
// is on CoStar's record for the place, the aerial with its true age, and the way into the walk.
export function PlaceSheet({
  place,
  onClose,
  onPass,
  onSheet,
}: {
  place: PlaceFeature;
  onClose: () => void;
  onPass: (pid: string) => void;
  onSheet?: (sheet: PlaceSheetData) => void;
}) {
  const p = place.properties;
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [tries, setTries] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    setLoad({ state: "loading" });
    fetchPlaceSheet(p.pid, ctl.signal)
      .then((sheet) => {
        setLoad({ state: "ready", pid: p.pid, sheet });
        onSheet?.(sheet);
      })
      .catch(() => {
        if (!ctl.signal.aborted) setLoad({ state: "error" });
      });
    return () => ctl.abort();
    // onSheet is a notification, not an input.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.pid, tries]);

  const sheet = load.state === "ready" && load.pid === p.pid ? load.sheet : null;
  const first = sheet?.plans[0];
  const photo = sheet ? aerialSrc(sheet) : null;
  const age = sheet?.aerial?.captured_on ? monthsOld(sheet.aerial.captured_on) : null;
  const hasScan = sheet ? sheet.has_3d_scan : p.has_scan;
  const walk = sheet?.walk_path ?? `/tour/${encodeURIComponent(p.pid)}`;

  return (
    <aside className="sheet" aria-label={S.kind(p.kind)} data-testid="place-sheet">
      <div className="sheet-aerial">
        {photo ? (
          <img src={photo} alt={S.aerialAlt} />
        ) : (
          <div className="sheet-standin">
            <HouseGlyph className="sheet-house" />
          </div>
        )}
        <span className="sheet-tag mono">
          {photo
            ? (sheet?.aerial?.line ?? S.aerialAlt)
            : p.source === "fixture"
              ? S.aerialStandIn
              : S.aerialNone}
        </span>
        {age != null ? <span className="sheet-age mono">{S.aerialAge(age)}</span> : null}
        <span className="sheet-inset" aria-hidden="true">
          <ColumnMark plans={p.n_plans} fits={p.fits_brief} scan={p.has_scan} />
        </span>
        <button type="button" className="sheet-close" aria-label={S.sheetClose} onClick={onClose}>
          <svg viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2 2l8 8M10 2l-8 8" />
          </svg>
        </button>
      </div>

      <div className="sheet-body">
        <div className="sheet-top">
          <p className="sheet-kicker mono">
            {S.kind(p.kind)} · {p.pid}
          </p>
          <SourceChip source={p.source} />
        </div>
        <h2 className="sheet-rent">
          {p.rent_from == null ? (
            S.rentFrom(null)
          ) : (
            <>
              <small>{S.rentLead}</small> {S.rentFrom(p.rent_from)} <small>{S.rentTail}</small>
            </>
          )}
        </h2>
        <p className="sheet-asof">{p.as_of}</p>
        {photo == null && sheet?.aerial?.line ? (
          <p className="sheet-line">{sheet.aerial.line}</p>
        ) : null}

        {load.state === "loading" ? <p className="sheet-wait">{S.sheetLoading}</p> : null}
        {load.state === "error" ? (
          <p className="sheet-wait" role="alert">
            {S.sheetError}{" "}
            <button type="button" className="btn-quiet" onClick={() => setTries((n) => n + 1)}>
              {S.retry}
            </button>
          </p>
        ) : null}

        {sheet ? (
          <>
            {hasScan ? (
              <div className="scan-badge" data-testid="scan-badge">
                <HouseGlyph className="scan-house" />
                <div>
                  <p className="scan-title">{S.scanBadge}</p>
                  <p className="scan-note">{S.scanNote}</p>
                </div>
                <a className="btn-press" href={walk}>
                  {S.walk}
                </a>
              </div>
            ) : null}

            <h3 className="sheet-h mono">{S.plansOnRecord}</h3>
            <ul className="plans">
              {sheet.plans.map((pl, i) => (
                <li key={pl.plan_key ?? i}>
                  <span className="plan-name">{pl.floor_plan ?? S.kind(p.kind)}</span>
                  <span className="plan-price">{pl.price_text}</span>
                </li>
              ))}
            </ul>
            {first ? <p className="sheet-line sheet-units">{first.availability_text}</p> : null}
            {first && first.must_haves.length > 0 ? (
              <ul className="musts">
                {first.must_haves.map((m) => (
                  <li
                    key={m.key}
                    className={m.met == null ? "must-unknown" : m.met ? "must-yes" : "must-no"}
                  >
                    <span className="must-tile" aria-hidden="true" />
                    {m.text}
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="sheet-line">
              <span className="sheet-label mono">{S.company}</span>
              {sheet.office_on_record ?? S.notOnRecord}
            </p>
          </>
        ) : null}

        <div className="sheet-acts">
          <a className="btn-line" href={`/?place=${encodeURIComponent(p.pid)}`}>
            {S.checkAd}
          </a>
          <button type="button" className="btn-quiet" onClick={() => onPass(p.pid)}>
            {S.pass}
          </button>
        </div>
      </div>
    </aside>
  );
}
