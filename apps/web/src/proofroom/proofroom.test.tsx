// The check team: the roster the page ships is the roster the report's checks need, a desk's
// state and finding come from the card and the timeline (never invented), a member nothing
// reached says so, the verdict shows only after the last step and is the card's own, and the
// links go where they say.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { matchRoute, proofRoomTarget } from "../App";
import { CHECK_ORDER } from "../case/answer";
import { CaseResult } from "../case/CaseResult";
import { headlineOf } from "../cardStrings";
import type { Card, CaseTimeline, TimelineStep } from "../contracts";
import { AgentStrip } from "./AgentStrip";
import { HomeTeam } from "./HomeTeam";
import {
  MIN_BEAT,
  asRoster,
  bundledRoster,
  deskOfCheck,
  floorAt,
  runLength,
  schedule,
  statusLine,
  teamSummary,
  type Floor,
} from "./model";
import { ReportTeam, teamHref } from "./ReportTeam";
import { sampleCard, sampleTimeline } from "./sample";
import { TeamPanel, answerHref } from "./TeamPanel";
import type { Run } from "./useRun";
import { WORDS } from "./words";

const roster = bundledRoster("en");
const w = WORDS.en;
const card = sampleCard;
const END = Infinity;

const floor = (at = END, timeline: CaseTimeline | null = sampleTimeline, c: Card | null = card) =>
  floorAt({ roster, card: c, timeline, at });
const desk = (f: Floor, id: string) => f.desks.find((d) => d.card.id === id)!;
const beats = schedule(sampleTimeline);
const beatOf = (kind: string) => beats[sampleTimeline.steps.findIndex((s) => s.kind === kind)]!;
const ready: Run = { status: "ready", card, timeline: sampleTimeline, listing: null };
const none: Run = { status: "none", card: null, timeline: null, listing: null };

function deepTimeline(): CaseTimeline {
  const step = (n: number, over: Partial<TimelineStep>): TimelineStep => ({
    step: n,
    label: "A step",
    started_ms: n * 1000,
    took_ms: 1000,
    result: "Done.",
    source: "fixture",
    by: "code",
    kind: null,
    ...over,
  });
  return {
    case_id: card.case_id,
    source: "fixture",
    mode: "deepagents",
    fell_back: false,
    steps: [
      step(0, { label: "Read the ad", took_ms: 0 }),
      step(1, { label: "Wrote its plan (0 of 3 done)", by: "agent" }),
      step(2, { label: "Handed the place checks to a sub-agent", by: "agent", kind: "place" }),
      step(3, { label: "Handed the search checks to a sub-agent", by: "agent", kind: "search" }),
      step(4, { label: "Compared the ad's claims with the record", kind: "claims" }),
      step(5, { label: "Code worked out the result", took_ms: 0 }),
    ],
    todos: [{ content: "Check the photos", done: true }],
    plan: ["place", "search"],
  };
}

afterEach(() => vi.useRealTimers());

describe("the roster the page ships", () => {
  it("has one desk for every check the report shows", () => {
    for (const check of CHECK_ORDER) expect(deskOfCheck(roster, check), check).not.toBeNull();
  });

  it("keeps the teams in floor order, in English and Spanish", () => {
    expect(roster.teams.map((t) => t.id)).toEqual([
      "planner",
      "scam_check",
      "listing_help",
      "decider",
    ]);
    const es = bundledRoster("es");
    expect(es.agents.map((a) => a.id)).toEqual(roster.agents.map((a) => a.id));
    expect(es.agents[0]!.name).toBe("Planificador");
  });

  it("takes a roster from GET /agents and refuses anything else", () => {
    expect(asRoster(JSON.parse(JSON.stringify(roster)))).not.toBeNull();
    expect(asRoster({ agents: [], teams: [] })).toBeNull();
    expect(asRoster({ agents: [{ id: "x" }], teams: [] })).toBeNull();
    expect(asRoster(null)).toBeNull();
  });
});

describe("with no case", () => {
  it("is the roster at rest: every desk idle, no thread, no verdict", () => {
    const rest = floor(END, null, null);
    expect(rest.phase).toBe("rest");
    expect(rest.desks).toHaveLength(roster.agents.length);
    expect(rest.desks.every((d) => d.state === "idle" && d.findings.length === 0)).toBe(true);
    expect(rest.log).toEqual([]);
    expect(rest.verdict).toBeNull();
    expect(statusLine(rest, w)).toBe("Run a check to watch them work");
  });

  it("the panel shows the team's cards and says to run a check, with no replay button", () => {
    render(<TeamPanel caseId="NONE" run={none} roster={roster} reduced />);
    expect(screen.getByTestId("team-status")).toHaveTextContent("Run a check to watch them work");
    expect(screen.queryByTestId("team-replay")).toBeNull();
    expect(screen.queryByTestId("team-verdict")).toBeNull();
    const desks = screen.getAllByTestId("desk");
    expect(desks).toHaveLength(roster.agents.length);
    const web = desks.find((d) => d.getAttribute("data-agent") === "web")!;
    expect(web).toHaveTextContent("Available when the web checks are on");
    expect(web).toHaveTextContent("Bright Data");
    expect(screen.queryByTestId("desk-out")).toBeNull();
  });
});

describe("desk states on a replay", () => {
  it("holds a quick step long enough to read and keeps the steps in order", () => {
    expect(beats[0]!.start).toBe(0);
    for (let i = 1; i < beats.length; i++) {
      expect(beats[i]!.start - beats[i - 1]!.start).toBeGreaterThanOrEqual(MIN_BEAT);
      expect(beats[i]!.end - beats[i]!.start).toBeGreaterThanOrEqual(MIN_BEAT);
    }
    // A long step keeps its recorded length.
    expect(beatOf("locate").end - beatOf("locate").start).toBe(4200);
    expect(runLength(beats)).toBeGreaterThan(sampleTimeline.steps.length * MIN_BEAT - 1);
  });

  it("is idle before its step, working during it, done after it", () => {
    const photo = beatOf("locate");
    expect(desk(floor(photo.start - 1), "photo").state).toBe("idle");
    const during = floor(photo.start + 10);
    expect(desk(during, "photo").state).toBe("working");
    expect(desk(during, "photo").findings).toEqual([]);
    expect(during.verdict).toBeNull();
    expect(during.phase).toBe("running");
    // The photo desk has a later step too (the photo that came back): done only after that.
    expect(desk(floor(beatOf("reply").end), "photo").state).toBe("done");
  });

  it("never shows the verdict before the last step has played", () => {
    const length = runLength(beats);
    expect(floor(length - 1).verdict).toBeNull();
    expect(desk(floor(length - 1), "decider").state).not.toBe("done");
    expect(floor(length).verdict?.headline).toBe(headlineOf(card));
  });

  it("the status line counts the checks done and names the one under way", () => {
    const during = floor(beatOf("locate").start + 10);
    expect(statusLine(during, w)).toBe(
      `${during.checksDone} of ${during.checksTotal} checks done · placing the photos in the building's 3D scan`,
    );
    expect(during.checksDone).toBeLessThan(during.checksTotal);
    const end = floor();
    expect(end.checksDone).toBe(end.checksTotal);
    expect(statusLine(end, w)).toBe(
      `${end.checksTotal} of ${end.checksTotal} checks done · code set the result`,
    );
    expect(end.progress).toBe(1);
    expect(during.progress).toBeGreaterThan(0);
    expect(during.progress).toBeLessThan(1);
  });
});

describe("findings come from the card, through the report's mapping", () => {
  it("gives each desk the card's own lines for its checks, with the worst tone", () => {
    const end = floor();
    expect(desk(end, "rules").findings).toEqual([
      { label: "Payment ask", text: "Zelle before a viewing. Red flag." },
    ]);
    expect(desk(end, "rules").tone).toBe("red_flag");
    expect(desk(end, "photo").tone).toBe("ok");
    expect(desk(end, "photo").findings.map((f) => f.label)).toEqual(["Real", "Here now"]);
    expect(desk(end, "phone_office").tone).toBe("not_shown");
    expect(desk(end, "photo").tookMs).toBe(4200 + 2400);
    expect(desk(end, "photo").evidence).toEqual([
      "Placed 3 of 3 photos in its 3D scan",
      "Checked the photo that came back",
    ]);
  });

  it("a desk nothing reached is unused, and one the plan left out says why", () => {
    const end = floor();
    for (const id of ["web", "finder", "tour_prep", "planner"]) {
      expect(desk(end, id).state, id).toBe("unused");
      expect(desk(end, id).findings, id).toEqual([]);
    }
    const skipped: CaseTimeline = {
      ...sampleTimeline,
      steps: sampleTimeline.steps.map((s) =>
        s.kind === "owner"
          ? { ...s, skipped: true, result: "Skipped owner of record: no owner on record to read." }
          : s,
      ),
    };
    const owner = desk(floor(END, skipped), "owner_licence");
    expect(owner.state).toBe("skipped");
    expect(owner.findings).toEqual([]);
    expect(owner.why).toBe("no owner on record to read");
  });

  it("the verdict and its reasons are the card's, each reason tied to its desk", () => {
    const end = floor();
    expect(end.verdict?.headline).toBe(headlineOf(card));
    expect(end.verdict?.reasons.map((r) => r.text)).toEqual(card.does_not);
    expect(end.verdict?.reasons.map((r) => r.deskId)).toEqual(["phone_office", "rules"]);
    expect(teamSummary(end)).toEqual({ checked: end.checksTotal, redFlags: 1 });
  });

  it("the thread says each step under its member's name, then that member's finding", () => {
    const lines = floor().log;
    const texts = lines.map((l) => `${l.who}: ${l.text}`);
    expect(texts[0]).toBe("SNAPBACK: Read the ad");
    const claims = texts.indexOf("Rules agent: Compared the ad's claims with the record");
    expect(texts[claims + 1]).toBe("Rules agent: Payment ask: Zelle before a viewing. Red flag.");
    expect(lines[claims + 1]).toMatchObject({ finding: true, tone: "red_flag" });
    expect(texts.at(-1)).toBe(`Decider: ${headlineOf(card)}`);
    // Mid-run the thread holds only what has started, and no finding of a desk still working.
    const mid = floor(beatOf("locate").start + 10).log;
    expect(mid.some((l) => l.text.startsWith("Real:"))).toBe(false);
    expect(mid.some((l) => l.who === "Decider")).toBe(false);
  });

  it("a finding the card holds with no step of its own lights its desk when the ad is read", () => {
    // The fixture API's text-only run has no claims step, yet the card carries the payment ask.
    const bare: CaseTimeline = {
      ...sampleTimeline,
      steps: sampleTimeline.steps.filter((s) => s.kind !== "claims"),
    };
    const first = schedule(bare)[0]!;
    expect(desk(floor(first.end - 1, bare), "rules").state).toBe("working");
    const end = floor(END, bare);
    expect(desk(end, "rules").state).toBe("done");
    expect(desk(end, "rules").tone).toBe("red_flag");
    expect(desk(end, "rules").evidence).toEqual(["Read the ad"]);
    expect(end.verdict?.reasons.at(-1)?.deskId).toBe("rules");
    expect(end.log[1]).toMatchObject({ who: "Rules agent", finding: true });
    expect(end.checksDone).toBe(end.checksTotal);
    expect(end.desks.filter((d) => d.card.id === "rules" && d.state === "unused")).toEqual([]);
  });

  it("when the deep agent ran, the Planner and the sub-agents it handed work to light up", () => {
    const end = floor(END, deepTimeline());
    expect(desk(end, "planner").state).toBe("done");
    expect(desk(end, "finder").state).toBe("done");
    expect(desk(end, "photo").state).toBe("done");
    expect(desk(end, "web").state).toBe("unused");
    expect(end.log.find((l) => l.text.startsWith("Wrote its plan"))?.who).toBe("Planner");
  });

  it("a run that is still live shows its newest step as under way and no verdict", () => {
    const live = { ...sampleTimeline, running: true, steps: sampleTimeline.steps.slice(0, 4) };
    const now = floor(END, live as CaseTimeline);
    expect(now.phase).toBe("running");
    expect(desk(now, "record").state).toBe("working");
    expect(desk(now, "rules").state).toBe("done");
    expect(now.verdict).toBeNull();
  });
});

describe("the panel beside the twin", () => {
  it("shows the whole run at once under reduced motion: lights, thread, stamp, links", () => {
    render(<TeamPanel caseId={card.case_id} run={ready} roster={roster} reduced />);
    expect(screen.getByRole("heading", { name: "Your check team" })).toBeInTheDocument();
    expect(screen.getByTestId("team-source")).toHaveTextContent("FIXTURE");
    expect(screen.getByTestId("team-verdict")).toHaveTextContent(headlineOf(card));
    expect(screen.getByTestId("team-decider")).toHaveTextContent(
      "Code sets the verdict. No model can talk a renter into paying.",
    );
    expect(screen.getByTestId("team-how")).toHaveAttribute(
      "href",
      `/case/${card.case_id}#case-answer-title`,
    );
    const lights = screen.getAllByTestId("agent-strip-item");
    expect(lights).toHaveLength(roster.agents.length);
    const web = lights.find((l) => l.getAttribute("data-agent") === "web")!;
    expect(web).toHaveAttribute("data-state", "unused");
    expect(web).toHaveTextContent("Not used on this case");
    const rules = lights.find((l) => l.getAttribute("data-agent") === "rules")!;
    expect(rules).toHaveAttribute("data-tone", "red_flag");
    expect(rules).toHaveTextContent("Red flag");
    const flagged = screen
      .getAllByTestId("team-line")
      .filter((l) => l.getAttribute("data-tone") === "red_flag");
    expect(flagged).toHaveLength(1);
    expect(flagged[0]).toHaveTextContent("Rules agent");
  });

  it("a reason opens Meet the team on the desk behind it, with its evidence line", () => {
    render(<TeamPanel caseId={card.case_id} run={ready} roster={roster} reduced />);
    const link = screen.getAllByTestId("team-reason-link").at(-1)!;
    expect(link).toHaveTextContent("See Rules agent");
    expect(link).toHaveAttribute("href", "#desk-rules");
    fireEvent.click(link);
    expect(screen.getByTestId("team-tab-meet")).toHaveAttribute("aria-selected", "true");
    const rules = screen.getAllByTestId("desk").find((d) => d.id === "desk-rules")!;
    expect(rules).toHaveFocus();
    expect(within(rules).getByTestId("desk-finding")).toHaveTextContent("Zelle before a viewing");
    expect(within(rules).getByTestId("desk-evidence")).toHaveTextContent(
      "Compared the ad's claims with the record",
    );
    expect(rules).toHaveTextContent("Rules table");
    expect(rules).toHaveTextContent("code");
    const web = screen.getAllByTestId("desk").find((d) => d.id === "desk-web")!;
    expect(web).toHaveTextContent("Not used on this case");
    expect(within(web).queryByTestId("desk-finding")).toBeNull();
  });

  it("replays the recorded run: lights come on step by step and the stamp lands last", () => {
    vi.useFakeTimers();
    render(<TeamPanel caseId={card.case_id} run={ready} roster={roster} reduced={false} />);
    const light = (id: string) =>
      screen.getAllByTestId("agent-strip-item").find((l) => l.getAttribute("data-agent") === id)!;
    expect(screen.queryByTestId("team-verdict")).toBeNull();
    expect(light("photo")).toHaveAttribute("data-state", "idle");
    act(() => {
      vi.advanceTimersByTime(beatOf("locate").start + 300);
    });
    expect(light("photo")).toHaveAttribute("data-state", "working");
    expect(light("rules")).toHaveAttribute("data-state", "done");
    expect(screen.queryByTestId("team-verdict")).toBeNull();
    expect(screen.getByTestId("team-status")).toHaveTextContent("placing the photos");
    act(() => {
      vi.advanceTimersByTime(runLength(beats) + 500);
    });
    expect(light("photo")).toHaveAttribute("data-state", "done");
    expect(screen.getByTestId("team-verdict")).toHaveTextContent(headlineOf(card));
    // "Replay this run" starts it again from the first step.
    fireEvent.click(screen.getByTestId("team-replay"));
    expect(screen.queryByTestId("team-verdict")).toBeNull();
    expect(light("photo")).toHaveAttribute("data-state", "idle");
    fireEvent.click(screen.getByTestId("team-skip"));
    expect(screen.getByTestId("team-verdict")).toBeInTheDocument();
  });

  it("says so when this browser cannot read the run, and shows no verdict", () => {
    const locked: Run = { status: "locked", card, timeline: null, listing: null };
    render(<TeamPanel caseId={card.case_id} run={locked} roster={roster} reduced />);
    expect(screen.getByTestId("team-status")).toHaveTextContent("only in the browser that started");
    expect(screen.queryByTestId("team-verdict")).toBeNull();
  });
});

describe("the strip and its links", () => {
  it("the report's strip counts the checks and the red flags and links to the live screen", () => {
    render(<ReportTeam card={card} timeline={sampleTimeline} />);
    const end = floor();
    expect(screen.getByTestId("report-team-summary")).toHaveTextContent(
      `${end.checksTotal} checked, 1 found a red flag`,
    );
    expect(screen.getByTestId("report-team-link")).toHaveAttribute(
      "href",
      `/case/${card.case_id}/twin`,
    );
    expect(screen.getByTestId("report-team-link")).toHaveTextContent("See your check team work");
    // Members nothing reached are left off the report's strip.
    const shown = screen
      .getAllByTestId("agent-strip-item")
      .map((l) => l.getAttribute("data-agent"));
    expect(shown).not.toContain("web");
    expect(shown).toContain("rules");
  });

  it("is not there without a timeline, and sits on the renter's report when there is one", () => {
    const { container } = render(<ReportTeam card={card} timeline={null} />);
    expect(container).toBeEmptyDOMElement();
    render(<CaseResult card={card} timeline={sampleTimeline} />);
    expect(screen.getByTestId("report-team")).toBeInTheDocument();
    expect(screen.getByTestId("case-answer")).toBeInTheDocument();
  });

  it("is left off the page a QR code opens for someone else", () => {
    render(<CaseResult card={card} timeline={sampleTimeline} variant="verify" />);
    expect(screen.queryByTestId("report-team")).toBeNull();
  });

  it("Home: before the case exists every member waits, and there is no link to follow", () => {
    render(<HomeTeam caseId={null} />);
    expect(screen.getByTestId("home-team")).toHaveTextContent("Your check team is on it");
    const lights = screen.getAllByTestId("agent-strip-item");
    expect(lights.length).toBeGreaterThan(5);
    expect(lights.every((l) => l.getAttribute("data-state") === "idle")).toBe(true);
    expect(screen.queryByTestId("home-team-link")).toBeNull();
    expect(screen.queryByTestId("home-team-status")).toBeNull();
  });

  it("Home: once the case exists the lights are its recorded steps, with Watch them work", () => {
    // No API in tests: the fixture case reads the sample run.
    render(<HomeTeam caseId={card.case_id} />);
    const light = (id: string) =>
      screen.getAllByTestId("agent-strip-item").find((l) => l.getAttribute("data-agent") === id)!;
    expect(light("rules")).toHaveAttribute("data-tone", "red_flag");
    expect(light("decider")).toHaveAttribute("data-state", "done");
    expect(screen.getByTestId("home-team-link")).toHaveAttribute(
      "href",
      `/case/${card.case_id}/twin`,
    );
    expect(screen.getByTestId("home-team-link")).toHaveTextContent("Watch them work");
  });

  it("AgentStrip names every member with its state in words", () => {
    render(<AgentStrip desks={floor().desks} label="Your check team" />);
    const list = screen.getByRole("list", { name: "Your check team" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(roster.agents.length);
    expect(list).toHaveTextContent("Photo agent");
    expect(list).toHaveTextContent("Checks out");
  });

  it("/proof-room?case=<id> lands on the twin; with no case, or a bad one, on Home", () => {
    expect(matchRoute("/proof-room")).toEqual({ name: "proof-room" });
    expect(proofRoomTarget("?case=7Q2M")).toBe("/case/7Q2M/twin");
    expect(proofRoomTarget("?case=fx-7Q2M")).toBe("/case/fx-7Q2M/twin");
    expect(proofRoomTarget("")).toBe("/");
    expect(proofRoomTarget("?case=../x")).toBe("/");
    expect(proofRoomTarget("?case=a%2Fb")).toBe("/");
    expect(teamHref("7Q2M")).toBe("/case/7Q2M/twin");
    expect(answerHref("7Q2M")).toBe("/case/7Q2M#case-answer-title");
  });
});
