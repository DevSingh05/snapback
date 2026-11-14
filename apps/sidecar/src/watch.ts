/**
 * iMessage watch alerts (M10, Vidyut's ruling R-M1): the one case where SNAPBACK texts first.
 *
 * - The renter taps "Watch on iMessage" in the web Finder (`POST /finder/{sid}/watch`). The API
 *   publishes `watch_added` for that Finder session with a one-time 4-digit code, and the web
 *   shows "Text WATCH 4821 to SNAPBACK". Texting exactly that, from an allowlisted thread,
 *   links the thread to the Finder session. A code links once and expires after CODE_TTL_MS.
 * - When `match_found` for that session arrives on the events stream, the thread gets one
 *   code-written message: "Simulated" when the event is, the record line, and the place's
 *   Walk it first link. At most MAX_PUSHES_A_DAY in any 24 hours per thread, and the count
 *   survives a stop and a new link.
 * - A stop word (stop, unsubscribe, cancel, end, quit) as a short message ends it for good.
 * - Every other thread stays reply-only. Links live in memory with the live thread: no phone
 *   number, handle or thread id is written anywhere, and a restart forgets them.
 * - Only the exact "watch" or "watch <code>" is a command. Anything else, "Watch out, is this
 *   real?" included, goes to the ad check.
 */

import type { PhotonContent, PhotonSpace } from "./photon";

export const MAX_PUSHES_A_DAY = 3;
export const DAY_MS = 24 * 60 * 60 * 1000;
export const CODE_TTL_MS = 60 * 60 * 1000;

/** An event from the API's events stream, as far as the sidecar reads it. */
export type StreamEvent = {
  id: string;
  kind: string;
  source?: string; // "renter" | "pipeline" | "simulated"
  subject: string; // match_found: the place; watch_added: the Finder session
  payload: {
    session?: string;
    code?: number; // watch_added: the one-time link code the web shows
    fits_brief?: boolean;
    rent_from?: number;
    has_scan?: boolean;
  };
};

const LINK = /^\s*watch\s+(\d{4})\s*[.!]?\s*$/i;
const BARE_WATCH = /^\s*watch\s*[.!]?\s*$/i;
const STOP = /^\s*(stop|unsubscribe|cancel|end|quit)\b/i;

/** "stop", "Stop texting me", "unsubscribe": short, no digits, no link. An ad that happens to
 * start with "End unit" has a price in it, so it still goes to the check. */
function isStop(text: string): boolean {
  return STOP.test(text) && text.length <= 60 && !/\d/.test(text) && !/https?:|www\./i.test(text);
}

/** The text a command can be in: plain text, or a swipe-reply wrapping text. */
export function commandText(content: PhotonContent): string | null {
  if (content.type === "text" && "text" in content) return content.text;
  if (content.type === "reply" && "content" in content) return commandText(content.content);
  return null;
}

type Link = { session: string; space: PhotonSpace };

/** The links this sidecar holds. In memory only. */
export class WatchBook {
  private codes = new Map<string, { session: string; at: number }>();
  private byThread = new Map<string, Link>();
  private bySession = new Map<string, string>();
  private sent = new Map<string, number[]>(); // per thread, kept across stop and re-link
  private seen = new Set<string>(); // event ids already acted on

  constructor(private now: () => number = Date.now) {}

  size(): number {
    return this.byThread.size;
  }

  /** A `watch_added` with a code: the code may link a thread for CODE_TTL_MS. */
  offer(event: StreamEvent): void {
    const { session, code } = event.payload;
    if (typeof session !== "string" || typeof code !== "number") return;
    this.codes.set(String(code).padStart(4, "0"), { session, at: this.now() });
  }

  /** Link the thread to the session the code was issued for. Null if unknown or expired. */
  link(space: PhotonSpace, code: string): string | null {
    const offered = this.codes.get(code);
    if (!offered || this.now() - offered.at > CODE_TTL_MS) return null;
    this.codes.delete(code); // a code links once
    this.stop(space.id);
    this.byThread.set(space.id, { session: offered.session, space });
    this.bySession.set(offered.session, space.id);
    return offered.session;
  }

  /** End the thread's watch for good. False if it had none. */
  stop(threadId: string): boolean {
    const link = this.byThread.get(threadId);
    if (!link) return false;
    this.byThread.delete(threadId);
    this.bySession.delete(link.session);
    return true;
  }

  /** True the first time an event id is seen: a replayed event is never acted on twice. */
  firstTime(eventId: string): boolean {
    if (!eventId || this.seen.has(eventId)) return !eventId;
    this.seen.add(eventId);
    return true;
  }

  /** The thread to text for this session, if it may be texted now (and count the text). */
  claim(session: string): PhotonSpace | null {
    const threadId = this.bySession.get(session);
    const link = threadId ? this.byThread.get(threadId) : undefined;
    if (!threadId || !link) return null;
    const now = this.now();
    const recent = (this.sent.get(threadId) ?? []).filter((at) => now - at < DAY_MS);
    if (recent.length >= MAX_PUSHES_A_DAY) {
      this.sent.set(threadId, recent);
      return null;
    }
    this.sent.set(threadId, [...recent, now]);
    return link.space;
  }
}

/** The reply to a watch command or a stop word, or null when it is neither (an ad to check). */
export function answerCommand(
  content: PhotonContent,
  space: PhotonSpace,
  book: WatchBook,
  webUrl: string,
  log: (line: string) => void = () => {},
): string | null {
  const text = commandText(content);
  if (text === null) return null;
  const finder = `${webUrl.replace(/\/$/, "")}/map`;
  if (isStop(text)) {
    return book.stop(space.id)
      ? "Stopped. SNAPBACK will not text you again. To watch again, start from the Finder."
      : "Nothing to stop. SNAPBACK only texts you first when you link a watch.";
  }
  const linked = LINK.exec(text);
  if (linked?.[1]) {
    if (book.link(space, linked[1]) === null) {
      return `That code did not match a watch. Get a new one from the Finder: ${finder}`;
    }
    log("[sidecar] linked a thread to a Finder watch");
    return (
      "Watching. SNAPBACK will text you here when a researched place fits your brief, at most " +
      `${MAX_PUSHES_A_DAY} times a day. Text stop to end it.`
    );
  }
  if (BARE_WATCH.test(text)) {
    return `To watch, set your brief in the Finder and tap Watch on iMessage, then text the code it shows: ${finder}`;
  }
  return null;
}

/** The one message a match sends. Code-written: no model, no listing text, no address. */
export function matchText(event: StreamEvent, webUrl: string): string {
  const web = webUrl.replace(/\/$/, "");
  const simulated = event.source === "simulated" ? "Simulated. " : "";
  const rent = event.payload.rent_from;
  const parts: string[] = [];
  if (typeof rent === "number") parts.push(`from $${rent.toLocaleString("en-US")} a month`);
  if (event.payload.has_scan) parts.push("a 3D scan on record");
  const record = parts.length
    ? ` On record: ${parts.join(", ")} (as of CoStar's last research).`
    : " (As of CoStar's last research.)";
  const link = event.payload.has_scan
    ? `Walk it first: ${web}/tour/${encodeURIComponent(event.subject)}`
    : `See it on the map: ${web}/map`;
  return `${simulated}A place fits your watch.${record} ${link} Check it before you pay anyone.`;
}

/** Act on the events stream: codes from watch_added, one text per match_found, within the
 * cap. Nothing else is sent. Returns the last event id seen, for Last-Event-ID. */
export async function pushEvents(
  events: AsyncIterable<StreamEvent>,
  book: WatchBook,
  webUrl: string,
  log: (line: string) => void = () => {},
  onId: (id: string) => void = () => {},
): Promise<void> {
  for await (const event of events) {
    if (event.id) onId(event.id);
    if (!book.firstTime(event.id)) continue;
    if (event.kind === "watch_added") {
      book.offer(event);
      continue;
    }
    if (event.kind !== "match_found" || event.payload.fits_brief === false) continue;
    const session = event.payload.session;
    const space = typeof session === "string" ? book.claim(session) : null;
    if (!space) continue;
    try {
      await space.send(matchText(event, webUrl));
      log("[sidecar] sent a watch match");
    } catch {
      log("[sidecar] a watch match could not be sent");
    }
  }
}

/** The API's events stream (`GET /events/stream`). The token goes in a header, never the
 * address. Send the last id seen as `lastEventId` so a reconnect does not replay. Ends when
 * the stream ends; the caller reconnects. */
export async function* readEvents(
  apiUrl: string,
  token: string,
  get: typeof fetch = fetch,
  lastEventId?: string,
): AsyncGenerator<StreamEvent> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (lastEventId) headers["Last-Event-ID"] = lastEventId;
  const res = await get(`${apiUrl.replace(/\/$/, "")}/events/stream`, { headers });
  if (!res.ok || !res.body) throw new Error(`events stream answered ${res.status}`);
  const decoder = new TextDecoder();
  let buffer = "";
  for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
    buffer += decoder.decode(chunk, { stream: true });
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const lines = block.split("\n");
      const id =
        lines
          .find((line) => line.startsWith("id:"))
          ?.slice(3)
          .trim() ?? "";
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data) continue;
      try {
        const event = JSON.parse(data) as StreamEvent;
        yield { ...event, id: event.id || id };
      } catch {
        // a line we cannot read is skipped, never echoed
      }
    }
  }
}
