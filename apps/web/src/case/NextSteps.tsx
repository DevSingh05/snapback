// "What to do now": the three steps after a result, as columns on one rule. Every action here is
// quiet; the page's one primary button lives in the verdict band.
import { useState } from "react";

import "../ui/ui.css";
import "./case.css";
import type { CaseTimeline, TimelineStep } from "../contracts";

export interface NextStep {
  // "02", "03", "04": the step's number on the path rail.
  n: string;
  title: string;
  text: string;
  action: { label: string; href: string };
  // A second action under the first. `external` opens in a new tab.
  more?: { label: string; href: string; external?: boolean };
}

// The hand-off when a case does not pass: CoStar's own rental site. The API gives no listing
// address for it, so this is the site's Houston search page, and the label says it is a search.
export const APARTMENTS_SEARCH = {
  label: "Search listings on Apartments.com",
  href: "https://www.apartments.com/houston-tx/",
  external: true,
} as const;

/** The usual three steps for a case. `walk` is false when no photo was placed in a home;
 *  `passed` is false when the case did not pass, which adds the Apartments.com hand-off. */
export function caseSteps(
  caseId: string,
  walk: boolean,
  saferHref = "/finder",
  passed = false,
): NextStep[] {
  const id = encodeURIComponent(caseId);
  return [
    {
      n: "02",
      title: "Walk it first",
      text: walk
        ? "See the real rooms, with the ad's photos placed where they were taken."
        : "See the rooms on record for this home, if it has a 3D scan.",
      action: { label: "Walk it first", href: `/case/${id}/twin` },
    },
    {
      n: "03",
      title: "Find safer places",
      text: passed
        ? "Researched homes like this one, picked by our rules."
        : "Researched homes like this one, picked by our rules. Or start again on Apartments.com, CoStar's rental site.",
      action: { label: "Find me safer places like this", href: saferHref },
      more: passed ? undefined : APARTMENTS_SEARCH,
    },
    {
      n: "04",
      title: "Ask for a tour",
      text: "For a place that passes. We draft it; you send it.",
      action: { label: "Draft a tour request", href: `/case/${id}/prep` },
    },
  ];
}

interface NextStepsProps {
  steps: NextStep[];
  // Which step is next (its `n`); it carries the word NEXT.
  next?: string | null;
  titleId?: string;
}

export function NextSteps({ steps, next = "02", titleId = "case-next-title" }: NextStepsProps) {
  return (
    <section className="case-next" aria-labelledby={titleId}>
      <h2 id={titleId}>What to do now</h2>
      <ol className="case-next-steps">
        {steps.map((step) => (
          <li key={step.n} data-next={step.n === next ? "true" : undefined}>
            <p className="ui-mono">{step.n === next ? `${step.n} · NEXT` : step.n}</p>
            <h3>{step.title}</h3>
            <p className="case-next-text">{step.text}</p>
            <a className="ui-btn-quiet" href={step.action.href}>
              {step.action.label}
            </a>
            {step.more ? (
              <a
                className="ui-btn-quiet case-next-more"
                href={step.more.href}
                data-testid="case-handoff"
                {...(step.more.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
              >
                {step.more.label}
                {step.more.external ? <span aria-hidden="true"> ↗</span> : null}
              </a>
            ) : null}
          </li>
        ))}
      </ol>
    </section>
  );
}

/** The Planner's drafted next step with a code-written draft, or null. */
export function draftedStep(timeline: CaseTimeline | null | undefined): TimelineStep | null {
  if (!timeline || !Array.isArray(timeline.steps)) return null;
  return timeline.steps.find((s) => s.choice === "next_step" && !!s.draft?.trim()) ?? null;
}

const DRAFT_WORDS = {
  en: {
    title: "A next step, drafted for you",
    by: "Drafted by a model · never sent",
    approve: "Approve",
    edit: "Edit",
    save: "Save",
    cancel: "Cancel",
    ready: "Ready: you send it",
    readyNote: "SNAPBACK never sends it. Copy it and send it yourself.",
    copy: "Copy",
    copied: "Copied",
    field: "Your next step",
  },
  es: {
    title: "Un próximo paso, redactado para usted",
    by: "Redactado por un modelo · nunca enviado",
    approve: "Aprobar",
    edit: "Editar",
    save: "Guardar",
    cancel: "Cancelar",
    ready: "Listo: usted lo envía",
    readyNote: "SNAPBACK nunca lo envía. Cópielo y envíelo usted.",
    copy: "Copiar",
    copied: "Copiado",
    field: "Su próximo paso",
  },
};

// The Planner's drafted next step: the renter approves it as is or edits it, then copies it and
// sends it themselves. Nothing here sends anything or calls the API; the text stays on this page.
export function DraftedStep({
  timeline,
  lang = "en",
  titleId = "case-draft-title",
}: {
  timeline: CaseTimeline | null | undefined;
  lang?: "en" | "es";
  titleId?: string;
}) {
  const step = draftedStep(timeline);
  const w = DRAFT_WORDS[lang === "es" ? "es" : "en"];
  const [mode, setMode] = useState<"draft" | "edit" | "ready">("draft");
  const [text, setText] = useState<string | null>(null);
  const [edit, setEdit] = useState("");
  const [copied, setCopied] = useState(false);
  if (!step) return null;
  const current = text ?? step.draft ?? "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(current);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <section className="case-draft" aria-labelledby={titleId} data-testid="drafted-step">
      <h2 id={titleId}>{w.title}</h2>
      <p className="case-draft-by ui-mono">{w.by}</p>
      <p className="case-draft-why">{step.label}</p>
      {mode === "edit" ? (
        <>
          <label className="case-draft-label" htmlFor={`${titleId}-field`}>
            {w.field}
          </label>
          <textarea
            id={`${titleId}-field`}
            className="case-draft-field"
            value={edit}
            rows={4}
            onChange={(e) => setEdit(e.target.value)}
          />
          <div className="case-draft-actions">
            <button
              type="button"
              className="case-draft-primary"
              disabled={!edit.trim()}
              onClick={() => {
                setText(edit.trim());
                setCopied(false);
                setMode("ready");
              }}
            >
              {w.save}
            </button>
            <button
              type="button"
              className="ui-btn-quiet"
              onClick={() => setMode(text ? "ready" : "draft")}
            >
              {w.cancel}
            </button>
          </div>
        </>
      ) : (
        <>
          <blockquote className="case-draft-text">{current}</blockquote>
          {mode === "ready" ? (
            <div className="case-draft-ready" role="status">
              <p className="case-draft-ready-title">{w.ready}</p>
              <p className="case-draft-ready-note">{w.readyNote}</p>
            </div>
          ) : null}
          <div className="case-draft-actions">
            {mode === "ready" ? (
              <button type="button" className="case-draft-primary" onClick={copy}>
                {copied ? w.copied : w.copy}
              </button>
            ) : (
              <button type="button" className="case-draft-primary" onClick={() => setMode("ready")}>
                {w.approve}
              </button>
            )}
            <button
              type="button"
              className="ui-btn-quiet"
              onClick={() => {
                setEdit(current);
                setMode("edit");
              }}
            >
              {w.edit}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
