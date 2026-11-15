// The agent's timeline while it works (SNAPBACK_AGENT=deepagents_async). The answer is already on
// screen; this follows the deep agent's plan, hand-offs and notes as they land, and a result
// change ("Updated after more checks") arrives as one more step.
//
// First choice: GET /cases/{id}/timeline/stream (server-sent events), read with fetch so the read
// token travels in an Authorization header and never in the address. If that cannot be had (no
// streaming in this browser or behind this proxy, a 5xx, a dropped connection) it falls back to
// GET /cases/{id}/timeline every second for as long as the agent is running. Either way it stops
// by itself once a timeline says `running: false`. It only reads; nothing here can change a case.
import { useEffect, useState } from "react";

import { apiBase, apiFetchRead } from "../api";
import type { CaseTimeline } from "../contracts";
import { createSseParser } from "../trace/stream";

export type TimelineFeed = "connecting" | "streaming" | "polling" | "done" | "off";

export const POLL_MS = 1000;
const MAX_POLL_FAILURES = 5;

/** The GET the hook makes: null when this browser has no API or no read token for the case. */
export type TimelineGet = (path: string, init: RequestInit) => Promise<Response> | null;

export interface OpenTimelineOptions {
  caseId: string;
  lang?: string;
  onTimeline: (t: CaseTimeline) => void;
  onFeed: (f: TimelineFeed) => void;
  get?: TimelineGet;
  pollMs?: number;
}

const langOf = (lang: string | undefined) => (lang === "es" ? "es" : "en");

function parseTimeline(text: string): CaseTimeline | null {
  try {
    const body = JSON.parse(text) as Partial<CaseTimeline> | null;
    if (!body || typeof body !== "object" || !Array.isArray(body.steps)) return null;
    return body as CaseTimeline;
  } catch {
    return null;
  }
}

/** Follow one case's timeline until the agent is done. Returns a function that stops it. */
export function openTimelineStream(opts: OpenTimelineOptions): () => void {
  const { caseId, onTimeline, onFeed, pollMs = POLL_MS } = opts;
  const get: TimelineGet =
    opts.get ?? ((path, init) => apiFetchRead(path, caseId, init) as Promise<Response> | null);
  const base = `/cases/${encodeURIComponent(caseId)}/timeline`;
  const query = `?lang=${langOf(opts.lang)}`;
  const controller = new AbortController();
  const { signal } = controller;
  let stopped = false;
  let lastRunning: boolean | undefined;

  const stop = (feed: TimelineFeed) => {
    if (stopped) return;
    stopped = true;
    controller.abort();
    onFeed(feed);
  };

  const accept = (t: CaseTimeline) => {
    if (stopped) return;
    lastRunning = t.running === true;
    onTimeline(t);
    if (!lastRunning) stop("done");
  };

  const sleep = (ms: number) =>
    new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, ms);
      signal.addEventListener(
        "abort",
        () => {
          clearTimeout(timer);
          resolve();
        },
        { once: true },
      );
    });

  // True when a stream was opened and read to its end (or until the agent was done).
  async function stream(): Promise<boolean> {
    const pending = get(`${base}/stream${query}`, {
      headers: { Accept: "text/event-stream" },
      signal,
    });
    if (!pending) return false;
    const res = await pending;
    const type = (res.headers.get("Content-Type") ?? "").toLowerCase();
    if (!res.ok || !res.body || !type.startsWith("text/event-stream")) return false;
    onFeed("streaming");
    const parse = createSseParser((m) => {
      if (m.event !== "timeline" || stopped) return;
      const t = parseTimeline(m.data);
      if (t) accept(t);
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (!stopped) {
      const { done, value } = await reader.read();
      if (done) break;
      parse(decoder.decode(value, { stream: true }));
    }
    parse(decoder.decode());
    await reader.cancel().catch(() => {});
    return true;
  }

  async function poll(): Promise<void> {
    onFeed("polling");
    let failures = 0;
    while (!stopped && !signal.aborted) {
      try {
        const pending = get(`${base}${query}`, { signal });
        if (!pending) return stop("off");
        const res = await pending;
        if (res.status >= 400 && res.status < 500) return stop("off");
        if (!res.ok) throw new Error(`The server answered ${res.status}.`);
        const t = parseTimeline(await res.text());
        if (!t) throw new Error("Not a timeline.");
        failures = 0;
        accept(t);
      } catch {
        if (signal.aborted) return;
        if (++failures >= MAX_POLL_FAILURES) return stop("off");
      }
      if (!stopped) await sleep(pollMs);
    }
  }

  (async () => {
    onFeed("connecting");
    try {
      await stream();
    } catch {
      // The stream broke; whatever it had shown stays, and polling picks up from here.
    }
    if (stopped || signal.aborted) return;
    // A stream that ended while the agent was still running (or never opened) is polled instead.
    if (lastRunning === false) return stop("done");
    await poll();
  })();

  return () => {
    stopped = true;
    controller.abort();
  };
}

/** The case's timeline, live. `timeline` is null until the first read lands, and stays null with
 *  no API or no read token for the case (`feed` is then "off"). */
export function useTimelineStream(
  caseId: string | null | undefined,
  lang?: string,
): { timeline: CaseTimeline | null; feed: TimelineFeed } {
  const [timeline, setTimeline] = useState<CaseTimeline | null>(null);
  const [feed, setFeed] = useState<TimelineFeed>("off");
  useEffect(() => {
    setTimeline(null);
    if (!caseId || !apiBase()) {
      setFeed("off");
      return;
    }
    return openTimelineStream({ caseId, lang, onTimeline: setTimeline, onFeed: setFeed });
  }, [caseId, lang]);
  return { timeline, feed };
}
