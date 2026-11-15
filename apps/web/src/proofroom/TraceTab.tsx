// "See how it worked": the deep agent's depth, as a short vertical story a renter can read.
// One card per member with the same mark and state colour as the graph: what ran it, what it
// was asked, the tools it called in order with one plain line each, what it said back, its
// time and model calls. The Planner's card carries its to-do list and who it sent work to.
// A member no model ran says so: code checked it. "Replay" steps through the cards one line
// at a time; lines not yet reached keep their room, so nothing moves. The raw trace stays
// under "Agent trace, raw" for anyone who wants every event.
import { useEffect, useRef, useState } from "react";

import "./proofroom.css";
import { tookText } from "../case/answer";
import { Avatar } from "./Avatar";
import type { Lang } from "./model";
import { revealed, safeTraceUrl, traceLength, type TraceCard } from "./trace";
import type { RoomWords } from "./words";

export const STEP_MS = 520;

function Card({
  card,
  index,
  cards,
  at,
  lang,
  w,
  focused,
}: {
  card: TraceCard;
  index: number;
  cards: TraceCard[];
  at: number;
  lang: Lang;
  w: RoomWords;
  focused: boolean;
}) {
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (!focused) return;
    ref.current?.focus();
    ref.current?.scrollIntoView?.({ block: "nearest" });
  }, [focused]);
  const on = (step: number) => revealed(cards, index, step, at);
  const all = on(card.steps.length - 1);
  return (
    <li
      ref={ref}
      id={`trace-${card.deskId}`}
      className="pr-trace-card pr-node"
      data-state={card.state}
      data-tone={card.tone}
      data-agent={card.deskId}
      data-shown={on(-1) ? "yes" : "no"}
      data-testid="trace-card"
      tabIndex={-1}
      aria-hidden={on(-1) ? undefined : true}
    >
      <div className="pr-trace-mark">
        <Avatar id={card.deskId} />
      </div>
      <div className="pr-trace-body">
        <header className="pr-trace-head">
          <h4>{card.name}</h4>
          <span className="pr-model ui-mono" data-testid="trace-model">
            {card.byModel ? card.model : w.code}
          </span>
        </header>
        <p className="pr-trace-meta ui-mono" data-testid="trace-meta">
          {card.tookMs !== null ? <span>{tookText(card.tookMs, lang)}</span> : null}
          <span>{card.modelCalls === null ? w.noModelCalls : w.modelCalls(card.modelCalls)}</span>
        </p>
        {card.byModel ? null : (
          <p className="pr-trace-code" data-testid="trace-code">
            {w.noModel}
          </p>
        )}
        {card.asked ? (
          <p className="pr-trace-asked">
            <span className="ui-mono">{w.asked}</span> {card.asked}
          </p>
        ) : null}
        {card.todos.length > 0 ? (
          <div className="pr-trace-plan" data-testid="trace-plan">
            <p className="ui-mono">{w.planTitle}</p>
            <ul>
              {card.todos.map((todo, i) => (
                <li key={`${todo.content}-${i}`} data-done={todo.done ? "yes" : "no"}>
                  <span aria-hidden="true">{todo.done ? "✓" : "○"}</span> {todo.content}
                  <span className="sr-only"> ({todo.done ? w.state.done : w.state.idle})</span>
                </li>
              ))}
            </ul>
            {card.sentTo.length > 0 ? (
              <p className="pr-trace-sent">
                <span className="ui-mono">{w.sentTo}</span> {card.sentTo.join(", ")}
              </p>
            ) : null}
          </div>
        ) : null}
        {card.steps.length > 0 ? (
          <ol className="pr-trace-steps">
            {card.steps.map((step, i) => (
              <li
                key={`${step.label}-${i}`}
                data-shown={on(i) ? "yes" : "no"}
                data-testid="trace-step"
                aria-hidden={on(i) ? undefined : true}
              >
                <span className="pr-trace-did">{step.label}</span>
                {step.result ? <span className="pr-trace-got">{step.result}</span> : null}
              </li>
            ))}
          </ol>
        ) : null}
        <div
          className="pr-trace-end"
          data-shown={all ? "yes" : "no"}
          aria-hidden={all ? undefined : true}
        >
          {card.said ? (
            <p className="pr-trace-said" data-testid="trace-said">
              <span className="ui-mono">{w.said}</span> {card.said}
            </p>
          ) : null}
          {card.findings.map((f) => (
            <p className="pr-trace-found" key={`${f.label}-${f.text}`} data-testid="trace-finding">
              {f.label ? <b>{f.label}: </b> : null}
              {f.text}
            </p>
          ))}
        </div>
      </div>
    </li>
  );
}

export function TraceTab({
  cards,
  lang,
  w,
  focus,
  traceUrl,
  reduced,
}: {
  cards: TraceCard[];
  lang: Lang;
  w: RoomWords;
  focus: string | null;
  traceUrl?: string | null;
  reduced: boolean;
}) {
  const total = traceLength(cards);
  // Infinity: everything on show. A replay counts up from 0, one card or step at a time.
  const [at, setAt] = useState(Infinity);
  const playing = at < total;
  useEffect(() => {
    if (!playing) return;
    const timer = setTimeout(() => setAt((n) => (n + 1 >= total ? Infinity : n + 1)), STEP_MS);
    return () => clearTimeout(timer);
  }, [at, playing, total]);
  const link = safeTraceUrl(traceUrl);
  if (cards.length === 0) return <p className="pr-quiet">{w.rest}</p>;
  return (
    <div className="pr-trace" data-testid="trace-tab" data-playing={playing ? "yes" : "no"}>
      <p className="pr-note">{w.traceLede}</p>
      <div className="pr-controls">
        <button
          type="button"
          className="pr-btn"
          onClick={() => setAt(reduced ? Infinity : 0)}
          data-testid="trace-replay"
        >
          {w.traceReplay}
        </button>
        <button
          type="button"
          className="pr-btn pr-btn-quiet"
          onClick={() => setAt(Infinity)}
          disabled={!playing}
          aria-label={w.skip}
        >
          {w.skipShort}
        </button>
        {link ? (
          <a
            className="pr-trace-out"
            href={link}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="trace-langsmith"
          >
            {w.langsmith} <span aria-hidden="true">↗</span>
          </a>
        ) : null}
      </div>
      <ol className="pr-trace-list">
        {cards.map((card, i) => (
          <Card
            key={card.deskId}
            card={card}
            index={i}
            cards={cards}
            at={at}
            lang={lang}
            w={w}
            focused={focus === card.deskId}
          />
        ))}
      </ol>
      <p className="pr-note">{w.traceRaw}</p>
    </div>
  );
}
