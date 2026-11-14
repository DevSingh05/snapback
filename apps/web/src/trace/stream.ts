import type { TraceEvent } from "../contracts";
import { parseTraceEvent } from "./parse";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "lost" | "done";

type OnEvent = (e: TraceEvent) => void;
type OnStatus = (s: StreamStatus) => void;

const MIN_GAP_MS = 400;
const MAX_GAP_MS = 2000;

// Replay compresses the recorded gaps: a quarter of real time, never under 400 ms, never over 2 s.
export function replayDelay(prev: TraceEvent, next: TraceEvent): number {
  const real = Date.parse(next.at) - Date.parse(prev.at);
  const scaled = Number.isFinite(real) ? real / 4 : MIN_GAP_MS;
  return Math.min(MAX_GAP_MS, Math.max(MIN_GAP_MS, scaled));
}

// Timed playback of a trace fixture. The first event is emitted at once. Returns a close function.
export function openReplayTrace(
  events: TraceEvent[],
  onEvent: OnEvent,
  onStatus: OnStatus,
): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;
  const step = (i: number) => {
    if (closed) return;
    const ev = events[i];
    if (!ev) {
      onStatus("done");
      return;
    }
    onEvent(ev);
    const next = events[i + 1];
    if (next) {
      timer = setTimeout(() => step(i + 1), replayDelay(ev, next));
    } else {
      onStatus("done");
    }
  };
  onStatus("live");
  step(0);
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
  };
}

// GET {base}/cases/{id}/trace[?token=] as SSE. EventSource reconnects by itself; repeats after a
// reconnect are dropped by mergeEvent. The stream closes after the verdict line.
export function openLiveTrace(
  base: string,
  caseId: string,
  onEvent: OnEvent,
  onStatus: OnStatus,
  token?: string | null,
): () => void {
  // EventSource cannot set an Authorization header, so API PR #60 takes the case secret as
  // ?token= on the trace route. Main ignores it. A recorded fixture case has no secret.
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  const url = `${base.replace(/\/$/, "")}/cases/${encodeURIComponent(caseId)}/trace${query}`;
  const es = new EventSource(url, { withCredentials: true });
  onStatus("connecting");
  es.addEventListener("open", () => onStatus("live"));
  es.addEventListener("trace", (msg) => {
    const ev = parseTraceEvent((msg as MessageEvent<string>).data);
    if (!ev) return;
    onStatus("live");
    onEvent(ev);
    if (ev.kind === "verdict") {
      es.close();
      onStatus("done");
    }
  });
  es.addEventListener("error", () => {
    if (es.readyState === 2) onStatus("lost");
    else onStatus("reconnecting");
  });
  return () => es.close();
}
