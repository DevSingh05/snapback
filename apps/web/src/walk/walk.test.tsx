import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { TourStop, TraceEvent, TraceKind } from "../contracts";
import { EVIDENCE_FIXTURE_A } from "../evidence/fixture";
import { FIXTURE_TOUR } from "../tour/fixtureTour";
import { parseTraceEvent } from "../trace/parse";
import { AgentRail, FOLLOW_PAUSE_MS } from "./AgentRail";
import { MISMATCH_TITLE, MismatchAerials, NAMED_LABEL, PICTURED_LABEL } from "./MismatchAerials";
import { plainLine, railCounts, railFiles, railItems, stepForStop, stopLine } from "./rail";
import { RAIL_STUB_A, RAIL_STUB_B } from "./railStub";
import { DRAWING_LABEL, REAL_LABEL, RealStill, StageViews } from "./StageViews";
import { StageCaption, StopStage } from "./StopStage";
import { ListingPhotos } from "./ListingPhotos";
import { MISMATCH_BANNER, OFFICE_LINE, photoAt, walkLook } from "./walkLook";

function ev(seq: number, kind: string, over: Partial<TraceEvent> = {}): TraceEvent {
  return {
    case_id: "c1",
    seq,
    at: "2026-11-14T15:00:00Z",
    kind: kind as TraceKind,
    options: [],
    pick: null,
    reason: `reason ${seq}`,
    source: "fixture",
    chosen_by: "policy",
    ...over,
  };
}

const lineOf = (seq: number) =>
  screen.getAllByTestId("rail-line").find((l) => l.getAttribute("data-seq") === String(seq))!;

describe("AgentRail: one line per event kind", () => {
  it("agent: a hand-off names the sub-agent and moves the relay", () => {
    render(
      <AgentRail
        events={[ev(0, "status"), ev(1, "agent", { pick: "place", reason: "Searching the scan." })]}
        source="fixture"
        reduced={false}
      />,
    );
    expect(lineOf(1)).toHaveTextContent("Hand-off");
    expect(lineOf(1)).toHaveTextContent("place");
    const runners = screen.getAllByTestId("rail-agent");
    expect(runners.map((r) => r.textContent)).toEqual(["main", "place"]);
    expect(runners[1]).toHaveAttribute("aria-current", "true");
    expect(lineOf(0)).toHaveAttribute("data-agent", "main");
  });

  it("file: the path and who wrote it", () => {
    render(
      <AgentRail
        events={[
          ev(0, "file", { pick: "/evidence/photos.json", reason: "" }),
          ev(1, "file", { pick: "/notes/place.md", reason: "", chosen_by: "model" }),
        ]}
        source="fixture"
        reduced={false}
      />,
    );
    expect(lineOf(0)).toHaveTextContent("/evidence/photos.json");
    expect(within(lineOf(0)).getByTestId("rail-written-by")).toHaveTextContent("written by code");
    expect(within(lineOf(1)).getByTestId("rail-written-by")).toHaveTextContent(
      "written by the agent",
    );
  });

  it("choice: stamped picked by model or picked by rules, with its reason", () => {
    render(
      <AgentRail
        events={[
          ev(0, "choice", {
            pick: "focus_scan:S2",
            options: ["focus_scan:S2", "wider_index", "stop"],
            chosen_by: "model",
            reason: "Search scan S2 on its own.",
          }),
          ev(1, "choice", { pick: "stop", options: ["stop"], reason: "Only option." }),
          ev(2, "choice", { pick: "spot 3", choice: "which_spot", reason: "Drawn at random." }),
        ]}
        source="fixture"
        reduced={false}
      />,
    );
    const stamp = (seq: number) => within(lineOf(seq)).getByTestId("rail-stamp");
    expect(stamp(0)).toHaveTextContent("Picked by the model");
    expect(stamp(0)).toHaveAttribute("data-by", "model");
    expect(lineOf(0)).toHaveTextContent("Search scan S2 on its own.");
    expect(lineOf(0)).toHaveTextContent("from 3 options");
    expect(within(lineOf(0)).getAllByTestId("pick-option")).toHaveLength(3);
    expect(within(lineOf(0)).getByText(/Look closer at scan S2/)).toHaveAttribute(
      "data-picked",
      "true",
    );
    expect(stamp(1)).toHaveTextContent("Picked by our rules");
    expect(stamp(2)).toHaveTextContent("Random draw");
  });

  it("unsure: the code's fixed sentence, marked Not sure", () => {
    render(
      <AgentRail
        events={[ev(0, "unsure", { reason: "Matterport's room labels can be wrong." })]}
        source="fixture"
        reduced={false}
      />,
    );
    expect(lineOf(0)).toHaveAttribute("data-kind", "unsure");
    expect(lineOf(0)).toHaveTextContent("Not sure");
    expect(lineOf(0)).toHaveTextContent("Matterport's room labels can be wrong.");
  });

  it("todo, tool, status, verdict, error and hitl each render as one labelled line", () => {
    const kinds = ["todo", "tool", "status", "verdict", "error", "hitl"];
    render(
      <AgentRail
        events={kinds.map((k, i) => ev(i, k, { pick: k === "tool" ? "locate_photos" : null }))}
        source="fixture"
        reduced={false}
      />,
    );
    const tags = ["Plan", "Tool", "Status", "Result", "Error", "Your OK"];
    kinds.forEach((k, i) => {
      expect(lineOf(i)).toHaveAttribute("data-kind", k);
      expect(lineOf(i)).toHaveTextContent(tags[i]!);
      expect(lineOf(i)).toHaveTextContent(`reason ${i}`);
    });
    expect(lineOf(1)).toHaveTextContent("locate_photos");
  });
});

describe("AgentRail: only what the stream delivered", () => {
  it("renders exactly the parsed events of a recorded stream, in seq order, and drops bad lines", () => {
    const recorded = [
      JSON.stringify(ev(2, "choice", { pick: "wider_index", chosen_by: "model" })),
      "not json",
      JSON.stringify(ev(0, "status")),
      JSON.stringify({ ...ev(1, "tool"), kind: "made_up_kind" }),
      JSON.stringify({ seq: 3, kind: "status" }),
    ];
    const parsed = recorded.map(parseTraceEvent).filter((e): e is TraceEvent => e !== null);
    render(<AgentRail events={parsed} source="fixture" reduced={false} />);
    const lines = screen.getAllByTestId("rail-line");
    expect(lines.map((l) => l.getAttribute("data-seq"))).toEqual(
      [...parsed].sort((a, b) => a.seq - b.seq).map((e) => String(e.seq)),
    );
    expect(lines).toHaveLength(parsed.length);
    expect(screen.getByTestId("rail-summary")).toHaveTextContent(
      `${parsed.length} steps our agents took, in order.`,
    );
    expect(screen.getByTestId("rail-counts")).toHaveTextContent(
      `${parsed.length} steps, 1 picked by model`,
    );
  });

  it("shows an empty state and no relay, spinner or files when there are no events", () => {
    render(<AgentRail events={[]} source="fixture" reduced={false} />);
    expect(screen.getByTestId("rail-empty")).toBeInTheDocument();
    expect(screen.queryAllByTestId("rail-line")).toHaveLength(0);
    expect(screen.queryAllByTestId("rail-agent")).toHaveLength(0);
    expect(screen.getByTestId("rail-summary")).toHaveTextContent(
      "Steps appear here as our agents work.",
    );
    expect(screen.queryByTestId("rail-counts")).not.toBeInTheDocument();
  });

  it("lists only files that a file event carried", () => {
    render(<AgentRail events={RAIL_STUB_A} source="fixture" reduced={false} />);
    const tab = screen.getByRole("tab", { name: "Files 4" });
    expect(railFiles(RAIL_STUB_A)).toHaveLength(4);
    fireEvent.click(tab);
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByTestId("files-file")).toHaveLength(4);
    // The files take the steps' place in the same box, inside the rail.
    expect(screen.getByTestId("rail-scroll")).toContainElement(screen.getByTestId("rail-files"));
    expect(screen.queryAllByTestId("rail-line")).toHaveLength(0);
  });

  it("shows the matched points for a pick that names a photo, read from the evidence file", () => {
    const onOpen = vi.fn();
    render(
      <AgentRail
        events={RAIL_STUB_A}
        source="fixture"
        evidence={EVIDENCE_FIXTURE_A}
        reduced={false}
        onOpenPhoto={onOpen}
      />,
    );
    const proofs = screen.getAllByTestId("rail-proof");
    expect(proofs[0]).toHaveTextContent("P3: 88 matching points, 30 needed");
    expect(proofs[1]).toHaveTextContent("P4: 24 matching points, 30 needed");
    fireEvent.click(proofs[0]!);
    expect(onOpen).toHaveBeenCalledWith("P3");
  });

  it("is static under reduced motion, and the phone sheet opens and closes", () => {
    render(<AgentRail events={RAIL_STUB_B} source="fixture" reduced />);
    const rail = screen.getByTestId("agent-rail");
    expect(rail).toHaveAttribute("data-motion", "reduced");
    const sheet = within(rail).getByRole("button", { expanded: false, name: /How we checked/ });
    fireEvent.click(sheet);
    expect(rail).toHaveAttribute("data-open", "true");
  });

  it("the stub lines carry no model musing: counts come from the events", () => {
    expect(railCounts(RAIL_STUB_A)).toEqual({ steps: RAIL_STUB_A.length, byModel: 2 });
    expect(railItems(RAIL_STUB_A).at(-1)!.agent).toBe("walk");
  });
});

const stopOf = (key: string): TourStop => FIXTURE_TOUR.stops.find((s) => s.key === key)!;

describe("the rail follows the walk", () => {
  const items = railItems(RAIL_STUB_A);
  const seqOf = (kind: string, pick: string) =>
    RAIL_STUB_A.find((e) => (e.kind as string) === kind && e.pick === pick)!.seq;
  const kitchenPhoto = photoAt(stopOf("room-3"), EVIDENCE_FIXTURE_A);
  const follow = (key: string, reduced = true) => (
    <AgentRail
      events={RAIL_STUB_A}
      source="fixture"
      evidence={EVIDENCE_FIXTURE_A}
      reduced={reduced}
      stop={stopOf(key)}
      photo={photoAt(stopOf(key), EVIDENCE_FIXTURE_A)}
    />
  );
  const lit = () => screen.getAllByTestId("rail-line").filter((l) => l.dataset.lit === "true");

  afterEach(() => vi.useRealTimers());

  it("maps each stop to the agent step behind it: record, place for a photo stop, walk", () => {
    expect(stepForStop(items, stopOf("arrive"))).toBe(seqOf("agent", "record"));
    // The kitchen's photo was placed by the base search, so the base search step is its step.
    expect(kitchenPhoto?.searches.at(-1)).toMatchObject({ option: "base", result: "placed" });
    expect(stepForStop(items, stopOf("room-3"), kitchenPhoto)).toBe(seqOf("tool", "locate_photos"));
    // A photo the agent's own pick placed lights that pick.
    const p3 = EVIDENCE_FIXTURE_A.photos.find((p) => p.alias === "P3")!;
    expect(stepForStop(items, stopOf("room-3"), p3)).toBe(seqOf("choice", "focus_scan:S2"));
    // A room the walk agent named lights that step; any other room, the walk agent's first step.
    expect(stepForStop(items, stopOf("room-4"))).toBe(seqOf("choice", "Bathroom"));
    expect(stepForStop(items, stopOf("room-2"))).toBe(seqOf("agent", "walk"));
    expect(stepForStop(items, stopOf("outro"))).toBe(RAIL_STUB_A.at(-1)!.seq);
    expect(stepForStop([], stopOf("arrive"))).toBeNull();
  });

  it("says what the step means at this stop in the evidence file's own numbers", () => {
    const n = kitchenPhoto!.inliers;
    const bar = EVIDENCE_FIXTURE_A.bars.min_inliers;
    expect(stopLine(stopOf("room-3"), kitchenPhoto, EVIDENCE_FIXTURE_A.bars)).toBe(
      `Ad photo ${kitchenPhoto!.alias}: ${n} matching points. We need ${bar} to be sure, so we say it's this room.`,
    );
    expect(stopLine(stopOf("room-2"), null, {})).toBe("The ad showed no photo of this room.");
    expect(stopLine(stopOf("arrive"), null, {})).toBeNull();
    expect(stopLine(stopOf("room-3"), null, {})).toBeNull();
    expect(plainLine(RAIL_STUB_A.find((e) => e.pick === "focus_scan:S2")!)).toBe(
      "Picked: Look closer at scan S2",
    );
  });

  it("lights and opens only the step for this stop; every other step is one line", () => {
    const { rerender } = render(follow("arrive"));
    expect(screen.getByRole("heading", { name: "How SNAPBACK checked this ad" })).toBeVisible();
    expect(screen.getByTestId("rail-summary")).toHaveTextContent(
      `${RAIL_STUB_A.length} steps our agents took, in order. The step behind this stop is lit.`,
    );
    expect(lit()).toHaveLength(1);
    expect(lit()[0]).toHaveAttribute("data-seq", String(seqOf("agent", "record")));
    expect(lit()[0]).toHaveAttribute("aria-current", "step");
    const open = () => screen.getAllByTestId("rail-line").filter((l) => l.dataset.state === "open");
    expect(open()).toHaveLength(1);
    expect(
      screen.getAllByTestId("rail-agent").find((a) => a.getAttribute("aria-current")),
    ).toHaveTextContent("record");

    rerender(follow("room-3"));
    expect(lit()[0]).toHaveAttribute("data-seq", String(seqOf("tool", "locate_photos")));
    expect(open()).toHaveLength(1);
    expect(screen.getByTestId("rail-here")).toHaveTextContent(
      "At this stopAd photo P2: 96 matching points. We need 30 to be sure, so we say it's this room.",
    );
    expect(within(lit()[0]!).getByTestId("rail-proof")).toHaveTextContent("P2: 96 matching points");
    expect(
      screen.getAllByTestId("rail-agent").find((a) => a.getAttribute("aria-current")),
    ).toHaveTextContent("place");
    expect(screen.getByTestId("rail-now")).toHaveTextContent(
      `Step 4 of ${RAIL_STUB_A.length}: Base search of 4 photos.`,
    );

    // The step's own reason already says it, so the sentence is not shown twice.
    rerender(follow("room-4"));
    expect(lit()[0]).toHaveAttribute("data-seq", String(seqOf("choice", "Bathroom")));
    expect(screen.queryByTestId("rail-here")).not.toBeInTheDocument();
  });

  it("opens a folded step on a tap and folds it again", () => {
    render(follow("arrive"));
    const row = screen.getByRole("button", { name: "Step 5: Picked: Look closer at scan S2" });
    expect(row).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(lineOf(seqOf("choice", "focus_scan:S2"))).toHaveTextContent("Picked by the model");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "false");
  });

  it("a scroll in the rail holds the follow for about 8 s; Follow the walk resumes it", () => {
    vi.useFakeTimers();
    render(follow("arrive"));
    const rail = screen.getByTestId("agent-rail");
    expect(rail).toHaveAttribute("data-follow", "on");
    expect(screen.queryByTestId("rail-follow")).not.toBeInTheDocument();
    fireEvent.wheel(rail.querySelector(".ar-scroll")!);
    expect(rail).toHaveAttribute("data-follow", "paused");
    fireEvent.click(screen.getByRole("button", { name: "Follow the walk" }));
    expect(rail).toHaveAttribute("data-follow", "on");

    fireEvent.wheel(rail.querySelector(".ar-scroll")!);
    act(() => void vi.advanceTimersByTime(FOLLOW_PAUSE_MS - 1));
    expect(rail).toHaveAttribute("data-follow", "paused");
    act(() => void vi.advanceTimersByTime(1));
    expect(rail).toHaveAttribute("data-follow", "on");
    expect(screen.queryByTestId("rail-follow")).not.toBeInTheDocument();
  });

  it("scrolls the lit step into its box, with the step before it in view, unless held", () => {
    const { rerender } = render(follow("arrive"));
    const box = screen.getByTestId("agent-rail").querySelector<HTMLElement>(".ar-scroll")!;
    const tops = (el: HTMLElement) => Number(el.dataset.seq ?? 0) * 50;
    const spy = vi.spyOn(HTMLElement.prototype, "offsetTop", "get").mockImplementation(function (
      this: HTMLElement,
    ) {
      return tops(this);
    });
    rerender(follow("room-3"));
    expect(box.scrollTop).toBe(tops(lineOf(seqOf("tool", "locate_photos") - 1)) - 8);
    fireEvent.wheel(box);
    box.scrollTop = 7;
    rerender(follow("room-4"));
    expect(box.scrollTop).toBe(7);
    spy.mockRestore();
  });
});

describe("the rail fits beside the player and scrolls in place", () => {
  const css = (rel: string) =>
    readFileSync(join(__dirname, rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rule = (src: string, selector: string, from = 0) => {
    const at = src.indexOf(`${selector} {`, from);
    expect(at, selector).toBeGreaterThanOrEqual(0);
    return src.slice(at, src.indexOf("}", at));
  };
  const walkCss = css("walk.css");
  const desktop = walkCss.indexOf("@media (min-width: 761px)");
  const phone = walkCss.indexOf("@media (max-width: 760px)");
  const follow = (key: string) => (
    <AgentRail
      events={RAIL_STUB_A}
      source="fixture"
      evidence={EVIDENCE_FIXTURE_A}
      reduced
      stop={stopOf(key)}
      photo={photoAt(stopOf(key), EVIDENCE_FIXTURE_A)}
    />
  );
  const tab = (name: string | RegExp) => screen.getByRole("tab", { name });
  const shownSeqs = () => screen.getAllByTestId("rail-line").map((l) => l.dataset.agent);

  it("the list scrolls in place: every step sits in one scroll box under a fixed head", () => {
    render(follow("arrive"));
    const rail = screen.getByTestId("agent-rail");
    const box = screen.getByTestId("rail-scroll");
    expect(screen.getAllByTestId("rail-line")).toHaveLength(RAIL_STUB_A.length);
    for (const line of screen.getAllByTestId("rail-line")) expect(box).toContainElement(line);
    // The title, explainer and tabs are outside the box, so they stay put while it scrolls.
    expect(box).not.toContainElement(screen.getByRole("heading", { name: /How SNAPBACK/ }));
    expect(box).not.toContainElement(screen.getByRole("tablist"));
    expect(rail).toContainElement(tab("Files 4"));
    const scroll = rule(walkCss, ".ar-scroll");
    expect(scroll).toMatch(/overflow-y:\s*auto/);
    expect(scroll).toMatch(/min-height:\s*0/);
    expect(scroll).toMatch(/flex:\s*1/);
    // Phone: the closed sheet opens to an inner scroll of about 60vh.
    expect(rule(walkCss, ".ar-scroll", phone)).toMatch(/max-height:\s*60vh/);
  });

  it("the page height does not change when a step opens: the rail never sizes its row", () => {
    render(follow("arrive"));
    const box = screen.getByTestId("rail-scroll");
    const row = screen.getByRole("button", { name: "Step 5: Picked: Look closer at scan S2" });
    fireEvent.click(row);
    // The opened step grows inside the scroll box only.
    expect(box).toContainElement(row);
    expect(within(box).getByText("Picked by the model")).toBeInTheDocument();
    // Desktop: the rail's own height is 0 and it stretches to its grid row, clipping its content,
    // so nothing inside it can push the page down.
    const ar = rule(walkCss, ".ar", desktop);
    expect(ar).toMatch(/height:\s*0;/);
    expect(ar).toMatch(/min-height:\s*100%/);
    expect(ar).toMatch(/overflow:\s*hidden/);
  });

  it("the rail bottom aligns with the player bottom at 1440x900: it shares only the stage row", () => {
    const tour = css("../tour/tour.css");
    const body = rule(tour, '.tour-page[data-rail="on"] .tour-body');
    expect(body).toMatch(/grid-template-areas:\s*"stage rail"\s*"panel panel"/);
    expect(rule(walkCss, ".ar")).toMatch(/grid-area:\s*rail/);
  });

  it("tabs filter the list to one agent's steps, with All first and chosen", () => {
    render(<AgentRail events={RAIL_STUB_A} source="fixture" reduced />);
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "All",
      "record",
      "place",
      "walk",
      "Files 4",
    ]);
    expect(tab("All")).toHaveAttribute("aria-selected", "true");
    fireEvent.click(tab("place"));
    expect(tab("place")).toHaveAttribute("aria-selected", "true");
    expect(new Set(shownSeqs())).toEqual(new Set(["place"]));
    fireEvent.click(tab("All"));
    expect(screen.getAllByTestId("rail-line")).toHaveLength(RAIL_STUB_A.length);
  });

  it("switches the tab when the walk lights a step of another agent; a held follow stays", () => {
    vi.useFakeTimers();
    const { rerender } = render(follow("room-3"));
    fireEvent.click(tab("place"));
    // A step keeps its number in the whole run.
    expect(
      screen.getByRole("button", { name: "Step 5: Picked: Look closer at scan S2" }),
    ).toBeVisible();
    // Picking a tab holds the follow like a scroll; Follow the walk lets it go.
    fireEvent.click(screen.getByRole("button", { name: "Follow the walk" }));
    rerender(follow("room-4"));
    expect(tab("walk")).toHaveAttribute("aria-selected", "true");
    expect(lit()).toHaveLength(1);

    fireEvent.click(tab("record"));
    rerender(follow("room-3"));
    expect(tab("record")).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: "Follow the walk" }));
    expect(tab("place")).toHaveAttribute("aria-selected", "true");
    expect(lit()).toHaveLength(1);
    vi.useRealTimers();
  });
});

const lit = () => screen.getAllByTestId("rail-line").filter((l) => l.dataset.lit === "true");

describe("StopStage and StageCaption", () => {
  it("lands the placed ad photo in its room and says Taken here", () => {
    const kitchen = stopOf("room-3");
    render(
      <>
        <StopStage stop={kitchen} plan={FIXTURE_TOUR} reduced={false} photoAlias="P2" />
        <StageCaption stop={kitchen} photoAlias="P2" />
      </>,
    );
    expect(screen.getByTestId("stage-photo")).toHaveAttribute("data-fly", "true");
    expect(screen.getByTestId("stage-caption")).toHaveTextContent("Taken here: Kitchen");
    expect(screen.getByText("Drawn stand-in (fixture)")).toBeInTheDocument();
  });

  it("does not fly under reduced motion: the photo is simply in place", () => {
    render(<StopStage stop={stopOf("room-3")} plan={FIXTURE_TOUR} reduced photoAlias="P2" />);
    expect(screen.getByTestId("stage-photo")).not.toHaveAttribute("data-fly");
    expect(screen.getByTestId("tour-placeholder")).toHaveAttribute("data-motion", "reduced");
  });

  it("frames a room the ad never showed in dashes, with words", () => {
    const bath = stopOf("room-4");
    render(
      <>
        <StopStage stop={bath} plan={FIXTURE_TOUR} reduced={false} unshown />
        <StageCaption stop={bath} unshown />
      </>,
    );
    expect(screen.getByTestId("stage-missing")).toBeInTheDocument();
    expect(screen.queryByTestId("stage-photo")).toBeNull();
    expect(screen.getByTestId("stage-caption")).toHaveTextContent(
      "The ad showed no photo of this room.",
    );
  });

  it("says nothing about the ad when it is not known", () => {
    const { container } = render(<StageCaption stop={stopOf("room-2")} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("walkLook: what the walk reads", () => {
  it("FIXTURE: the E0 evidence fixture, and the placed photo joins its stop", () => {
    const look = walkLook(FIXTURE_TOUR, "");
    expect(look.evidence?.case_id).toBe(EVIDENCE_FIXTURE_A.case_id);
    expect(look.mismatch).toBeNull();
    expect(photoAt(stopOf("room-3"), look.evidence)?.alias).toBe("P2");
    expect(photoAt(stopOf("room-4"), look.evidence)).toBeNull();
  });

  it("LIVE: passes the case's own evidence, images and events through, and draws no stub", () => {
    const livePlan = { ...FIXTURE_TOUR, source: "live" as const };
    expect(walkLook(livePlan, "?demo=b")).toEqual({
      evidence: null,
      images: {},
      events: [],
      mismatch: null,
    });
    const images = { P1: { ad: "blob:a", scan: "blob:b" } };
    const look = walkLook(livePlan, "", { evidence: EVIDENCE_FIXTURE_A, images, events: [] });
    expect(look.images).toBe(images);
    expect(look.evidence).toBe(EVIDENCE_FIXTURE_A);
  });

  it("the copied-ad case: by the plan's own mode, or ?demo=b in FIXTURE", () => {
    expect(walkLook(FIXTURE_TOUR, "?demo=b").mismatch?.banner).toBe(MISMATCH_BANNER);
    const elsewhere = walkLook({ ...FIXTURE_TOUR, mode: "elsewhere" }, "");
    expect(elsewhere.mismatch?.banner).toBeNull();
    expect(elsewhere.mismatch?.officeLine).toBe(OFFICE_LINE);
  });

  it("the office line is the plan's own mode line when set, else the exact fallback", () => {
    expect(OFFICE_LINE).toBe("We can't tell you if it is offered, or at this price.");
    const line = "The home in these photos is listed by its office on CoStar's record.";
    for (const source of ["fixture", "live"] as const) {
      const base = { ...FIXTURE_TOUR, source, mode: "elsewhere" as const };
      expect(walkLook({ ...base, mode_line: line }, "").mismatch?.officeLine).toBe(line);
      expect(walkLook({ ...base, mode_line: null }, "").mismatch?.officeLine).toBe(OFFICE_LINE);
    }
  });
});

const IMG = "data:image/png;base64,AA==";

describe("StageViews: 3D and Real, one large and one in the corner", () => {
  const drawing = <div data-testid="the-drawing">drawing</div>;
  const real = <div data-testid="the-real">real</div>;

  it("Real fills the stage when a real view exists; the drawing sits in the corner, labelled", () => {
    render(<StageViews real={real} drawing={drawing} reduced={false} />);
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-main", "real");
    expect(screen.getByTestId("view-real")).toHaveAttribute("data-role", "main");
    expect(screen.getByTestId("view-drawing")).toHaveAttribute("data-role", "corner");
    expect(screen.getByTestId("view-swap")).toHaveTextContent(DRAWING_LABEL);
  });

  it("tapping the corner window swaps the two, and both stay mounted", () => {
    render(<StageViews real={real} drawing={drawing} reduced={false} />);
    const realNode = screen.getByTestId("the-real");
    fireEvent.click(screen.getByTestId("view-swap"));
    expect(screen.getByTestId("view-drawing")).toHaveAttribute("data-role", "main");
    expect(screen.getByTestId("view-swap")).toHaveTextContent(REAL_LABEL);
    expect(screen.getByTestId("the-real")).toBe(realNode);
    fireEvent.click(screen.getByTestId("view-swap"));
    expect(screen.getByTestId("view-real")).toHaveAttribute("data-role", "main");
  });

  it("the 3D | Real switch does the same", () => {
    render(<StageViews real={real} drawing={drawing} reduced={false} />);
    fireEvent.click(screen.getByRole("button", { name: "3D" }));
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-main", "drawing");
    expect(screen.getByRole("button", { name: "3D" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Real" }));
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-main", "real");
  });

  it("with no real view the drawing fills the stage, Real is off and there is no corner", () => {
    render(<StageViews real={null} drawing={drawing} reduced={false} />);
    expect(screen.getByTestId("view-drawing")).toHaveAttribute("data-role", "main");
    expect(screen.queryByTestId("view-real")).toBeNull();
    expect(screen.queryByTestId("view-swap")).toBeNull();
    expect(screen.getByRole("button", { name: "Real" })).toBeDisabled();
  });

  it("is instant under reduced motion", () => {
    render(<StageViews real={real} drawing={drawing} reduced />);
    expect(screen.getByTestId("stage-views")).toHaveAttribute("data-motion", "reduced");
  });

  it("a real still says what it is", () => {
    render(<RealStill src={IMG} label="Scan view: a render made from the scan" alt="scan" />);
    expect(screen.getByTestId("real-still")).toHaveTextContent("a render made from the scan");
    expect(screen.getByRole("img", { name: "scan" })).toHaveAttribute("src", IMG);
  });
});

describe("ListingPhotos", () => {
  it("shows the record's photos with their source and as-of line", () => {
    render(
      <ListingPhotos
        photos={[
          { src: IMG, alt: "Listing photo 1" },
          { src: IMG, alt: "Listing photo 2" },
        ]}
        site="Homes.com"
        asOf="as of CoStar's last research"
      />,
    );
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByTestId("listing-source")).toHaveTextContent(
      "Homes.com, on CoStar's record · as of CoStar's last research",
    );
  });

  it("draws nothing when the record gives no photos", () => {
    const { container } = render(<ListingPhotos photos={[]} site="Homes.com" asOf="x" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("MismatchAerials: the section 7 copy guards", () => {
  it("names both homes, the office line and the office, with no address", () => {
    render(
      <MismatchAerials
        named={{ capturedOn: "2025-03-02" }}
        pictured={{ capturedOn: "2025-03-02" }}
        source="fixture"
        officeLine={OFFICE_LINE}
        officeName="Fixture Leasing Office"
      />,
    );
    const el = screen.getByTestId("mismatch-aerials");
    expect(screen.getByTestId("aerial-named")).toHaveTextContent(NAMED_LABEL);
    expect(screen.getByTestId("aerial-pictured")).toHaveTextContent(PICTURED_LABEL);
    expect(el).toHaveTextContent(MISMATCH_TITLE);
    expect(screen.getByTestId("office-line")).toHaveTextContent("Fixture Leasing Office");
    // A drawn tile is never captioned as an aerial photo, even when a date is known.
    for (const which of ["named", "pictured"])
      expect(screen.getByTestId(`aerial-${which}-caption`)).toHaveTextContent(
        "Drawn stand-in, not an aerial photo",
      );
    expect(el).not.toHaveTextContent("Vexcel aerial, captured");
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getAllByText("Drawn stand-in (fixture)")).toHaveLength(2);
  });

  it("never says the real one, for rent or available, and shows no street address", () => {
    const copy = [OFFICE_LINE, MISMATCH_BANNER, MISMATCH_TITLE, NAMED_LABEL, PICTURED_LABEL].join(
      " ",
    );
    expect(copy).not.toMatch(/the real one|for rent|available/i);
    expect(copy).not.toMatch(/\d+\s+\w+\s+(st|street|ave|avenue|rd|road|blvd|dr|drive)\b/i);
    expect(copy).not.toMatch(/[\u2013\u2014]/);
  });

  it("shows the real tiles when our server gives them", () => {
    render(
      <MismatchAerials
        named={{ src: "data:image/png;base64,AA==" }}
        pictured={{ src: "data:image/png;base64,AA==" }}
        source="live"
        officeLine={OFFICE_LINE}
      />,
    );
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.queryByText("Drawn stand-in (fixture)")).toBeNull();
    // Each pane carries only its own date: none is borrowed from the other.
    expect(screen.getByTestId("aerial-named-caption")).toHaveTextContent("Vexcel aerial");
    expect(screen.getByTestId("aerial-named-caption")).not.toHaveTextContent("captured");
  });

  it("captions a real tile with its own capture date", () => {
    render(
      <MismatchAerials
        named={{ src: "data:image/png;base64,AA==", capturedOn: "2025-03-02" }}
        pictured={{ src: "data:image/png;base64,AA==" }}
        source="live"
        officeLine={OFFICE_LINE}
      />,
    );
    expect(screen.getByTestId("aerial-named-caption")).toHaveTextContent(
      "Vexcel aerial, captured 2025-03-02",
    );
    expect(screen.getByTestId("aerial-pictured-caption")).not.toHaveTextContent("captured");
  });
});
