// One case result, built from the case pieces: the path rail, the verdict band with the proof
// pair, the ledger beside the ad, what to do now, and the footer the card carries. The case page renders it at
// full size; the Home thread renders the same thing inline (`inline`), where the headline is an
// h2 and the rail is left to the page around it.
import type { ReactNode } from "react";

import "../ui/ui.css";
import "./case.css";
import { STATE_WORD, historySteps, shortDate } from "../cardStrings";
import type { Card, CardLine, CardRowKind } from "../contracts";
import { PathRail, Tag } from "../ui";
import { AnnotatedAd } from "./AnnotatedAd";
import { Ledger } from "./Ledger";
import {
  VERDICT_TONE,
  checkedStamp,
  expiryText,
  flaggedLines,
  photosPlaced,
  type AdMark,
  type PriceFigures,
  type ProofCard,
  type ProofData,
  type RealListing as RealListingData,
  type SaferPlace,
} from "./model";
import { NextSteps, caseSteps } from "./NextSteps";
import { ProofPair } from "./ProofPair";
import { RealListing } from "./RealListing";
import { SaferTiles } from "./SaferTiles";
import { VerdictBand } from "./VerdictBand";

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
  // Where "Find me safer places like this" goes. Left out: the tiles below, else the Finder.
  saferHref?: string;
  // Anything the page adds under the next steps (the safer places, the office check).
  children?: ReactNode;
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
  saferHref: saferTo,
  children,
}: CaseResultProps) {
  const id = encodeURIComponent(card.case_id);
  const key = inline ? `-${card.case_id}` : "";
  const own = variant === "result";
  const walk = photosPlaced(card);
  const history = historySteps(card.for_sale);
  // A result that did not pass: it gets the reasons heading and the places to go to instead.
  const failed = card.state === "hold" || card.state === "dont_pay";
  const tiles = own && failed && safer_places.length > 0;
  // "Safer places" goes to the tiles on this page when they are there, else to the Finder.
  const saferHref = saferTo ?? (tiles ? `#safer${key}` : "/finder");
  // Beside the ledger: the real listing when the API has it, and the pasted ad when we have it.
  const side = Boolean(realListing || adText);
  const caseTag = (
    <>
      <span>
        CASE <span data-testid="case-id">{card.case_id}</span>
      </span>
      <Tag source={card.source} testId="source-chip" />
    </>
  );
  // The one primary button: the walk when a photo was placed, else the safer places.
  const safer = { label: "Find me safer places like this", href: saferHref };
  const primary = walk ? { label: "Walk it first", href: `/case/${id}/twin` } : safer;
  return (
    <article className={`case-page${inline ? " case-inline" : ""}`} data-variant={variant}>
      {own && !inline ? (
        <PathRail
          next={2}
          hrefs={{ 1: `/case/${id}`, 2: `/case/${id}/twin`, 3: saferHref, 4: `/case/${id}/prep` }}
          className="case-rail"
        >
          {caseTag}
        </PathRail>
      ) : (
        <p className="case-head ui-mono">{caseTag}</p>
      )}

      <VerdictBand
        tone={VERDICT_TONE[card.state]}
        headline={STATE_WORD[card.state]}
        level={inline ? 2 : 1}
        titleId={`case-title${key}`}
        meta={
          <>
            <span>THE RESULT · {checkedStamp(card.checked_at)}</span>
            <span data-testid="expiry">{expiryText(card.expires_at)}</span>
          </>
        }
        why={flaggedLines(card)}
        reasons={(card as ProofCard).summary ?? []}
        reasonsTitle={failed ? "WHY THIS IS NOT A GOOD DEAL" : null}
        summary={
          own ? null : (
            <>
              This is the SNAPBACK result for case {card.case_id}. It covers the place, the person
              and the price, and lists what was not checked: {card.not_checked.join(", ")}.
            </>
          )
        }
        primary={own ? primary : null}
        link={own && walk ? safer : null}
      >
        {proof ? <ProofPair {...proof} handoff={own && !inline} /> : null}
      </VerdictBand>

      <div className={`case-body${side ? " case-body-with-side" : ""}`}>
        <Ledger card={card} adSays={adSays} price={price} titleId={`case-ledger-title${key}`} />
        {side ? (
          <div className="case-side" data-side={realListing ? "real" : "ad"}>
            {realListing ? (
              <RealListing listing={realListing} titleId={`case-real-title${key}`} />
            ) : null}
            {adText ? <AnnotatedAd text={adText} marks={adMarks} origin={adOrigin} /> : null}
          </div>
        ) : null}
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

      {own ? (
        <NextSteps
          steps={caseSteps(card.case_id, walk, saferHref, card.state === "verified")}
          titleId={`case-next-title${key}`}
        />
      ) : null}

      {tiles ? (
        <SaferTiles places={safer_places} id={`safer${key}`} titleId={`case-safer-title${key}`} />
      ) : null}

      {children}

      <footer className="case-rules" data-testid="case-rules">
        {card.footer.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </footer>
    </article>
  );
}
