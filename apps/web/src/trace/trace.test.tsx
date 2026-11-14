import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import traceRaw from "../../../../fixtures/contracts/trace_events.jsonl?raw";
import type { TraceEvent } from "../contracts";
import { mergeEvent, parseFixtureLines, parseTraceEvent } from "./parse";
import { openLiveTrace, openReplayTrace, replayDelay } from "./stream";
import { TracePanel } from "./TracePanel";

const events = parseFixtureLines(traceRaw);
const at = (i: number): TraceEvent => events[i] as TraceEvent;

const MIN = '{"case_id":"a","seq":0,"at":"x","kind":"tool","reason":"r","source":"live"}';

describe("parsing", () => {
  it("reads the 7 fixture lines", () => {
    expect(events).toHaveLength(7);
    expect(at(0).choice).toBe("which_checks");
  });
  it("returns null for junk and for the wrong shape", () => {
    expect(parseTraceEvent("not json")).toBeNull();
    expect(parseTraceEvent('{"seq":1}')).toBeNull();
    expect(parseTraceEvent(MIN.replace('"seq":0', '"seq":-1'))).toBeNull();
    expect(parseTraceEvent(MIN.replace('"tool"', '"banana"'))).toBeNull();
  });
  it("defaults options to an empty list", () => {
    expect(parseTraceEvent(MIN)?.options).toEqual([]);
  });
});

describe("mergeEvent", () => {
  it("drops a repeated seq and keeps seq order", () => {
    let list: TraceEvent[] = [];
    for (const e of [at(2), at(0), at(0), at(1)]) list = mergeEvent(list, e);
    expect(list.map((e) => e.seq)).toEqual([0, 1, 2]);
  });
});

describe("TracePanel with a duplicate seq", () => {
  it("renders 7 lines in order", () => {
    const withDup = [...events.slice(0, 3), at(2), ...events.slice(3)];
    render(<TracePanel caseId="fx-7Q2M" initialEvents={withDup} mode="static" />);
    const lines = screen.getAllByTestId("trace-line");
    expect(lines).toHaveLength(7);
    expect(lines.map((l) => l.getAttribute("data-seq"))).toEqual([
      "0",
      "1",
      "2",
      "3",
      "4",
      "5",
      "6",
    ]);
  });
  it("marks the 5 bounded choices and shows options, pick, reason", () => {
    render(<TracePanel caseId="fx-7Q2M" initialEvents={events} mode="static" />);
    const lines = screen.getAllByTestId("trace-line");
    expect(lines.filter((l) => l.dataset.choice)).toHaveLength(5);
    const spot = lines[3] as HTMLElement;
    expect(within(spot).getByText(/Which spot/i)).toBeInTheDocument();
    expect(within(spot).getByTestId("trace-pick")).toHaveTextContent("fx-spot-window-n");
    expect(within(spot).getAllByTestId("trace-option")).toHaveLength(5);
    expect(within(spot).getByText(/overlaps listing photo 2/)).toBeInTheDocument();
  });
  it("says on every choice line who picked, and treats an unstamped line as the rules", () => {
    const stamped = (by: "model" | "policy"): TraceEvent => ({ ...at(0), chosen_by: by });
    render(
      <TracePanel
        caseId="fx-7Q2M"
        initialEvents={[stamped("model"), { ...stamped("policy"), seq: 1 }]}
        mode="static"
      />,
    );
    const labels = screen.getAllByTestId("trace-by");
    expect(labels.map((l) => l.textContent)).toEqual(["picked by model", "picked by rules"]);
    expect(parseTraceEvent(MIN)?.chosen_by).toBe("policy");
    expect(
      parseTraceEvent(MIN.replace('"source"', '"chosen_by":"model","source"'))?.chosen_by,
    ).toBe("model");
  });
  it("calls the random spot draw a random draw, not a rule", () => {
    render(<TracePanel caseId="fx-7Q2M" initialEvents={[at(3)]} mode="static" />);
    expect(at(3).choice).toBe("which_spot");
    expect(screen.getByTestId("trace-by")).toHaveTextContent("random draw");
  });
  it("labels the plan's choice", () => {
    const next: TraceEvent = { ...at(0), choice: "next_check", chosen_by: "model" };
    render(<TracePanel caseId="fx-7Q2M" initialEvents={[next]} mode="static" />);
    expect(screen.getByText("Which check next")).toBeInTheDocument();
  });
  it("shows the FIXTURE chip", () => {
    render(<TracePanel caseId="fx-7Q2M" initialEvents={events} mode="static" />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });
  it("shows waiting for your OK when the last line is a hitl with no pick", () => {
    const waiting: TraceEvent = { ...at(4), pick: null };
    render(
      <TracePanel
        caseId="fx-7Q2M"
        initialEvents={[...events.slice(0, 4), waiting]}
        mode="static"
      />,
    );
    expect(screen.getByTestId("trace-waiting")).toHaveTextContent(/waiting for your OK/i);
  });
  it("does not show waiting once the human has answered", () => {
    render(<TracePanel caseId="fx-7Q2M" initialEvents={events} mode="static" />);
    expect(screen.queryByTestId("trace-waiting")).toBeNull();
  });
});

describe("fixture replay timing", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("emits events one at a time with the compressed gap", () => {
    const got: number[] = [];
    openReplayTrace(
      events,
      (e) => got.push(e.seq),
      () => {},
    );
    expect(got).toEqual([0]);
    vi.advanceTimersByTime(replayDelay(at(0), at(1)) - 1);
    expect(got).toEqual([0]);
    vi.advanceTimersByTime(1);
    expect(got).toEqual([0, 1]);
    vi.advanceTimersByTime(60_000);
    expect(got).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });
  it("caps long real gaps and floors short ones", () => {
    expect(replayDelay(at(4), at(5))).toBeLessThanOrEqual(2500);
    expect(replayDelay(at(0), at(1))).toBeGreaterThanOrEqual(400);
  });
  it("stops when closed", () => {
    const got: number[] = [];
    const close = openReplayTrace(
      events,
      (e) => got.push(e.seq),
      () => {},
    );
    close();
    vi.advanceTimersByTime(60_000);
    expect(got).toEqual([0]);
  });
  it("panel fills up over time in replay mode", () => {
    render(<TracePanel caseId="fx-7Q2M" mode="replay" replaySource={events} />);
    expect(screen.getAllByTestId("trace-line")).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(screen.getAllByTestId("trace-line")).toHaveLength(7);
    expect(screen.getByTestId("trace-status")).toHaveTextContent(/done/i);
  });
});

class FakeES {
  static last: FakeES;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  readyState = 0;
  closed = false;
  constructor(public url: string) {
    FakeES.last = this;
  }
  addEventListener(t: string, f: (e: MessageEvent) => void) {
    (this.listeners[t] ??= []).push(f);
  }
  emit(t: string, data?: string) {
    for (const f of this.listeners[t] ?? []) f({ data } as MessageEvent);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
}

describe("live stream", () => {
  beforeEach(() => vi.stubGlobal("EventSource", FakeES));
  afterEach(() => vi.unstubAllGlobals());

  it("opens /cases/{id}/trace and parses each trace event", () => {
    const got: number[] = [];
    openLiveTrace(
      "http://api/",
      "fx-7Q2M",
      (e) => got.push(e.seq),
      () => {},
    );
    expect(FakeES.last.url).toBe("http://api/cases/fx-7Q2M/trace");
    FakeES.last.emit("trace", JSON.stringify(at(0)));
    FakeES.last.emit("trace", "garbage");
    FakeES.last.emit("trace", JSON.stringify(at(1)));
    expect(got).toEqual([0, 1]);
  });
  it("closes itself after the verdict line and on close()", () => {
    const status: string[] = [];
    const close = openLiveTrace(
      "http://api",
      "x",
      () => {},
      (s) => status.push(s),
    );
    FakeES.last.emit("trace", JSON.stringify(at(6)));
    expect(FakeES.last.closed).toBe(true);
    expect(status.at(-1)).toBe("done");
    close();
  });
  it("reports reconnecting on a transient error and lost when the source is closed", () => {
    const status: string[] = [];
    openLiveTrace(
      "http://api",
      "x",
      () => {},
      (s) => status.push(s),
    );
    FakeES.last.readyState = 0;
    FakeES.last.emit("error");
    expect(status.at(-1)).toBe("reconnecting");
    FakeES.last.readyState = 2;
    FakeES.last.emit("error");
    expect(status.at(-1)).toBe("lost");
  });
});
