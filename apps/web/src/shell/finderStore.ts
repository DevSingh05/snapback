// What the renter did, kept for this visit so the Finder tab can show it: places opened or
// passed on, filters changed, what was remembered, and notes typed in the Finder. It lives in
// sessionStorage in this browser only. Nothing here is sent anywhere, and nothing answers.

export interface FinderEvent {
  at: string;
  kind: "opened" | "passed" | "criteria" | "remembered" | "note";
  text: string;
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

/** Adds one event, newest first. Returns the new list. */
export function recordFinderEvent(kind: FinderEvent["kind"], text: string): FinderEvent[] {
  const next = [{ at: new Date().toISOString(), kind, text }, ...loadFinderEvents()].slice(0, MAX);
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Storage is blocked: the Finder tab simply starts empty.
  }
  return next;
}
