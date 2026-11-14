import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import { SourceChip } from "../components/SourceChip";
import { Wordmark } from "../components/HouseGlyph";
import type { LocateResult } from "../contracts";
import { TracePanel } from "../trace";
import { AerialProof, type AerialSide } from "./AerialProof";
import { PhotoLanding, type FlyFrom, type LandingPhase } from "./PhotoLanding";
import { TraceStrip } from "./TraceStrip";
import {
  FIXTURE_ROOM_LABELS,
  chooseLocate,
  hasDifferentHome,
  landingFromLocate,
  type LandingState,
} from "./landing";
import { poseToSdkCall } from "./pose";
import { COPIED_LOCATE, FIXTURE_CLAIMED, FIXTURE_MATCHED } from "./proofFixtures";
import { connectShowcase, embedUrl, flyToPose, watchSweeps, type ShowcaseSdk } from "./showcase";
import { usePrefersReducedMotion } from "./useReducedMotion";

// Synthetic stand-in for a listing photo (team-made, not sponsor imagery).
const PLACEHOLDER_PHOTO =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#d3eedc"/><text x="320" y="205" text-anchor="middle" font-family="sans-serif" font-size="28" fill="#0e5630">Listing photo (fixture)</text></svg>`,
  );

const NO_LABELS: Record<string, string> = {};
const FLIGHT_MS = 900;
const LANDED_OPACITY = 0.6;

const fixtureLocate = hold.locate as unknown as LocateResult;

interface ViewProps {
  caseId: string;
  sdkKey: string | undefined;
  modelId: string | undefined;
  /** A live LocateResult. Used only when liveLocate is on; otherwise the fixture pose runs. */
  locate?: LocateResult;
  liveLocate?: boolean;
  roomLabels?: Record<string, string>;
  /** The building the photo was matched to, and the building the listing claims. */
  matchedAerial?: AerialSide;
  claimedAerial?: AerialSide;
  /** Fixture scenario: "copied" runs a fixture photo that was taken in a different building. */
  demo?: "copied";
}

function TwinViewInner({
  caseId,
  sdkKey,
  modelId,
  locate: liveResult,
  liveLocate = false,
  roomLabels: roomLabelsProp,
  matchedAerial = FIXTURE_MATCHED,
  claimedAerial = FIXTURE_CLAIMED,
  demo,
}: ViewProps) {
  const fixtureBase = demo === "copied" ? COPIED_LOCATE : fixtureLocate;
  const locate = chooseLocate(liveLocate, liveResult, fixtureBase);
  // A photo placed in a different building than the claimed one: show both buildings.
  const mismatch = hasDifferentHome(locate);
  const poseIsLive = locate !== fixtureBase;
  // Fixture room names belong to the fixture pose only; a live result without labels shows none.
  const roomLabels = roomLabelsProp ?? (poseIsLive ? NO_LABELS : FIXTURE_ROOM_LABELS);
  const live = Boolean(sdkKey && modelId);
  const reduced = usePrefersReducedMotion();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const stageRef = useRef<HTMLElement>(null);
  const cardRef = useRef<HTMLElement>(null);
  const alive = useRef(true);
  const run = useRef(0);
  const autoRan = useRef(false);
  const [sdk, setSdk] = useState<ShowcaseSdk | null>(null);
  const [sdkFailed, setSdkFailed] = useState(false);
  const [sweeps, setSweeps] = useState<string[]>([]);
  const [status, setStatus] = useState<string>("");
  const [opacity, setOpacity] = useState(0);
  const [phase, setPhase] = useState<LandingPhase>("idle");
  const [photoId, setPhotoId] = useState<string>(locate.photos[0]?.photo_id ?? "");
  const [from, setFrom] = useState<FlyFrom | undefined>();

  useEffect(() => {
    if (!live || !iframeRef.current || !sdkKey) return;
    let cancelled = false;
    let cancelSweeps: (() => void) | null = null;
    let connected: ShowcaseSdk | null = null;
    connectShowcase(iframeRef.current, sdkKey)
      .then((s) => {
        if (cancelled) {
          s.disconnect();
          return;
        }
        connected = s;
        setSdk(s);
        setStatus("Model ready");
        cancelSweeps = watchSweeps(s, (ids) => {
          if (!cancelled) setSweeps(ids);
        });
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

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const sdkStatus = !live || sdkFailed ? "unavailable" : sdk ? "ready" : "connecting";

  const state: LandingState = useMemo(
    () =>
      sdkStatus === "connecting"
        ? { kind: "loading" }
        : landingFromLocate(locate, photoId, roomLabels),
    [sdkStatus, locate, photoId, roomLabels],
  );

  const land = useCallback(
    async (id: string) => {
      const mine = ++run.current;
      setPhotoId(id);
      setOpacity(0);
      const target = landingFromLocate(locate, id, roomLabels);
      if (target.kind !== "match") {
        setPhase("landed");
        setStatus("");
        return;
      }
      // Measure once; the flight itself is a CSS animation, nothing runs per frame.
      const stage = stageRef.current?.getBoundingClientRect();
      const card = cardRef.current?.getBoundingClientRect();
      if (stage && card && stage.width > 0) {
        setFrom({
          x: card.left + card.width / 2 - (stage.left + stage.width / 2),
          y: card.top + card.height / 2 - (stage.top + stage.height / 2),
          scale: Math.max(0.1, card.width / stage.width),
        });
      }
      setPhase("flying");
      const flight = new Promise<void>((resolve) => {
        setTimeout(resolve, reduced ? 0 : FLIGHT_MS);
      });
      let moved: Promise<unknown> = Promise.resolve();
      if (sdk) {
        const call = poseToSdkCall({
          sweep_id: target.sweepId,
          position: target.position,
          rotation_quat: locate.poses[id]!.rotation_quat,
          fov_deg: target.fovDeg,
        });
        if (reduced)
          call.options = { ...call.options, transition: "transition.instant", transitionTime: 0 };
        moved = flyToPose(sdk, call, sweeps).then((result) => {
          setStatus(
            result
              ? result.stand
                ? "Flew to a stand-in sweep (fixture pose does not exist in this model)"
                : "Flew to the photo pose"
              : "Model has no sweeps",
          );
        });
      } else {
        setStatus(
          sdkStatus === "unavailable" ? "3D view unavailable: showing the static plan" : "",
        );
      }
      try {
        await Promise.all([flight, moved]);
      } catch (e) {
        // The 3D move failed: land on the static view instead of staying at opacity 0.
        setStatus(e instanceof Error ? e.message : "Could not move the 3D view");
        setSdkFailed(true);
      }
      if (!alive.current || run.current !== mine) return;
      setPhase("landed");
      setOpacity(LANDED_OPACITY);
    },
    [locate, roomLabels, reduced, sdk, sdkStatus, sweeps],
  );

  // Run the landing once on the first pose we can use: at once without a 3D view, or when the
  // model's sweeps are known with one.
  const ready = sdkStatus === "unavailable" || (sdkStatus === "ready" && sweeps.length > 0);
  useEffect(() => {
    if (!ready || autoRan.current || !photoId) return;
    autoRan.current = true;
    void land(photoId);
  }, [ready, photoId, land]);

  return (
    <div className="twin-page">
      <header className="twin-head">
        <Wordmark />
        <span className="mono">Model</span>
        {live && sdkFailed ? (
          <span className="chip chip-fixture" data-testid="source-chip">
            <span className="chip-dot" aria-hidden="true" />
            UNAVAILABLE
            <span className="sr-only">. The 3D view could not load; a schematic is shown</span>
          </span>
        ) : (
          <SourceChip source={live ? "live" : "fixture"} />
        )}
        <span className="mono">Photo poses</span>
        <SourceChip source={poseIsLive ? "live" : "fixture"} />
        <span className="mono">{caseId}</span>
      </header>
      <div className="twin-body">
        <section className="twin-stage" aria-label="3D view" ref={stageRef}>
          {live && sdkKey && modelId ? (
            <iframe
              ref={iframeRef}
              className="twin-frame"
              title="Matterport 3D view"
              src={embedUrl(modelId, sdkKey)}
              allow="fullscreen; xr-spatial-tracking"
            />
          ) : (
            <p className="twin-placeholder">3D view needs a Matterport key</p>
          )}
          <PhotoLanding
            state={state}
            photoSrc={PLACEHOLDER_PHOTO}
            opacity={opacity}
            phase={phase}
            sdk={sdkStatus}
            reduced={reduced}
            from={from}
          />
        </section>
        <aside className="twin-side">
          <figure className="listing-card" ref={cardRef}>
            <img src={PLACEHOLDER_PHOTO} alt={`Listing photo ${photoId}`} />
            <figcaption className="mono">Listing photo {photoId}</figcaption>
          </figure>
          <div className="twin-photos">
            {locate.photos.map(({ photo_id: id }) => (
              <button key={id} type="button" onClick={() => void land(id)}>
                Fly to photo {id}
              </button>
            ))}
            <label>
              Photo fade
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
              />
            </label>
            <p className="twin-status">{status}</p>
          </div>
          <AerialProof
            caseId={demo ? undefined : caseId}
            matched={matchedAerial}
            claimed={claimedAerial}
            mismatch={mismatch}
          />
        </aside>
      </div>
      <TraceStrip>
        <TracePanel caseId={caseId} />
      </TraceStrip>
    </div>
  );
}

// A new LocateResult remounts the view, so the photo, phase and first-landing guard start fresh.
const locateIds = new WeakMap<object, number>();
let nextLocateId = 0;
function locateKey(l: LocateResult): number {
  let id = locateIds.get(l);
  if (id === undefined) locateIds.set(l, (id = nextLocateId++));
  return id;
}

export function TwinView(props: ViewProps) {
  const base = props.demo === "copied" ? COPIED_LOCATE : fixtureLocate;
  const locate = chooseLocate(props.liveLocate ?? false, props.locate, base);
  return <TwinViewInner key={locateKey(locate)} {...props} />;
}

/** /case/:id/twin?demo=copied shows the two-building mismatch from fixtures. */
export function demoFromSearch(search: string): "copied" | undefined {
  return new URLSearchParams(search).get("demo") === "copied" ? "copied" : undefined;
}

export function TwinPage({ caseId }: { caseId: string }) {
  return (
    <TwinView
      caseId={caseId}
      sdkKey={import.meta.env.VITE_MATTERPORT_SDK_KEY}
      modelId={import.meta.env.VITE_DEMO_MODEL_ID}
      liveLocate={import.meta.env.VITE_LIVE_LOCATE === "1"}
      demo={demoFromSearch(window.location.search)}
    />
  );
}
