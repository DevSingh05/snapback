import { useEffect, useRef, useState } from "react";

import { CaseNotFound, apiBase, fetchCard } from "../api";
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
  openTimelineStream,
  useTimeline,
} from "../case";
import "../case/case.css";
import { asLang, loadLang, saveLang, type Lang } from "../lang";
import { OfficeConfirm } from "../office/OfficeConfirm";
import { replayForCase } from "../replay";
import { Loading, Problem } from "../ui";
import type { Card, CaseTimeline } from "../contracts";

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

// While the deep agent is still working (`running`), follow its timeline; when it finishes, reload
// the card so the Planner's follow-up lines and choice appear without a manual refresh.
export function useLiveTimeline(
  caseId: string,
  lang: string | undefined,
  first: CaseTimeline | null,
  onDone: () => void,
): CaseTimeline | null {
  const [live, setLive] = useState<CaseTimeline | null>(null);
  const done = useRef(onDone);
  done.current = onDone;
  const running = first?.running === true;
  useEffect(() => {
    setLive(null);
    if (!running) return;
    return openTimelineStream({
      caseId,
      lang,
      onTimeline: setLive,
      onFeed: (feed) => {
        if (feed === "done") done.current();
      },
    });
  }, [caseId, lang, running]);
  return live ?? first;
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
  const proof = useProofRead(card);
  const realListing = useRealListingRead(card.case_id, card.lang);
  const copyAlert = useCopyAlertRead(card.case_id, card.lang);
  const reportPack = useReportPackRead(card.case_id, card.lang);
  const first = useTimeline(card.case_id, card.lang);
  const timeline = useLiveTimeline(card.case_id, card.lang, first, onChanged);
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

  // An iMessage red flag links to its proof, /case/<id>#check-<label> (or #checks). The card
  // loads after mount, so the browser's own jump to the fragment happens before that line
  // exists: once the card is ready, scroll to it, once per page load.
  const jumped = useRef(false);
  const ready = load.status === "ready";
  useEffect(() => {
    if (!ready || jumped.current) return;
    const id = decodeURIComponent(window.location.hash.slice(1));
    if (!id) return;
    jumped.current = true;
    const target = document.getElementById(id);
    if (!target) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    target.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
  }, [ready]);

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
            ? { label: "Check an ad", href: "/home" }
            : { label: "Try again", onClick: () => setAttempt((n) => n + 1) }
        }
      />
    </div>
  );
}
