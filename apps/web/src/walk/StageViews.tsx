import { useState, type ReactNode } from "react";

import { ViewToggle, type ViewChoice } from "../evidence/ViewToggle";
import "./walk.css";

interface Props {
  /** The real view: the live scan, or a real image. Null when none exists for this stop. */
  real: ReactNode | null;
  /** The team's 3D drawing. Always there, always labelled as a drawing. */
  drawing: ReactNode;
  reduced: boolean;
  /** The real view is there but must not be shown (the loaded scan is not this home's). It
   *  stays mounted and hidden, and the drawing fills the stage. */
  realHidden?: boolean;
}

export const REAL_LABEL = "Real view";
export const DRAWING_LABEL = "3D drawing";

// Two views of one stop, like a video call: one fills the stage and the other sits as a small
// window in the corner. Tap the window, or use the 3D | Real switch, to swap them. Real fills
// the stage whenever a real view exists. Both stay mounted, so the live scan keeps its place.
export function StageViews({ real, drawing, reduced, realHidden = false }: Props) {
  const hasReal = real !== null && !realHidden;
  const [choice, setChoice] = useState<ViewChoice>("real");
  const main: ViewChoice = hasReal ? choice : "drawing";
  const swap = () => setChoice(main === "real" ? "drawing" : "real");

  const pane = (which: ViewChoice, content: ReactNode) => {
    const role = which === main ? "main" : "corner";
    const label = which === "real" ? REAL_LABEL : DRAWING_LABEL;
    return (
      <div className="sv-pane" data-view={which} data-role={role} data-testid={`view-${which}`}>
        <div className="sv-content" inert={role === "corner" ? true : undefined}>
          {content}
        </div>
        {role === "corner" && (
          <button
            type="button"
            className="sv-swap"
            data-testid="view-swap"
            onClick={swap}
            aria-label={`Show the ${label.toLowerCase()} large`}
          >
            <span className="sv-label">{label}</span>
          </button>
        )}
      </div>
    );
  };

  return (
    <div
      className="sv"
      data-testid="stage-views"
      data-main={main}
      data-motion={reduced ? "reduced" : "full"}
    >
      {hasReal && pane("real", real)}
      {real !== null && realHidden && <div hidden>{real}</div>}
      {pane("drawing", drawing)}
      <div className="sv-switch">
        <ViewToggle
          value={main}
          onChange={setChoice}
          hasReal={hasReal}
          drawingLabel="3D"
          label="Which view fills the stage"
        />
      </div>
    </div>
  );
}

interface StillProps {
  src: string;
  label: string;
  alt: string;
}

/** A real image as the real view, when there is no live scan: the scan render or the ad photo. */
export function RealStill({ src, label, alt }: StillProps) {
  return (
    <figure className="sv-still" data-testid="real-still">
      <img className="sv-still-img" src={src} alt={alt} />
      <figcaption className="sv-still-label mono">{label}</figcaption>
    </figure>
  );
}
