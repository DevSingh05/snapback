// The matte band at the top of a case result: the result line, the headline with its state bar,
// the lines that hold the case up, and the one primary action. The headline is passed in from
// cardStrings.ts; this file never writes one. The bar draws once (the snap) and is still under
// reduced motion.
import type { ReactNode } from "react";

import "../ui/ui.css";
import "./case.css";
import type { CardLine } from "../contracts";
import type { VerdictTone } from "./model";

export interface BandAction {
  label: string;
  href: string;
}

interface VerdictBandProps {
  tone: VerdictTone;
  // The headline, from cardStrings.ts (STATE_WORD).
  headline: string;
  // "THE RESULT · NOV 13, 9:42 PM" and anything else for the mono line above the headline.
  meta?: ReactNode;
  // The lines that do not check out, worst first, as the API wrote them. The first is the one
  // plain sentence under the headline; the rest are counted and shown in the ledger below.
  why?: CardLine[];
  // Card.summary: the sentences code wrote for this verdict. When present they take the place
  // of `why`, under `reasonsTitle`.
  reasons?: string[];
  reasonsTitle?: string | null;
  // A plain paragraph in place of the actions (the verify page).
  summary?: ReactNode;
  // The page's one primary button, and one text link beside it.
  primary?: BandAction | null;
  link?: BandAction | null;
  // h1 on the case page, h2 inline in the Home thread.
  level?: 1 | 2;
  titleId?: string;
  // The proof pair, on the right of the band.
  children?: ReactNode;
}

export function VerdictBand({
  tone,
  headline,
  meta,
  why = [],
  reasons = [],
  reasonsTitle = null,
  summary,
  primary,
  link,
  level = 1,
  titleId = "case-title",
  children,
}: VerdictBandProps) {
  const Title = level === 1 ? "h1" : "h2";
  return (
    <section
      className="case-band ui-band ui-on-matte"
      data-verdict={tone}
      data-testid="case-band"
      aria-labelledby={titleId}
    >
      <div className="case-band-main">
        {meta ? <p className="case-band-meta ui-mono">{meta}</p> : null}
        <div className="case-verdict">
          <Title id={titleId} className="case-headline">
            {headline}
          </Title>
          {reasons.length > 0 ? (
            <div className="case-reasons" data-testid="case-reasons">
              {reasonsTitle ? <p className="ui-mono">{reasonsTitle}</p> : null}
              <ul>
                {reasons.map((sentence) => (
                  <li key={sentence}>{sentence}</li>
                ))}
              </ul>
            </div>
          ) : why[0] ? (
            <p className="case-why" data-testid="case-why">
              <b>{`${why[0].label}. ${why[0].text}`}</b>
              {why.length > 1 ? (
                <span className="case-why-more">
                  {why.length - 1} more below, with the proof for each.
                </span>
              ) : null}
            </p>
          ) : null}
          {summary ? (
            <p className="case-summary" data-testid="summary">
              {summary}
            </p>
          ) : null}
          {primary || link ? (
            <p className="case-band-actions">
              {primary ? (
                <a className="case-primary" href={primary.href} data-testid="case-primary">
                  {primary.label}
                  <span aria-hidden="true">→</span>
                </a>
              ) : null}
              {link ? (
                <a className="case-link" href={link.href}>
                  {link.label}
                </a>
              ) : null}
            </p>
          ) : null}
        </div>
      </div>
      {children ? <div className="case-band-proof">{children}</div> : null}
    </section>
  );
}
