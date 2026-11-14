import assert from "node:assert/strict";
import { test } from "node:test";

import { runPhoton, type PhotonApp, type PhotonMessage, type PhotonSpace } from "./photon";
import {
  MAX_PUSHES_A_DAY,
  WatchBook,
  parseWatch,
  pushMatches,
  readEvents,
  type MatchEvent,
} from "./watch";

const SALT = "fx-sidecar-salt";
const RENTER = "fx-space-renter";
const WEB = "https://snapback.example";

function space(id: string): PhotonSpace & { sent: string[] } {
  const sent: string[] = [];
  return { id, sent, send: async (text: string) => void sent.push(text) };
}

const said = (body: string): PhotonMessage => ({
  direction: "inbound",
  content: { type: "text", text: body },
});

function app(items: [PhotonSpace, PhotonMessage][]): PhotonApp {
  return {
    messages: (async function* () {
      for (const item of items) yield item;
    })(),
  };
}

function config(book: WatchBook, allowed: string[] = [RENTER]) {
  return {
    apiUrl: "http://api.test",
    webUrl: WEB,
    allowedThreads: new Set(allowed),
    renterSalt: SALT,
    fetch: (async () => new Response("unused", { status: 500 })) as typeof fetch,
    quietMs: 5,
    watches: book,
  };
}

function match(session: string, extra: Partial<MatchEvent["payload"]> = {}): MatchEvent {
  return {
    id: "ev-000001",
    kind: "match_found",
    subject: "fx-place-1",
    payload: { session, fits_brief: true, rent_from: 1450, has_scan: true, ...extra },
  };
}

async function* events(...items: MatchEvent[]) {
  for (const item of items) yield item;
}

// --- reading what the renter asks for -------------------------------------------------------

test("code reads budget, beds, parking, pets and no walk-up from a watch text", () => {
  assert.deepEqual(parseWatch("watch 2 beds under $1,500 with parking, pets ok, no walk-up"), {
    max_rent_month: 1500,
    beds_min: 2,
    needs_parking: true,
    pets: true,
    needs_no_walkup: true,
  });
  assert.deepEqual(parseWatch("Watch studio up to 1200"), { max_rent_month: 1200, beds_min: 0 });
  assert.deepEqual(parseWatch("watch"), {}); // nothing code can read
  assert.equal(parseWatch("is this listing real? 2 beds $1,500"), null); // not a watch
});

// --- the commands, in the renter's own thread ----------------------------------------------

test("'watch' in an allowed thread saves the watch and says plainly what happens next", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  await runPhoton(app([[renter, said("watch 2 beds under $1,500")]]), config(book));
  assert.equal(book.size(), 1);
  assert.equal(renter.sent.length, 1);
  assert.match(renter.sent[0] ?? "", /2\+ beds, up to \$1,500/);
  assert.match(renter.sent[0] ?? "", /at most 3 times a day/);
  assert.match(renter.sent[0] ?? "", /stop/);
});

test("a 'watch' code cannot read gets the map link, and no watch is saved", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  await runPhoton(app([[renter, said("watch something nice")]]), config(book));
  assert.equal(book.size(), 0);
  assert.match(renter.sent[0] ?? "", new RegExp(`${WEB}/map`));
});

test("'watch' from a thread not on the allowlist saves nothing and sends nothing", async () => {
  const book = new WatchBook();
  const stranger = space("fx-space-stranger");
  await runPhoton(app([[stranger, said("watch 2 beds")]]), config(book));
  assert.equal(book.size(), 0);
  assert.equal(stranger.sent.length, 0);
});

// --- texting first: only a thread that asked, at most 3 a day, and stop ends it ------------

test("a match is pushed only to the thread that asked to watch", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  const session = book.add(renter, { beds_min: 2 });
  await pushMatches(events(match(session), match("w-someone-else")), book, WEB);
  assert.equal(renter.sent.length, 1);
  assert.match(renter.sent[0] ?? "", /from \$1,450 a month/);
  assert.match(renter.sent[0] ?? "", /As of CoStar's last research/);
  assert.match(renter.sent[0] ?? "", new RegExp(`${WEB}/map`));
});

test("at most 3 pushes a day per thread, then more the next day", async () => {
  let now = Date.parse("2026-11-14T12:00:00Z");
  const book = new WatchBook(() => now);
  const renter = space(RENTER);
  const session = book.add(renter, { beds_min: 2 });
  const five = Array.from({ length: 5 }, () => match(session));
  await pushMatches(events(...five), book, WEB);
  assert.equal(renter.sent.length, MAX_PUSHES_A_DAY);
  assert.equal(MAX_PUSHES_A_DAY, 3);
  now += 24 * 60 * 60 * 1000 + 1;
  await pushMatches(events(match(session)), book, WEB);
  assert.equal(renter.sent.length, 4);
});

test("'stop' ends the watch for good: no push after it, and it says so", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  const session = book.add(renter, { beds_min: 2 });
  await runPhoton(app([[renter, said("stop")]]), config(book));
  assert.equal(book.size(), 0);
  assert.match(renter.sent[0] ?? "", /will not text you again/);
  const before = renter.sent.length;
  // a match for the old watch arrives later: nothing goes out
  await pushMatches(events(match(session)), book, WEB);
  assert.equal(renter.sent.length, before);
});

test("a match that does not fit the brief is not pushed", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  const session = book.add(renter, { beds_min: 2 });
  await pushMatches(events(match(session, { fits_brief: false })), book, WEB);
  assert.equal(renter.sent.length, 0);
});

test("a thread with no watch is never texted first", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  await runPhoton(app([[renter, said("2 bed for rent, $500 Zelle deposit")]]), config(book));
  await pushMatches(events(match("w-anything")), book, WEB);
  // the only message it got is the reply to its own ad
  assert.ok(renter.sent.every((text) => !/fits your watch/.test(text)));
});

// --- the events stream ----------------------------------------------------------------------

test("the events stream is read as server-sent events, match_found only, with the token", async () => {
  const body =
    'id: ev-000001\nevent: event\ndata: {"id":"ev-000001","kind":"watch_added","subject":"w-1","payload":{}}\n\n' +
    ": keep-alive\n\n" +
    'id: ev-000002\nevent: event\ndata: {"id":"ev-000002","kind":"match_found","subject":"fx-place-1","payload":{"session":"w-1","fits_brief":true,"rent_from":1450,"has_scan":false}}\n\n';
  const seen: { url: string; auth: string | null }[] = [];
  const get = (async (input: string | URL | Request, init?: RequestInit) => {
    seen.push({ url: String(input), auth: new Headers(init?.headers).get("authorization") });
    return new Response(body, { headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  const got: MatchEvent[] = [];
  for await (const event of readEvents("http://api.test", "fx-events-token", get)) got.push(event);
  assert.deepEqual(
    got.map((e) => [e.id, e.payload.session]),
    [["ev-000002", "w-1"]],
  );
  assert.equal(seen[0]?.url, "http://api.test/events/stream");
  assert.equal(seen[0]?.auth, "Bearer fx-events-token"); // in a header, never the address
});
