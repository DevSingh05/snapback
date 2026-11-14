export type ViewChoice = "real" | "drawing";

interface Props {
  value: ViewChoice;
  onChange: (v: ViewChoice) => void;
  /** False when no real image exists: Real is then off and says why. */
  hasReal: boolean;
  drawingLabel?: string;
  label: string;
}

// The visible switch between what the place really looks like and the team's drawing of it.
export function ViewToggle({ value, onChange, hasReal, drawingLabel = "Drawing", label }: Props) {
  return (
    <div className="vt" role="group" aria-label={label} data-testid="view-toggle">
      <button
        type="button"
        className="vt-opt"
        aria-pressed={value === "drawing"}
        onClick={() => onChange("drawing")}
      >
        {drawingLabel}
      </button>
      <button
        type="button"
        className="vt-opt"
        aria-pressed={value === "real"}
        disabled={!hasReal}
        title={hasReal ? undefined : "No real image for this yet"}
        onClick={() => onChange("real")}
      >
        Real
      </button>
    </div>
  );
}
