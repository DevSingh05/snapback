import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CaseTimeline, TimelineStep } from "../contracts";
import { DraftedStep, draftedStep } from "./NextSteps";

const DRAFT =
  "Before we go further, what is your Texas real estate licence number, and which brokerage sponsors it?";
const LABEL =
  "Planner drafted: ask the poster for their Texas licence number because Allowed to rent it: Not confirmed";

const step = (n: number, over: Partial<TimelineStep> = {}): TimelineStep => ({
  step: n,
  label: `Step ${n}`,
  started_ms: n,
  took_ms: 1,
  result: "Done",
  source: "fixture",
  by: "code",
  ...over,
});
const timeline = (steps: TimelineStep[]): CaseTimeline => ({
  case_id: "AB12",
  source: "fixture",
  mode: "deepagents",
  fell_back: false,
  steps,
  todos: [],
  plan: [],
});
const withDraft = () =>
  timeline([
    step(0),
    step(1, { kind: "followup", label: LABEL, choice: "next_step", draft: DRAFT, by: "agent" }),
  ]);

afterEach(() => vi.restoreAllMocks());

describe("DraftedStep", () => {
  it("shows the Planner's draft with Approve and Edit, and says it is never sent", () => {
    render(<DraftedStep timeline={withDraft()} />);
    const box = screen.getByTestId("drafted-step");
    expect(box).toHaveTextContent(LABEL);
    expect(box).toHaveTextContent(DRAFT);
    expect(box).toHaveTextContent("Drafted by a model · never sent");
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("Approve: Ready, you send it, and Copy puts the draft on the clipboard (nothing is fetched)", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<DraftedStep timeline={withDraft()} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByRole("status")).toHaveTextContent("Ready: you send it");
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(DRAFT));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("Edit: the renter's own words are what get copied", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<DraftedStep timeline={withDraft()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByLabelText("Your next step");
    expect(field).toHaveValue(DRAFT);
    fireEvent.change(field, { target: { value: "  What is your licence number?  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("status")).toHaveTextContent("Ready: you send it");
    expect(screen.getByTestId("drafted-step")).toHaveTextContent("What is your licence number?");
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("What is your licence number?"));
  });

  it("will not save an empty edit, and Cancel keeps the draft", () => {
    render(<DraftedStep timeline={withDraft()} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Your next step"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByTestId("drafted-step")).toHaveTextContent(DRAFT);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("says our rules picked it when code, not a model, chose the step", () => {
    const t = timeline([
      step(1, { kind: "followup", label: LABEL, choice: "next_step", draft: DRAFT, by: "code" }),
    ]);
    render(<DraftedStep timeline={t} />);
    const box = screen.getByTestId("drafted-step");
    expect(box).toHaveTextContent("Picked by our rules · never sent");
    expect(box).not.toHaveTextContent("Drafted by a model");
  });

  it("is not there without a drafted step that has a code draft", () => {
    expect(draftedStep(timeline([step(0)]))).toBeNull();
    expect(draftedStep(timeline([step(1, { choice: "next_step", draft: null })]))).toBeNull();
    const { container } = render(<DraftedStep timeline={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("speaks Spanish on a Spanish report", () => {
    render(<DraftedStep timeline={withDraft()} lang="es" />);
    expect(screen.getByRole("button", { name: "Aprobar" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));
    expect(screen.getByRole("status")).toHaveTextContent("Listo: usted lo envía");
  });
});
