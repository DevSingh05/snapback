import { CHIP_LABEL, chipState, failedLine } from "./read";
import type { Calibration, EvidencePhoto } from "./types";

interface Props {
  photo: EvidencePhoto;
  bars: Record<string, number>;
  /** The Lab's own row for this state. Shown as "k of n (n=N)"; left out when there is none. */
  calibration?: Calibration | null;
}

function Icon({ state }: { state: "strong" | "placed" | "not_placed" }) {
  return (
    <svg className="conf-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      {state === "not_placed" ? (
        <path d="M3 7h10v2H3z" />
      ) : state === "strong" ? (
        <path d="M1 8.5 2.5 7l2.5 2.5L9.5 5 11 6.500 5 12.500zM8 11l1.500 1.500L15 7l-1.500-1.500L9.500 9.500z" />
      ) : (
        <path d="M2.500 8.500 4 7l2.500 2.500L12 4l1.500 1.500-7 7z" />
      )}
    </svg>
  );
}

// Three states only. "Could not place" names the bar that was missed, and it is never "fake":
// a photo that could not be placed says nothing about the listing.
export function ConfidenceChip({ photo, bars, calibration }: Props) {
  const state = chipState(photo, bars);
  const why = failedLine(photo, bars);
  return (
    <div className="conf-wrap">
      <span className={`conf conf-${state}`} data-testid="confidence-chip" data-state={state}>
        <Icon state={state} />
        {CHIP_LABEL[state]}
      </span>
      {state === "not_placed" && why && (
        <span className="conf-why" data-testid="confidence-why">
          {why}
        </span>
      )}
      {calibration && (
        <span className="conf-cal mono" data-testid="confidence-cal">
          on {calibration.on}: {calibration.k} of {calibration.n} (n={calibration.n})
        </span>
      )}
    </div>
  );
}
