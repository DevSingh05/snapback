// The ad the renter pasted, quoted on a raised sheet with the risky phrases underlined in their
// state colour, like a proofreader's marks. The text is the renter's own, shown as pasted. A
// phrase is underlined only where it appears word for word; nothing is added or reworded.
import type { ReactNode } from "react";

import "../ui/ui.css";
import "./case.css";
import type { AdMark } from "./model";

const LEGEND: Record<AdMark["kind"], string> = {
  mismatch: "doesn't match the record",
  warn: "a warning sign",
};

interface AnnotatedAdProps {
  text: string;
  marks?: AdMark[];
  // Where the ad came from, as the renter said ("MARKETPLACE"). Left out when not known.
  origin?: string | null;
}

/** The ad cut into plain and underlined runs. The earliest phrase wins; marks never overlap. */
export function markRuns(
  text: string,
  marks: AdMark[],
): { text: string; kind: AdMark["kind"] | null }[] {
  const runs: { text: string; kind: AdMark["kind"] | null }[] = [];
  const lower = text.toLowerCase();
  let at = 0;
  while (at < text.length) {
    let next: { start: number; mark: AdMark } | null = null;
    for (const mark of marks) {
      if (!mark.phrase.trim()) continue;
      const start = lower.indexOf(mark.phrase.toLowerCase(), at);
      if (start >= 0 && (!next || start < next.start)) next = { start, mark };
    }
    if (!next) break;
    if (next.start > at) runs.push({ text: text.slice(at, next.start), kind: null });
    const end = next.start + next.mark.phrase.length;
    runs.push({ text: text.slice(next.start, end), kind: next.mark.kind });
    at = end;
  }
  if (at < text.length) runs.push({ text: text.slice(at), kind: null });
  return runs;
}

export function AnnotatedAd({ text, marks = [], origin }: AnnotatedAdProps) {
  const runs = markRuns(text, marks);
  const kinds = (["mismatch", "warn"] as const).filter((k) => runs.some((r) => r.kind === k));
  const body: ReactNode[] = runs.map((run, i) =>
    run.kind ? (
      <mark key={i} className="case-mark" data-kind={run.kind}>
        {run.text}
      </mark>
    ) : (
      run.text
    ),
  );
  return (
    <aside className="case-ad ui-sheet" aria-label="The ad you pasted" data-testid="case-ad">
      <p className="case-ad-head ui-mono">
        <span>The ad you pasted</span>
        {origin ? <span>{origin}</span> : null}
      </p>
      <blockquote className="case-ad-text">{body}</blockquote>
      {kinds.length > 0 ? (
        <ul className="case-ad-legend">
          {kinds.map((k) => (
            <li key={k} data-kind={k}>
              {LEGEND[k]}
            </li>
          ))}
        </ul>
      ) : null}
    </aside>
  );
}
