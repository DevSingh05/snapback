import { useEffect, useState } from "react";

import { CaseNotFound, fetchCard } from "../api";
import {
  CaseResult,
  VerdictBand,
  expiryText,
  useCopyAlertRead,
  useProof,
  useProofRead,
  useRealListingRead,
  useReportPackRead,
  useSaferPlacesRead,
  useTimeline,
} from "../case";
import "../case/case.css";
import { OfficeConfirm } from "../office/OfficeConfirm";
import { replayForCase } from "../replay";
import { Loading, Problem } from "../ui";
import type { Card } from "../contracts";

export { expiryText };

// The replay for this case, when there is one: a quiet link under the result.
function ReplayLink({ caseId }: { caseId: string }) {
  const replay = replayForCase(caseId);
  if (!replay) return null;
  return (
    <p className="case-replay">
      <a className="case-text-link" href={`/replay/${replay.slug}`}>
        {replay.fictional
          ? "See a fictional example"
          : "See a case like this, re-created from a public report"}
      </a>
    </p>
  );
}

// The card as a case result (design v4 ticket 3). The pieces live in ../case; this file only
// loads the card and hangs the page's own extras under the next steps.
export function CardView({ card, variant }: { card: Card; variant: "result" | "verify" }) {
  const proof = useProof(card);
  return (
    <CaseResult card={card} variant={variant} proof={proof}>
      <ReplayLink caseId={card.case_id} />
    </CaseResult>
  );
}

function ResultPage({ card, onChanged }: { card: Card; onChanged: () => void }) {
  const proof = useProofRead(card);
  const realListing = useRealListingRead(card.case_id, card.lang);
  const copyAlert = useCopyAlertRead(card.case_id, card.lang);
  const reportPack = useReportPackRead(card.case_id, card.lang);
  const timeline = useTimeline(card.case_id, card.lang);
  const saferPlaces = useSaferPlacesRead(
    card.case_id,
    card.state === "hold" || card.state === "dont_pay",
  );
  return (
    <CaseResult
      card={card}
      variant="result"
      proof={proof.value}
      realListing={realListing.value}
      copyAlert={copyAlert.value}
      reportPack={reportPack.value}
      timeline={timeline}
      saferPlaces={saferPlaces.value ?? []}
      checking={{
        proof: proof.waiting,
        real: realListing.waiting,
        next: copyAlert.waiting || reportPack.waiting,
        safer: saferPlaces.waiting,
      }}
    >
      <OfficeConfirm caseId={card.case_id} onChanged={onChanged} />
      <ReplayLink caseId={card.case_id} />
    </CaseResult>
  );
}

type Load =
  | { status: "loading" }
  | { status: "ready"; card: Card }
  | { status: "missing" }
  | { status: "error" };

export function CardPage({ caseId, variant }: { caseId: string; variant: "result" | "verify" }) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoad({ status: "loading" });
    fetchCard(caseId, ctrl.signal)
      .then((card) => setLoad({ status: "ready", card }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setLoad({ status: err instanceof CaseNotFound ? "missing" : "error" });
      });
    return () => ctrl.abort();
  }, [caseId, attempt]);

  if (load.status === "ready")
    return variant === "result" ? (
      <ResultPage card={load.card} onChanged={() => setAttempt((n) => n + 1)} />
    ) : (
      <CardView card={load.card} variant={variant} />
    );
  if (load.status === "loading")
    return (
      <div className="case-page case-notice">
        <Loading label={`Loading the result for case ${caseId}`} shape="band" />
      </div>
    );
  // Nothing loaded, so nothing was checked: the slate band, never a pass and never a warning.
  return (
    <div className="case-page case-notice" data-testid="case-failed">
      <VerdictBand
        tone="slate"
        headline={
          load.status === "missing"
            ? `No result for case ${caseId}`
            : "We could not load this result"
        }
        meta={<span>CASE {caseId}</span>}
      />
      <Problem
        message={
          load.status === "missing"
            ? "Check the code on your message. Results are kept for 24 hours, then removed."
            : "We can't reach the record right now. Nothing was checked. Try again."
        }
        action={
          load.status === "missing"
            ? { label: "Check an ad", href: "/" }
            : { label: "Try again", onClick: () => setAttempt((n) => n + 1) }
        }
      />
    </div>
  );
}
