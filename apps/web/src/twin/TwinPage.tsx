import { useEffect, useMemo, useRef, useState } from "react";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import { SourceChip } from "../components/SourceChip";
import type { LocateResult } from "../contracts";
import { PhotoOverlay } from "./PhotoOverlay";
import { poseToSdkCall } from "./pose";
import { connectShowcase, embedUrl, flyToPose, watchSweeps, type ShowcaseSdk } from "./showcase";

// Synthetic stand-in for a listing photo (team-made, not sponsor imagery).
const PLACEHOLDER_PHOTO =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400"><rect width="640" height="400" fill="#dff3ee"/><text x="320" y="205" text-anchor="middle" font-family="sans-serif" font-size="28" fill="#0b7a6c">Listing photo (fixture)</text></svg>`,
  );

const fixtureLocate = hold.locate as unknown as LocateResult;

interface ViewProps {
  caseId: string;
  sdkKey: string | undefined;
  modelId: string | undefined;
  locate?: LocateResult;
}

export function TwinView({ caseId, sdkKey, modelId, locate = fixtureLocate }: ViewProps) {
  const live = Boolean(sdkKey && modelId);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [sdk, setSdk] = useState<ShowcaseSdk | null>(null);
  const [sweeps, setSweeps] = useState<string[]>([]);
  const [status, setStatus] = useState<string>("");
  const [opacity, setOpacity] = useState(0);
  const [activePhoto, setActivePhoto] = useState<string | null>(null);

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
        setStatus(e instanceof Error ? e.message : "Could not connect");
      });
    return () => {
      cancelled = true;
      cancelSweeps?.();
      connected?.disconnect();
    };
  }, [live, sdkKey]);

  const located = useMemo(
    () => Object.entries(locate.poses).map(([id, pose]) => ({ id, call: poseToSdkCall(pose) })),
    [locate],
  );

  async function fly(id: string) {
    const item = located.find((l) => l.id === id);
    if (!item) return;
    setActivePhoto(id);
    setOpacity(0);
    if (!sdk) {
      setStatus("Fixture mode: no 3D view to move");
      setOpacity(0.6);
      return;
    }
    const result = await flyToPose(sdk, item.call, sweeps);
    setStatus(
      result
        ? result.stand
          ? "Flew to a stand-in sweep (fixture pose does not exist in this model)"
          : "Flew to the photo pose"
        : "Model has no sweeps",
    );
    setOpacity(0.6);
  }

  return (
    <div className="twin-page">
      <header className="twin-head">
        <span className="wordmark">SNAPBACK</span>
        <span className="mono">Model</span>
        <SourceChip source={live ? "live" : "fixture"} />
        <span className="mono">Photo poses</span>
        <SourceChip source="fixture" />
        <span className="mono">{caseId}</span>
      </header>
      <div className="twin-body">
        <section className="twin-stage" aria-label="3D view">
          {live && sdkKey && modelId ? (
            <iframe
              ref={iframeRef}
              className="twin-frame"
              title="Matterport 3D view"
              src={embedUrl(modelId, sdkKey)}
              allow="fullscreen; xr-spatial-tracking"
            />
          ) : (
            <div className="twin-placeholder" role="status">
              <p>3D view needs a Matterport key</p>
            </div>
          )}
          <PhotoOverlay
            src={activePhoto ? PLACEHOLDER_PHOTO : null}
            opacity={opacity}
            label={`Listing photo ${activePhoto ?? ""}`}
          />
        </section>
        <aside className="twin-side">
          <div className="twin-photos">
            {located.map(({ id }) => (
              <button key={id} type="button" onClick={() => void fly(id)}>
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
            <p role="status" className="twin-status">
              {status}
            </p>
          </div>
          <div data-testid="trace-slot" className="twin-trace" />
        </aside>
      </div>
    </div>
  );
}

export function TwinPage({ caseId }: { caseId: string }) {
  return (
    <TwinView
      caseId={caseId}
      sdkKey={import.meta.env.VITE_MATTERPORT_SDK_KEY}
      modelId={import.meta.env.VITE_DEMO_MODEL_ID}
    />
  );
}
