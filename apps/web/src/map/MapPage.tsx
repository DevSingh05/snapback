import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import { Wordmark } from "../components/HouseGlyph";
import { usePrefersReducedMotion } from "../twin/useReducedMotion";
import { CityMap } from "./CityMap";
import type { MapStatus } from "./CityMap";
import { PlaceSheet } from "./PlaceSheet";
import { fetchPlacesMap } from "./api";
import type { Look } from "./mapStyle";
import { CriteriaPanel, FinderPip, PlaceLedger } from "./panels";
import { recordFinderEvent } from "../shell/finderStore";
import { S } from "./strings";
import { EMPTY_CRITERIA, criteriaCount } from "./types";
import type { Criteria, PlaceSheetData, PlacesMap, RenterEvent } from "./types";
import "./map.css";

const NARROW = "(max-width: 760px)";
const PROPOSE_AFTER = 2; // walk-ups passed on before the finder offers to remember

function useNarrow(): boolean {
  const read = () => typeof window.matchMedia === "function" && window.matchMedia(NARROW).matches;
  const [narrow, setNarrow] = useState(read);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(NARROW);
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

type Feed = { state: "loading" } | { state: "error" } | { state: "ready"; feed: PlacesMap };

// The city: every place CoStar has researched, as a column on a 3D map of Houston. The stage
// holds the map with the count, the brief and the finder over it and the place sheet at its
// side; the attribution line and the ledger of places sit under the stage, always in view.
export default function MapPage({ MapView = CityMap }: { MapView?: typeof CityMap }) {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const look: Look = params.get("look") === "paper" ? "paper" : "glass";
  const narrow = useNarrow();
  const reducedMotion = usePrefersReducedMotion();

  const [criteria, setCriteria] = useState<Criteria>(EMPTY_CRITERIA);
  const [load, setLoad] = useState<Feed>({ state: "loading" });
  const [tries, setTries] = useState(0);
  const [selectedPid, setSelectedPid] = useState<string | null>(params.get("place"));
  const [passed, setPassed] = useState<ReadonlySet<string>>(new Set());
  const [events, setEvents] = useState<RenterEvent[]>([]);
  const [mapStatus, setMapStatus] = useState<MapStatus>("loading");
  const [miss, setMiss] = useState(false);
  const [briefOpen, setBriefOpen] = useState(!narrow);
  const [finderOpen, setFinderOpen] = useState(!narrow);
  const [walkupsPassed, setWalkupsPassed] = useState(0);
  const [proposalOff, setProposalOff] = useState(false);
  const sheets = useRef(new Map<string, PlaceSheetData>());
  const nextId = useRef(1);

  const log = useCallback((kind: RenterEvent["kind"], text: string, pid?: string) => {
    setEvents((prev) => [{ id: nextId.current++, kind, text, pid }, ...prev].slice(0, 30));
    recordFinderEvent(kind, text); // so the Finder tab can show this visit's events
  }, []);

  useEffect(() => {
    const ctl = new AbortController();
    fetchPlacesMap(criteria, ctl.signal)
      .then((feed) => setLoad({ state: "ready", feed }))
      .catch(() => {
        if (!ctl.signal.aborted) setLoad({ state: "error" });
      });
    return () => ctl.abort();
  }, [criteria, tries]);

  useEffect(() => {
    if (!miss) return;
    const t = window.setTimeout(() => setMiss(false), 3200);
    return () => window.clearTimeout(t);
  }, [miss]);

  const feed = load.state === "ready" ? load.feed : null;
  const places = useMemo(() => feed?.features ?? [], [feed]);
  const selected = places.find((f) => f.properties.pid === selectedPid) ?? null;
  const set = criteriaCount(criteria) > 0;
  const ledgerName = feed?.source === "live" ? S.ledger : S.ledgerSample;
  const flatMap = look === "paper" || mapStatus === "raster" || mapStatus === "failed";

  const pick = useCallback(
    (pid: string) => {
      setMiss(false);
      setSelectedPid(pid);
      log("opened", S.evOpened(pid), pid);
      if (window.matchMedia?.(NARROW).matches) setFinderOpen(false);
    },
    [log],
  );

  const pass = (pid: string) => {
    setPassed((prev) => new Set(prev).add(pid));
    setSelectedPid(null);
    log("passed", S.evPassed(pid), pid);
    const walkup = sheets.current.get(pid)?.plans[0]?.must_haves.find((m) => m.key === "walkup");
    if (walkup?.met === false) setWalkupsPassed((n) => n + 1);
  };

  const change = (next: Criteria) => {
    setCriteria(next);
    log("criteria", S.evCriteria);
  };

  const proposal =
    !proposalOff && !criteria.no_walkup && walkupsPassed >= PROPOSE_AFTER
      ? { count: walkupsPassed }
      : null;

  const padding = useMemo(
    () =>
      narrow
        ? { top: 0, right: 0, bottom: 0, left: 0 }
        : { top: 0, right: selectedPid ? 440 : 0, bottom: 0, left: 340 },
    [narrow, selectedPid],
  );

  return (
    <div className={`city${selected ? " city-picked" : ""}`} data-look={look}>
      <div className="stage">
        <MapView
          places={places}
          passed={passed}
          selectedPid={selected ? selectedPid : null}
          look={look}
          forceRaster={params.get("tiles") === "raster"}
          reducedMotion={reducedMotion}
          padding={padding}
          onPick={pick}
          onMiss={() => setMiss(true)}
          onStatus={setMapStatus}
        />

        <p className="attribution mono" data-testid="attribution">
          Map:{" "}
          <a href="https://openfreemap.org" target="_blank" rel="noreferrer">
            OpenFreeMap
          </a>{" "}
          ©{" "}
          <a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">
            OpenMapTiles
          </a>
          . Data from{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            OpenStreetMap
          </a>{" "}
          contributors.
        </p>

        <ul className="legend mono" aria-label="Map key">
          <li className="lg-fit">{S.legendFit}</li>
          <li className="lg-other">{S.legendOther}</li>
          <li className="lg-scan">{S.legendScan}</li>
          {flatMap ? null : <li className="lg-height">{S.legendHeight}</li>}
          <li className="lg-chip">{S.legendChip(feed?.source ?? "fixture")}</li>
        </ul>

        <div className="col-left">
          <div className="hud">
            <div className="hud-top">
              <a className="hud-brand" href="/">
                <Wordmark />
              </a>
              <span className="hud-city mono">
                {S.eyebrow} · {S.city}
              </span>
              <SourceChip source={feed?.source ?? "fixture"} />
            </div>
            {load.state === "ready" ? (
              <h1 className="hud-count" data-testid="count">
                <span className="hud-n">{load.feed.n_places.toLocaleString("en-US")}</span>
                <span className="hud-noun">
                  {S.countNoun(load.feed.n_places, load.feed.source)}
                </span>
              </h1>
            ) : load.state === "loading" ? (
              <p className="hud-wait">{S.loading}</p>
            ) : (
              <p className="hud-wait" role="alert">
                {S.loadError}{" "}
                <button type="button" className="btn-quiet" onClick={() => setTries((n) => n + 1)}>
                  {S.retry}
                </button>
              </p>
            )}
            {feed ? (
              <p className="hud-fit">
                <strong>{set ? S.fitLine(feed.n_fit, feed.n_places) : S.noBrief}</strong>
                <span className="hud-asof">{feed.as_of}</span>
              </p>
            ) : null}
          </div>

          <CriteriaPanel
            value={criteria}
            onChange={change}
            collapsed={!briefOpen}
            onToggle={() => setBriefOpen((v) => !v)}
          />
        </div>

        <div className="rail-right">
          <FinderPip
            events={events}
            proposal={proposal}
            collapsed={!finderOpen}
            onToggle={() => setFinderOpen((v) => !v)}
            onYes={() => {
              setCriteria((c) => ({ ...c, no_walkup: true }));
              log("remembered", S.remembered);
            }}
            onNo={() => setProposalOff(true)}
          />
          {selected ? (
            <PlaceSheet
              key={selected.properties.pid}
              place={selected}
              onClose={() => setSelectedPid(null)}
              onPass={pass}
              onSheet={(sheet) => sheets.current.set(sheet.property_id, sheet)}
            />
          ) : null}
        </div>

        {mapStatus === "failed" || mapStatus === "raster" ? (
          <p className="stage-note" role="status">
            {mapStatus === "failed" ? S.mapError : S.rasterNote}
          </p>
        ) : null}
        {miss ? (
          <p className="stage-toast" role="status" data-testid="no-building">
            {S.noBuilding}
          </p>
        ) : null}
      </div>

      <section className="ledger-wrap" aria-label={ledgerName}>
        <header className="ledger-head">
          <h2>{ledgerName}</h2>
          <p className="mono">{S.everyFigure(feed?.source ?? "fixture")}</p>
        </header>
        {feed ? (
          <PlaceLedger places={places} passed={passed} selectedPid={selectedPid} onPick={pick} />
        ) : null}
      </section>
    </div>
  );
}
