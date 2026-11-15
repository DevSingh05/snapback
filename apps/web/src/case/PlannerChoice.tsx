// The Planner's choice, on the report: which follow-up check the model picked for which gap on the
// card, in the timeline's own words, linked to the trace that shows how it chose. Information
// only: code set the verdict before the Planner ran, and nothing here can change it.
import type { CaseTimeline, TimelineStep } from "../contracts";
import type { Lang } from "../lang";

/** The Planner's follow-up choices in a timeline, oldest first. Empty when it chose none. */
export function plannerChoices(timeline: CaseTimeline | null | undefined): TimelineStep[] {
  if (!timeline || !Array.isArray(timeline.steps)) return [];
  return timeline.steps.filter((s) => s.choice === "follow_up");
}

const WORDS = {
  en: {
    title: "The Planner's choice",
    by: "Chosen by a model · code set the result",
    how: "See how it chose",
  },
  es: {
    title: "La elección del planificador",
    by: "Elegido por un modelo · el código fijó el resultado",
    how: "Ver cómo eligió",
  },
};

export function PlannerChoice({
  caseId,
  timeline,
  lang = "en",
}: {
  caseId: string;
  timeline: CaseTimeline | null | undefined;
  lang?: Lang;
}) {
  const choices = plannerChoices(timeline);
  if (choices.length === 0) return null;
  const w = WORDS[lang === "es" ? "es" : "en"];
  return (
    <section className="case-planner" aria-label={w.title} data-testid="planner-choice">
      <p className="case-planner-by ui-mono">{w.by}</p>
      <ul className="case-planner-list">
        {choices.map((s) => (
          <li key={s.step}>{s.label}</li>
        ))}
      </ul>
      <a className="case-text-link" href={`/case/${encodeURIComponent(caseId)}/trace`}>
        {w.how}
      </a>
    </section>
  );
}
