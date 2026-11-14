import { useMemo, type CSSProperties } from "react";

import { landingLine, landingNote, viewCone, type LandingState } from "./landing";

export type LandingPhase = "idle" | "flying" | "landed";
export type SdkStatus = "ready" | "connecting" | "unavailable";

/** Where the listing card starts, relative to the stage, so the photo can fly from it. */
export interface FlyFrom {
  x: number;
  y: number;
  scale: number;
}

interface Props {
  state: LandingState;
  photoSrc: string | null;
  opacity: number; // 0 to 1, driven by the page
  phase: LandingPhase;
  sdk: SdkStatus;
  reduced: boolean;
  from?: FlyFrom;
}

const VIEW = 240;
const CENTER = VIEW / 2;
const CONE_RADIUS = 56;
const PX_PER_M = 20;
const clamp = (n: number, lim: number) => Math.max(-lim, Math.min(lim, n));

// Photo layer, camera marker, view cone and the one-line caption laid over the twin. Everything
// that moves does so with a CSS transform or transition on elements that stay mounted.
export function PhotoLanding({ state, photoSrc, opacity, phase, sdk, reduced, from }: Props) {
  const fov = state.kind === "match" ? state.fovDeg : null;
  const coneD = useMemo(() => viewCone(fov, CONE_RADIUS), [fov]);
  const flying = phase === "flying" && !reduced;
  const style = from
    ? ({
        "--from-x": `${from.x}px`,
        "--from-y": `${from.y}px`,
        "--from-s": from.scale,
      } as CSSProperties)
    : undefined;

  return (
    <div
      className="landing"
      data-testid="photo-landing"
      data-state={state.kind}
      data-phase={phase}
      data-sdk={sdk}
      data-motion={reduced ? "reduced" : "full"}
      style={style}
    >
      {state.kind === "match" && (
        <>
          {sdk === "unavailable" && (
            <svg className="landing-plan" viewBox={`0 0 ${VIEW} ${VIEW}`} data-testid="static-plan">
              <title>Static plan of where the photo was taken</title>
              <rect x="20" y="20" width="200" height="200" className="plan-floor" />
            </svg>
          )}
          <svg
            className={sdk === "unavailable" ? "landing-map landing-map-plan" : "landing-map"}
            viewBox={`0 0 ${VIEW} ${VIEW}`}
            aria-hidden="true"
          >
            <g
              transform={`translate(${CENTER + clamp(state.position[0] * PX_PER_M, 60)} ${
                CENTER + clamp(state.position[2] * PX_PER_M, 60)
              })`}
            >
              <g
                data-testid="view-cone"
                className="view-cone"
                style={{ transform: `rotate(${-state.yaw}deg)` }}
              >
                <path data-testid="view-cone-path" d={coneD} />
              </g>
              <circle data-testid="camera-marker" className="camera-marker" r="5" />
            </g>
          </svg>
          {photoSrc && (
            <img
              className="landing-photo"
              data-testid="photo-overlay"
              data-flying={flying ? "true" : undefined}
              src={photoSrc}
              alt={`Listing photo ${state.photoId}`}
              style={{ opacity }}
            />
          )}
        </>
      )}
      {state.kind === "match" && sdk === "unavailable" && (
        <span className="landing-schematic">Schematic</span>
      )}
      {landingNote(state) && <p className="landing-note">{landingNote(state)}</p>}
      <p
        className={`landing-line landing-${state.kind}`}
        role="status"
        aria-busy={state.kind === "loading"}
      >
        {landingLine(state)}
      </p>
    </div>
  );
}
