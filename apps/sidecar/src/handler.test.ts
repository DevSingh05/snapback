import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { handleMessage, renterId, type InboundMessage, type MessageClient } from "./handler";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);

type Call = { url: string; method: string; body?: FormData };

function mockApi(calls: Call[], createStatus = 201) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as FormData | undefined });
    if (url.startsWith("https://photos.example/")) return new Response(new Blob(["jpeg"]));
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json(
        { case_id: card.case_id, token: "fx-secret", challenge_text: "Hold up the code 7Q2M." },
        { status: createStatus },
      );
    }
    if (url.endsWith(`/cases/${card.case_id}/card`)) return Response.json(card);
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

const config = (calls: Call[], status = 201) => ({
  apiUrl: "http://api.test",
  webUrl: "http://web.test",
  allowedThreads: new Set(["fx-thread-renter"]),
  fetch: mockApi(calls, status),
});

test("inbound message -> one API call -> one reply containing the case link", async () => {
  const calls: Call[] = [];
  const photon = mockPhoton();
  assert.equal(await handleMessage(msg, photon, config(calls)), true);

  const posts = calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 1);
  assert.equal(first(posts).url, "http://api.test/cases");
  assert.equal(first(posts).body?.get("renter_id"), renterId("fx-thread-renter"));
  assert.equal(first(posts).body?.getAll("photos").length, 1);

  assert.equal(photon.sent.length, 1);
  assert.equal(first(photon.sent).threadId, "fx-thread-renter");
  assert.match(first(photon.sent).text, new RegExp(`http://web\\.test/case/${card.case_id}`));
  assert.match(first(photon.sent).text, /FIXTURE/);
  assert.match(first(photon.sent).text, /Hold up the code 7Q2M\./);
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
  await handleMessage(msg, photon, config([], 429));
  assert.deepEqual(
    photon.sent.map((s) => s.threadId),
    ["fx-thread-renter"],
  );
  assert.match(first(photon.sent).text, /today's checks/);
});
