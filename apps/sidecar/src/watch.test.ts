import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { runPhoton, type PhotonApp, type PhotonMessage, type PhotonSpace } from "./photon";
import {
  CODE_TTL_MS,
  DAY_MS,
  MAX_PUSHES_A_DAY,
  WatchBook,
  matchText,
  pushEvents,
  readEvents,
  type StreamEvent,
} from "./watch";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const SALT = "fx-sidecar-salt";
const RENTER = "fx-space-renter";
const WEB = "https://snapback.example";
const SESSION = "fs-fixture-1";

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

type Call = { url: string; method: string };

function config(book: WatchBook, calls: Call[] = [], allowed: string[] = [RENTER]) {
  return {
    apiUrl: "http://api.test",
    webUrl: WEB,
    allowedThreads: new Set(allowed),
    renterSalt: SALT,
    quietMs: 5,
    watches: book,
    fetch: (async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, method: init?.method ?? "GET" });
      if (url.endsWith("/cases") && init?.method === "POST") {
        return Response.json({ case_id: card.case_id }, { status: 201 });
      }
      if (url.endsWith(`/cases/${card.case_id}/card`)) return Response.json(card);
      return new Response("not found", { status: 404 });
    }) as typeof fetch,
  };
}

let next = 0;
const watchAdded = (code: number, session = SESSION): StreamEvent => ({
  id: `ev-${String(++next).padStart(6, "0")}`,
  kind: "watch_added",
  source: "renter",
  subject: session,
  payload: { session, code },
});
const match = (session = SESSION, extra: Partial<StreamEvent> = {}): StreamEvent => ({
  id: `ev-${String(++next).padStart(6, "0")}`,
  kind: "match_found",
  source: "pipeline",
  subject: "fx-place-1",
  payload: { session, fits_brief: true, rent_from: 1450, has_scan: true },
  ...extra,
});

async function* events(...items: StreamEvent[]) {
  for (const item of items) yield item;
}

/** A book with RENTER linked to SESSION through the code flow. */
async function linked(now?: () => number) {
  const book = new WatchBook(now);
  const renter = space(RENTER);
  await pushEvents(events(watchAdded(4821)), book, WEB);
  await runPhoton(app([[renter, said("WATCH 4821")]]), config(book));
  return { book, renter };
}

// --- linking a Finder watch to the thread with a one-time code (#238) -----------------------

test("'WATCH <code>' links the thread to the Finder session the code was issued for", async () => {
  const { book, renter } = await linked();
  assert.equal(book.size(), 1);
  assert.match(renter.sent[0] ?? "", /^Watching\./);
  assert.match(renter.sent[0] ?? "", /at most 3 times a day/);
  await pushEvents(events(match()), book, WEB);
  assert.equal(renter.sent.length, 2);
  assert.match(renter.sent[1] ?? "", /A place fits your watch/);
});

test("a code links once, an unknown or expired code links nothing", async () => {
  let now = 0;
  const book = new WatchBook(() => now);
  const a = space(RENTER);
  const b = space("fx-space-other");
  await pushEvents(events(watchAdded(1111), watchAdded(2222)), book, WEB);
  const cfg = config(book, [], [RENTER, "fx-space-other"]);
  await runPhoton(app([[a, said("watch 1111")]]), cfg);
  await runPhoton(app([[b, said("watch 1111")]]), cfg); // already used
  assert.match(b.sent[0] ?? "", /did not match a watch/);
  now += CODE_TTL_MS + 1;
  await runPhoton(app([[b, said("watch 2222")]]), cfg); // expired
  assert.match(b.sent[1] ?? "", /did not match a watch/);
  assert.equal(book.size(), 1);
});

test("no local sessions: a bare 'watch' points to the Finder and links nothing", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  await runPhoton(app([[renter, said("watch")]]), config(book));
  assert.equal(book.size(), 0);
  assert.match(renter.sent[0] ?? "", new RegExp(`${WEB}/map`));
});

test("'WATCH <code>' from a thread not on the allowlist links nothing and sends nothing", async () => {
  const book = new WatchBook();
  const stranger = space("fx-space-stranger");
  await pushEvents(events(watchAdded(4821)), book, WEB);
  await runPhoton(app([[stranger, said("watch 4821")]]), config(book));
  assert.equal(book.size(), 0);
  assert.equal(stranger.sent.length, 0);
});

// --- item 5: "watch out" and ads are not commands --------------------------------------------

test("'Watch out, is this real?' with an ad goes to the scam check, not the watch", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  const calls: Call[] = [];
  const ad = "Watch out, is this real? 2 bed $1,200, send Zelle deposit first";
  await runPhoton(app([[renter, said(ad)]]), config(book, calls));
  assert.equal(calls.filter((c) => c.method === "POST").length, 1);
  assert.equal(book.size(), 0);
});

test("an ad whose price looks like a live code is still checked, and links nothing", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  const calls: Call[] = [];
  await pushEvents(events(watchAdded(1200)), book, WEB);
  await runPhoton(
    app([[renter, said("watch out: 2 bed $1200, Zelle first")]]),
    config(book, calls),
  );
  assert.equal(calls.filter((c) => c.method === "POST").length, 1);
  assert.equal(book.size(), 0);
});

// --- item 1: the alert text -----------------------------------------------------------------

test("the alert carries the record line", () => {
  const text = matchText(match(), WEB);
  assert.match(text, /On record: from \$1,450 a month, a 3D scan on record/);
  assert.match(text, /as of CoStar's last research/);
});

test("a simulated match says Simulated, a real one does not", () => {
  assert.match(matchText(match(SESSION, { source: "simulated" }), WEB), /^Simulated\. /);
  assert.doesNotMatch(matchText(match(), WEB), /Simulated/);
});

test("the alert links the place's Walk it first, and the map only with no scan", () => {
  assert.match(matchText(match(), WEB), new RegExp(`Walk it first: ${WEB}/tour/fx-place-1`));
  const noScan = match();
  noScan.payload.has_scan = false;
  assert.doesNotMatch(matchText(noScan, WEB), /\/tour\//);
  assert.match(matchText(noScan, WEB), new RegExp(`${WEB}/map`));
});

// --- the push: only the linked thread, cap, stop ----------------------------------------------

test("a match is pushed only to the linked thread", async () => {
  const { book, renter } = await linked();
  await pushEvents(events(match("fs-someone-else")), book, WEB);
  assert.equal(renter.sent.length, 1); // only the "Watching." reply
});

test("a match that does not fit the brief is not pushed", async () => {
  const { book, renter } = await linked();
  const off = match();
  off.payload.fits_brief = false;
  await pushEvents(events(off), book, WEB);
  assert.equal(renter.sent.length, 1);
});

test("item 6: 3 sent, then 23 hours later a 4th is refused; after 24 hours it goes", async () => {
  let now = Date.parse("2026-11-14T12:00:00Z");
  const { book, renter } = await linked(() => now);
  await pushEvents(events(match(), match(), match(), match()), book, WEB);
  assert.equal(renter.sent.length, 1 + MAX_PUSHES_A_DAY);
  now += 23 * 60 * 60 * 1000;
  await pushEvents(events(match()), book, WEB);
  assert.equal(renter.sent.length, 1 + MAX_PUSHES_A_DAY, "still inside the 24 hours");
  now += DAY_MS - 23 * 60 * 60 * 1000 + 1;
  await pushEvents(events(match()), book, WEB);
  assert.equal(renter.sent.length, 2 + MAX_PUSHES_A_DAY);
});

test("item 6: linking again does not reset the day's count", async () => {
  const now = Date.parse("2026-11-14T12:00:00Z");
  const { book, renter } = await linked(() => now);
  await pushEvents(events(match(), match(), match()), book, WEB);
  await pushEvents(events(watchAdded(5555)), book, WEB);
  await runPhoton(app([[renter, said("watch 5555")]]), config(book));
  const before = renter.sent.length;
  await pushEvents(events(match()), book, WEB);
  assert.equal(renter.sent.length, before);
});

// --- item 4: stop words, inline replies ----------------------------------------------------------

for (const word of ["stop", "Stop texting me", "unsubscribe", "cancel", "END", "quit."]) {
  test(`'${word}' ends the watch for good`, async () => {
    const { book, renter } = await linked();
    await runPhoton(app([[renter, said(word)]]), config(book));
    assert.equal(book.size(), 0);
    assert.match(renter.sent.at(-1) ?? "", /will not text you again/);
    const before = renter.sent.length;
    await pushEvents(events(match()), book, WEB);
    assert.equal(renter.sent.length, before);
  });
}

test("an inline-reply 'stop' ends the watch too", async () => {
  const { book, renter } = await linked();
  const reply: PhotonMessage = {
    direction: "inbound",
    content: { type: "reply", content: { type: "text", text: "stop" } },
  };
  await runPhoton(app([[renter, reply]]), config(book));
  assert.equal(book.size(), 0);
});

test("an ad that starts with 'End unit' is checked, not taken as a stop", async () => {
  const { book, renter } = await linked();
  const calls: Call[] = [];
  await runPhoton(
    app([[renter, said("End unit 2 bed, $1,300, Zelle to hold")]]),
    config(book, calls),
  );
  assert.equal(book.size(), 1);
  assert.equal(calls.filter((c) => c.method === "POST").length, 1);
});

test("a thread with no watch is never texted first", async () => {
  const book = new WatchBook();
  const renter = space(RENTER);
  await pushEvents(events(watchAdded(4821), match()), book, WEB);
  assert.equal(renter.sent.length, 0);
});

// --- item 3: the events stream, and reconnects --------------------------------------------------

test("the stream is read with the token in a header, and ids are kept", async () => {
  const body =
    'id: ev-000001\nevent: event\ndata: {"id":"ev-000001","kind":"watch_added","subject":"fs-1","payload":{"session":"fs-1","code":4821}}\n\n' +
    ": keep-alive\n\n" +
    'id: ev-000002\nevent: event\ndata: {"id":"ev-000002","kind":"match_found","source":"simulated","subject":"fx-place-1","payload":{"session":"fs-1","fits_brief":true}}\n\n';
  const seen: { url: string; auth: string | null; last: string | null }[] = [];
  const get = (async (input: string | URL | Request, init?: RequestInit) => {
    const h = new Headers(init?.headers);
    seen.push({ url: String(input), auth: h.get("authorization"), last: h.get("last-event-id") });
    return new Response(body, { headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  const got: StreamEvent[] = [];
  for await (const e of readEvents("http://api.test", "fx-events-token", get, "ev-000000")) {
    got.push(e);
  }
  assert.deepEqual(
    got.map((e) => [e.id, e.kind]),
    [
      ["ev-000001", "watch_added"],
      ["ev-000002", "match_found"],
    ],
  );
  assert.equal(seen[0]?.url, "http://api.test/events/stream");
  assert.equal(seen[0]?.auth, "Bearer fx-events-token");
  assert.equal(seen[0]?.last, "ev-000000"); // resume after the last event seen
});

test("a reconnect that replays an event does not text the same match twice", async () => {
  const { book, renter } = await linked();
  const once = match();
  let lastId = "";
  await pushEvents(
    events(once),
    book,
    WEB,
    () => {},
    (id) => void (lastId = id),
  );
  await pushEvents(events(once), book, WEB); // the server replayed it
  assert.equal(renter.sent.length, 2);
  assert.equal(lastId, once.id);
});
