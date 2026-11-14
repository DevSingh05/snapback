import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import type { TourPlan, TourStop } from "../contracts";
import { poseToSdkCall } from "../twin/pose";
import { connectShowcase, embedUrl, watchSweeps, type ShowcaseSdk } from "../twin/showcase";
import { useLiveAerial, canGoLive } from "../twin/useLiveAerial";
import { usePrefersReducedMotion } from "../twin/useReducedMotion";
import { fetchTour, type TourTarget } from "./api";
import "./tour.css";

export const AUTOPLAY_MS = 6000;
const MAX_LOCAL_STOPS = 8;

/** Stops from the 3D view's own sweeps, evenly spaced, when the plan's sweeps are not in the
 *  loaded model. Never labelled with room names, and the plan's note says so. */
export function evenStops(ids: string[]): TourStop[] {
  if (ids.length === 0) return [];
  const rest = ids.slice(1);
  const n = Math.min(MAX_LOCAL_STOPS, rest.length);
  const picks =
    n > 1
      ? Array.from({ length: n }, (_, i) => rest[Math.round((i * (rest.length - 1)) / (n - 1))]!)
      : rest.slice(0, n);
  const mk = (kind: TourStop["kind"], key: string, title: string, id: string): TourStop => ({
    kind,
    key,
    title,
    sweep_id: id,
    sweep_count: 1,
    sweep_ids: [id],
    photos: [],
    facts: [],
  });
  return [
    { ...mk("door", "door", "Front door", ids[0]!), note: "Start of the 3D scan" },
    ...picks.map((id, i) => mk("stop", `stop-${i + 1}`, `Stop ${i + 1}`, id)),
  ];
}

function Placeholder({ stop, plan }: { stop: TourStop; plan: TourPlan }) {
  return (
    <div
      className="tour-placeholder"
      data-testid="tour-placeholder"
      role="img"
      aria-label={stop.title}
    >
      <span className="mono">Placeholder visual (fixture)</span>
      <strong>{stop.title}</strong>
      {stop.kind === "arrive" && plan.aerial?.captured_on && (
        <span>Aerial photo captured {plan.aerial.captured_on}</span>
      )}
    </div>
  );
}

interface ViewProps {
  plan: TourPlan;
  sdkKey?: string;
  modelId?: string;
  caseId?: string | null;
}

export function TourView({ plan: given, sdkKey, modelId, caseId }: ViewProps) {
  const live = Boolean(sdkKey && modelId);
  const reduced = usePrefersReducedMotion();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [sdk, setSdk] = useState<ShowcaseSdk | null>(null);
  const [sdkFailed, setSdkFailed] = useState(false);
  const [sweeps, setSweeps] = useState<string[]>([]);
  const [index, setIndex] = useState(0);
  const [autoplay, setAutoplay] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (!live || !iframeRef.current || !sdkKey) return;
    let cancelled = false;
    let cancelSweeps: (() => void) | null = null;
    let connected: ShowcaseSdk | null = null;
    connectShowcase(iframeRef.current, sdkKey)
      .then((s) => {
        if (cancelled) return s.disconnect();
        connected = s;
        setSdk(s);
        cancelSweeps = watchSweeps(s, (ids) => !cancelled && setSweeps(ids));
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setSdkFailed(true);
        setStatus(e instanceof Error ? e.message : "Could not connect");
      });
    return () => {
      cancelled = true;
      cancelSweeps?.();
      connected?.disconnect();
    };
  }, [live, sdkKey]);

  // When the loaded model holds none of the plan's sweeps, walk the model's own sweeps instead.
  const plan = useMemo<TourPlan>(() => {
    const walk = given.stops.filter((s) => s.sweep_id);
    if (!sdk || sweeps.length === 0 || walk.some((s) => sweeps.includes(s.sweep_id!))) return given;
    const mid = evenStops(sweeps);
    return {
      ...given,
      rooms_labelled: false,
      rooms_note:
        "Rooms are not labelled for the loaded 3D model, so the stops are numbered along its path.",
      stops: [
        ...given.stops.filter((s) => s.kind === "arrive"),
        ...mid,
        ...given.stops.filter((s) => s.kind === "outro"),
      ],
    };
  }, [given, sdk, sweeps]);

  const last = plan.stops.length - 1;
  const stop = plan.stops[Math.min(index, last)]!;
  const aerial = useLiveAerial(
    caseId ?? undefined,
    Boolean(caseId) && canGoLive(caseId ?? undefined),
  );

  // Move the 3D view to the stop's own sweep. Never a stand-in sweep: a stop not in the model
  // says so instead of flying somewhere else.
  useEffect(() => {
    if (!sdk || !stop.sweep_id || sweeps.length === 0) return;
    if (!sweeps.includes(stop.sweep_id)) {
      setStatus("This stop is not in the loaded 3D model");
      return;
    }
    const call = poseToSdkCall({
      sweep_id: stop.sweep_id,
      position: stop.position ?? [0, 0, 0],
      rotation_quat: stop.rotation_quat ?? [0, 0, 0, 1],
    });
    if (reduced)
      call.options = { ...call.options, transition: "transition.instant", transitionTime: 0 };
    let current = true;
    sdk.Sweep.moveTo(call.sweepId, call.options)
      .then(() => current && setStatus(`At: ${stop.title}`))
      .catch(
        (e: unknown) =>
          current && setStatus(e instanceof Error ? e.message : "Could not move the 3D view"),
      );
    return () => {
      current = false;
    };
  }, [sdk, sweeps, stop, reduced]);

  const next = useCallback(() => setIndex((i) => Math.min(i + 1, last)), [last]);
  const back = useCallback(() => setIndex((i) => Math.max(i - 1, 0)), []);

  // Autoplay: one step every AUTOPLAY_MS; any interaction pauses it; it stops at the end.
  useEffect(() => {
    if (!autoplay) return;
    if (index >= last) {
      setAutoplay(false);
      return;
    }
    const t = setTimeout(next, AUTOPLAY_MS);
    return () => clearTimeout(t);
  }, [autoplay, index, last, next]);
  const pause = () => setAutoplay(false);

  const showAerial = stop.kind === "arrive" && aerial.status === "ready" && aerial.claimed.imageUrl;
  return (
    <div
      className="tour-page"
      onPointerDownCapture={pause}
      onKeyDownCapture={pause}
      onWheelCapture={pause}
    >
      <header className="tour-head">
        <span className="wordmark">SNAPBACK</span>
        <span className="mono">Walk it first</span>
        <SourceChip source={plan.source} />
        <span className="mono">3D view</span>
        {live && !sdkFailed ? <SourceChip source="live" /> : <SourceChip source="fixture" />}
      </header>
      {plan.scan_label && <p className="tour-scan">This tour uses {plan.scan_label}.</p>}
      <div className="tour-body">
        <section className="tour-stage" aria-label="3D view">
          {live && modelId && sdkKey ? (
            <iframe
              ref={iframeRef}
              className="tour-frame"
              title="Matterport 3D view"
              src={embedUrl(modelId, sdkKey)}
              allow="fullscreen; xr-spatial-tracking"
            />
          ) : showAerial ? (
            <img className="tour-aerial" src={showAerial} alt="Aerial view of the building" />
          ) : (
            <Placeholder stop={stop} plan={plan} />
          )}
        </section>
        <aside className="tour-panel" aria-live="polite">
          <p className="mono tour-count">
            Step {Math.min(index, last) + 1} of {plan.stops.length}
          </p>
          <h1 className="tour-title">{stop.title}</h1>
          {stop.note && <p className="tour-note">{stop.note}</p>}
          {stop.kind === "room" && <p className="tour-note">{plan.rooms_note}</p>}
          {stop.kind === "door" && !plan.rooms_labelled && (
            <p className="tour-note">{plan.rooms_note}</p>
          )}
          {stop.facts.length > 0 && (
            <ul className="tour-facts" aria-label="What the record says">
              {stop.facts.map((f) => (
                <li key={f.text}>
                  {f.text} <span className="tour-src">{f.source}</span>
                </li>
              ))}
            </ul>
          )}
          {stop.photos.length > 0 && (
            <p className="tour-photos">
              {stop.photos.length === 1 ? "Your ad photo" : "Your ad photos"}{" "}
              {stop.photos.map((p) => p.photo_id).join(", ")}{" "}
              {stop.photos.length === 1 ? "was" : "were"} placed in this room.
            </p>
          )}
          {stop.tip && (
            <p className="tour-tip">
              <strong>Check this in person:</strong> {stop.tip}
            </p>
          )}
          {stop.kind === "outro" && (
            <p className="tour-outro">
              <a className="pf-action" href={plan.links.tour_prep} data-testid="tour-prep-link">
                Tour prep: what to ask
              </a>{" "}
              <span className="tour-note">{plan.links.tour_draft_hint}</span>
            </p>
          )}
          {!plan.has_scan && <p className="tour-note">No 3D scan is on record for this place.</p>}
          <p className="tour-status" role="status">
            {status}
          </p>
          <div className="tour-controls">
            <button type="button" onClick={back} disabled={index === 0}>
              Back
            </button>
            <button type="button" onClick={next} disabled={index >= last}>
              Next
            </button>
            <button
              type="button"
              aria-pressed={autoplay}
              onClick={(e) => {
                e.stopPropagation();
                setAutoplay((a) => !a);
              }}
              disabled={index >= last}
            >
              Autoplay {autoplay ? "on" : "off"}
            </button>
          </div>
        </aside>
      </div>
      <nav aria-label="Tour progress">
        <ol className="tour-rail">
          {plan.stops.map((s, i) => (
            <li key={s.key}>
              <button
                type="button"
                aria-current={i === Math.min(index, last) ? "step" : undefined}
                onClick={() => setIndex(i)}
              >
                {s.title}
              </button>
            </li>
          ))}
        </ol>
      </nav>
    </div>
  );
}

type Load =
  | { status: "loading" }
  | { status: "ready"; plan: TourPlan }
  | { status: "error"; message: string };

export function TourPage({ target }: { target: TourTarget }) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  useEffect(() => {
    const ctl = new AbortController();
    setLoad({ status: "loading" });
    fetchTour(target, ctl.signal)
      .then((plan) => !ctl.signal.aborted && setLoad({ status: "ready", plan }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted)
          setLoad({ status: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctl.abort();
  }, [target.propertyId, target.planKey, target.caseId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (load.status === "ready")
    return (
      <TourView
        plan={load.plan}
        sdkKey={import.meta.env.VITE_MATTERPORT_SDK_KEY}
        modelId={import.meta.env.VITE_DEMO_MODEL_ID}
        caseId={target.caseId}
      />
    );
  return (
    <div className="tour-page notice" role="status">
      <span className="wordmark">SNAPBACK</span>
      <p>{load.status === "loading" ? "Loading the tour…" : load.message}</p>
    </div>
  );
}
