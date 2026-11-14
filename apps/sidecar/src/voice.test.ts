import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { runPhoton, type PhotonApp, type PhotonMessage, type PhotonSpace } from "./photon";
import { MAX_VOICE_BYTES, MAX_VOICE_SECONDS } from "./voice";
import { WatchBook } from "./watch";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const RENTER = "fx-space-renter";
const SPOKEN_AD = "Two bed for rent, the owner is abroad, send six hundred by Zelle to hold it";

type Call = { url: string; method: string; body?: unknown; headers?: Headers };
type Sent = { kind: "text" | "voice"; text?: string; mimeType?: string; bytes?: number };

function space(id: string): PhotonSpace & { sent: Sent[] } {
  const sent: Sent[] = [];
  return {
    id,
    sent,
    send: async (content: unknown) => {
      if (typeof content === "string") sent.push({ kind: "text", text: content });
      else sent.push(content as Sent);
    },
  };
}

// The SDK's voice() builder, faked: what space.send receives for a voice memo.
const makeVoice = (bytes: Uint8Array, mimeType: string): Sent => ({
  kind: "voice",
  mimeType,
  bytes: bytes.length,
});

function memo(opts: { seconds?: number; size?: number; mimeType?: string } = {}): PhotonMessage {
  return {
    direction: "inbound",
    content: {
      type: "voice",
      mimeType: opts.mimeType ?? "audio/x-caf",
      ...(opts.seconds === undefined ? {} : { duration: opts.seconds }),
      ...(opts.size === undefined ? {} : { size: opts.size }),
      read: async () => Buffer.from("caf-bytes"),
    },
  };
}

function app(items: [PhotonSpace, PhotonMessage][]): PhotonApp {
  return {
    messages: (async function* () {
      for (const item of items) yield item;
    })(),
  };
}

function api(calls: Call[], opts: { stt?: number; tts?: number } = {}): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({
      url,
      method: init?.method ?? "GET",
      body: init?.body,
      headers: new Headers(init?.headers),
    });
    if (url.endsWith("/voice/stt")) {
      if (opts.stt) return Response.json({ reason: "voice not configured" }, { status: opts.stt });
      return Response.json({ text: SPOKEN_AD });
    }
    if (url.endsWith("/voice/tts")) {
      if (opts.tts) return Response.json({ reason: "voice not configured" }, { status: opts.tts });
      return new Response(new Blob(["mp3-bytes"], { type: "audio/mpeg" }), {
        headers: { "content-type": "audio/mpeg" },
      });
    }
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json({ case_id: card.case_id }, { status: 201 });
    }
    if (url.endsWith(`/cases/${card.case_id}/card`)) return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function config(calls: Call[], opts: Parameters<typeof api>[1] = {}, converted: string[] = []) {
  return {
    apiUrl: "http://api.test",
    webUrl: "https://snapback.example",
    allowedThreads: new Set([RENTER]),
    renterSalt: "fx-salt",
    quietMs: 5,
    fetch: api(calls, opts),
    makeVoice,
    // the CAF-to-m4a step, faked: records what it was asked to convert
    convertVoice: async (bytes: Uint8Array, mimeType: string) => {
      converted.push(mimeType);
      return { bytes, mimeType: "audio/mp4" };
    },
  };
}

test("a voice memo is written down by /voice/stt and checked like a typed ad", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(app([[renter, memo({ seconds: 6, size: 9000 })]]), config(calls));
  const stt = calls.find((c) => c.url.endsWith("/voice/stt"));
  assert.ok(stt, "the memo went to /voice/stt");
  assert.ok((stt?.body as FormData).get("audio") instanceof Blob);
  const post = calls.find((c) => c.url.endsWith("/cases") && c.method === "POST");
  assert.equal((post?.body as FormData).get("text"), SPOKEN_AD);
});

test("Apple's CAF memo is converted before speech to text", async () => {
  const calls: Call[] = [];
  const converted: string[] = [];
  await runPhoton(app([[space(RENTER), memo()]]), config(calls, {}, converted));
  assert.deepEqual(converted, ["audio/x-caf"]);
  const clip = (calls.find((c) => c.url.endsWith("/voice/stt"))?.body as FormData).get("audio");
  assert.equal((clip as Blob).type, "audio/mp4");
});

test("a spoken ad gets the card as text plus a voice memo from /voice/tts", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(app([[renter, memo()]]), config(calls));
  assert.equal(renter.sent[0]?.kind, "text");
  assert.match(renter.sent[0]?.text ?? "", /Full result:/);
  assert.equal(renter.sent[1]?.kind, "voice");
  const tts = calls.find((c) => c.url.endsWith("/voice/tts"));
  const said = JSON.parse(String(tts?.body)) as { text: string };
  assert.ok(said.text.length <= 600);
  assert.match(said.text, /^Hold off for now\./); // the locked headline, spoken
});

test("a typed ad gets text only: no voice memo", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  const typed: PhotonMessage = {
    direction: "inbound",
    content: { type: "text", text: "2 bed $900 Zelle" },
  };
  await runPhoton(app([[renter, typed]]), config(calls));
  assert.equal(renter.sent.length, 1);
  assert.equal(calls.filter((c) => c.url.includes("/voice/")).length, 0);
});

test("if /voice/tts fails, the text reply still goes out alone", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(app([[renter, memo()]]), config(calls, { tts: 503 }));
  assert.deepEqual(
    renter.sent.map((s) => s.kind),
    ["text"],
  );
});

test("if /voice/stt is off, the renter is asked to type or paste the ad, and nothing is checked", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(app([[renter, memo()]]), config(calls, { stt: 503 }));
  assert.equal(calls.filter((c) => c.url.endsWith("/cases")).length, 0);
  assert.match(renter.sent[0]?.text ?? "", /type or paste/i);
});

test("a memo over the length or size cap is not downloaded or sent anywhere", async () => {
  for (const over of [{ seconds: MAX_VOICE_SECONDS + 1 }, { size: MAX_VOICE_BYTES + 1 }]) {
    const calls: Call[] = [];
    const renter = space(RENTER);
    await runPhoton(app([[renter, memo(over)]]), config(calls));
    assert.equal(calls.length, 0, JSON.stringify(over));
    assert.match(renter.sent[0]?.text ?? "", /under 2 minutes/);
  }
});

test("a memo from a thread not on the allowlist is never transcribed", async () => {
  const calls: Call[] = [];
  const stranger = space("fx-space-stranger");
  await runPhoton(app([[stranger, memo()]]), config(calls));
  assert.equal(calls.length, 0);
  assert.equal(stranger.sent.length, 0);
});

test("no key leaves the sidecar: speech goes only to our own API", async () => {
  const calls: Call[] = [];
  await runPhoton(app([[space(RENTER), memo()]]), config(calls));
  for (const call of calls) {
    assert.ok(call.url.startsWith("http://api.test/"), call.url);
    assert.equal(call.headers?.get("xi-api-key"), null);
  }
});

test("watch alerts stay text only, even for a thread that spoke its ad", async () => {
  // the voice path never touches the watch: pushes go through watch.ts, which sends text
  const book = new WatchBook();
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(app([[renter, memo()]]), { ...config(calls), watches: book });
  assert.equal(book.size(), 0);
});
