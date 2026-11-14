// What the renter did, kept for this visit so the Finder tab can show it: places opened or
// passed on, filters changed, what was remembered, and notes typed in the Finder. It lives in
// sessionStorage in this browser only. A pick or pass can carry a signal (the place's attributes,
// never which place); when the Finder service runs, the Finder tab sends each signal once.
import type { FinderSignal } from "../contracts";

export interface FinderEvent {
  at: string;
  kind: "opened" | "passed" | "criteria" | "remembered" | "note";
  text: string;
  signal?: FinderSignal;
  sent?: boolean;
}

const KEY = "snapback.finder-events";
const MAX = 60;

export function loadFinderEvents(): FinderEvent[] {
  try {
    const raw: unknown = JSON.parse(window.sessionStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (e): e is FinderEvent =>
        typeof e === "object" &&
        e !== null &&
        typeof (e as FinderEvent).text === "string" &&
        typeof (e as FinderEvent).kind === "string" &&
        typeof (e as FinderEvent).at === "string",
    );
  } catch {
    return [];
  }
}

function save(events: FinderEvent[]): FinderEvent[] {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(events));
  } catch {
    // Storage is blocked: the Finder tab simply starts empty.
  }
  return events;
}

/** Adds one event, newest first. Returns the new list. */
export function recordFinderEvent(
  kind: FinderEvent["kind"],
  text: string,
  signal?: FinderSignal,
): FinderEvent[] {
  const event: FinderEvent = { at: new Date().toISOString(), kind, text };
  if (signal) event.signal = signal;
  return save([event, ...loadFinderEvents()].slice(0, MAX));
}

/** Signals not yet sent to the Finder service, oldest first. */
export function unsentSignals(events: FinderEvent[]): FinderSignal[] {
  return [...events]
    .reverse()
    .filter((e) => e.signal && !e.sent)
    .map((e) => e.signal!);
}

/** Marks every event with a signal as sent. Returns the new list. */
export function markSignalsSent(): FinderEvent[] {
  return save(loadFinderEvents().map((e) => (e.signal ? { ...e, sent: true } : e)));
}

// The conversation with the Finder service: your words and its replies, kept for this tab.
export interface FinderTurn {
  at: string;
  who: "you" | "finder";
  text: string;
  by?: "model" | "policy";
}

const THREAD_KEY = "snapback.finder-thread";

export function loadThread(): FinderTurn[] {
  try {
    const raw: unknown = JSON.parse(window.sessionStorage.getItem(THREAD_KEY) ?? "[]");
    if (!Array.isArray(raw)) return [];
    return raw.filter(
      (t): t is FinderTurn =>
        typeof t === "object" &&
        t !== null &&
        typeof (t as FinderTurn).text === "string" &&
        ((t as FinderTurn).who === "you" || (t as FinderTurn).who === "finder"),
    );
  } catch {
    return [];
  }
}

export function saveThread(thread: FinderTurn[]): void {
  try {
    window.sessionStorage.setItem(THREAD_KEY, JSON.stringify(thread.slice(-MAX)));
  } catch {
    // Storage is blocked: the conversation lasts until the page reloads.
  }
}
