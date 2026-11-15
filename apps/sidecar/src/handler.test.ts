import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  COULD_NOT_CHECK,
  HEADLINES,
  handleMessage,
  renterId,
  type InboundMessage,
  type MessageClient,
} from "./handler";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);

const SALT = "fx-sidecar-salt";
const WRITE_TOKEN = "fx-secret-write-token";
const READ_TOKEN = "fx-secret-read-token";

type Call = { url: string; method: string; body?: FormData };

function mockApi(calls: Call[], opts: { status?: number; state?: string; throws?: boolean } = {}) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as FormData | undefined });
    if (opts.throws && url.startsWith("http://api.test")) throw new TypeError("fetch failed");
    if (url.startsWith("https://photos.example/")) return new Response(new Blob(["jpeg"]));
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json(
        {
          case_id: card.case_id,
          token: WRITE_TOKEN,
          read_token: READ_TOKEN,
          challenge_text: "Hold up the code 7Q2M.",
        },
        { status: opts.status ?? 201 },
      );
    }
    if (url.endsWith(`/cases/${card.case_id}/card`)) {
      // An overridden state is a different card: the fixture's own (hold) headline no longer fits,
      // so the sidecar falls back to the locked headline for that state.
      return Response.json(
        opts.state ? { ...card, state: opts.state, headline: undefined } : { ...card },
      );
    }
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function mockPhoton(): MessageClient & { sent: { threadId: string; text: string }[] } {
  const sent: { threadId: string; text: string }[] = [];
  return { sent, reply: async (threadId, text) => void sent.push({ threadId, text }) };
}

function first<T>(items: T[]): T {
  const item = items[0];
  assert.ok(item, "expected at least one item");
  return item;
}

const msg: InboundMessage = {
  threadId: "fx-thread-renter",
  text: "Is this listing real? fx-listing-link",
  imageUrls: ["https://photos.example/a.jpg"],
  receivedAt: "2026-11-14T03:00:00Z",
};

const config = (calls: Call[], opts: Parameters<typeof mockApi>[1] = {}) => ({
  apiUrl: "http://api.test",
  webUrl: "http://web.test",
  allowedThreads: new Set(["fx-thread-renter"]),
  renterSalt: SALT,
  fetch: mockApi(calls, opts),
});

test("inbound message -> one API call -> one reply containing the case link", async () => {
  const calls: Call[] = [];
  const photon = mockPhoton();
  assert.equal(await handleMessage(msg, photon, config(calls)), true);

  const posts = calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 1);
  assert.equal(first(posts).url, "http://api.test/cases");
  assert.equal(first(posts).body?.get("renter_id"), renterId("fx-thread-renter", SALT));
  assert.equal(first(posts).body?.getAll("photos").length, 1);

  assert.equal(photon.sent.length, 1);
  assert.equal(first(photon.sent).threadId, "fx-thread-renter");
  assert.match(first(photon.sent).text, new RegExp(`http://web\\.test/case/${card.case_id}`));
  assert.match(first(photon.sent).text, /FIXTURE/);
  assert.match(first(photon.sent).text, /Hold up the code 7Q2M\./);
});

for (const [state, headline] of [
  ["hold", "Hold off for now"],
  ["unverified", "Could not place these photos"],
  ["dont_pay", "Don't pay. Something here doesn't match."],
  ["verified", "Checks passed. Still follow the two rules."],
] as const) {
  test(`the first line is the locked headline for ${state}`, async () => {
    const photon = mockPhoton();
    await handleMessage(msg, photon, config([], { state }));
    assert.equal(first(photon.sent).text.split("\n")[0], headline);
    assert.equal(HEADLINES[state], headline);
  });
}

test("the card's own headline (the shared fixture carries one) leads the reply when state is not overridden", async () => {
  assert.ok(card.headline, "the contract fixture carries a code-built headline");
  const photon = mockPhoton();
  await handleMessage(msg, photon, config([]));
  assert.equal(first(photon.sent).text.split("\n")[0], card.headline);
});

test("no case token ever appears in the reply", async () => {
  for (const state of ["hold", "unverified", "dont_pay", "verified"]) {
    const photon = mockPhoton();
    await handleMessage(msg, photon, config([], { state }));
    const text = first(photon.sent).text;
    assert.ok(!text.includes(WRITE_TOKEN), "write token leaked");
    assert.ok(!text.includes(READ_TOKEN), "read token leaked");
  }
});

test("if the API call throws, the renter still gets a safe reply", async () => {
  const photon = mockPhoton();
  assert.equal(await handleMessage(msg, photon, config([], { throws: true })), true);
  assert.deepEqual(photon.sent, [{ threadId: "fx-thread-renter", text: COULD_NOT_CHECK }]);
});

test("the renter id is a keyed hash: not plain sha256, and it changes with the salt", () => {
  const plain = createHash("sha256").update("fx-thread-renter").digest("hex");
  const id = renterId("fx-thread-renter", SALT);
  assert.ok(!plain.includes(id.replace("imsg-", "")));
  assert.notEqual(id, renterId("fx-thread-renter", "fx-other-salt"));
  assert.equal(id, renterId("fx-thread-renter", SALT));
});

test("a thread not on the allowlist gets nothing and starts nothing", async () => {
  const calls: Call[] = [];
  const photon = mockPhoton();
  const stranger = { ...msg, threadId: "fx-thread-poster" };
  assert.equal(await handleMessage(stranger, photon, config(calls)), false);
  assert.equal(calls.length, 0);
  assert.equal(photon.sent.length, 0);
});

test("the API never sees the thread id or handle", async () => {
  const calls: Call[] = [];
  await handleMessage(msg, mockPhoton(), config(calls));
  const form = calls.find((c) => c.method === "POST")?.body;
  for (const [, value] of form?.entries() ?? []) {
    assert.ok(!String(value).includes("fx-thread-renter"));
  }
});

test("a used-up daily limit is said plainly, in the renter's thread only", async () => {
  const photon = mockPhoton();
  await handleMessage(msg, photon, config([], { status: 429 }));
  assert.deepEqual(
    photon.sent.map((s) => s.threadId),
    ["fx-thread-renter"],
  );
  assert.match(first(photon.sent).text, /today's checks/);
});
