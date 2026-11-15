// "What to do now": the three steps after a result, as columns on one rule. Every action here is
// quiet; the page's one primary button lives in the verdict band.
import "../ui/ui.css";
import "./case.css";

export interface NextStep {
  // "02", "03", "04": the step's number on the path rail.
  n: string;
  title: string;
  text: string;
  action: { label: string; href: string };
  // A second action under the first. `external` opens in a new tab.
  more?: { label: string; href: string; external?: boolean };
}

// The hand-off when a case does not pass: CoStar's own rental site. The API gives no listing
// address for it, so this is the site's Houston search page, and the label says it is a search.
export const APARTMENTS_SEARCH = {
  label: "Search listings on Apartments.com",
  href: "https://www.apartments.com/houston-tx/",
  external: true,
} as const;

/** The usual three steps for a case. `walk` is false when no photo was placed in a home;
 *  `passed` is false when the case did not pass, which adds the Apartments.com hand-off. */
export function caseSteps(
  caseId: string,
  walk: boolean,
  saferHref = "/finder",
  passed = false,
): NextStep[] {
  const id = encodeURIComponent(caseId);
  return [
    {
      n: "02",
      title: "Walk it first",
      text: walk
        ? "See the real rooms, with the ad's photos placed where they were taken."
        : "See the rooms on record for this home, if it has a 3D scan.",
      action: { label: "Walk it first", href: `/case/${id}/twin` },
    },
    {
      n: "03",
      title: "Find safer places",
      text: passed
        ? "Researched homes like this one, picked by our rules."
        : "Researched homes like this one, picked by our rules. Or start again on Apartments.com, CoStar's rental site.",
      action: { label: "Find me safer places like this", href: saferHref },
      more: passed ? undefined : APARTMENTS_SEARCH,
    },
    {
      n: "04",
      title: "Ask for a tour",
      text: "For a place that passes. We draft it; you send it.",
      action: { label: "Draft a tour request", href: `/case/${id}/prep` },
    },
  ];
}

interface NextStepsProps {
  steps: NextStep[];
  // Which step is next (its `n`); it carries the word NEXT.
  next?: string | null;
  titleId?: string;
}

export function NextSteps({ steps, next = "02", titleId = "case-next-title" }: NextStepsProps) {
  return (
    <section className="case-next" aria-labelledby={titleId}>
      <h2 id={titleId}>What to do now</h2>
      <ol className="case-next-steps">
        {steps.map((step) => (
          <li key={step.n} data-next={step.n === next ? "true" : undefined}>
            <p className="ui-mono">{step.n === next ? `${step.n} · NEXT` : step.n}</p>
            <h3>{step.title}</h3>
            <p className="case-next-text">{step.text}</p>
            <a className="ui-btn-quiet" href={step.action.href}>
              {step.action.label}
            </a>
            {step.more ? (
              <a
                className="ui-btn-quiet case-next-more"
                href={step.more.href}
                data-testid="case-handoff"
                {...(step.more.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              >
                {step.more.label}
                {step.more.external ? <span aria-hidden="true"> ↗</span> : null}
              </a>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}
