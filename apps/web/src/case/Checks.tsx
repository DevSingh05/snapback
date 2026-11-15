// "What checks out and what doesn't": the card's two lists side by side. Every string is one
// the API's code wrote ("label: text"); this file splits it at the first colon for the eye and
// never edits a word. A list the card left out or left empty is a column left out, and with
// neither there is no section.
import "../ui/ui.css";
import "./case.css";
import type { DataSource } from "../contracts";
import { State, Tag } from "../ui";

function Item({ line }: { line: string }) {
  const cut = line.indexOf(": ");
  if (cut < 1) return <li>{line}</li>;
  return (
    <li>
      <b>{line.slice(0, cut)}</b>
      <span>{line.slice(cut + 2)}</span>
    </li>
  );
}

export function Checks({
  checksOut = [],
  doesNot = [],
  source,
  titleId = "case-checks-title",
}: {
  checksOut?: string[] | null;
  doesNot?: string[] | null;
  source: DataSource;
  titleId?: string;
}) {
  const good = checksOut ?? [];
  const bad = doesNot ?? [];
  if (good.length === 0 && bad.length === 0) return null;
  return (
    <section className="case-checks" aria-labelledby={titleId} data-testid="case-checks">
      <header className="case-sheet-head">
        <h2 id={titleId}>What checks out, and what doesn't</h2>
        <Tag source={source} testId="checks-source" />
      </header>
      <div className="case-checks-cols">
        {bad.length > 0 ? (
          <div className="case-checks-col" data-side="does-not" data-testid="checks-does-not">
            <h3>
              <State kind="mismatch">What doesn't</State>
            </h3>
            <ul>
              {bad.map((line) => (
                <Item key={line} line={line} />
              ))}
            </ul>
          </div>
        ) : null}
        {good.length > 0 ? (
          <div className="case-checks-col" data-side="checks-out" data-testid="checks-out">
            <h3>
              <State kind="ok">What checks out</State>
            </h3>
            <ul>
              {good.map((line) => (
                <Item key={line} line={line} />
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}
