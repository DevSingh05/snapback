import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TourStop, TraceEvent, TraceKind } from "../contracts";
import { EVIDENCE_STUB_A } from "../evidence/evidenceStub";
import { FIXTURE_TOUR } from "../tour/fixtureTour";
import { parseTraceEvent } from "../trace/parse";
import { AgentRail } from "./AgentRail";
import { MISMATCH_TITLE, MismatchAerials, NAMED_LABEL, PICTURED_LABEL } from "./MismatchAerials";
import { railCounts, railFiles, railItems } from "./rail";
import { RAIL_STUB_A, RAIL_STUB_B } from "./railStub";
import { StageCaption, StopStage } from "./StopStage";
import { MISMATCH_BANNER, OFFICE_LINE, adViewOf, photoAt, walkLook } from "./walkLook";

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
    expect(stamp(0)).toHaveTextContent("picked by model");
    expect(stamp(0)).toHaveAttribute("data-by", "model");
    expect(lineOf(0)).toHaveTextContent("Search scan S2 on its own.");
    expect(lineOf(0)).toHaveTextContent("from 3 options");
    expect(stamp(1)).toHaveTextContent("picked by rules");
    expect(stamp(2)).toHaveTextContent("random draw");
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
      `${parsed.length} steps, 1 picked by model`,
    );
  });

  it("shows an empty state and no relay, spinner or files when there are no events", () => {
    render(<AgentRail events={[]} source="fixture" reduced={false} />);
    expect(screen.getByTestId("rail-empty")).toBeInTheDocument();
    expect(screen.queryAllByTestId("rail-line")).toHaveLength(0);
    expect(screen.queryAllByTestId("rail-agent")).toHaveLength(0);
    expect(screen.getByTestId("rail-summary")).toHaveTextContent("0 steps, 0 picked by model");
  });

  it("lists only files that a file event carried", () => {
    render(<AgentRail events={RAIL_STUB_A} source="fixture" reduced={false} />);
    const toggle = screen.getByRole("button", { name: "Files (4)" });
    expect(railFiles(RAIL_STUB_A)).toHaveLength(4);
    fireEvent.click(toggle);
    expect(screen.getAllByTestId("files-file")).toHaveLength(4);
  });

  it("shows the matched points for a pick that names a photo, read from the evidence file", () => {
    const onOpen = vi.fn();
    render(
      <AgentRail
        events={RAIL_STUB_A}
        source="fixture"
        evidence={EVIDENCE_STUB_A}
        reduced={false}
        onOpenPhoto={onOpen}
      />,
    );
    const proofs = screen.getAllByTestId("rail-proof");
    expect(proofs[0]).toHaveTextContent("P3: 88 matched points, bar 30");
    expect(proofs[1]).toHaveTextContent("P4: 24 matched points, bar 30");
    fireEvent.click(proofs[0]!);
    expect(onOpen).toHaveBeenCalledWith("P3");
  });

  it("is static under reduced motion, and the phone sheet opens and closes", () => {
    render(<AgentRail events={RAIL_STUB_B} source="fixture" reduced />);
    const rail = screen.getByTestId("agent-rail");
    expect(rail).toHaveAttribute("data-motion", "reduced");
    const sheet = within(rail).getByRole("button", { expanded: false, name: /steps/ });
    fireEvent.click(sheet);
    expect(rail).toHaveAttribute("data-open", "true");
  });

  it("the stub lines carry no model musing: counts come from the events", () => {
    expect(railCounts(RAIL_STUB_A)).toEqual({ steps: RAIL_STUB_A.length, byModel: 2 });
    expect(railItems(RAIL_STUB_A).at(-1)!.agent).toBe("walk");
  });
});

const stopOf = (key: string): TourStop => FIXTURE_TOUR.stops.find((s) => s.key === key)!;

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

describe("walkLook: what the fixture walk reads", () => {
  it("joins placed photos to rooms and counts coverage from them", () => {
    const look = walkLook(FIXTURE_TOUR, "");
    expect(photoAt(stopOf("room-3"), look.evidence)?.alias).toBe("P2");
    expect(photoAt(stopOf("room-4"), look.evidence)).toBeNull();
    expect(adViewOf(stopOf("room-4"), look.evidence, false)).toBe("none_placed");
    expect(look.coverage?.line).toBe("The ad showed 3 of the 4 rooms in this scan.");
    expect(look.coverage).toMatchObject({ total: 4, with_photo: 3, placed: 3, unplaced: 1 });
  });

  it("uses the plan's own coverage when the walk has written one", () => {
    const line = "The ad showed 2 of the 5 rooms in this scan.";
    const cov = {
      counted: "rooms",
      total: 5,
      with_photo: 2,
      placed: 2,
      elsewhere: 0,
      unplaced: 0,
      line,
    } as const;
    expect(walkLook({ ...FIXTURE_TOUR, coverage: cov }, "").coverage?.line).toBe(line);
  });

  it("draws no stub over a live plan", () => {
    const look = walkLook({ ...FIXTURE_TOUR, source: "live" }, "?case=b");
    expect(look).toEqual({ evidence: null, events: [], coverage: null, mismatch: null });
  });

  it("case b: no coverage count for the home the ad names, and no room is marked unshown", () => {
    const look = walkLook(FIXTURE_TOUR, "?case=b");
    expect(look.coverage).toBeNull();
    expect(look.mismatch?.banner).toBe(MISMATCH_BANNER);
    expect(adViewOf(stopOf("room-4"), look.evidence, true)).toBe("unknown");
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
    expect(screen.getByTestId("aerial-named")).toHaveTextContent(
      "Vexcel aerial, captured 2025-03-02",
    );
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getAllByText("Drawn stand-in (fixture)")).toHaveLength(2);
  });

  it("never says the real one, for rent or available, and shows no street address", () => {
    const copy = [OFFICE_LINE, MISMATCH_BANNER, MISMATCH_TITLE, NAMED_LABEL, PICTURED_LABEL].join(
      " ",
    );
    expect(copy).not.toMatch(/the real one|for rent|available/i);
    expect(copy).not.toMatch(/\d+\s+\w+\s+(st|street|ave|avenue|rd|road|blvd|dr|drive)\b/i);
    expect(copy).not.toMatch(/[–—]/);
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
  });
});
