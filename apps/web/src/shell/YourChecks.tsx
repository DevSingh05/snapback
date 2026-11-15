import { useEffect, useState } from "react";

import { apiBase, fetchCard } from "../api";
import { STATE_WORD, shortDate } from "../cardStrings";
import { SourceChip } from "../components/SourceChip";
import type { Card } from "../contracts";
import { EmptyRows, Loading, State, type StateKind } from "../ui";

// The square beside each verdict. The words are the card's own (cardStrings.ts).
const STATE_KIND: Record<Card["state"], StateKind> = {
  hold: "warn",
  dont_pay: "mismatch",
  unverified: "unconfirmed",
  verified: "ok",
};

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

// Home's dashboard: the ads you have checked in this browser, as rows, each with the verdict the
// code set, and the way to check another. With no live server it shows the one team-made sample
// case, labelled as a sample. A row never carries a stock photo: a picture here would read as
// the renter's own.
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
    <section className="yc" aria-labelledby="yc-title" data-testid="your-checks">
      <header className="yc-head">
        <h2 id="yc-title" className="yc-title">
          Your reports
        </h2>
        <a className="yc-new" href="#listing">
          Check another ad
        </a>
      </header>
      <p className="yc-sub">
        {sample
          ? "A sample report made by the team. Your own reports appear here."
          : "A report for each ad you checked in this browser, this visit."}
      </p>
      {rows === null ? (
        <Loading label="Loading your checks" rows={2} className="yc-wait" />
      ) : rows.length === 0 ? (
        <div data-testid="checks-empty">
          <EmptyRows
            message="Nothing checked yet. Paste an ad above and it will be kept here for this visit."
            examples={["A Marketplace or Craigslist ad, pasted as text", "A link, or screenshots"]}
          />
        </div>
      ) : (
        <ul className="yc-list">
          {rows.map(({ id, card }) => (
            <li key={id} className="yc-row" data-state={card?.state ?? "unknown"}>
              <a className="yc-link" href={`/case/${encodeURIComponent(id)}`}>
                <span className="yc-main">
                  <State kind={card ? STATE_KIND[card.state] : "unchecked"} className="yc-verdict">
                    {card ? STATE_WORD[card.state] : "Could not load this check"}
                  </State>
                  <span className="yc-meta ui-mono">
                    <span className="yc-id">Case {id}</span>
                    {card && <span className="yc-date">Checked {shortDate(card.checked_at)}</span>}
                    {card && <SourceChip source={card.source} />}
                  </span>
                </span>
                <span className="yc-open" aria-hidden="true">
                  →
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
