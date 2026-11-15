import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CaseTimeline, TimelineStep } from "../contracts";
import { PlannerChoice, plannerChoices } from "./PlannerChoice";

const step = (n: number, over: Partial<TimelineStep> = {}): TimelineStep => ({
  step: n,
  label: `Step ${n}`,
  started_ms: n * 100,
  took_ms: 100,
  result: "Done",
  source: "fixture",
  by: "code",
  ...over,
});

const timeline = (steps: TimelineStep[], running = false): CaseTimeline => ({
  case_id: "AB12",
  source: "fixture",
  mode: "deepagents",
  fell_back: false,
  running,
  steps,
  todos: [],
  plan: [],
});

const CHOSE = "Planner chose: Google Lens search of the ad's photos because Here now: Not checked";

describe("PlannerChoice", () => {
  it("shows nothing when code, not a model, picked the follow-up", () => {
    const t = timeline([
      step(1, { kind: "followup", label: CHOSE, choice: "follow_up", by: "code" }),
    ]);
    const { container } = render(<PlannerChoice caseId="AB12" timeline={t} />);
    expect(container).toBeEmptyDOMElement();
    expect(plannerChoices(t)).toEqual([]);
  });

  it("shows the Planner's follow-up choice in the timeline's words, linked to the trace", () => {
    const t = timeline([
      step(0),
      step(1, { kind: "followup", by: "agent", label: CHOSE, choice: "follow_up" }),
      step(2, { kind: "followup", label: "Follow-up check" }),
      step(3, {
        kind: "followup",
        label: "Planner drafted: ask for a licence",
        choice: "next_step",
      }),
    ]);
    render(<PlannerChoice caseId="AB12" timeline={t} />);
    const box = screen.getByTestId("planner-choice");
    expect(box).toHaveTextContent(CHOSE);
    expect(box).toHaveTextContent("Chosen by a model · code set the result");
    expect(box).not.toHaveTextContent("Follow-up check");
    expect(box).not.toHaveTextContent("Planner drafted");
    expect(screen.getByRole("link", { name: "See how it chose" })).toHaveAttribute(
      "href",
      "/case/AB12/trace",
    );
  });

  it("is not there when the Planner chose nothing, or before the timeline lands", () => {
    const { rerender } = render(<PlannerChoice caseId="AB12" timeline={timeline([step(0)])} />);
    expect(screen.queryByTestId("planner-choice")).toBeNull();
    rerender(<PlannerChoice caseId="AB12" timeline={null} />);
    expect(screen.queryByTestId("planner-choice")).toBeNull();
  });

  it("speaks Spanish on a Spanish report", () => {
    const t = timeline([
      step(1, { label: "El planificador eligió: X porque Y", choice: "follow_up", by: "agent" }),
    ]);
    render(<PlannerChoice caseId="AB12" timeline={t} lang="es" />);
    expect(screen.getByRole("link", { name: "Ver cómo eligió" })).toBeInTheDocument();
  });

  it("finds choices by field, never by label", () => {
    const t = timeline([
      step(1, { label: CHOSE }),
      step(2, { label: "x", choice: "follow_up", by: "agent" }),
    ]);
    expect(plannerChoices(t).map((s) => s.step)).toEqual([2]);
  });
});
