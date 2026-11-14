import { PICKED_BY, optionPlain, resultPlain, type PickedBy } from "./match";
import type { PlaceStep } from "./types";

interface Props {
  /** Every option on the menu. Empty when the step carried none: the pick is then shown alone. */
  options: string[];
  pick: string | null;
  by: PickedBy;
  why?: string;
  /** What the pick led to, read from the evidence file. Left out when it is not on file. */
  result?: PlaceStep["result"] | null;
}

// One choice, in plain words: who picked, the options there were as chips with the picked one
// lit, why in one line, and what came of it. The stamp is honest about the model and the rules.
export function PickCard({ options, pick, by, why, result }: Props) {
  const menu = options.length > 0 ? options : pick ? [pick] : [];
  return (
    <div className="pc" data-testid="pick-card" data-by={by}>
      <p className="pc-head">
        <span className="pc-stamp" data-testid="rail-stamp" data-by={by}>
          {PICKED_BY[by]}
        </span>
        {menu.length > 1 && <span className="pc-from">from {menu.length} options</span>}
      </p>
      {menu.length > 0 && (
        <ul className="pc-opts" aria-label="The options it had">
          {menu.map((o) => (
            <li
              key={o}
              className="pc-opt"
              data-testid="pick-option"
              data-picked={o === pick ? "true" : undefined}
            >
              {o === pick && <span className="pc-tick" aria-hidden="true" />}
              {optionPlain(o)}
              {o === pick && <span className="sr-only"> (picked)</span>}
            </li>
          ))}
        </ul>
      )}
      {why && (
        <p className="pc-row">
          <span className="pc-k">Why</span>
          <span className="pc-v">{why}</span>
        </p>
      )}
      {result && (
        <p className="pc-row pc-out" data-testid="pick-outcome" data-result={result}>
          <span className="pc-k">Outcome</span>
          <span className="pc-v">{resultPlain(result)}</span>
        </p>
      )}
    </div>
  );
}

// The searches spent on one photo, in order: what was tried, who picked it, what came of it.
export function SearchSteps({ searches }: { searches: PlaceStep[] }) {
  if (searches.length === 0) return null;
  return (
    <div className="ss" data-testid="search-steps">
      <h4 className="ss-title">How the agent searched</h4>
      <ol className="ss-list">
        {searches.map((s, i) => (
          <li key={i} className="ss-step" data-by={s.chosen_by} data-result={s.result}>
            <span className="ss-n mono" aria-hidden="true">
              {i + 1}
            </span>
            <span className="ss-what">{optionPlain(s.option)}</span>
            <span className="pc-stamp" data-by={s.chosen_by}>
              {PICKED_BY[s.chosen_by]}
            </span>
            <span className="ss-out">
              {resultPlain(s.result)}
              {typeof s.seconds === "number" && (
                <span className="ss-secs mono"> {Number(s.seconds.toFixed(2))} s</span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
