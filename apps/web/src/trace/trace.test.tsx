import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import traceRaw from "../../../../fixtures/contracts/trace_events.jsonl?raw";
import type { TraceEvent } from "../contracts";
import { mergeEvent, parseFixtureLines, parseTraceEvent } from "./parse";
import {
  createSseParser,
  openLiveTrace,
  openReplayTrace,
  replayDelay,
  type SseMessage,
} from "./stream";
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

const enc = new TextEncoder();
const frame = (i: number) => `id: ${i}\nevent: trace\ndata: ${JSON.stringify(at(i))}\n\n`;

// A controllable text/event-stream response: push() sends a chunk, end() closes it.
function sseResponse(status = 200) {
  let ctl!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      ctl = c;
    },
  });
  return {
    res: new Response(status === 200 ? body : null, {
      status,
      headers: { "Content-Type": "text/event-stream" },
    }),
    push: (t: string) => ctl.enqueue(enc.encode(t)),
    end: () => ctl.close(),
  };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

describe("sse parser", () => {
  const run = (chunks: string[]) => {
    const out: SseMessage[] = [];
    const feed = createSseParser((m) => out.push(m));
    chunks.forEach(feed);
    return out;
  };
  it("joins an event split across chunks, even mid-line", () => {
    const out = run(["id: 3\nev", "ent: trace\nda", 'ta: {"a":1}\n', "\n"]);
    expect(out).toEqual([{ event: "trace", data: '{"a":1}', id: "3" }]);
  });
  it("joins multi-line data with newlines and defaults the event name", () => {
    expect(run(["data: a\ndata: b\n\n"])).toEqual([
      { event: "message", data: "a\nb", id: undefined },
    ]);
  });
  it("skips comments and keeps CRLF and a split CR LF pair", () => {
    const out = run([": hi\r\nid: 1\r", "\ndata: x\r\n\r\n", "data: y\r\r"]);
    expect(out.map((m) => m.data)).toEqual(["x", "y"]);
  });
  it("does not emit an event with no blank line yet, or a comment-only block", () => {
    expect(run(["data: x\n"])).toEqual([]);
    expect(run([": keepalive\n\n"])).toEqual([]);
  });
});

describe("live stream", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });
  const stub = (...responses: Response[]) => {
    const f = vi.fn(async (...args: [string, RequestInit?]) => {
      void args;
      const r = responses.shift();
      if (!r) return new Promise<Response>(() => {});
      return r;
    });
    vi.stubGlobal("fetch", f);
    return f;
  };
  const noop = () => {};

  it("sends the read token in a header, never in the URL, and parses split events", async () => {
    const s = sseResponse();
    const f = stub(s.res);
    const got: number[] = [];
    const close = openLiveTrace("http://api/", "fx-7Q2M", (e) => got.push(e.seq), noop, "RTOK");
    await tick();
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api/cases/fx-7Q2M/trace");
    expect(url).not.toContain("RTOK");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer RTOK");
    const a = frame(0);
    s.push(a.slice(0, 20));
    s.push(a.slice(20) + ": ping\n\n" + "event: trace\ndata: garbage\n\n" + frame(1));
    await tick();
    expect(got).toEqual([0, 1]);
    close();
  });
  it("sends no Authorization header for a fixture case without a token", async () => {
    const f = stub(sseResponse().res);
    const close = openLiveTrace("http://api", "x", noop, noop);
    await tick();
    expect((f.mock.calls[0]![1]!.headers as Record<string, string>).Authorization).toBeUndefined();
    close();
  });
  it("closes after the verdict line and reports done", async () => {
    const s = sseResponse();
    stub(s.res);
    const status: string[] = [];
    openLiveTrace("http://api", "x", noop, (st) => status.push(st), "T");
    await tick();
    s.push(frame(6));
    await tick();
    expect(status.at(-1)).toBe("done");
  });
  it("abort stops reading and sends no more events", async () => {
    const s = sseResponse();
    const f = stub(s.res);
    const got: number[] = [];
    const close = openLiveTrace("http://api", "x", (e) => got.push(e.seq), noop, "T");
    await tick();
    const signal = (f.mock.calls[0]![1] as RequestInit).signal as AbortSignal;
    expect(signal.aborted).toBe(false);
    close();
    expect(signal.aborted).toBe(true);
    try {
      s.push(frame(0));
    } catch {
      // the stream is already torn down
    }
    await tick();
    expect(got).toEqual([]);
    expect(f).toHaveBeenCalledTimes(1);
  });
  it("shows locked on 401 and 403, lost on 404, and does not retry", async () => {
    for (const [code, want] of [
      [401, "locked"],
      [403, "locked"],
      [404, "lost"],
    ] as const) {
      const f = stub(sseResponse(code).res);
      const status: string[] = [];
      openLiveTrace("http://api", "x", noop, (st) => status.push(st), "T");
      await tick();
      expect(status.at(-1)).toBe(want);
      expect(f).toHaveBeenCalledTimes(1);
    }
  });
  it("retries a dropped stream with Last-Event-ID and says reconnecting", async () => {
    const first = sseResponse();
    const second = sseResponse();
    const f = stub(first.res, second.res);
    const status: string[] = [];
    const got: number[] = [];
    const close = openLiveTrace(
      "http://api",
      "x",
      (e) => got.push(e.seq),
      (s) => status.push(s),
      "T",
    );
    await tick();
    first.push(frame(0) + frame(1));
    first.end();
    await tick();
    expect(status.at(-1)).toBe("reconnecting");
    await new Promise((r) => setTimeout(r, 600));
    expect(f).toHaveBeenCalledTimes(2);
    const h = (f.mock.calls[1]![1] as RequestInit).headers as Record<string, string>;
    expect(h["Last-Event-ID"]).toBe("1");
    expect(h.Authorization).toBe("Bearer T");
    second.push(frame(2));
    await tick();
    expect(got).toEqual([0, 1, 2]);
    close();
  });
  it("never gives up while each reconnect opens and delivers, even when reads error", async () => {
    vi.useFakeTimers();
    let n = 0;
    const f = vi.fn(async () => {
      const i = n++;
      let c!: ReadableStreamDefaultController<Uint8Array>;
      const body = new ReadableStream<Uint8Array>({
        start(ctl) {
          c = ctl;
        },
      });
      c.enqueue(enc.encode(frame(0).replace(/id: 0/, `id: ${i}`)));
      queueMicrotask(() => c.error(new Error("reset")));
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", f);
    const status: string[] = [];
    const close = openLiveTrace("http://api", "x", noop, (s) => status.push(s), "T");
    await vi.advanceTimersByTimeAsync(120_000);
    expect(f.mock.calls.length).toBeGreaterThan(12);
    expect(status).not.toContain("lost");
    close();
  });
  it("treats a 200 that is not an event stream as lost, without retrying", async () => {
    const f = stub(new Response("<html></html>", { headers: { "Content-Type": "text/html" } }));
    const status: string[] = [];
    openLiveTrace("http://api", "x", noop, (s) => status.push(s), "T");
    await tick();
    expect(status.at(-1)).toBe("lost");
    expect(f).toHaveBeenCalledTimes(1);
  });
  it("retries a 503 and gives up as lost after the retry limit", async () => {
    vi.useFakeTimers();
    const f = vi.fn(async () => new Response(null, { status: 503 }));
    vi.stubGlobal("fetch", f);
    const status: string[] = [];
    openLiveTrace("http://api", "x", noop, (s) => status.push(s), "T");
    await vi.advanceTimersByTimeAsync(60_000);
    expect(f.mock.calls.length).toBeGreaterThan(2);
    expect(status).toContain("reconnecting");
    expect(status.at(-1)).toBe("lost");
  });
});

describe("CaseNotes", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the notes the agent wrote once a file lands, and nothing before", async () => {
    const { CaseNotes } = await import("./CaseNotes");
    const body = {
      case_id: "A",
      source: "fixture",
      footer: "",
      notes: [
        {
          path: "/case/A/owner.md",
          stem: "owner",
          agent: "owner",
          text: "Owner of record: a private owner",
          written_by: "model",
        },
      ],
    };
    sessionStorage.setItem("snapback.case-read-token.A", "tok");
    vi.stubEnv("VITE_API_URL", "http://api.test");
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(body)));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<CaseNotes caseId="A" events={[at(0)]} />);
    expect(screen.queryByTestId("case-notes")).toBeNull();
    const written: TraceEvent = { ...at(1), kind: "tool", pick: "file: /case/A/owner.md", seq: 9 };
    rerender(<CaseNotes caseId="A" events={[at(0), written]} />);
    expect(await screen.findByText("Owner of record: a private owner")).toBeTruthy();
    expect(screen.getByText("written by model")).toBeTruthy();
    vi.unstubAllEnvs();
  });
});
