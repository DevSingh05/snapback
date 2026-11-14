import { useEffect, useState, type CSSProperties } from "react";

import { CaseNotFound, fetchCard } from "../api";
import { SourceChip } from "../components/SourceChip";
import { HouseGlyph, Wordmark } from "../components/HouseGlyph";
import { KitArt, type KitArtKind } from "../components/KitArt";
import { LabSection } from "../lab";
import { loadBrief } from "../search/api";
import { OfficeConfirm } from "../office/OfficeConfirm";
import { PlacesStrip } from "../search/PlacesStrip";
import { replayForCase } from "../replay";
import { STATE_WORD, historySteps, shortDate, toneWord } from "../cardStrings";
import type { Card, CardLine, CardRowKind, CardTone, VerdictState } from "../contracts";

const ROW_LABEL = {
  place: "PLACE",
  person: "PERSON",
  price: "PRICE",
  claims: "WHAT THE AD CLAIMS",
} as const;

// The drawing beside each group of checks. The place check is the product's own move: the ad's
// photo pinned where it was taken, so that one is the room with a pinned photo.
const ROW_ART: Record<CardRowKind, KitArtKind> = {
  place: "scan",
  person: "person",
  price: "price",
  claims: "claims",
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

// The chip's colour and icon follow the word it shows, so one word always looks one way.
const WORD_KIND: Record<string, { kind: string; icon: string }> = {
  Matches: { kind: "ok", icon: "✓" },
  "Doesn't match": { kind: "mismatch", icon: "✕" },
  Warning: { kind: "warn", icon: "!" },
  "Not confirmed": { kind: "unconfirmed", icon: "?" },
  "Not checked": { kind: "unchecked", icon: "–" },
};

const STATE_ICON: Record<VerdictState, string> = {
  dont_pay: "✕",
  hold: "!",
  unverified: "?",
  verified: "✓",
};

function ToneMark({ tone, row }: { tone: CardTone; row: CardRowKind }) {
  const word = toneWord(tone, row);
  const { kind, icon } = WORD_KIND[word] ?? { kind: "unchecked", icon: "–" };
  return (
    <span className={`tone tone-${tone} tone-is-${kind}`}>
      <span className="tone-icon" aria-hidden="true">
        {icon}
      </span>
      {word}
    </span>
  );
}

function EvidenceRow({
  line,
  first,
  label,
  row,
  span,
  index,
}: {
  line: CardLine;
  first: boolean;
  label: string;
  row: CardRowKind;
  // How many lines this group has: its label and drawing sit beside all of them.
  span: number;
  // Where this line sits in the whole card: the lines land one after another.
  index: number;
}) {
  return (
    <tr className={first ? "row-first" : undefined} style={{ "--i": index } as CSSProperties}>
      {first ? (
        <th scope="rowgroup" rowSpan={span} className="cell-kind">
          <span className="kind" data-testid="row-label">
            {label}
          </span>
          <KitArt kind={ROW_ART[row]} className="kind-art" detail="low" />
          {row === "place" ? <span className="kind-standin mono">Drawn stand-in</span> : null}
        </th>
      ) : null}
      <td className="cell-what">{line.label}</td>
      <td className="cell-text">{line.text}</td>
      <td className="cell-tone">
        <ToneMark tone={line.tone} row={row} />
      </td>
    </tr>
  );
}

export function CardView({
  card,
  variant,
  withLab = false,
}: {
  card: Card;
  variant: "result" | "verify";
  withLab?: boolean;
}) {
  const rows = card.rows;
  const history = historySteps(card.for_sale);
  const stateTone = STATE_TONE[card.state];
  const firstIndex = rows.map((_, r) => rows.slice(0, r).reduce((n, g) => n + g.lines.length, 0));
  return (
    <article className={`card-page variant-${variant}`}>
      <header className="masthead">
        <Wordmark />
        <SourceChip source={card.source} />
      </header>

      <section className={`hero hero-${stateTone}`} aria-labelledby="card-title">
        <KitArt kind="pinned" className="hero-house" />
        <span className="hero-mark" aria-hidden="true">
          {STATE_ICON[card.state]}
        </span>
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
            This is the SNAPBACK result for case {card.case_id}. It covers the place, the person and
            the price, and lists what was not checked: {card.not_checked.join(", ")}.
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
            {rows.map((row, r) => (
              <tbody key={row.kind} className={`group group-${row.kind}`}>
                {row.lines.map((line, i) => (
                  <EvidenceRow
                    key={`${line.label}-${i}`}
                    line={line}
                    first={i === 0}
                    label={ROW_LABEL[row.kind]}
                    row={row.kind}
                    span={row.lines.length}
                    index={(firstIndex[r] ?? 0) + i}
                  />
                ))}
              </tbody>
            ))}
          </table>
        </div>
      </section>

      {history.length > 0 ? (
        <section className="history" aria-label="Listing history">
          <ol data-testid="history-strip">
            {history.map((step) => (
              <li key={step.what}>
                <span className="history-what">{step.what}</span>
                <time dateTime={step.on}>{shortDate(step.on)}</time>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="not-checked" aria-labelledby="nc-title">
        <h2 id="nc-title">Not checked</h2>
        <ul data-testid="not-checked">
          {card.not_checked.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      {withLab ? <LabSection /> : null}

      {replayForCase(card.case_id) ? (
        <p className="replay-link">
          <a href={`/replay/${replayForCase(card.case_id)?.slug}`}>
            {replayForCase(card.case_id)?.fictional
              ? "See a fictional example"
              : "See a case like this, re-created from a public report"}
          </a>
        </p>
      ) : null}

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

  if (load.status === "ready")
    return variant === "result" ? (
      <div className="pf-stack">
        <CardView card={load.card} variant={variant} withLab />
        <OfficeConfirm caseId={caseId} onChanged={() => setAttempt((n) => n + 1)} />
        <a className="pf-action pf-link" href={`/case/${caseId}/prep`} data-testid="card-prep-link">
          Tour prep: be your own realtor
        </a>
        <PlacesStrip caseId={caseId} brief={loadBrief(caseId)} />
      </div>
    ) : (
      <CardView card={load.card} variant={variant} />
    );
  return (
    <div className="card-page notice" role="status">
      <Wordmark />
      {load.status === "loading" && <p>Loading the result for case {caseId}…</p>}
      {load.status === "missing" && (
        <>
          <HouseGlyph className="notice-house" lit={false} />
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
