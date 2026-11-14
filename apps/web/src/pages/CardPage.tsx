import { useEffect, useState } from "react";

import { CaseNotFound, fetchCard } from "../api";
import { SourceChip } from "../components/SourceChip";
import type { Card, CardLine, CardTone, VerdictState } from "../contracts";

const ROW_LABEL = { place: "PLACE", person: "PERSON", price: "PRICE" } as const;

// Words next to every colour. These are status labels for the tone, not new claims.
const TONE_WORD: Record<CardTone, string> = {
  ok: "Held up",
  hold: "On hold",
  red_flag: "Red flag",
  not_shown: "Not shown",
  not_checked: "Not checked",
};

const STATE_WORD: Record<VerdictState, string> = {
  hold: "Hold",
  dont_pay: "Don't pay · could not verify",
  unverified: "Not verified yet",
  verified: "Checks held up",
};

const STATE_TONE: Record<VerdictState, string> = {
  hold: "amber",
  dont_pay: "coral",
  unverified: "blue",
  verified: "teal",
};

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function day(iso: string): string {
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });
}

export function expiryText(expiresAt: string, now: Date = new Date()): string {
  const ms = new Date(expiresAt).getTime() - now.getTime();
  if (ms <= 0) return "Expired";
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 1) return `Expires in ${hours} h`;
  return `Expires in ${Math.max(1, Math.round(ms / 60_000))} min`;
}

function ToneMark({ tone }: { tone: CardTone }) {
  return (
    <span className={`tone tone-${tone}`}>
      <span className="tone-icon" aria-hidden="true">
        {tone === "ok" ? "✓" : tone === "red_flag" ? "!" : tone === "hold" ? "…" : "–"}
      </span>
      {TONE_WORD[tone]}
    </span>
  );
}

function EvidenceRow({ line, first, label }: { line: CardLine; first: boolean; label: string }) {
  return (
    <tr className={first ? "row-first" : undefined}>
      <th scope="row" className="cell-kind">
        {first ? (
          <span className="kind" data-testid="row-label">
            {label}
          </span>
        ) : null}
      </th>
      <td className="cell-what">{line.label}</td>
      <td className="cell-text">{line.text}</td>
      <td className="cell-tone">
        <ToneMark tone={line.tone} />
      </td>
    </tr>
  );
}

export function CardView({ card, variant }: { card: Card; variant: "result" | "verify" }) {
  const stateTone = STATE_TONE[card.state];
  const placeLine = card.rows.find((r) => r.kind === "place")?.lines[0];
  return (
    <article className={`card-page variant-${variant}`}>
      <header className="masthead">
        <span className="wordmark">SNAPBACK</span>
        <SourceChip source={card.source} />
      </header>

      <section className="hero" aria-labelledby="card-title">
        <p className="eyebrow">
          Case{" "}
          <span className="mono case-id" data-testid="case-id">
            {card.case_id}
          </span>
        </p>
        <h1 id="card-title" className={`state state-${stateTone}`}>
          {STATE_WORD[card.state]}
        </h1>
        <p className="meta">
          <span>
            Checked {clock(card.checked_at)}, {day(card.checked_at)}
          </span>
          <span className="sep" aria-hidden="true">
            ·
          </span>
          <span data-testid="expiry">{expiryText(card.expires_at)}</span>
        </p>
        {variant === "verify" ? (
          <p className="summary" data-testid="summary">
            This page confirms a SNAPBACK result. {placeLine ? placeLine.text : ""} Not checked:{" "}
            {card.not_checked.join(", ")}.
          </p>
        ) : null}
      </section>

      <section className="evidence" aria-label="What we checked">
        <div className="table-wrap">
          <table>
            <thead className="sr-only">
              <tr>
                <th>Check</th>
                <th>Item</th>
                <th>Finding</th>
                <th>Status</th>
              </tr>
            </thead>
            {card.rows.map((row) => (
              <tbody key={row.kind} className={`group group-${row.kind}`}>
                {row.lines.map((line, i) => (
                  <EvidenceRow
                    key={line.label}
                    line={line}
                    first={i === 0}
                    label={ROW_LABEL[row.kind]}
                  />
                ))}
              </tbody>
            ))}
          </table>
        </div>
      </section>

      <section className="not-checked" aria-labelledby="nc-title">
        <h2 id="nc-title">Not checked</h2>
        <ul data-testid="not-checked">
          {card.not_checked.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <footer className="rules">
        {card.footer.map((line) => (
          <p key={line}>{line}</p>
        ))}
        {card.footer.some((l) => l.includes("never texts first")) ? null : (
          <p>SNAPBACK never texts first and never asks for money.</p>
        )}
      </footer>
    </article>
  );
}

type Load =
  | { status: "loading" }
  | { status: "ready"; card: Card }
  | { status: "missing" }
  | { status: "error"; message: string };

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
        if (err instanceof CaseNotFound) setLoad({ status: "missing" });
        else
          setLoad({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => ctrl.abort();
  }, [caseId, attempt]);

  if (load.status === "ready") return <CardView card={load.card} variant={variant} />;
  return (
    <div className="card-page notice" role="status">
      <span className="wordmark">SNAPBACK</span>
      {load.status === "loading" && <p>Loading the result for case {caseId}…</p>}
      {load.status === "missing" && (
        <>
          <h1>No result for case {caseId}</h1>
          <p>Check the code on your message. Results are kept for 24 hours, then removed.</p>
        </>
      )}
      {load.status === "error" && (
        <>
          <h1>We could not load this result</h1>
          <p>{load.message}</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
        </>
      )}
    </div>
  );
}
