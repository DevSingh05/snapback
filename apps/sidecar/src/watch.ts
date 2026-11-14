/**
 * iMessage watch alerts (M10, Vidyut's ruling R-M1): the one case where SNAPBACK texts first.
 *
 * - A renter texts "watch ..." in their own (allowlisted) thread. Code reads budget, beds,
 *   parking, pets and no walk-up from it; nothing else is read. A watch code cannot read gets
 *   the map link instead, and nothing is saved.
 * - When a `match_found` event for that watch arrives on the API's events stream, the thread
 *   gets one code-written message. At most MAX_PUSHES_A_DAY in any 24 hours, per thread.
 * - "stop" ends the watch for good: no message goes out for it again. A new "watch" starts a
 *   new one, and only the renter can send that.
 * - Every other thread stays reply-only. A watch lives in memory with the live thread it came
 *   from: no phone number, handle or thread id is written anywhere, and a restart forgets it.
 */

import { randomBytes } from "node:crypto";

import type { PhotonSpace } from "./photon";

export const MAX_PUSHES_A_DAY = 3;
const DAY_MS = 24 * 60 * 60 * 1000;

/** The part of the API's `RenterBrief` a text can carry. Only what code read is set. */
export type WatchBrief = {
  max_rent_month?: number;
  beds_min?: number;
  needs_parking?: boolean;
  pets?: boolean;
  needs_no_walkup?: boolean;
};

/** The events-stream `match_found` event, as far as the sidecar reads it. */
export type MatchEvent = {
  id: string;
  kind: string;
  subject: string;
  payload: { session?: string; fits_brief?: boolean; rent_from?: number; has_scan?: boolean };
};

const WATCH = /^\s*watch\b/i;
const STOP = /^\s*stop\s*[.!]?\s*$/i;

/** The brief in a "watch ..." text, `{}` if code read nothing, or null if it is not a watch. */
export function parseWatch(text: string): WatchBrief | null {
  if (!WATCH.test(text)) return null;
  const words = text.slice(0, 300);
  const brief: WatchBrief = {};
  const money =
    /(?:\$|under|below|up to|max(?:imum)?|budget)\s*\$?\s*(\d{1,2},\d{3}|\d{3,5})\b/i.exec(words);
  if (money?.[1]) brief.max_rent_month = Number(money[1].replace(",", ""));
  const beds = /\b(\d{1,2})\s*\+?\s*(?:beds?|bedrooms?|br|bd)\b/i.exec(words);
  if (beds?.[1]) brief.beds_min = Number(beds[1]);
  else if (/\bstudio\b/i.test(words)) brief.beds_min = 0;
  if (/\b(?:parking|garage)\b/i.test(words)) brief.needs_parking = true;
  if (/\b(?:pets?|dogs?|cats?)\b/i.test(words) && !/\bno\s+pets?\b/i.test(words)) brief.pets = true;
  if (/\bno\s*walk-?\s*ups?\b|\belevator\b/i.test(words)) brief.needs_no_walkup = true;
  return brief;
}

function describe(brief: WatchBrief): string {
  const parts: string[] = [];
  if (brief.beds_min === 0) parts.push("a studio or larger");
  else if (brief.beds_min !== undefined) parts.push(`${brief.beds_min}+ beds`);
  if (brief.max_rent_month !== undefined) {
    parts.push(`up to $${brief.max_rent_month.toLocaleString("en-US")}`);
  }
  if (brief.needs_parking) parts.push("parking");
  if (brief.pets) parts.push("pets allowed");
  if (brief.needs_no_walkup) parts.push("no walk-up");
  return parts.join(", ");
}

type Watch = { session: string; space: PhotonSpace; brief: WatchBrief; sent: number[] };

/** The watches this sidecar holds, by thread. In memory only. */
export class WatchBook {
  private byThread = new Map<string, Watch>();
  private bySession = new Map<string, string>();

  constructor(private now: () => number = Date.now) {}

  size(): number {
    return this.byThread.size;
  }

  /** Save (or replace) the thread's watch. Returns its session id, which events carry. */
  add(space: PhotonSpace, brief: WatchBrief): string {
    this.stop(space.id);
    const session = `w-${randomBytes(6).toString("hex")}`;
    this.byThread.set(space.id, { session, space, brief, sent: [] });
    this.bySession.set(session, space.id);
    return session;
  }

  /** End the thread's watch for good. False if it had none. */
  stop(threadId: string): boolean {
    const watch = this.byThread.get(threadId);
    if (!watch) return false;
    this.byThread.delete(threadId);
    this.bySession.delete(watch.session);
    return true;
  }

  /** The thread to text for this session, if it may be texted now (and count the text). */
  claim(session: string): PhotonSpace | null {
    const threadId = this.bySession.get(session);
    const watch = threadId ? this.byThread.get(threadId) : undefined;
    if (!watch) return null;
    const now = this.now();
    watch.sent = watch.sent.filter((at) => now - at < DAY_MS);
    if (watch.sent.length >= MAX_PUSHES_A_DAY) return null;
    watch.sent.push(now);
    return watch.space;
  }
}

/** The reply to "watch" or "stop", or null when the text is neither (it is an ad to check). */
export function answerCommand(
  text: string,
  space: PhotonSpace,
  book: WatchBook,
  webUrl: string,
  log: (line: string) => void = () => {},
): string | null {
  const map = `${webUrl.replace(/\/$/, "")}/map`;
  if (STOP.test(text)) {
    return book.stop(space.id)
      ? "Stopped. SNAPBACK will not text you again. Text watch to start a new one."
      : "Nothing to stop. SNAPBACK only texts you first when you ask it to watch.";
  }
  const brief = parseWatch(text);
  if (brief === null) return null;
  if (Object.keys(brief).length === 0) {
    return (
      "Tell me what to watch for, like: watch 2 beds under $1,500 with parking. " +
      `Or look around the map: ${map}`
    );
  }
  const session = book.add(space, brief);
  log(`[sidecar] watch added (${session})`);
  return (
    `Watching for: ${describe(brief)}. SNAPBACK will text you here when a researched place ` +
    `fits, at most ${MAX_PUSHES_A_DAY} times a day. Text stop to end it.`
  );
}

/** The one message a match sends. Code-written: no model, no listing text, no address. */
export function matchText(event: MatchEvent, webUrl: string): string {
  const rent = event.payload.rent_from;
  const from = typeof rent === "number" ? `, from $${rent.toLocaleString("en-US")} a month` : "";
  const scan = event.payload.has_scan ? ", with a 3D tour" : "";
  return (
    `A place fits your watch${from}${scan}. As of CoStar's last research. ` +
    `See it, and check it before you pay anyone: ${webUrl.replace(/\/$/, "")}/map`
  );
}

/** Send each match to the thread that asked for it, within the cap. Nothing else is sent. */
export async function pushMatches(
  events: AsyncIterable<MatchEvent>,
  book: WatchBook,
  webUrl: string,
  log: (line: string) => void = () => {},
): Promise<void> {
  for await (const event of events) {
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

/** The API's events stream (`GET /events/stream`), match_found only. The token goes in a
 * header, never the address. Ends when the stream ends; the caller reconnects. */
export async function* readEvents(
  apiUrl: string,
  token: string,
  get: typeof fetch = fetch,
  lastEventId?: string,
): AsyncGenerator<MatchEvent> {
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
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data) continue;
      try {
        const event = JSON.parse(data) as MatchEvent;
        if (event.kind === "match_found") yield event;
      } catch {
        // a line we cannot read is skipped, never echoed
      }
    }
  }
}
