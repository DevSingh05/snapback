import { useEffect, useState } from "react";

import { SourceChip } from "../components/SourceChip";
import type { ChoiceKind, DataSource, TraceEvent } from "../contracts";
import traceRaw from "../../../../fixtures/contracts/trace_events.jsonl?raw";
import { mergeEvent, parseFixtureLines } from "./parse";
import { apiBase, loadCaseReadToken } from "../api";
import { openLiveTrace, openReplayTrace, type StreamStatus } from "./stream";

export const CHOICE_LABELS: Record<ChoiceKind, string> = {
  which_checks: "Which checks to run",
  which_floor_plan: "Which floor plan",
  which_spot: "Which spot",
  retry_or_stop: "Retry or stop",
  ask_human: "Ask the human",
  next_check: "Which check next",
};

const KIND_LABELS: Record<TraceEvent["kind"], string> = {
  choice: "Choice",
  tool: "Tool",
  status: "Status",
  hitl: "Your OK",
  verdict: "Verdict",
  error: "Error",
};

const STATUS_TEXT: Record<StreamStatus, string> = {
  connecting: "Connecting",
  live: "Streaming",
  reconnecting: "Reconnecting",
  lost: "Connection lost",
  locked: "Locked: this trace needs the case link",
  done: "Done",
};

export const fixtureTrace: TraceEvent[] = parseFixtureLines(traceRaw);

export type TraceMode = "auto" | "live" | "replay" | "static";

export interface TracePanelProps {
  caseId: string;
  /** auto: live when VITE_API_URL is set, otherwise fixture replay. static: render initialEvents only. */
  mode?: TraceMode;
  initialEvents?: TraceEvent[];
  replaySource?: TraceEvent[];
}

function timeOf(at: string): string {
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : d.toLocaleTimeString([], { hour12: false });
}

export function isWaitingForHuman(events: TraceEvent[]): boolean {
  const last = events.at(-1);
  return last?.kind === "hitl" && !last.pick;
}

// The spot is a random draw: neither the model nor a rule picks it.
function byLabel(event: TraceEvent): string {
  if (event.choice === "which_spot") return "random draw";
  return event.chosen_by === "model" ? "picked by model" : "picked by rules";
}

export function TraceLine({ event }: { event: TraceEvent }) {
  const isChoice = event.kind === "choice" || (event.kind === "hitl" && !!event.choice);
  const title = event.choice ? CHOICE_LABELS[event.choice] : KIND_LABELS[event.kind];
  return (
    <li
      className={`trace-line trace-${event.kind}${isChoice ? " trace-choice" : ""}`}
      data-testid="trace-line"
      data-seq={event.seq}
      data-kind={event.kind}
      data-choice={event.choice ?? undefined}
    >
      <div className="trace-head">
        <span className="trace-title">{title}</span>
        {event.kind === "choice" && (
          <span className="mono trace-by" data-testid="trace-by" data-by={event.chosen_by}>
            {byLabel(event)}
          </span>
        )}
        <span className="mono trace-time">{timeOf(event.at)}</span>
      </div>
      {event.options.length > 0 && (
        <ul className="trace-options" aria-label="Options considered">
          {event.options.map((o) => (
            <li
              key={o}
              data-testid="trace-option"
              className={o === event.pick ? "trace-option picked" : "trace-option"}
            >
              {o}
            </li>
          ))}
        </ul>
      )}
      {event.pick && (
        <p className="trace-pickline">
          {event.kind === "verdict" ? "Result: " : event.kind === "tool" ? "Tool: " : "Picked: "}
          <span className="mono" data-testid="trace-pick">
            {event.pick}
          </span>
        </p>
      )}
      <p className="trace-reason">{event.reason}</p>
    </li>
  );
}

export function TracePanel({
  caseId,
  mode = "auto",
  initialEvents = [],
  replaySource,
}: TracePanelProps) {
  const [events, setEvents] = useState<TraceEvent[]>(() =>
    initialEvents.reduce<TraceEvent[]>(mergeEvent, []),
  );
  const [status, setStatus] = useState<StreamStatus>(mode === "static" ? "done" : "connecting");

  const base = apiBase();
  const resolved: Exclude<TraceMode, "auto"> = mode === "auto" ? (base ? "live" : "replay") : mode;

  useEffect(() => {
    if (resolved === "static") return;
    const add = (e: TraceEvent) => setEvents((list) => mergeEvent(list, e));
    if (resolved === "live" && base)
      return openLiveTrace(base, caseId, add, setStatus, loadCaseReadToken(caseId));
    const source = replaySource ?? fixtureTrace.map((e) => ({ ...e, case_id: caseId }));
    return openReplayTrace(source, add, setStatus);
  }, [caseId, resolved, base, replaySource]);

  const source: DataSource = events.at(-1)?.source ?? (resolved === "live" ? "live" : "fixture");
  const waiting = isWaitingForHuman(events);

  return (
    <section className="trace-panel" aria-label="Agent trace" data-testid="trace-panel">
      <header className="trace-panel-head">
        <h2>What the agent chose</h2>
        <SourceChip source={source} />
      </header>
      <p className="trace-judge">
        The agent decides what to check next. The code decides what the card says.
      </p>
      {waiting && (
        <p className="trace-waiting" data-testid="trace-waiting" role="status">
          Waiting for your OK before anything is sent.
        </p>
      )}
      <ol className="trace-list" aria-live="polite">
        {events.map((e) => (
          <TraceLine key={e.seq} event={e} />
        ))}
      </ol>
      <p className="trace-status mono" data-testid="trace-status">
        {STATUS_TEXT[status]}
      </p>
    </section>
  );
}
