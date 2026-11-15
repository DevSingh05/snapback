import { useEffect, useState } from "react";

import { CaseNotFound, apiBase, fetchCard } from "../api";
import {
  CaseResult,
  VerdictBand,
  expiryText,
  useCopyAlert,
  useProof,
  useRealListing,
  useReportPack,
  useSaferPlaces,
} from "../case";
import "../case/case.css";
import { asLang, loadLang, saveLang, type Lang } from "../lang";
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
export function CardView({
  card,
  variant,
  lang,
  onLang,
}: {
  card: Card;
  variant: "result" | "verify";
  lang?: Lang;
  onLang?: (lang: Lang) => void;
}) {
  const proof = useProof(card);
  return (
    <CaseResult card={card} variant={variant} proof={proof} lang={lang} onLang={onLang}>
      <ReplayLink caseId={card.case_id} />
    </CaseResult>
  );
}

function ResultPage({
  card,
  onChanged,
  lang,
  onLang,
}: {
  card: Card;
  onChanged: () => void;
  lang?: Lang;
  onLang: (lang: Lang) => void;
}) {
  const proof = useProof(card);
  const realListing = useRealListing(card.case_id, card.lang);
  const copyAlert = useCopyAlert(card.case_id, card.lang);
  const reportPack = useReportPack(card.case_id, card.lang);
  const saferPlaces = useSaferPlaces(
    card.case_id,
    card.state === "hold" || card.state === "dont_pay",
  );
  return (
    <CaseResult
      card={card}
      variant="result"
      proof={proof}
      realListing={realListing}
      copyAlert={copyAlert}
      reportPack={reportPack}
      saferPlaces={saferPlaces}
      lang={lang}
      onLang={onLang}
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
  // ?lang=es opens in Spanish; else the viewer's last choice (see ../lang).
  const [lang, setLang] = useState<Lang>(() => loadLang());
  // With no API there is only the English fixture, so no switch.
  const live = Boolean(apiBase());
  const choose = (next: Lang) => {
    saveLang(next);
    setLang(asLang(next) ?? "en");
  };

  useEffect(() => {
    const ctrl = new AbortController();
    // A new language keeps the report on screen until the other one lands; a new case, or a
    // retry, starts from the loading band.
    setLoad((was) =>
      was.status === "ready" && was.card.case_id === caseId ? was : { status: "loading" },
    );
    fetchCard(caseId, ctrl.signal, lang)
      .then((card) => setLoad({ status: "ready", card }))
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setLoad({ status: err instanceof CaseNotFound ? "missing" : "error" });
      });
    return () => ctrl.abort();
  }, [caseId, attempt, lang]);

  if (load.status === "ready")
    return variant === "result" ? (
      <ResultPage
        card={load.card}
        onChanged={() => setAttempt((n) => n + 1)}
        lang={live ? lang : undefined}
        onLang={choose}
      />
    ) : (
      <CardView card={load.card} variant={variant} lang={live ? lang : undefined} onLang={choose} />
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
