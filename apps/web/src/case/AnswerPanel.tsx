// "How we got this answer", as a thread (SNAPBACK lives in iMessage). Each check is a message
// from its own agent: the finding the report already holds for it, with the LIVE or FIXTURE chip
// and the time in the footer. Red-flag messages come first, then hold, then ok. Checks the plan
// left out are one quiet line. The last message is SNAPBACK's: the verdict in the card's own
// words and the reasons, each a link that jumps to the message behind it. The deep agent's plan
// and to-do list sit in a closed "Planner" message at the top. No timeline, an empty one or a
// failed read: the panel is not there and the report stands as it was.
import "../ui/ui.css";
import "./case.css";
import type { Card, CaseTimeline, RealListing } from "../contracts";
import { Tag } from "../ui";
import { answerView, tookText, type CheckId } from "./answer";

const WORDS = {
  en: {
    title: "How we got this answer",
    lede: "Each check is a message from the agent that ran it. Code, not a model, works out the result.",
    agent: {
      record: "Record agent",
      photos: "Photo agent",
      rules: "Rules agent",
      phone: "Phone agent",
      owner: "Owner and licence agent",
      forsale: "For-sale agent",
    },
    short: {
      record: "Record",
      photos: "Photos",
      rules: "Rules",
      phone: "Phone and office",
      owner: "Owner and licence",
      forsale: "For sale",
    },
    notChecked: "Not checked",
    snapback: "SNAPBACK",
    because: "Because",
    from: "See",
    planner: "Planner",
    plan: "Plan and to-do list",
    handed: "Handed to sub-agents",
    done: "Done",
    open: "Not done",
    fellBack: "The agent stopped, so code finished the checks.",
  },
  es: {
    title: "Cómo llegamos a esta respuesta",
    lede: "Cada comprobación es un mensaje del agente que la hizo. El código, no un modelo, calcula el resultado.",
    agent: {
      record: "Agente del registro",
      photos: "Agente de fotos",
      rules: "Agente de reglas",
      phone: "Agente del teléfono",
      owner: "Agente de propietario y licencia",
      forsale: "Agente de venta",
    },
    short: {
      record: "Registro",
      photos: "Fotos",
      rules: "Reglas",
      phone: "Teléfono y oficina",
      owner: "Propietario y licencia",
      forsale: "En venta",
    },
    notChecked: "No comprobado",
    snapback: "SNAPBACK",
    because: "Porque",
    from: "Ver",
    planner: "Planificador",
    plan: "Plan y lista de tareas",
    handed: "Encargado a subagentes",
    done: "Hecho",
    open: "Pendiente",
    fellBack: "El agente se detuvo, así que el código terminó las comprobaciones.",
  },
} as const;

export function AnswerPanel({
  card,
  timeline,
  realListing = null,
  idSuffix = "",
}: {
  card: Card;
  timeline: CaseTimeline | null;
  realListing?: RealListing | null;
  idSuffix?: string;
}) {
  const view = answerView(card, timeline, realListing);
  if (!view || !timeline) return null;
  const lang = card.lang === "es" ? "es" : "en";
  const w = WORDS[lang];
  const titleId = `case-answer-title${idSuffix}`;
  const bubbleId = (check: CheckId) => `answer-${check}${idSuffix}`;
  const deep =
    timeline.mode === "deepagents" && (timeline.todos.length > 0 || timeline.plan.length > 0);
  return (
    <section className="case-answer" aria-labelledby={titleId} data-testid="case-answer">
      <header className="case-sheet-head">
        <h2 id={titleId}>{w.title}</h2>
        <Tag source={timeline.source} testId="answer-source" />
      </header>
      <p className="case-answer-lede">{w.lede}</p>

      <div className="case-thread">
        {deep ? (
          <div className="case-msg" data-testid="answer-plan-msg">
            <p className="case-msg-from ui-mono">{w.planner}</p>
            <details className="case-bubble" data-tone="none" data-testid="answer-plan">
              <summary>{w.plan}</summary>
              {timeline.plan.length > 0 ? (
                <>
                  <p className="case-msg-from ui-mono">{w.handed}</p>
                  <ul>
                    {timeline.plan.map((name, i) => (
                      <li key={`${name}-${i}`}>{name}</li>
                    ))}
                  </ul>
                </>
              ) : null}
              {timeline.todos.length > 0 ? (
                <ul className="case-answer-todos">
                  {timeline.todos.map((todo, i) => (
                    <li key={`${todo.content}-${i}`} data-done={todo.done ? "yes" : "no"}>
                      <span aria-hidden="true">{todo.done ? "✓" : "○"}</span> {todo.content}{" "}
                      <span className="sr-only">({todo.done ? w.done : w.open})</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </details>
          </div>
        ) : null}

        {view.bubbles.map((b) => (
          <div className="case-msg" key={b.check}>
            <p className="case-msg-from ui-mono">{w.agent[b.check]}</p>
            <div
              id={bubbleId(b.check)}
              className="case-bubble"
              data-tone={b.tone}
              data-testid="answer-bubble"
              data-check={b.check}
            >
              <ul>
                {b.findings.map((f) => (
                  <li key={`${f.label}-${f.text}`}>
                    {f.label ? <b>{f.label}: </b> : null}
                    {f.text}
                  </li>
                ))}
              </ul>
              <p className="case-bubble-foot ui-mono">
                <Tag source={b.source} testId="answer-bubble-source" />
                {b.tookMs !== null ? <span>{tookText(b.tookMs, lang)}</span> : null}
              </p>
            </div>
          </div>
        ))}

        {view.notChecked.length > 0 ? (
          <p className="case-thread-note" data-testid="answer-not-checked">
            {w.notChecked}:{" "}
            {view.notChecked.map((n) => `${w.short[n.check]}: ${n.text}`).join(" · ")}
          </p>
        ) : null}
        {timeline.fell_back ? <p className="case-thread-note">{w.fellBack}</p> : null}

        <div className="case-msg case-msg-out" data-testid="answer-verdict">
          <p className="case-msg-from ui-mono">{w.snapback}</p>
          <div className="case-bubble case-bubble-out" data-tone="none">
            <p className="case-answer-headline">{view.verdict}</p>
            {view.reasons.length > 0 ? (
              <>
                <p className="case-msg-from ui-mono">{w.because}</p>
                <ul className="case-answer-reasons">
                  {view.reasons.map((reason) => (
                    <li
                      key={reason.text}
                      data-testid="answer-reason"
                      data-linked={reason.bubbleId ? "yes" : "no"}
                    >
                      <span>{reason.text}</span>
                      {reason.bubbleId ? (
                        <a
                          className="case-text-link"
                          href={`#${bubbleId(reason.bubbleId)}`}
                          data-testid="answer-reason-link"
                        >
                          {w.from} {w.agent[reason.bubbleId]} <span aria-hidden="true">↑</span>
                        </a>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
