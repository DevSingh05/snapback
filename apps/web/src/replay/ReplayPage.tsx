import { Fragment, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import { findingWord, getReplay, REPLAY_VERDICT_WORDS, startsWithToneWord } from "./index";
import { openCase, runReplayCase, type RunCase } from "./runCase";
import { replayLang, shortDate, words, type Lang } from "./text";
import type { Replay, ReplayStepKind } from "./types";
import { useReplays } from "./useReplays";
import { dataMode } from "../api";
import "./replay.css";

// Dates arrive as YYYY-MM-DD; format in UTC so the day never shifts with the viewer's timezone.
export function reportedDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function dollars(amount: number): string {
  return `$${amount.toLocaleString("en-US")}`;
}

function NotFound() {
  return (
    <article className="replay-page replay-missing" role="status">
      <h1>Replay not found</h1>
      <p>There is no replay at this address.</p>
      <p>
        <a href="/">Back to SNAPBACK</a>
      </p>
    </article>
  );
}

function FindingLine({
  finding,
  stepKind,
  lang,
}: {
  finding?: Replay["snapback"]["findings"][number];
  stepKind?: ReplayStepKind;
  lang: Lang;
}) {
  if (!finding) return <p>{words(lang).nothingFlagged}</p>;
  return (
    <p className={`finding finding-${finding.status}`} data-status={finding.status}>
      {startsWithToneWord(finding.text) ? null : (
        <strong>{findingWord(finding.status, stepKind ?? "listing")}. </strong>
      )}
      {finding.text}
    </p>
  );
}

// A replay can have several findings for one step; every one is shown, in file order.
function FindingLines({
  list,
  stepKind,
  lang,
}: {
  list: Replay["snapback"]["findings"];
  stepKind: ReplayStepKind;
  lang: Lang;
}) {
  if (list.length === 0) return <FindingLine lang={lang} />;
  return (
    <>
      {list.map((f) => (
        <FindingLine key={`${f.step_id}-${f.text}`} finding={f} stepKind={stepKind} lang={lang} />
      ))}
    </>
  );
}

// "Run this case" starts the replay's staged case on the API and opens its real card.
function RunButton({ replay, run, lang }: { replay: Replay; run: RunCase; lang: Lang }) {
  const t = words(lang);
  const [state, setState] = useState<"idle" | "busy" | "failed">("idle");
  const offline = dataMode() === "fixture";
  const go = async () => {
    setState("busy");
    try {
      openCase(await run(replay.case_id));
    } catch {
      setState("failed");
    }
  };
  return (
    <div className="replay-run">
      <button
        type="button"
        className="replay-run-btn"
        onClick={go}
        disabled={offline || state === "busy"}
      >
        {state === "busy" ? t.running : t.run}
      </button>
      {offline ? <p className="muted">{t.runNeedsApi}</p> : null}
      {state === "failed" ? (
        <p role="alert" className="replay-error">
          {t.runFailed}
        </p>
      ) : null}
    </div>
  );
}

export function ReplayView({
  replay,
  lang = replayLang(),
  runCase = runReplayCase,
}: {
  replay: Replay;
  lang?: Lang;
  runCase?: RunCase;
}) {
  const t = words(lang);
  const { steps, snapback } = replay;
  // The stop is the first payment step; stop_before, when given, must agree.
  const stopIndex = steps.findIndex((s) => s.kind === "payment");
  const stopProblem =
    stopIndex < 0
      ? "This replay has no payment step, so the stop cannot be placed."
      : snapback.stop_before && snapback.stop_before !== steps[stopIndex]?.id
        ? "This replay's stop_before does not name its first payment step."
        : null;
  const findings = new Map<string, Replay["snapback"]["findings"]>();
  for (const f of snapback.findings)
    findings.set(f.step_id, [...(findings.get(f.step_id) ?? []), f]);

  return (
    <article className="replay-page">
      <header className="replay-head">
        <div className="replay-masthead">
          <span className="wordmark">SNAPBACK</span>
          <SourceChip source="fixture" />
        </div>
        <p className="replay-label">{replay.fictional ? t.fictional : t.reportedLabel}</p>
        <h1>{replay.title}</h1>
        {replay.source && !replay.fictional ? (
          <p className="replay-source">
            {t.source}:{" "}
            <a href={replay.source.url} rel="noopener noreferrer" target="_blank">
              {replay.source.name}
            </a>
            {", "}
            <span data-testid="source-date">{shortDate(replay.source.published_on, lang)}</span>
          </p>
        ) : null}
        {replay.fictional ? (
          <p className="replay-note">
            Modelled on a public pattern and made up by the team: no real person, address, listing,
            source or date.
          </p>
        ) : null}
      </header>

      {stopProblem ? (
        <p className="replay-error" role="alert">
          {stopProblem}
        </p>
      ) : (
        <>
          <div className="replay-legend" aria-hidden="true">
            <span>{t.happened}</span>
            <span>{t.withSnapback}</span>
          </div>

          <ol className="timeline" data-testid="timeline">
            {steps.map((step, i) => (
              <Fragment key={step.id}>
                {i === stopIndex ? (
                  <li
                    key="stop"
                    className={`tl-stop tl-stop-${snapback.verdict}`}
                    data-step-id="stop"
                    data-testid="stop-marker"
                  >
                    <span className="stop-tag">SNAPBACK stops here</span>
                    <strong className="stop-words">{REPLAY_VERDICT_WORDS[snapback.verdict]}</strong>
                    <span className="stop-amount" data-testid="amount-line">
                      {dollars(replay.amount_usd)} was still in their account here
                    </span>
                  </li>
                ) : null}
                <li
                  className={`tl-step${stopIndex >= 0 && i >= stopIndex ? " tl-after" : ""}`}
                  data-step-id={step.id}
                  data-testid={`step-${step.id}`}
                >
                  <div className="tl-real">
                    <span className="tl-label">{t.happened}</span>
                    {step.reported_on ? (
                      <time dateTime={step.reported_on}>{reportedDate(step.reported_on)}</time>
                    ) : null}
                    <h2>{step.label}</h2>
                    <p>{step.detail}</p>
                  </div>
                  <div className="tl-snap">
                    <span className="tl-label">{t.withSnapback}</span>
                    {i >= stopIndex && stopIndex >= 0 ? (
                      <p className="muted">{t.notSent}</p>
                    ) : (
                      <FindingLines
                        list={findings.get(step.id) ?? []}
                        stepKind={step.kind}
                        lang={lang}
                      />
                    )}
                  </div>
                </li>
              </Fragment>
            ))}
          </ol>
        </>
      )}

      {replay.cant_catch ? (
        <section className="replay-cant" aria-label={t.cantCatch}>
          <h2>{t.cantCatch}</h2>
          <p>{replay.cant_catch}</p>
        </section>
      ) : null}

      {replay.fictional ? null : <RunButton replay={replay} run={runCase} lang={lang} />}

      <footer className="replay-foot">
        {replay.source && !replay.fictional ? (
          <p data-testid="replay-footer">
            {t.footer(replay.source.name, shortDate(replay.source.published_on, lang))}{" "}
            <a href={replay.source.url} rel="noopener noreferrer" target="_blank">
              {t.source}
            </a>
          </p>
        ) : null}
        <p>SNAPBACK never texts first and never asks for money.</p>
      </footer>
    </article>
  );
}

export function ReplayPage({
  slug,
  replay,
  runCase,
}: {
  slug: string;
  replay?: Replay;
  runCase?: RunCase;
}) {
  const all = useReplays();
  const found = replay ?? getReplay(slug, all);
  return found ? <ReplayView replay={found} runCase={runCase} /> : <NotFound />;
}
