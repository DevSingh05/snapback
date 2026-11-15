// @vitest-environment jsdom
// The crew scene: who stands where, who gets a note when, what each member says and when the
// Decider stamps. Everything is worked out from the same floor the rest of the Proof Room reads.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { headlineOf } from "../cardStrings";
import type { Card, CaseTimeline } from "../contracts";
import { Badge } from "./Badge";
import { CrewScene } from "./CrewScene";
import { VIEW, crewActions, crewBubbles, crewCast, hasPersona, personaOf, shortSay } from "./crew";
import { bundledRoster, floorAt, runLength, schedule, teamView, type Floor } from "./model";
import { sampleCard, sampleTimeline } from "./sample";
import { TeamPanel } from "./TeamPanel";
import type { Run } from "./useRun";
import { WORDS } from "./words";

const roster = bundledRoster("en");
const card = sampleCard;
const END = Infinity;
const beats = schedule(sampleTimeline);
const beatOf = (kind: string) => beats[sampleTimeline.steps.findIndex((s) => s.kind === kind)]!;
const floor = (at = END, timeline: CaseTimeline = sampleTimeline, c: Card = card, hold = false) =>
  floorAt({ roster, card: c, timeline, at, hold });
const whole = floor();
const castAt = (f: Floor, all: Floor = whole) => crewCast(f, teamView(f, all));
const desk = (f: Floor, id: string) => f.desks.find((d) => d.card.id === id)!;

// The first moment a member is done on the replay clock (its last step has played).
const doneAt = (id: string) => {
  for (let at = 0; at <= runLength(beats) + 200; at += 100)
    if (desk(floor(at), id).state === "done") return at;
  throw new Error(`${id} is never done`);
};

afterEach(cleanup);

describe("who stands where", () => {
  it("puts the Planner at the back, the Decider at its desk in front, the members around the home", () => {
    const cast = castAt(whole);
    const planner = cast.find((a) => a.id === "planner")!;
    const decider = cast.find((a) => a.id === "decider")!;
    const ring = cast.filter((a) => a.place === "ring");
    expect(planner.place).toBe("lead");
    expect(decider.place).toBe("desk");
    expect(ring.map((a) => a.id).sort()).toEqual([
      "owner_licence",
      "phone_office",
      "photo",
      "record",
      "rules",
    ]);
    for (const a of ring) {
      expect(a.sy).toBeGreaterThan(planner.sy);
      expect(a.sy).toBeLessThan(decider.sy);
    }
    // Half stand on each side of the home, and nobody stands off the stage.
    expect(ring.filter((a) => a.side === "left")).toHaveLength(3);
    expect(ring.filter((a) => a.side === "right")).toHaveLength(2);
    for (const a of cast) {
      expect(a.sx).toBeGreaterThan(0);
      expect(a.sx).toBeLessThan(VIEW.w);
      expect(a.sy).toBeGreaterThan(0);
      expect(a.sy).toBeLessThan(VIEW.h);
    }
  });

  it("sits the members this ad did not need on the bench at the edge, in the same spots all run", () => {
    const bench = castAt(whole).filter((a) => a.place === "bench");
    expect(bench.map((a) => a.id)).toEqual(["web", "finder", "tour_prep"]);
    for (const a of bench) expect(a.state).toBe("unused");
    // From the first moment of a replay: the whole run is known, so nobody changes place.
    const early = castAt(floor(0));
    expect(early.map((a) => [a.id, a.place, a.sx, a.sy])).toEqual(
      castAt(whole).map((a) => [a.id, a.place, a.sx, a.sy]),
    );
  });

  it("keeps everyone on stage while a run is live: nobody is known to be unneeded yet", () => {
    const live = { ...sampleTimeline, running: true, steps: sampleTimeline.steps.slice(0, 4) };
    const now = floor(END, live);
    const cast = crewCast(now, teamView(now, now));
    expect(cast.filter((a) => a.place === "bench")).toHaveLength(0);
    // The ring holds six; the two that come last in the roster wait at the edge, in the run.
    expect(cast.filter((a) => a.place === "ring")).toHaveLength(6);
    const wing = cast.filter((a) => a.place === "wing");
    expect(wing.map((a) => a.id)).toEqual(["finder", "tour_prep"]);
    for (const a of wing) expect(a.state).toBe("idle");
  });

  it("a check the plan left out stays in the ring as not checked", () => {
    const skipped: CaseTimeline = {
      ...sampleTimeline,
      steps: sampleTimeline.steps.map((s) =>
        s.kind === "phone" ? { ...s, skipped: true, result: "Skipped: the ad has no phone." } : s,
      ),
    };
    const f = floor(END, skipped);
    const a = crewCast(f, teamView(f, f)).find((x) => x.id === "phone_office")!;
    expect(a.place).toBe("ring");
    expect(a.state).toBe("skipped");
  });

  it("gives every member of the roster its own character and badge", () => {
    for (const a of roster.agents) expect(hasPersona(a.id), a.id).toBe(true);
    expect(new Set(roster.agents.map((a) => personaOf(a.id))).size).toBe(roster.agents.length);
    expect(personaOf("planner")).toBe("foreman");
    expect(personaOf("decider")).toBe("judge");
    expect(personaOf("someone-new")).toBe("helper");
  });
});

describe("the notes, from recorded state changes only", () => {
  const start = beatOf("locate").start;
  const end = doneAt("photo");

  it("the Planner hands a member a note when its work starts", () => {
    expect(crewActions(floor(start - 1), floor(start + 10))).toContainEqual({
      kind: "brief",
      to: "photo",
    });
  });

  it("the member sends its note on to the Decider when it is done, red tagged for a red flag", () => {
    const acts = crewActions(floor(end - 100), floor(end));
    expect(acts).toContainEqual({ kind: "report", from: "photo", flag: false });
    expect(acts.some((a) => a.kind === "brief" && a.to === "photo")).toBe(false);
    // The rules read the ad as it comes in, and on this card they found a red flag.
    expect(desk(whole, "rules").tone).toBe("red_flag");
    expect(crewActions(floor(doneAt("rules") - 100), floor(doneAt("rules")))).toContainEqual({
      kind: "report",
      from: "rules",
      flag: true,
    });
  });

  it("a member that starts and finishes between two looks gets its note and sends it on", () => {
    const acts = crewActions(floor(start - 1), floor(end)).filter(
      (a) => a.kind !== "stamp" && (a.kind === "brief" ? a.to : a.from) === "photo",
    );
    expect(acts).toEqual([
      { kind: "brief", to: "photo" },
      { kind: "report", from: "photo", flag: false },
    ]);
  });

  it("nothing flies when the scene first shows, when nothing changed, or when a replay restarts", () => {
    expect(crewActions(null, whole)).toEqual([]);
    expect(crewActions(whole, whole)).toEqual([]);
    expect(crewActions(whole, floor(0))).toEqual([]);
  });

  it("members that were skipped or never used get no note", () => {
    const ids = new Set<string>();
    let before = floor(0);
    for (let at = 100; at <= runLength(beats) + 200; at += 100) {
      const now = floor(at);
      for (const a of crewActions(before, now))
        if (a.kind !== "stamp") ids.add(a.kind === "brief" ? a.to : a.from);
      before = now;
    }
    expect([...ids].sort()).toEqual(["owner_licence", "phone_office", "photo", "record", "rules"]);
  });
});

describe("the stamp", () => {
  it("lands once, when the last step has played", () => {
    const last = runLength(beats);
    expect(crewActions(floor(last - 200), floor(last - 100))).not.toContainEqual({ kind: "stamp" });
    expect(crewActions(floor(last - 100), floor(END))).toContainEqual({ kind: "stamp" });
  });

  it("waits for the fresh card after a live run: no stamp while the old card is in hand", () => {
    const live = { ...sampleTimeline, running: true };
    const running = floor(END, live);
    const held = floor(END, sampleTimeline, card, true);
    expect(held.verdict).toBeNull();
    expect(crewActions(running, held)).not.toContainEqual({ kind: "stamp" });
    const fresh: Card = { ...card, state: "dont_pay", headline: "Don't pay" };
    const stamped = floor(END, sampleTimeline, fresh);
    expect(crewActions(held, stamped)).toContainEqual({ kind: "stamp" });
    // While it waits the Decider says what it is doing, and never the old verdict.
    const says = crewBubbles(held, castAt(held, held));
    expect(says.find((b) => b.deskId === "decider")?.text).toBe(desk(held, "decider").card.doing);
    expect(says.map((b) => b.text).join(" ")).not.toContain(headlineOf(card));
  });
});

describe("what the crew says", () => {
  it("a member at work says what it is doing, in the roster's own words", () => {
    const f = floor(beatOf("locate").start + 10);
    const says = crewBubbles(f, castAt(f));
    expect(says[0]).toMatchObject({
      deskId: "photo",
      kind: "working",
      text: desk(f, "photo").card.doing,
    });
  });

  it("a member that is done says the card's own finding, cut short", () => {
    const f = floor(doneAt("photo"));
    const says = crewBubbles(f, castAt(f));
    const photo = says.find((b) => b.deskId === "photo")!;
    const first = desk(f, "photo").findings[0]!;
    const said = first.label ? `${first.label}: ${first.text}` : first.text;
    expect(photo.kind).toBe("finding");
    expect(photo.text).toBe(shortSay(said));
    expect(photo.tone).toBe(desk(f, "photo").tone);
  });

  it("never shows more than two bubbles, and leads with the red flag once the run is over", () => {
    for (let at = 0; at <= runLength(beats) + 200; at += 300) {
      const f = floor(at);
      expect(crewBubbles(f, castAt(f)).length).toBeLessThanOrEqual(2);
    }
    const end = crewBubbles(whole, castAt(whole));
    expect(end[0]).toMatchObject({ deskId: "rules", tone: "red_flag", kind: "finding" });
    // Nobody on the bench speaks.
    expect(end.every((b) => !["web", "finder", "tour_prep"].includes(b.deskId))).toBe(true);
  });

  it("says nothing before a run", () => {
    const rest = floorAt({ roster, card: null, timeline: null });
    expect(crewBubbles(rest, crewCast(rest, teamView(rest, rest)))).toEqual([]);
  });

  it("cuts a long line at a word and keeps a short one whole", () => {
    expect(shortSay("Asks for a deposit before a tour")).toBe("Asks for a deposit before a tour");
    const cut = shortSay("The ad asks for a deposit by wire before any tour of the home", 30);
    expect(cut.length).toBeLessThanOrEqual(31);
    expect(cut.endsWith("…")).toBe(true);
    expect(cut).toBe("The ad asks for a deposit by…");
  });
});

describe("the scene on screen", () => {
  const props = (f: Floor, moving: boolean) => ({
    floor: f,
    team: teamView(f, whole),
    w: WORDS.en,
    lang: "en" as const,
    moving,
  });

  it("names each member on stage with what runs it and its state in words", () => {
    render(<CrewScene {...props(whole, false)} />);
    const tags = screen.getAllByTestId("team-node");
    expect(tags.map((t) => t.getAttribute("data-agent"))).toEqual([
      "planner",
      "rules",
      "record",
      "phone_office",
      "photo",
      "owner_licence",
      "decider",
    ]);
    const rules = tags.find((t) => t.getAttribute("data-agent") === "rules")!;
    expect(rules).toHaveAttribute("data-state", "done");
    expect(rules).toHaveAttribute("data-tone", "red_flag");
    expect(rules).toHaveTextContent("Rules");
    expect(rules).toHaveTextContent("code");
    expect(rules).toHaveTextContent("Red flag");
    expect(screen.getByTestId("team-not-needed")).toHaveTextContent(
      "Not needed for this ad: Web agent, Finder, Tour prep",
    );
    expect(screen.getByTestId("crew-scene")).toHaveAttribute("data-moving", "no");
    // The home in the middle and one drawn character per member, bench included.
    expect(screen.getByTestId("crew-home")).toBeInTheDocument();
    expect(screen.getAllByTestId("crew-actor")).toHaveLength(roster.agents.length);
    expect(screen.getByTestId("crew-verdict")).toHaveTextContent(headlineOf(card));
  });

  it("shows the model on the tag when a model ran the member", () => {
    const deep: CaseTimeline = {
      ...sampleTimeline,
      mode: "deepagents",
      steps: sampleTimeline.steps.map((s) => (s.kind === "locate" ? { ...s, by: "agent" } : s)),
    };
    const f = floor(END, deep);
    render(<CrewScene floor={f} team={teamView(f, f)} w={WORDS.en} lang="en" moving={false} />);
    const tag = (id: string) =>
      screen.getAllByTestId("team-node").find((t) => t.getAttribute("data-agent") === id)!;
    expect(tag("photo")).toHaveTextContent("Claude Haiku");
    expect(tag("planner")).toHaveTextContent("Claude Sonnet");
    expect(tag("decider")).toHaveTextContent("code");
  });

  it("flies a note only while a run is playing; with no motion the states and bubbles still change", () => {
    const start = beatOf("locate").start;
    const moving = render(<CrewScene {...props(floor(start - 1), true)} />);
    expect(screen.queryAllByTestId("crew-note")).toHaveLength(0);
    moving.rerender(<CrewScene {...props(floor(start + 10), true)} />);
    const flying = screen
      .getAllByTestId("crew-note")
      .filter((n) => n.getAttribute("data-agent") === "photo");
    expect(flying).toHaveLength(1);
    expect(flying[0]).toHaveAttribute("data-kind", "brief");
    moving.unmount();

    const still = render(<CrewScene {...props(floor(start - 1), false)} />);
    still.rerender(<CrewScene {...props(floor(start + 10), false)} />);
    expect(screen.queryAllByTestId("crew-note")).toHaveLength(0);
    const tag = screen
      .getAllByTestId("team-node")
      .find((t) => t.getAttribute("data-agent") === "photo")!;
    expect(tag).toHaveAttribute("data-state", "working");
    const bubble = screen
      .getAllByTestId("crew-bubble")
      .find((b) => b.getAttribute("data-agent") === "photo")!;
    expect(bubble).toHaveTextContent(desk(whole, "photo").card.doing);
    expect(screen.queryByTestId("crew-verdict")).toBeNull();
  });

  it("opens a member's card when its tag is picked", () => {
    const picked: string[] = [];
    render(<CrewScene {...props(whole, false)} onPick={(id) => picked.push(id)} />);
    const rules = screen
      .getAllByTestId("team-node")
      .find((t) => t.getAttribute("data-agent") === "rules")!;
    fireEvent.click(within(rules).getByRole("button"));
    expect(picked).toEqual(["rules"]);
  });

  it("draws a badge for any member, as decoration", () => {
    const { container } = render(<Badge id="photo" />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("data-persona", "photographer");
    expect(render(<Badge id="nobody" />).container.querySelector("svg")).toHaveAttribute(
      "data-persona",
      "helper",
    );
  });
});

describe("the panel", () => {
  const ready: Run = { status: "ready", card, timeline: sampleTimeline, listing: null };

  it("opens on the crew, and keeps the diagram one press away", () => {
    render(<TeamPanel caseId={card.case_id} run={ready} roster={roster} reduced />);
    expect(screen.getByTestId("crew-scene")).toBeInTheDocument();
    expect(screen.queryByTestId("team-graph")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Diagram" }));
    expect(screen.getByTestId("team-graph")).toBeInTheDocument();
    expect(screen.queryByTestId("crew-scene")).toBeNull();
    expect(screen.getByRole("button", { name: "Diagram" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Crew" }));
    expect(screen.getByTestId("crew-scene")).toBeInTheDocument();
    // Meet the team opens with the whole cast: one badge for every member of the roster.
    const cast = screen.getByTestId("crew-cast");
    expect(cast.querySelectorAll("svg.crew-badge")).toHaveLength(roster.agents.length);
    expect(cast).toHaveTextContent("Phone and office");
  });
});
