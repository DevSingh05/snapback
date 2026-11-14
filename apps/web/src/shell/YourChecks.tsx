import { useEffect, useState } from "react";

import { apiBase, fetchCard } from "../api";
import { STATE_WORD, shortDate } from "../cardStrings";
import { SourceChip } from "../components/SourceChip";
import type { Card } from "../contracts";

const READ_PREFIX = "snapback.case-read-token.";
const FIXTURE_CASE = "7Q2M";

/** The cases this browser holds a read token for (this visit), newest key last. */
export function knownCaseIds(): string[] {
  try {
    const ids: string[] = [];
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const key = window.sessionStorage.key(i);
      if (key?.startsWith(READ_PREFIX)) ids.push(key.slice(READ_PREFIX.length));
    }
    return ids;
  } catch {
    return [];
  }
}

type Row = { id: string; card: Card | null };

// Home's dashboard: the ads you have checked in this browser, each with the verdict the code
// set, and the way to check another. With no live server it shows the one team-made sample
// case, labelled as a sample.
export function YourChecks() {
  const [rows, setRows] = useState<Row[] | null>(null);
  useEffect(() => {
    const ctl = new AbortController();
    const ids = apiBase() ? knownCaseIds() : [FIXTURE_CASE];
    Promise.all(
      ids.map((id) =>
        fetchCard(id, ctl.signal)
          .then((card): Row => ({ id, card }))
          .catch((): Row => ({ id, card: null })),
      ),
    ).then((r) => !ctl.signal.aborted && setRows(r));
    return () => ctl.abort();
  }, []);

  const sample = !apiBase();
  return (
    <section className="yc" aria-label="Your checks" data-testid="your-checks">
      <header className="yc-head">
        <h2 className="yc-title">Your checks</h2>
        <p className="yc-sub">
          {sample
            ? "A sample case made by the team. Your own checks appear here."
            : "The ads you checked in this browser, this visit."}
        </p>
        <a className="yc-new" href="#listing">
          Check another ad
        </a>
      </header>
      {rows === null ? (
        <p className="yc-empty" role="status">
          Loading your checks...
        </p>
      ) : rows.length === 0 ? (
        <p className="yc-empty" data-testid="checks-empty">
          No checks yet. Paste an ad below and its result is kept here for this visit.
        </p>
      ) : (
        <ul className="yc-list">
          {rows.map(({ id, card }) => (
            <li key={id} className="yc-row" data-state={card?.state ?? "unknown"}>
              <a className="yc-link" href={`/case/${encodeURIComponent(id)}`}>
                <span className="yc-verdict">
                  {card ? STATE_WORD[card.state] : "Could not load this check"}
                </span>
                <span className="yc-id mono">Case {id}</span>
                {card && <span className="yc-date">Checked {shortDate(card.checked_at)}</span>}
                {card && <SourceChip source={card.source} />}
                <span className="yc-open">Open</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
