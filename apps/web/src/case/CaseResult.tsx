// One SNAPBACK report, built from the case pieces, in one order: the verdict and why, the ad
// beside the real listing, what checks out and what doesn't, what to do next, safer homes, and
// last what this check could not do, with every check on the table under it. A section whose
// read did not come back is not there. The case page renders it at full size; the Home thread
// renders the same thing inline (`inline`), where the headline is an h2.
import type { ReactNode } from "react";

import "../ui/ui.css";
import "./case.css";
import { headlineOf, historySteps, shortDate } from "../cardStrings";
import type {
  Card,
  CardLine,
  CardRowKind,
  CaseTimeline,
  CopyAlert,
  ReportPack,
} from "../contracts";
import { Tag } from "../ui";
import { AnnotatedAd } from "./AnnotatedAd";
import { asLang, type Lang } from "../lang";
import { ReportTeam } from "../proofroom/ReportTeam";
import { AnswerPanel } from "./AnswerPanel";
import { Checks } from "./Checks";
import { Ledger } from "./Ledger";
import { LangSwitch } from "./LangSwitch";
import {
  VERDICT_TONE,
  checkedStamp,
  couldNotDo,
  missingFact,
  expiryText,
  flaggedLines,
  photosPlaced,
  type AdMark,
  type PriceFigures,
  type ProofData,
  type RealListing as RealListingData,
  type SaferPlace,
} from "./model";
import { APARTMENTS_SEARCH, NextSteps, caseSteps } from "./NextSteps";
import { PlannerChoice } from "./PlannerChoice";
import { ProofPair } from "./ProofPair";
import { RealListing } from "./RealListing";
import { SaferTiles } from "./SaferTiles";
import { StillChecking } from "./StillChecking";
import { VerdictBand } from "./VerdictBand";
import { WhatNext } from "./WhatNext";

export interface CaseResultProps {
  card: Card;
  // "result" is the renter's own page; "verify" is the page a QR code opens for someone else.
  variant?: "result" | "verify";
  // Inside the Home thread: no rail, an h2 headline, and ids made unique by the case code.
  inline?: boolean;
  proof?: ProofData | null;
  // The renter's pasted ad and the phrases in it to underline, when the caller has them.
  adText?: string | null;
  adMarks?: AdMark[];
  adOrigin?: string | null;
  adSays?: (row: CardRowKind, line: CardLine) => string | null | undefined;
  price?: PriceFigures | null;
  // GET /cases/{id}/real-listing, when the API has it.
  realListing?: RealListingData | null;
  // Places from /alternatives; the ones with a hand-off link become tiles on a failed result.
  saferPlaces?: SaferPlace[];
  // GET /cases/{id}/copy-alert, only when it fires: the draft note for the leasing office.
  copyAlert?: CopyAlert | null;
  // GET /cases/{id}/report: the pack behind "File this report".
  reportPack?: ReportPack | null;
  // GET /cases/{id}/timeline: the "How we got this answer" panel. Left out or empty: no panel.
  timeline?: CaseTimeline | null;
  // Sections whose read answered 202 (the check is still running): each shows "Still checking…".
  checking?: { proof?: boolean; real?: boolean; next?: boolean; safer?: boolean };
  // Where "Find me safer places like this" goes. Left out: the tiles below, else the Finder.
  saferHref?: string;
  // Anything the page adds under the next steps (the safer places, the office check).
  children?: ReactNode;
  // The report's language switch (EN | ES), when the caller can refetch in the other one.
  lang?: Lang;
  onLang?: (lang: Lang) => void;
}

export function CaseResult({
  card,
  variant = "result",
  inline = false,
  proof = null,
  adText = null,
  adMarks,
  adOrigin,
  adSays,
  price,
  realListing = null,
  saferPlaces: safer_places = [],
  copyAlert = null,
  reportPack = null,
  timeline = null,
  saferHref: saferTo,
  checking = {},
  children,
  lang,
  onLang,
}: CaseResultProps) {
  const id = encodeURIComponent(card.case_id);
  const key = inline ? `-${card.case_id}` : "";
  const own = variant === "result";
  const walk = photosPlaced(card);
  const history = historySteps(card.for_sale);
  const passed = card.state === "verified";
  // A result that did not pass: it gets the reasons heading and the places to go to instead.
  const failed = card.state === "hold" || card.state === "dont_pay";
  const tiles = own && failed && safer_places.length > 0;
  // "Safer places" goes to the section on this page when it is there, else to the Finder.
  const saferHref = saferTo ?? (own && failed ? `#safer${key}` : "/finder");
  const beside = Boolean(realListing || adText);
  const couldNot = couldNotDo(card);
  const walkTo = { label: "Walk it first", href: `/case/${id}/twin` };
  // The one primary button. A result that did not pass points at what to do next; one that
  // passed opens the walk when a photo was placed, else the safer places.
  const primary = !passed
    ? { label: failed ? "Who do I call?" : "What to do next", href: `#next${key}` }
    : walk
      ? walkTo
      : { label: "Find me safer places like this", href: saferHref };
  return (
    <article className={`case-page${inline ? " case-inline" : ""}`} data-variant={variant}>
      <p className="case-head ui-mono">
        <span className="case-head-name">SNAPBACK REPORT</span>
        <span>
          CASE <span data-testid="case-id">{card.case_id}</span>
        </span>
        <Tag source={card.source} testId="source-chip" />
        {lang && onLang ? <LangSwitch lang={lang} onChange={onLang} /> : null}
      </p>

      <VerdictBand
        tone={VERDICT_TONE[card.state]}
        headline={headlineOf(card)}
        level={inline ? 2 : 1}
        titleId={`case-title${key}`}
        meta={
          <>
            <span>THE RESULT · {checkedStamp(card.checked_at)}</span>
            <span data-testid="expiry">{expiryText(card.expires_at)}</span>
          </>
        }
        why={flaggedLines(card)}
        reasons={card.summary ?? []}
        settles={own ? missingFact(card) : null}
        reasonsTitle={failed ? "WHY THIS IS NOT A GOOD DEAL" : null}
        summary={
          own ? null : (
            <>
              This is the SNAPBACK report for case {card.case_id}. It covers the place, the person
              and the price, and lists what was not checked: {card.not_checked.join(", ")}.
            </>
          )
        }
        primary={own ? primary : null}
        link={own && !passed && !failed && walk ? walkTo : null}
      >
        {proof ? <ProofPair {...proof} handoff={own && !inline} /> : null}
        {!proof && checking.proof ? <StillChecking testId="checking-proof" /> : null}
      </VerdictBand>
      {own ? <ReportTeam card={card} timeline={timeline} realListing={realListing} /> : null}

      {!realListing && checking.real ? <StillChecking testId="checking-real" /> : null}
      {beside ? (
        <div
          className={`case-beside${realListing && adText ? " case-beside-two" : ""}`}
          data-side={realListing ? "real" : "ad"}
          data-testid="case-beside"
        >
          {realListing ? (
            <RealListing listing={realListing} titleId={`case-real-title${key}`} />
          ) : null}
          {adText ? <AnnotatedAd text={adText} marks={adMarks} origin={adOrigin} /> : null}
        </div>
      ) : null}

      <Checks
        checksOut={card.checks_out}
        doesNot={card.does_not}
        source={card.source}
        titleId={`case-checks-title${key}`}
      />
      {own ? (
        <PlannerChoice
          caseId={card.case_id}
          timeline={timeline}
          lang={lang ?? asLang(card.lang) ?? undefined}
        />
      ) : null}

      {own ? (
        <AnswerPanel card={card} timeline={timeline} realListing={realListing} idSuffix={key} />
      ) : null}

      {own && !passed && checking.next && !copyAlert && !reportPack ? (
        <StillChecking testId="checking-next" />
      ) : null}
      {own && !passed ? (
        <WhatNext
          id={`next${key}`}
          alert={copyAlert}
          pack={reportPack}
          officeHost={realListing?.website_host ?? copyAlert?.website_host ?? null}
          pageUrl={card.verify_url ?? null}
          titleId={`case-next-title${key}`}
        />
      ) : null}
      {own && passed ? (
        <NextSteps
          steps={caseSteps(card.case_id, walk, saferHref, true)}
          titleId={`case-next-title${key}`}
        />
      ) : null}

      {own && failed ? (
        <section
          className="case-safer"
          id={`safer${key}`}
          aria-labelledby={`case-safer-title${key}`}
          data-testid="case-safer"
        >
          <h2 id={`case-safer-title${key}`}>Safer homes on Apartments.com</h2>
          {tiles ? <SaferTiles places={safer_places} /> : null}
          {!tiles && checking.safer ? <StillChecking testId="checking-safer" /> : null}
          <p className="case-safer-more">
            <a
              className="ui-btn-quiet"
              href={APARTMENTS_SEARCH.href}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="case-handoff"
            >
              {APARTMENTS_SEARCH.label} <span aria-hidden="true">↗</span>
            </a>
          </p>
        </section>
      ) : null}

      {children}

      <footer className="case-foot">
        {couldNot.length > 0 ? (
          <section
            className="case-could-not"
            aria-labelledby={`case-could-not-title${key}`}
            data-testid="case-could-not"
          >
            <header className="case-sheet-head">
              <h2 id={`case-could-not-title${key}`}>What this check could not do</h2>
              <Tag source={card.source} testId="could-not-source" />
            </header>
            <ul>
              {couldNot.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        ) : null}

        <div className="case-body">
          <Ledger card={card} adSays={adSays} price={price} titleId={`case-ledger-title${key}`} />
        </div>

        {history.length > 0 ? (
          <section className="case-history" aria-label="Listing history">
            <ol data-testid="history-strip">
              {history.map((step) => (
                <li key={step.what}>
                  <span className="ui-mono">{step.what}</span>
                  <time dateTime={step.on}>{shortDate(step.on)}</time>
                </li>
              ))}
            </ol>
          </section>
        ) : null}

        {own && !inline ? (
          <p className="case-how">
            <a className="case-text-link" href={`/case/${id}/trace`} data-testid="case-how">
              How we checked
            </a>
          </p>
        ) : null}

        <div className="case-rules" data-testid="case-rules">
          {card.footer.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      </footer>
    </article>
  );
}
