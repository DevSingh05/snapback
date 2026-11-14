// The path rail: the four steps of one case, always in view under the bar. Steps before `next`
// read as done (ink), `next` carries the accent (the only accent in the rail), later steps are
// muted. The right end holds the case code and the page's one LIVE or FIXTURE tag.
import type { ReactNode } from "react";

import "./ui.css";

export const PATH_STEPS = ["Check", "Walk it first", "Safer places", "Tour request"] as const;

export type PathStep = 1 | 2 | 3 | 4;

interface PathRailProps {
  // The step to take next. null when all four are done.
  next: PathStep | null;
  // Where each step goes, by step number. A step with no address renders as text.
  hrefs?: Partial<Record<PathStep, string>>;
  // The right end: case code, <Tag />.
  children?: ReactNode;
  className?: string;
}

export function PathRail({ next, hrefs, children, className }: PathRailProps) {
  return (
    <nav className={`ui-rail${className ? ` ${className}` : ""}`} aria-label="Your path">
      <ol>
        {PATH_STEPS.map((name, i) => {
          const step = (i + 1) as PathStep;
          const status = next === null || step < next ? "done" : step === next ? "next" : "later";
          const href = hrefs?.[step];
          const label = (
            <>
              <span className="ui-mono">{`0${step}`}</span>
              <b>{name}</b>
              {status !== "later" && (
                <span className="sr-only">{status === "done" ? " (done)" : " (next step)"}</span>
              )}
            </>
          );
          return (
            <li key={name} className={`ui-rail-${status}`} data-status={status}>
              {href ? (
                <a href={href} aria-current={status === "next" ? "step" : undefined}>
                  {label}
                </a>
              ) : (
                <span aria-current={status === "next" ? "step" : undefined}>{label}</span>
              )}
            </li>
          );
        })}
      </ol>
      {children && <div className="ui-rail-end ui-mono">{children}</div>}
    </nav>
  );
}
