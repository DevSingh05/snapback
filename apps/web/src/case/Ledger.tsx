// "How we know": the proof file. Every check is on the table in three groups, the failing ones
// first: what doesn't check out, what checks out, and what was not checked. Each line shows the
// ad's words (only when the caller has them) beside what the record gave us, the record's name,
// and the state word. Every line's text and tone are the API's, shown as given, and the group a
// line lands in follows its locked state word. The ad side is never made up here.
import type { CSSProperties } from "react";

import "../ui/ui.css";
import "./case.css";
import { toneWord } from "../cardStrings";
import type { Card, CardLine, CardRowKind, DataSource } from "../contracts";
import { RecordLine, State, type StateKind } from "../ui";
import { checkCount, recordSourceOf, stateKind, type PriceFigures } from "./model";
import { PriceBar } from "./PriceBar";

const ROW_LABEL: Record<CardRowKind, string> = {
  place: "PLACE",
  person: "PERSON",
  price: "PRICE",
  claims: "WHAT THE AD CLAIMS",
};

export type LedgerGroup = "fails" | "passes" | "unchecked";

const GROUP_TITLE: Record<LedgerGroup, string> = {
  fails: "What doesn't check out",
  passes: "What checks out",
  unchecked: "Not checked",
};
const GROUP_ORDER: LedgerGroup[] = ["fails", "passes", "unchecked"];

const GROUP_OF: Record<StateKind, LedgerGroup> = {
  mismatch: "fails",
  warn: "fails",
  unconfirmed: "fails",
  ok: "passes",
  unchecked: "unchecked",
};

interface Entry {
  row: CardRowKind;
  line: CardLine;
}

/** The card's lines by group, each group in card order. */
export function groupLines(card: Card): Record<LedgerGroup, Entry[]> {
  const groups: Record<LedgerGroup, Entry[]> = { fails: [], passes: [], unchecked: [] };
  for (const row of card.rows)
    for (const line of row.lines)
      groups[GROUP_OF[stateKind(line.tone, row.kind)]].push({ row: row.kind, line });
  return groups;
}

// A line that opens with the API's capitals for "not shown" keeps every character, but the
// capitals are set in sentence case by CSS: the state word beside the line already says it.
const SHOUTED = /^(NOT SHOWN\.)([\s\S]*)$/;

function LineText({ text }: { text: string }) {
  const parts = SHOUTED.exec(text);
  return (
    <span className="case-line-text">
      {parts ? (
        <>
          <span className="case-line-tone">{parts[1]}</span>
          {parts[2]}
        </>
      ) : (
        text
      )}
    </span>
  );
}

interface LedgerProps {
  card: Card;
  // The words of the pasted ad that a line is about, when the caller has them.
  adSays?: (row: CardRowKind, line: CardLine) => string | null | undefined;
  // The rent figures behind the price check, when the caller has them.
  price?: PriceFigures | null;
  titleId?: string;
}

function LedgerRow({
  entry,
  index,
  ad,
  hasAd,
  source,
  lang,
  price,
}: {
  entry: Entry;
  index: number;
  ad: string | null;
  hasAd: boolean;
  source: DataSource;
  lang: string;
  price: PriceFigures | null;
}) {
  const { row, line } = entry;
  const record = recordSourceOf(line, lang);
  return (
    <tr className="case-row" style={{ "--i": index } as CSSProperties}>
      <th scope="row" className="case-cell-check">
        <span className="case-group ui-mono" data-testid="row-label">
          {ROW_LABEL[row]}
        </span>
        <span className="case-check-name">{line.label}</span>
        {line.source_name ? (
          <span className="case-check-source ui-mono" data-testid="line-source">
            {line.source_name} · {line.source ?? source}
          </span>
        ) : null}
      </th>
      {ad ? (
        <td className="case-cell-ad" data-label="The ad says">
          {ad}
        </td>
      ) : null}
      <td
        className="case-cell-record"
        colSpan={hasAd && !ad ? 2 : 1}
        data-label={ad ? "The record says" : ""}
      >
        <LineText text={line.text} />
        {record ? <RecordLine source={record} live={source} /> : null}
        {price ? <PriceBar price={price} /> : null}
      </td>
      <td className="case-cell-result">
        <State kind={stateKind(line.tone, row)}>{toneWord(line.tone, row)}</State>
      </td>
    </tr>
  );
}

export function Ledger({ card, adSays, price = null, titleId = "case-ledger-title" }: LedgerProps) {
  const count = checkCount(card);
  const groups = groupLines(card);
  const priceLines = card.rows.find((r) => r.kind === "price")?.lines ?? [];
  // The bar sits under the rent comparison; with no such line, under the last price line.
  const priceLine =
    priceLines.find((l) => recordSourceOf(l, card.lang) === "costar") ?? priceLines.at(-1);
  // With no ad words for any line, the two middle columns are one: what the record gave us.
  const hasAd = card.rows.some((row) => row.lines.some((line) => adSays?.(row.kind, line)));
  let index = 0;
  return (
    <section className="case-ledger" aria-labelledby={titleId}>
      <header className="case-sheet-head">
        <h2 id={titleId}>How we know</h2>
        <p className="ui-mono" data-testid="case-set-by">
          {count} {count === 1 ? "CHECK" : "CHECKS"} · SET BY CODE
        </p>
      </header>
      {GROUP_ORDER.map((group) => {
        const entries = groups[group];
        const last = group === "unchecked";
        if (entries.length === 0 && !last) return null;
        return (
          <section key={group} className="case-group-block" data-group={group}>
            <h3 className="case-group-title" data-testid={`group-${group}`}>
              {GROUP_TITLE[group]}
              <span className="ui-mono">
                {last ? entries.length + card.not_checked.length : entries.length}
              </span>
            </h3>
            {entries.length > 0 ? (
              <table className="case-table" data-has-ad={hasAd ? "true" : undefined}>
                <thead>
                  <tr className="ui-mono">
                    <th scope="col">Check</th>
                    {hasAd ? <th scope="col">The ad says</th> : null}
                    <th scope="col">{hasAd ? "The record says" : "What we found"}</th>
                    <th scope="col">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry, i) => (
                    <LedgerRow
                      key={`${entry.row}-${entry.line.label}-${i}`}
                      entry={entry}
                      index={index++}
                      ad={adSays?.(entry.row, entry.line) ?? null}
                      hasAd={hasAd}
                      source={card.source}
                      lang={card.lang}
                      price={price && entry.line === priceLine ? price : null}
                    />
                  ))}
                </tbody>
              </table>
            ) : null}
            {last ? (
              <div className="case-not-checked">
                <ul data-testid="not-checked">
                  {card.not_checked.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <span>No tool can check these from an ad.</span>
              </div>
            ) : null}
          </section>
        );
      })}
    </section>
  );
}
