// "See how it worked": a card per member from the API's own trace, a plain "code checked it"
// card where no model ran, a replay that reveals one line at a time, and a LangSmith link that
// can never carry a token.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CaseTimeline } from "../contracts";
import { bundledRoster, floorAt, teamView } from "./model";
import { deepCard, deepTimeline, sampleCard, sampleTimeline } from "./sample";
import deepSample from "./deepSample.json";
import { TeamPanel } from "./TeamPanel";
import { revealed, safeTraceUrl, traceCards, traceLength } from "./trace";
import { STEP_MS, TraceTab } from "./TraceTab";
import type { Run } from "./useRun";
import { WORDS } from "./words";

const roster = bundledRoster("en");
const w = WORDS.en;

function cardsFor(card: typeof deepCard, timeline: CaseTimeline) {
  const whole = floorAt({ roster, card, timeline });
  return traceCards(roster, teamView(whole, whole), timeline);
}
const deep = cardsFor(deepCard, deepTimeline);
const policy = cardsFor(sampleCard, sampleTimeline);
const of = (cards: typeof deep, id: string) => cards.find((c) => c.deskId === id)!;
const deepRun: Run = { status: "ready", card: deepCard, timeline: deepTimeline, listing: null };

afterEach(() => vi.useRealTimers());

describe("the deep-agent sample", () => {
  it("is a fixture, in the API's own shape, with nothing a renter should not see", () => {
    expect(deepTimeline.source).toBe("fixture");
    expect(deepCard.source).toBe("fixture");
    expect(deepTimeline.mode).toBe("deepagents");
    const members = (deepTimeline.members ?? [])
      .flatMap((m) => [m.asked, m.said, ...m.tools.flatMap((t) => [t.label, t.result])])
      .join(" | ");
    expect(members.length).toBeGreaterThan(200);
    expect(members).not.toMatch(/\d{3}\D{0,2}\d{3}\D?\d{4}/);
    expect(members).not.toMatch(/\$\s?\d/);
    expect(members).not.toMatch(/\d{3,}/);
    expect(JSON.stringify(deepSample)).not.toMatch(/token|api[_-]?key|secret/i);
  });
});

describe("trace cards", () => {
  it("come in the team's order: the Planner, the members as they acted, the Decider", () => {
    expect(deep[0]!.deskId).toBe("planner");
    expect(deep.at(-1)!.deskId).toBe("decider");
    expect(new Set(deep.map((c) => c.deskId)).size).toBe(deep.length);
  });

  it("a member the model ran shows what it was asked, its tools in order, and what it said", () => {
    const record = of(deep, "record");
    expect(record.byModel).toBe(true);
    expect(record.model).toBe("Claude Haiku");
    expect(record.asked).toContain("CoStar's record");
    expect(record.steps.map((s) => s.tool)).toEqual(["read_record_facts", "write_file"]);
    expect(record.steps[0]!.label).toContain("CoStar's record");
    expect(record.steps[0]!.result).toBeTruthy();
    expect(record.said).toContain("record");
    expect(record.modelCalls).toBe(3);
    expect(record.tookMs).toBeGreaterThan(0);
  });

  it("the Planner's card carries the plan it wrote and who it sent work to", () => {
    const planner = of(deep, "planner");
    expect(planner.model).toBe("Claude Sonnet");
    expect(planner.asked).toBeNull();
    expect(planner.todos.map((t) => t.done)).toEqual([true, true, true]);
    expect(planner.sentTo).toEqual([
      "Record agent",
      "Phone and office agent",
      "Owner and licence agent",
      "Photo agent",
      "Finder",
    ]);
    expect(planner.steps.filter((s) => s.tool === "task")).toHaveLength(5);
  });

  it("a member no model ran is a code card with the timeline's own steps and no model calls", () => {
    const rules = of(deep, "rules");
    expect(rules.byModel).toBe(false);
    expect(rules.model).toBe("code");
    expect(rules.asked).toBeNull();
    expect(rules.said).toBeNull();
    expect(rules.modelCalls).toBeNull();
    expect(rules.findings.length).toBeGreaterThan(0);
    expect(of(deep, "decider").byModel).toBe(false);
  });

  it("with the policy every card is a code card", () => {
    expect(policy.length).toBeGreaterThan(4);
    expect(policy.every((c) => !c.byModel && c.modelCalls === null && c.asked === null)).toBe(true);
    expect(of(policy, "photo").steps.map((s) => s.label)).toEqual([
      "Placed 3 of 3 photos in its 3D scan",
      "Checked the photo that came back",
    ]);
    expect(
      traceCards(
        roster,
        teamView(
          floorAt({ roster, card: null, timeline: null }),
          floorAt({ roster, card: null, timeline: null }),
        ),
        null,
      ),
    ).toEqual([]);
  });

  it("a replay reveals each card, then each of its steps, one at a time", () => {
    const total = traceLength(deep);
    expect(total).toBe(deep.reduce((n, c) => n + 1 + c.steps.length, 0));
    expect(revealed(deep, 0, -1, 0)).toBe(false);
    expect(revealed(deep, 0, -1, 1)).toBe(true);
    expect(revealed(deep, 0, 0, 1)).toBe(false);
    expect(revealed(deep, 0, 0, 2)).toBe(true);
    expect(revealed(deep, 1, -1, 1 + deep[0]!.steps.length)).toBe(false);
    expect(revealed(deep, 1, -1, 2 + deep[0]!.steps.length)).toBe(true);
    expect(revealed(deep, deep.length - 1, deep.at(-1)!.steps.length - 1, Infinity)).toBe(true);
  });

  it("only a plain https LangSmith page is ever linked", () => {
    const ok = "https://smith.langchain.com/o/team/projects/p/snapback";
    expect(safeTraceUrl(ok)).toBe(ok);
    expect(safeTraceUrl("https://eu.smith.langchain.com/o/team")).not.toBeNull();
    for (const bad of [
      "https://smith.langchain.com/o/team?api_key=lsv2_abc",
      "https://smith.langchain.com/o/team#token=abc",
      "http://smith.langchain.com/o/team",
      "https://evil.example/smith.langchain.com",
      "https://user:pw@smith.langchain.com/o/team",
      "https://smith.langchain.com/o/team/lsv2_pt_abc123",
      "https://smith.langchain.com/sk-ant-abc123/o",
      "javascript:alert(1)",
      "",
      null,
    ])
      expect(safeTraceUrl(bad), String(bad)).toBeNull();
  });
});

describe("the tab", () => {
  it("shows the model, the ask, the tools, what it said, the time and the model calls", () => {
    render(<TraceTab cards={deep} lang="en" w={w} focus={null} reduced />);
    const card = screen.getAllByTestId("trace-card").find((c) => c.id === "trace-record")!;
    expect(within(card).getByTestId("trace-model")).toHaveTextContent("Claude Haiku");
    expect(card).toHaveTextContent("Asked");
    expect(within(card).getAllByTestId("trace-step")).toHaveLength(2);
    expect(within(card).getByTestId("trace-said")).toHaveTextContent("Said");
    expect(within(card).getByTestId("trace-meta")).toHaveTextContent("3 model calls");
    expect(within(card).queryByTestId("trace-code")).toBeNull();
    const planner = screen.getAllByTestId("trace-card").find((c) => c.id === "trace-planner")!;
    expect(within(planner).getByTestId("trace-plan")).toHaveTextContent("The plan it wrote");
    expect(within(planner).getByTestId("trace-plan")).toHaveTextContent("Sent work to");
    const rules = screen.getAllByTestId("trace-card").find((c) => c.id === "trace-rules")!;
    expect(within(rules).getByTestId("trace-code")).toHaveTextContent(
      "No model ran this step: code checked it.",
    );
    expect(within(rules).getByTestId("trace-model")).toHaveTextContent("code");
    expect(within(rules).getByTestId("trace-meta")).toHaveTextContent("no model calls");
    expect(screen.queryByTestId("trace-langsmith")).toBeNull();
  });

  it("links to LangSmith only with a safe address, in a new tab", () => {
    const { unmount } = render(
      <TraceTab
        cards={deep}
        lang="en"
        w={w}
        focus={null}
        reduced
        traceUrl="https://smith.langchain.com/o/t/projects/p/s"
      />,
    );
    const link = screen.getByTestId("trace-langsmith");
    expect(link).toHaveAttribute("href", "https://smith.langchain.com/o/t/projects/p/s");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    unmount();
    render(
      <TraceTab
        cards={deep}
        lang="en"
        w={w}
        focus={null}
        reduced
        traceUrl="https://smith.langchain.com/o/t?key=abc"
      />,
    );
    expect(screen.queryByTestId("trace-langsmith")).toBeNull();
  });

  it("Replay steps through it: cards and steps come on in order and keep their room", () => {
    vi.useFakeTimers();
    render(<TraceTab cards={deep} lang="en" w={w} focus={null} reduced={false} />);
    const cards = () => screen.getAllByTestId("trace-card");
    expect(cards().every((c) => c.getAttribute("data-shown") === "yes")).toBe(true);
    fireEvent.click(screen.getByTestId("trace-replay"));
    expect(cards().every((c) => c.getAttribute("data-shown") === "no")).toBe(true);
    expect(cards()).toHaveLength(deep.length); // hidden, not removed: nothing moves
    const tick = (n: number) => {
      for (let i = 0; i < n; i++)
        act(() => {
          vi.advanceTimersByTime(STEP_MS);
        });
    };
    tick(2);
    expect(cards()[0]).toHaveAttribute("data-shown", "yes");
    expect(cards()[1]).toHaveAttribute("data-shown", "no");
    const steps = within(cards()[0]!).getAllByTestId("trace-step");
    expect(steps[0]).toHaveAttribute("data-shown", "yes");
    expect(steps[1]).toHaveAttribute("data-shown", "no");
    tick(traceLength(deep) + 2);
    expect(cards().every((c) => c.getAttribute("data-shown") === "yes")).toBe(true);
  });

  it("with reduced motion Replay shows everything at once", () => {
    render(<TraceTab cards={deep} lang="en" w={w} focus={null} reduced />);
    fireEvent.click(screen.getByTestId("trace-replay"));
    expect(
      screen.getAllByTestId("trace-card").every((c) => c.getAttribute("data-shown") === "yes"),
    ).toBe(true);
  });

  it("a member's mark in the graph opens its trace card", () => {
    render(<TeamPanel caseId="deep-sample" run={deepRun} roster={roster} reduced />);
    const node = screen
      .getAllByTestId("team-node")
      .find((n) => n.getAttribute("data-agent") === "record")!;
    fireEvent.click(within(node).getByRole("button"));
    expect(screen.getByTestId("team-tab-trace")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("team-tab-trace")).toHaveTextContent("See how it worked");
    const card = screen.getAllByTestId("trace-card").find((c) => c.id === "trace-record")!;
    expect(card).toHaveFocus();
    // The verdict is still the card's own, set by code; the trace only explains.
    expect(screen.getByTestId("team-verdict")).toBeInTheDocument();
  });
});
