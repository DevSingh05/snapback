import type { TraceEvent } from "../contracts";
import { parseTraceEvent } from "./parse";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "lost" | "locked" | "done";

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

export type SseMessage = { event: string; data: string; id?: string };

// Incremental text/event-stream parser. Feed it decoded text in any chunking; it calls
// onMessage once per blank-line-terminated event. Handles \n, \r\n and \r line ends, `:`
// comments, multi-line data, and a UTF-8 BOM at the start. A trailing event with no blank line
// after it is never emitted (the spec drops it).
export function createSseParser(onMessage: (m: SseMessage) => void): (chunk: string) => void {
  let buffer = "";
  let started = false;
  let skipLf = false;
  let event = "";
  let data: string[] = [];
  let id: string | undefined;

  const line = (l: string) => {
    if (l === "") {
      if (data.length) onMessage({ event: event || "message", data: data.join("\n"), id });
      event = "";
      data = [];
      return;
    }
    if (l.startsWith(":")) return;
    const colon = l.indexOf(":");
    const field = colon === -1 ? l : l.slice(0, colon);
    let value = colon === -1 ? "" : l.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id" && !value.includes("\0")) id = value;
  };

  return (chunk) => {
    if (!started && chunk) {
      started = true;
      if (chunk.charCodeAt(0) === 0xfeff) chunk = chunk.slice(1);
    }
    buffer += chunk;
    let start = 0;
    for (let i = 0; i < buffer.length; i++) {
      const c = buffer[i];
      if (skipLf) {
        skipLf = false;
        if (c === "\n") {
          start = i + 1;
          continue;
        }
      }
      if (c === "\n" || c === "\r") {
        line(buffer.slice(start, i));
        start = i + 1;
        if (c === "\r") {
          if (buffer[i + 1] === "\n") {
            i++;
            start = i + 1;
          } else if (i + 1 >= buffer.length) skipLf = true;
        }
      }
    }
    buffer = buffer.slice(start);
  };
}

const RETRY_BASE_MS = 500;
const RETRY_MAX_MS = 5000;
const RETRY_LIMIT = 8;

// GET {base}/cases/{id}/trace as SSE, read with fetch so the read token travels in an
// Authorization header, never in the address (decisions.md 02:27 and 06:58). fetch does not
// reconnect by itself: a dropped stream or a 5xx retries with a growing delay and a
// Last-Event-ID header; repeats are dropped by mergeEvent. A 401 or 403 shows "locked", other
// 4xx "lost", and neither retries. The stream closes after the verdict line.
export function openLiveTrace(
  base: string,
  caseId: string,
  onEvent: OnEvent,
  onStatus: OnStatus,
  token?: string | null,
): () => void {
  const url = `${base.replace(/\/$/, "")}/cases/${encodeURIComponent(caseId)}/trace`;
  const controller = new AbortController();
  const { signal } = controller;
  let lastId: string | undefined;
  let finished = false;

  const finish = (s: StreamStatus) => {
    finished = true;
    controller.abort();
    onStatus(s);
  };

  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      const t = setTimeout(resolve, ms);
      signal.addEventListener(
        "abort",
        () => {
          clearTimeout(t);
          resolve();
        },
        { once: true },
      );
    });

  // Set once a stream opened, even if it later errors, so the next failure starts the backoff over.
  let opened = false;
  async function attempt(): Promise<void> {
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (lastId !== undefined) headers["Last-Event-ID"] = lastId;
    const res = await fetch(url, { headers, signal, credentials: "include" });
    const type = res.headers.get("Content-Type") ?? "";
    if (res.ok && !type.toLowerCase().startsWith("text/event-stream")) {
      // A proxy or SPA fallback answering 200 with a page: retrying would never help.
      finish("lost");
      return;
    }
    if (!res.ok || !res.body) {
      if (res.status === 401 || res.status === 403) finish("locked");
      else if (res.status >= 400 && res.status < 500) finish("lost");
      return;
    }
    opened = true;
    onStatus("live");
    const parse = createSseParser((m) => {
      if (m.id !== undefined) lastId = m.id;
      if (m.event !== "trace" || finished) return;
      const ev = parseTraceEvent(m.data);
      if (!ev) return;
      onEvent(ev);
      if (ev.kind === "verdict") finish("done");
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (!finished) {
      const { done, value } = await reader.read();
      if (done) break;
      parse(decoder.decode(value, { stream: true }));
    }
    parse(decoder.decode());
    await reader.cancel().catch(() => {});
  }

  async function run() {
    onStatus("connecting");
    for (let tries = 0; !finished && !signal.aborted; tries++) {
      try {
        opened = false;
        await attempt();
        if (finished) return;
      } catch {
        if (signal.aborted) return;
      }
      if (opened) tries = 0; // it was streaming, then ended or broke without a verdict
      if (tries >= RETRY_LIMIT) {
        finish("lost");
        return;
      }
      onStatus("reconnecting");
      await sleep(Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** tries));
    }
  }

  void run();
  return () => {
    finished = true;
    controller.abort();
  };
}
