import { Fragment } from "react";

import { SourceChip } from "../components/SourceChip";
import { Wordmark } from "../components/HouseGlyph";
import { FINDING_WORDS, getReplay, REPLAY_VERDICT_WORDS } from "./index";
import type { Replay } from "./types";
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

function FindingLine({ finding }: { finding?: Replay["snapback"]["findings"][number] }) {
  if (!finding) return <p>Nothing flagged yet.</p>;
  return (
    <p className={`finding finding-${finding.status}`} data-status={finding.status}>
      <strong>{FINDING_WORDS[finding.status]}.</strong> {finding.text}
    </p>
  );
}

export function ReplayView({ replay }: { replay: Replay }) {
  const { steps, snapback } = replay;
  // The stop is the first payment step; stop_before, when given, must agree.
  const stopIndex = steps.findIndex((s) => s.kind === "payment");
  const stopProblem =
    stopIndex < 0
      ? "This replay has no payment step, so the stop cannot be placed."
      : snapback.stop_before && snapback.stop_before !== steps[stopIndex]?.id
        ? "This replay's stop_before does not name its first payment step."
        : null;
  const findings = new Map(snapback.findings.map((f) => [f.step_id, f]));

  return (
    <article className="replay-page">
      <header className="replay-head">
        <div className="replay-masthead">
          <Wordmark />
          <SourceChip source="fixture" />
        </div>
        <p className="replay-label">
          {replay.fictional ? "Fictional example" : "Re-created from a public report"}
        </p>
        <h1>{replay.title}</h1>
        {replay.source && !replay.fictional ? (
          <p className="replay-source">
            Source:{" "}
            <a href={replay.source.url} rel="noopener noreferrer" target="_blank">
              {replay.source.name}
            </a>
            {", "}
            <span data-testid="source-date">{reportedDate(replay.source.published_on)}</span>
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
            <span>What was reported</span>
            <span>What SNAPBACK would have shown</span>
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
                    <time dateTime={step.reported_on}>{reportedDate(step.reported_on)}</time>
                    <h2>{step.label}</h2>
                    <p>{step.detail}</p>
                  </div>
                  <div className="tl-snap">
                    {i >= stopIndex && stopIndex >= 0 ? (
                      <p className="muted">Not sent. Stopped before this.</p>
                    ) : (
                      <FindingLine finding={findings.get(step.id)} />
                    )}
                  </div>
                </li>
              </Fragment>
            ))}
          </ol>
        </>
      )}

      <footer className="replay-foot">
        <p>SNAPBACK never texts first and never asks for money.</p>
      </footer>
    </article>
  );
}

export function ReplayPage({ slug, replay }: { slug: string; replay?: Replay }) {
  const found = replay ?? getReplay(slug);
  return found ? <ReplayView replay={found} /> : <NotFound />;
}
