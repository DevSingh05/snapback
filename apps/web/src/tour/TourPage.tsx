import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { SourceChip } from "../components/SourceChip";
import { EvidenceDrawer, RENDER_NOTE } from "../evidence/EvidenceDrawer";
import type { TourPlan, TourStop } from "../contracts";
import { PhotoLanding } from "../twin/PhotoLanding";
import { connectShowcase, embedUrl, watchSweeps, type ShowcaseSdk } from "../twin/showcase";
import { useLiveAerial, canGoLive } from "../twin/useLiveAerial";
import { usePrefersReducedMotion } from "../twin/useReducedMotion";
import { AgentRail } from "../walk/AgentRail";
import { ListingPhotos } from "../walk/ListingPhotos";
import { MismatchAerials } from "../walk/MismatchAerials";
import { RealStill, StageViews } from "../walk/StageViews";
import { StageCaption, StopStage } from "../walk/StopStage";
import { useNarrow } from "../walk/useNarrow";
import { useWalkLive } from "../walk/useWalkLive";
import { photoAt, walkLook } from "../walk/walkLook";
import { fetchTour, type TourResult, type TourTarget } from "./api";
import { RoomStop, landingOfStop } from "./RoomStop";
import { useAdPhoto } from "./useAdPhoto";
import { stopMove } from "./walkMove";
import "./tour.css";

export const AUTOPLAY_MS = 6000;
const LANDED_OPACITY = 0.6;

// Synthetic stand-in for an ad photo (team-made, not sponsor imagery). An image cannot read page
// CSS variables, so the design tokens are resolved here and written into the picture.
function token(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function placeholderPhoto(): string {
  const bg = token("--teal-soft", "white");
  const ink = token("--teal", "gray");
  return (
    "data:image/svg+xml;utf8," +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="${bg}"/><text x="320" y="205" text-anchor="middle" font-family="sans-serif" font-size="28" fill="${ink}">Listing photo (fixture)</text></svg>`,
    )
  );
}

interface ViewProps {
  plan: TourPlan;
  sdkKey?: string;
  modelId?: string;
  caseId?: string | null;
  /** Where the agent rail mounts (the walk's real trace); nothing is shown until it exists. */
  rail?: ReactNode;
  /** Said above the tour when the case's own photos could not be loaded. */
  notice?: string | null;
}

export function TourView({ plan: given, sdkKey, modelId, caseId, rail, notice }: ViewProps) {
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

  // The loaded model must be this home's scan. When the plan has sweep stops and the model holds
  // none of them, the 3D view is some other home: show the placeholder and say so. Never walk
  // another home's sweeps in its place.
  const plan = given;
  const wrongModel =
    Boolean(sdk) &&
    sweeps.length > 0 &&
    given.stops.some((s) => s.sweep_id) &&
    !given.stops.some((s) => s.sweep_id && sweeps.includes(s.sweep_id));

  const last = plan.stops.length - 1;
  const stop = plan.stops[Math.min(index, last)]!;
  const aerial = useLiveAerial(
    caseId ?? undefined,
    Boolean(caseId) && canGoLive(caseId ?? undefined),
  );

  // Move the 3D view to the stop (or to where its ad photo was taken). Never a stand-in sweep:
  // a stop not in the model says so instead of flying somewhere else.
  const [showPhoto, setShowPhoto] = useState(true);
  useEffect(() => setShowPhoto(true), [stop.key]);
  useEffect(() => {
    const move = stopMove(stop, reduced);
    if (!sdk || !move || sweeps.length === 0 || wrongModel) return;
    if (!sweeps.includes(move.sweepId)) {
      setStatus("This stop is not in the loaded 3D model");
      return;
    }
    let current = true;
    sdk.Sweep.moveTo(move.sweepId, move.options)
      .then(() => current && setStatus(`At: ${stop.title}`))
      .catch(
        (e: unknown) =>
          current && setStatus(e instanceof Error ? e.message : "Could not move the 3D view"),
      );
    return () => {
      current = false;
    };
  }, [sdk, sweeps, stop, reduced, wrongModel]);

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

  const landing = landingOfStop(stop);
  // The ad's real photo when this browser can read it; else the labelled placeholder.
  const realPhoto = useAdPhoto(caseId, stop.photos[0]?.alias);
  const photoNote = realPhoto
    ? null
    : live
      ? "Placeholder: the ad's own photo could not be loaded here."
      : "Placeholder photo (fixture).";
  const showAerial = stop.kind === "arrive" && aerial.status === "ready" && aerial.claimed.imageUrl;

  // The look layer: evidence, real images, trace events and the two-buildings case.
  const narrow = useNarrow();
  const walkLive = useWalkLive(caseId);
  const look = useMemo(() => walkLook(plan, window.location.search, walkLive), [plan, walkLive]);
  const [drawer, setDrawer] = useState<string | null>(null);
  const placedPhoto = photoAt(stop, look.evidence);
  const photoAlias = placedPhoto?.alias ?? stop.photos[0]?.alias ?? stop.photos[0]?.photo_id;
  const unshown = stop.ad_view === "none_placed";
  const firstAlias = placedPhoto?.alias ?? look.evidence?.photos[0]?.alias ?? null;
  const stills = placedPhoto ? look.images[placedPhoto.alias] : undefined;
  const liveScan = Boolean(live && modelId && sdkKey);
  const inRoom = stop.kind !== "arrive" && stop.kind !== "outro";
  // The real view: the live scan with the ad photo landed, else a real image of this stop.
  const realView = liveScan ? (
    <>
      <iframe
        ref={iframeRef}
        hidden={wrongModel}
        className="tour-frame"
        title="Matterport 3D view"
        src={embedUrl(modelId!, sdkKey!)}
        allow="fullscreen; xr-spatial-tracking"
      />
      {landing && !wrongModel && (
        <PhotoLanding
          state={landing}
          photoSrc={realPhoto ?? placeholderPhoto()}
          opacity={showPhoto ? LANDED_OPACITY : 0}
          phase="landed"
          sdk={sdk ? "ready" : "unavailable"}
          reduced={reduced}
        />
      )}
    </>
  ) : showAerial ? (
    <RealStill src={showAerial} label="Vexcel aerial" alt="Aerial view of the building" />
  ) : inRoom && stills?.scan ? (
    <RealStill
      src={stills.scan}
      label="Scan view: a render made from the scan"
      alt={`The scan view that ad photo ${photoAlias ?? ""} matched`}
    />
  ) : inRoom && (stills?.ad ?? realPhoto) ? (
    <RealStill
      src={(stills?.ad ?? realPhoto)!}
      label="The ad's own photo"
      alt={`Ad photo ${photoAlias ?? ""}`}
    />
  ) : null;
  const twoHomes = look.mismatch && stop.kind === "arrive" && !liveScan;
  return (
    <div
      className="tour-page"
      data-rail={look.events.length > 0 ? "on" : "off"}
      data-two-homes={look.mismatch ? "true" : undefined}
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
      {look.evidence && (
        <p className="tour-render mono" data-testid="tour-render-note">
          {RENDER_NOTE}
        </p>
      )}
      {look.mismatch?.banner && (
        <p className="tour-mismatch" role="note" data-testid="tour-mismatch">
          <span className="tour-mismatch-mark" aria-hidden="true" />
          {look.mismatch.banner}
        </p>
      )}
      {notice && (
        <p className="tour-banner" data-testid="tour-notice" role="alert">
          {notice}
        </p>
      )}
      {plan.mode === "elsewhere" && (
        <p className="tour-mode" data-testid="elsewhere-heading">
          Where the photos were taken: the home in these photos.
        </p>
      )}
      {plan.mode_line && (
        <p className="tour-mode-line" data-testid="mode-line">
          {plan.mode_line}
        </p>
      )}
      {plan.coverage?.line && (
        <p className="tour-coverage" data-testid="coverage-line">
          {plan.coverage.line}
        </p>
      )}
      {plan.coverage && plan.coverage.elsewhere > 0 && (
        <p className="tour-banner" data-testid="elsewhere-banner">
          {plan.coverage.elsewhere === 1
            ? "1 of the ad's photos was taken in a different building. It is not shown in these rooms."
            : `${plan.coverage.elsewhere} of the ad's photos were taken in a different building. They are not shown in these rooms.`}
        </p>
      )}
      <div className="tour-body">
        <section
          className="tour-stage"
          aria-label="3D view"
          data-drawer={drawer ? "open" : undefined}
          data-unshown={unshown ? "true" : undefined}
        >
          {twoHomes && look.mismatch ? (
            <MismatchAerials
              named={{
                src: aerial.status === "ready" ? aerial.claimed.imageUrl : null,
                capturedOn: plan.aerial?.captured_on,
              }}
              pictured={{
                src: aerial.status === "ready" ? aerial.matched?.imageUrl : null,
                capturedOn: plan.aerial?.captured_on,
              }}
              source={plan.source}
              officeLine={look.mismatch.officeLine}
              officeName={look.mismatch.officeName}
            />
          ) : (
            <StageViews
              key={liveScan ? "live" : stop.key}
              reduced={reduced}
              real={realView}
              realHidden={wrongModel}
              drawing={
                <>
                  <StopStage
                    key={stop.key}
                    stop={stop}
                    plan={plan}
                    reduced={reduced}
                    photoAlias={stop.photos.length > 0 ? photoAlias : null}
                    photoShown={showPhoto}
                    unshown={unshown}
                  />
                  {/* With no live scan the drawing carries the landing: the drawn photo on the
                      wall follows the same Show the photo / Show the scan switch. */}
                  {!liveScan && landing && (
                    <div hidden>
                      <PhotoLanding
                        state={landing}
                        photoSrc={realPhoto ?? placeholderPhoto()}
                        opacity={showPhoto ? LANDED_OPACITY : 0}
                        phase="landed"
                        sdk="unavailable"
                        reduced={reduced}
                      />
                    </div>
                  )}
                </>
              }
            />
          )}
          {wrongModel && (
            <p className="tour-wrong-model" data-testid="wrong-model" role="status">
              The 3D view here is not this home&apos;s scan
            </p>
          )}
          <StageCaption
            stop={stop}
            photoAlias={stop.photos.length > 0 ? photoAlias : null}
            unshown={unshown}
          />
          {look.evidence && firstAlias && !drawer && (
            <button
              type="button"
              className="tour-how"
              data-testid="how-we-know"
              onClick={() => setDrawer(firstAlias)}
            >
              How we know
            </button>
          )}
          {look.evidence && drawer && (
            <EvidenceDrawer
              file={look.evidence}
              alias={drawer}
              onClose={() => setDrawer(null)}
              reduced={reduced}
              stacked={narrow}
              images={look.images}
            />
          )}
        </section>
        <aside className="tour-panel" aria-live="polite">
          <p className="mono tour-count">
            Step {Math.min(index, last) + 1} of {plan.stops.length}
          </p>
          <h1 className="tour-title">{stop.title}</h1>
          <RoomStop
            stop={stop}
            plan={plan}
            dwell={Boolean(plan.director?.dwell.includes(stop.key))}
            showingPhoto={showPhoto}
            onToggle={() => setShowPhoto((v) => !v)}
            photoNote={photoNote}
            rail={rail}
          />
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
        {look.events.length > 0 && (
          <AgentRail
            events={look.events}
            source={plan.source}
            evidence={look.evidence}
            reduced={reduced}
            onOpenPhoto={setDrawer}
          />
        )}
      </div>
      <ListingPhotos photos={[]} site="" asOf={plan.as_of} />
      <nav className="tour-cover" aria-label="Tour progress">
        {plan.coverage?.line && (
          <p className="tour-cover-key" aria-hidden="true">
            <span className="tour-key tour-key-placed">an ad photo was placed here</span>
            <span className="tour-key tour-key-none">the ad showed no photo</span>
          </p>
        )}
        <ol className="tour-rail">
          {plan.stops.map((s, i) => (
            <li key={s.key} data-kind={s.kind} data-ad-view={s.ad_view}>
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
  | { status: "ready"; result: TourResult }
  | { status: "error"; message: string };

export function TourPage({ target }: { target: TourTarget }) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  useEffect(() => {
    const ctl = new AbortController();
    setLoad({ status: "loading" });
    fetchTour(target, ctl.signal)
      .then((result) => !ctl.signal.aborted && setLoad({ status: "ready", result }))
      .catch((e: unknown) => {
        if (!ctl.signal.aborted)
          setLoad({ status: "error", message: e instanceof Error ? e.message : String(e) });
      });
    return () => ctl.abort();
  }, [target.propertyId, target.planKey, target.caseId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (load.status === "ready")
    return (
      <TourView
        plan={load.result.plan}
        sdkKey={import.meta.env.VITE_MATTERPORT_SDK_KEY}
        // A case walk loads the scan the walk was built from, and no other. The configured demo
        // model is only for a place tour with no case.
        modelId={
          load.result.fromCase
            ? (load.result.modelId ?? undefined)
            : import.meta.env.VITE_DEMO_MODEL_ID
        }
        caseId={load.result.fromCase ? target.caseId : null}
        notice={load.result.notice}
      />
    );
  return (
    <div className="tour-page notice" role="status">
      <span className="wordmark">SNAPBACK</span>
      <p>{load.status === "loading" ? "Loading the tour…" : load.message}</p>
    </div>
  );
}
