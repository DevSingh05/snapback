import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { runPhoton, type PhotonMessage, type PhotonSpace } from "./photon";

// Photon's SDK (spectrum-ts) throws a RateLimitError, with `retryAfterMs`, when the project is
// over its send rate (gRPC RESOURCE_EXHAUSTED). A reply must wait and retry, never be lost.

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const RENTER = "fx-space-renter";

class RateLimitError extends Error {
  constructor(public retryAfterMs?: number) {
    super("rate limit exceeded");
    this.name = "RateLimitError";
  }
}

function api(): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json({ case_id: card.case_id }, { status: 201 });
    }
    if (url.endsWith(`/cases/${card.case_id}/card`)) return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function run(fail: (n: number) => Error | null) {
  const sent: unknown[] = [];
  const waits: number[] = [];
  const logs: string[] = [];
  let n = 0;
  const renter: PhotonSpace = {
    id: RENTER,
    send: async (content: unknown) => {
      const err = fail(++n);
      if (err) throw err;
      sent.push(content);
    },
  };
  const ad: PhotonMessage = {
    direction: "inbound",
    content: { type: "text", text: "2 bed $900, Zelle first" },
  };
  const done = runPhoton(
    {
      messages: (async function* () {
        yield [renter, ad] as [PhotonSpace, PhotonMessage];
      })(),
    },
    {
      apiUrl: "http://api.test",
      webUrl: "https://snapback.example",
      allowedThreads: new Set([RENTER]),
      renterSalt: "fx-salt",
      quietMs: 5,
      fetch: api(),
      sleep: async (ms: number) => void waits.push(ms),
    },
    (line: string) => void logs.push(line),
  );
  return { done, sent, waits, logs };
}

test("a rate-limited reply waits Photon's retryAfterMs and is sent, not lost", async () => {
  const r = run((n) => (n === 1 ? new RateLimitError(1200) : null));
  await r.done;
  assert.equal(r.sent.length, 1);
  assert.match(String(r.sent[0]), /^Hold off/);
  assert.deepEqual(r.waits, [1200]);
  assert.ok(r.logs.some((l) => /Photon rate limit/.test(l)));
});

test("the wait is capped at 15 s, and at least 0.5 s when Photon gives no time", async () => {
  const long = run((n) => (n === 1 ? new RateLimitError(600_000) : null));
  await long.done;
  assert.deepEqual(long.waits, [15_000]);
  const none = run((n) => (n === 1 ? new RateLimitError() : null));
  await none.done;
  assert.deepEqual(none.waits, [2_000]);
  const tiny = run((n) => (n === 1 ? new RateLimitError(10) : null));
  await tiny.done;
  assert.deepEqual(tiny.waits, [500]);
});

test("it retries at most twice, then gives up", async () => {
  const r = run(() => new RateLimitError(100));
  await r.done;
  assert.equal(r.sent.length, 0);
  assert.equal(r.waits.length, 2);
  assert.ok(r.logs.some((l) => /a reply could not be sent/.test(l)));
});

test("any other send error is never retried", async () => {
  const r = run((n) => (n === 1 ? new Error("network down") : null));
  await r.done;
  assert.equal(r.waits.length, 0);
  assert.equal(r.sent.length, 0);
});
