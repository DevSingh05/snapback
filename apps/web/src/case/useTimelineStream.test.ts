import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CaseTimeline } from "../contracts";
import { openTimelineStream, type TimelineFeed, type TimelineGet } from "./useTimelineStream";

const timeline = (running: boolean, steps: number): CaseTimeline => ({
  case_id: "7Q2M",
  source: "fixture",
  mode: "deepagents",
  fell_back: false,
  running,
  steps: Array.from({ length: steps }, (_, i) => ({
    step: i,
    label: `Step ${i}`,
    started_ms: i * 100,
    took_ms: 100,
    result: "Done.",
    source: "fixture",
    by: "agent",
  })),
  todos: [],
  plan: [],
});

const sseBody = (...frames: CaseTimeline[]) =>
  frames.map((t) => `event: timeline\ndata: ${JSON.stringify(t)}\n\n`).join("");

function sseResponse(text: string, chunk = 40): Response {
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunk) controller.enqueue(bytes.slice(i, i + chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const json = (t: CaseTimeline) =>
  new Response(JSON.stringify(t), { status: 200, headers: { "Content-Type": "application/json" } });

function run(get: TimelineGet, pollMs = 1000) {
  const seen: CaseTimeline[] = [];
  const feeds: TimelineFeed[] = [];
  const close = openTimelineStream({
    caseId: "7Q2M",
    get,
    pollMs,
    onTimeline: (t) => seen.push(t),
    onFeed: (f) => feeds.push(f),
  });
  return { seen, feeds, close };
}

const settle = async () => {
  for (let i = 0; i < 20; i++) await vi.advanceTimersByTimeAsync(0);
};

describe("openTimelineStream", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("follows the stream, in order and across chunk boundaries, and stops when the agent is done", async () => {
    const calls: string[] = [];
    const get: TimelineGet = (path) => {
      calls.push(path);
      return Promise.resolve(
        sseResponse(sseBody(timeline(true, 1), timeline(true, 3), timeline(false, 5))),
      );
    };
    const { seen, feeds } = run(get);
    await settle();
    expect(seen.map((t) => t.steps.length)).toEqual([1, 3, 5]);
    expect(feeds).toEqual(["connecting", "streaming", "done"]);
    expect(calls).toEqual(["/cases/7Q2M/timeline/stream?lang=en"]); // never polled
  });

  it("falls back to a 1 s poll when the stream cannot be had, until running is false", async () => {
    const seen: number[] = [];
    let n = 0;
    const get: TimelineGet = (path) => {
      if (path.includes("/stream")) return Promise.resolve(new Response("nope", { status: 502 }));
      n += 1;
      const t = timeline(n < 3, n);
      seen.push(n);
      return Promise.resolve(json(t));
    };
    const out = run(get);
    await settle();
    expect(seen).toEqual([1]); // the first poll is at once
    await vi.advanceTimersByTimeAsync(999);
    expect(seen).toEqual([1]);
    await vi.advanceTimersByTimeAsync(1);
    expect(seen).toEqual([1, 2]);
    await vi.advanceTimersByTimeAsync(1000);
    await settle();
    expect(seen).toEqual([1, 2, 3]);
    expect(out.seen.map((t) => t.running)).toEqual([true, true, false]);
    expect(out.feeds).toEqual(["connecting", "polling", "done"]);
    await vi.advanceTimersByTimeAsync(5000);
    expect(seen).toEqual([1, 2, 3]); // done means done
  });

  it("polls on when a stream drops while the agent is still running", async () => {
    let polls = 0;
    const get: TimelineGet = (path) => {
      if (path.includes("/stream")) {
        return Promise.resolve(sseResponse(sseBody(timeline(true, 2))));
      }
      polls += 1;
      return Promise.resolve(json(timeline(false, 4)));
    };
    const { seen, feeds } = run(get);
    await settle();
    expect(polls).toBe(1);
    expect(seen.map((t) => t.steps.length)).toEqual([2, 4]);
    expect(feeds).toEqual(["connecting", "streaming", "polling", "done"]);
  });

  it("does nothing, and says off, with no read token (the GET gives null)", async () => {
    const { seen, feeds } = run(() => null);
    await settle();
    expect(seen).toEqual([]);
    expect(feeds).toEqual(["connecting", "polling", "off"]);
  });

  it("stops polling after a run of failures, and on a 4xx at once", async () => {
    let hits = 0;
    const down: TimelineGet = () => {
      hits += 1;
      return Promise.reject(new Error("offline"));
    };
    const a = run(down);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(hits).toBe(6); // the stream try, then five polls
    expect(a.feeds.at(-1)).toBe("off");

    const b = run((path) =>
      Promise.resolve(
        path.includes("/stream")
          ? new Response("", { status: 403 })
          : new Response("", { status: 403 }),
      ),
    );
    await settle();
    expect(b.feeds).toEqual(["connecting", "polling", "off"]);
  });

  it("closing stops everything", async () => {
    let polls = 0;
    const get: TimelineGet = (path) => {
      if (path.includes("/stream")) return Promise.resolve(new Response("", { status: 500 }));
      polls += 1;
      return Promise.resolve(json(timeline(true, polls)));
    };
    const { close } = run(get);
    await settle();
    close();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(polls).toBe(1);
  });

  it("asks for Spanish when the page is Spanish, and never puts a token in the address", async () => {
    const paths: string[] = [];
    const out: TimelineFeed[] = [];
    openTimelineStream({
      caseId: "7Q2M",
      lang: "es",
      pollMs: 1000,
      get: (p) => {
        paths.push(p);
        return Promise.resolve(sseResponse(sseBody(timeline(false, 1))));
      },
      onTimeline: () => {},
      onFeed: (f) => out.push(f),
    });
    await settle();
    expect(paths).toEqual(["/cases/7Q2M/timeline/stream?lang=es"]);
    expect(paths[0]).not.toMatch(/token/i);
  });
});

describe("openTimelineStream never follows a run forever", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows a stopped run, with one step that says why, when no step lands for too long", async () => {
    // The server says "running" and then nothing changes: a stream that stays open.
    const get: TimelineGet = () => Promise.resolve(json(timeline(true, 2)));
    const seen: CaseTimeline[] = [];
    const feeds: TimelineFeed[] = [];
    openTimelineStream({
      caseId: "7Q2M",
      get,
      pollMs: 1000,
      stallMs: 5000,
      onTimeline: (t) => seen.push(t),
      onFeed: (f) => feeds.push(f),
    });
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(6000);
    const end = seen.at(-1)!;
    expect(end.running).toBe(false);
    expect(end.fell_back).toBe(true);
    expect(end.steps.at(-1)!.label).toBe(
      "The deep agent stopped: it stopped answering; code set the verdict",
    );
    expect(end.steps).toHaveLength(3);
    expect(feeds.at(-1)).toBe("done");
  });

  it("a run that keeps landing steps is not cut off", async () => {
    let n = 2;
    const get: TimelineGet = () => Promise.resolve(json(timeline(true, n++)));
    const seen: CaseTimeline[] = [];
    openTimelineStream({
      caseId: "7Q2M",
      get,
      pollMs: 1000,
      stallMs: 5000,
      onTimeline: (t) => seen.push(t),
      onFeed: () => {},
    });
    await vi.advanceTimersByTimeAsync(20_000);
    expect(seen.every((t) => t.running)).toBe(true);
  });

  it("shows the run as stopped when the feed is lost while the agent was still working", async () => {
    let calls = 0;
    const get: TimelineGet = () => {
      calls++;
      if (calls <= 2) return Promise.resolve(json(timeline(true, 1))); // the stream try, then a poll
      return Promise.reject(new Error("offline"));
    };
    const seen: CaseTimeline[] = [];
    openTimelineStream({
      caseId: "7Q2M",
      get,
      pollMs: 100,
      onTimeline: (t) => seen.push(t),
      onFeed: () => {},
    });
    await vi.advanceTimersByTimeAsync(2000);
    const end = seen.at(-1)!;
    expect(end.running).toBe(false);
    expect(end.steps.at(-1)!.label).toBe(
      "The deep agent stopped: the connection to it was lost; code set the verdict",
    );
  });
});
