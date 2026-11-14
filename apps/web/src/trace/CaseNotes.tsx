import { useEffect, useState } from "react";

import { apiFetchRead } from "../api";
import type { CaseNote, CaseNotes as CaseNotesBody, TraceEvent } from "../contracts";

const AGENT_LABELS: Record<string, string> = {
  record: "Record sub-agent",
  "office-and-licence": "Office and licence sub-agent",
  owner: "Owner sub-agent",
  place: "Place sub-agent",
  search: "Search sub-agent",
  main: "Main agent",
};

// Reload the notes when a note was just written or the case reached its result.
function changeMark(events: TraceEvent[]): string {
  const last = events.at(-1);
  if (!last) return "";
  return last.kind === "verdict" || last.pick?.startsWith("file: ") ? String(last.seq) : "";
}

/** The files the agent wrote for this case, read-only: derived text only, never images. */
export function CaseNotes({ caseId, events }: { caseId: string; events: TraceEvent[] }) {
  const [notes, setNotes] = useState<CaseNote[]>([]);
  const mark = changeMark(events);

  useEffect(() => {
    if (!mark) return;
    const ctl = new AbortController();
    const pending = apiFetchRead(`/cases/${encodeURIComponent(caseId)}/notes`, caseId, {
      signal: ctl.signal,
    });
    if (!pending) return;
    pending
      .then((res) => (res.ok ? (res.json() as Promise<CaseNotesBody>) : null))
      .then((body) => body && setNotes(body.notes))
      .catch(() => undefined);
    return () => ctl.abort();
  }, [caseId, mark]);

  if (notes.length === 0) return null;
  return (
    <section className="case-notes" aria-label="Notes the agent wrote" data-testid="case-notes">
      <h3>Notes the agent wrote</h3>
      <p className="trace-judge">
        Working notes in the agent's file system. They never change the result on the card.
      </p>
      <ul className="case-notes-list">
        {notes.map((n) => (
          <li key={n.path} data-testid="case-note" data-by={n.written_by}>
            <div className="trace-head">
              <span className="trace-title">{AGENT_LABELS[n.agent] ?? n.agent}</span>
              <span className="mono trace-by">
                {n.written_by === "model" ? "written by model" : "written by code"}
              </span>
            </div>
            <p className="mono">{n.path}</p>
            <pre className="case-note-text">{n.text}</pre>
          </li>
        ))}
      </ul>
    </section>
  );
}
