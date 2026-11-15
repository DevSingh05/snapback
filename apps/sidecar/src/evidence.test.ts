import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { handleMessage, type InboundMessage } from "./handler";

// P3 (#11, Photon v2): after the verdict, the evidence image for the best-placed photo
// (GET /cases/{id}/evidence-image, #283, read token in a header only), then the card picture.

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
const CARD_PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 9, 9]);

type Call = { url: string; auth: string | null };
type Photo = { alias: string; status: string };

function api(calls: Call[], photos: Photo[] | null, imageStatus = 200) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, auth: new Headers(init?.headers).get("authorization") });
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json({ case_id: card.case_id, read_token: "fx-read" }, { status: 201 });
    }
    if (url.endsWith(`/cases/${card.case_id}/evidence`)) {
      return photos
        ? Response.json({ case_id: card.case_id, source: "fixture", photos })
        : new Response("none yet", { status: 404 });
    }
    if (url.includes(`/cases/${card.case_id}/evidence-image`)) {
      return imageStatus === 200
        ? new Response(PNG, { headers: { "content-type": "image/png" } })
        : new Response("not placed", { status: imageStatus });
    }
    if (url.endsWith(`/cases/${card.case_id}/card.png`)) {
      return new Response(CARD_PNG, { headers: { "content-type": "image/png" } });
    }
    if (url.includes(`/cases/${card.case_id}/card`)) return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function client() {
  const sent: { kind: "text" | "image"; first?: number }[] = [];
  return {
    sent,
    reply: async (_t: string, _text: string) => void sent.push({ kind: "text" }),
    image: async (_t: string, bytes: Uint8Array) =>
      void sent.push({ kind: "image", first: bytes[4] }),
  };
}

const cfg = (calls: Call[], photos: Photo[] | null, imageStatus = 200) => ({
  apiUrl: "http://api.test",
  webUrl: "http://web.test",
  allowedThreads: new Set([THREAD]),
  renterSalt: "fx-salt",
  fetch: api(calls, photos, imageStatus),
});

const blob = () => new Blob([new Uint8Array([1])], { type: "image/jpeg" });
const withPhotos = (n: number): InboundMessage => ({
  threadId: THREAD,
  text: "2 bed $900, Zelle first",
  imageUrls: [],
  images: Array.from({ length: n }, blob),
  receivedAt: "2026-11-15T02:30:00Z",
});

test("P3: the first photo placed in the claimed home gets its evidence image, then the card", async () => {
  const calls: Call[] = [];
  const c = client();
  const photos = [
    { alias: "P1", status: "not_located" },
    { alias: "P2", status: "located_elsewhere" },
    { alias: "P3", status: "located_in_claimed" },
  ];
  await handleMessage(withPhotos(3), c, cfg(calls, photos));
  const image = calls.find((x) => x.url.includes("/evidence-image"));
  assert.equal(image?.url, `http://api.test/cases/${card.case_id}/evidence-image?photo=3&lang=en`);
  assert.equal(image?.auth, "Bearer fx-read", "read token in a header");
  assert.ok(
    calls.every((x) => !x.url.includes("fx-read")),
    "never a token in an address",
  );
  assert.deepEqual(
    c.sent.map((s) => (s.kind === "image" ? `image:${s.first}` : s.kind)),
    ["text", "image:1", "image:9"],
  );
});

test("P3: with none in the claimed home, the first placed elsewhere is shown", async () => {
  const calls: Call[] = [];
  const photos = [
    { alias: "P1", status: "not_indexed" },
    { alias: "P2", status: "located_elsewhere" },
  ];
  await handleMessage(withPhotos(2), client(), cfg(calls, photos));
  assert.match(calls.find((x) => x.url.includes("/evidence-image"))?.url ?? "", /photo=2&/);
});

test("P3: nothing placed, no evidence file or a 404 image: only the card picture", async () => {
  for (const [photos, status] of [
    [[{ alias: "P1", status: "not_located" }], 200],
    [null, 200],
    [[{ alias: "P1", status: "located_in_claimed" }], 404],
  ] as const) {
    const calls: Call[] = [];
    const c = client();
    await handleMessage(withPhotos(1), c, cfg(calls, photos as Photo[] | null, status));
    assert.deepEqual(
      c.sent.map((s) => (s.kind === "image" ? `image:${s.first}` : s.kind)),
      ["text", "image:9"],
    );
  }
});

test("P3: a text-only ad never asks for evidence", async () => {
  const calls: Call[] = [];
  await handleMessage(
    withPhotos(0),
    client(),
    cfg(calls, [{ alias: "P1", status: "located_in_claimed" }]),
  );
  assert.ok(!calls.some((x) => x.url.includes("/evidence")));
});
