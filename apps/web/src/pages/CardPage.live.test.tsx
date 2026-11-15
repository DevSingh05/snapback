import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CaseTimeline } from "../contracts";

const stream = vi.hoisted(() => ({ open: vi.fn() }));
vi.mock("../case/useTimelineStream", async (orig) => ({
  ...(await orig<typeof import("../case/useTimelineStream")>()),
  openTimelineStream: stream.open,
}));

import { useLiveTimeline } from "./CardPage";

const timeline = (running: boolean, steps = 0): CaseTimeline => ({
  case_id: "AB12",
  source: "fixture",
  mode: "deepagents",
  fell_back: false,
  running,
  steps: Array.from({ length: steps }, (_, i) => ({
    step: i,
    label: `Step ${i}`,
    started_ms: i,
    took_ms: 1,
    result: "Done",
    source: "fixture" as const,
    by: "code" as const,
  })),
  todos: [],
  plan: [],
});

describe("useLiveTimeline", () => {
  it("follows a running agent and reloads the card once it is done", () => {
    stream.open.mockImplementation((o) => {
      o.onTimeline(timeline(false, 3));
      o.onFeed("done");
      return () => {};
    });
    const onDone = vi.fn();
    const { result } = renderHook(() => useLiveTimeline("AB12", "en", timeline(true, 1), onDone));
    expect(stream.open).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(result.current?.steps).toHaveLength(3);
    expect(result.current?.running).toBe(false);
  });

  it("opens nothing for a finished agent, and does not reload", () => {
    stream.open.mockClear();
    const onDone = vi.fn();
    const first = timeline(false, 2);
    const { result } = renderHook(() => useLiveTimeline("AB12", "en", first, onDone));
    expect(stream.open).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(result.current).toBe(first);
  });
});
