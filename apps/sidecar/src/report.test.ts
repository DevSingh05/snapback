import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory, handleMessage, reportText, type InboundMessage } from "./handler";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";
const LINK = `http://web.test/case/${card.case_id}`;
const TOKEN = "fx-secret-write-token";

// The card as lane A's #250 builds it: summary fields made by code in verdict.build_card.
const summarised = {
  ...card,
  summary: ["The poster asks for Zelle before a viewing."],
  checks_out: ["Real: Taken in this building (3 of 3 photos)."],
  does_not: [
    "Payment ask: Zelle before a viewing. Red flag.",
    "Allowed to rent it: NOT SHOWN. Being inside does not mean they may rent it.",
    "Rent vs record: Not checked (our data has no rent for this building).",
  ],
};

type Call = { url: string; method: string };

function api(calls: Call[], body: object = summarised, challenge: string | null = null) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET" });
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json(
        { case_id: card.case_id, token: TOKEN, challenge_text: challenge },
        { status: 201 },
      );
    }
    if (url.endsWith(`/cases/${card.case_id}/card`)) return Response.json(body);
    if (url.endsWith(`/cases/${card.case_id}/card.png`)) {
      return new Response(new Blob(["png-bytes"], { type: "image/png" }), {
        headers: { "content-type": "image/png" },
      });
    }
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function client() {
  const texts: string[] = [];
  const images: { threadId: string; mimeType: string; bytes: number }[] = [];
  return {
    texts,
    images,
    reply: async (_threadId: string, text: string) => void texts.push(text),
    image: async (threadId: string, bytes: Uint8Array, mimeType: string) =>
      void images.push({ threadId, mimeType, bytes: bytes.length }),
  };
}

function config(calls: Call[], body?: object, challenge: string | null = null) {
  return {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set([THREAD]),
    renterSalt: "fx-salt",
    fetch: api(calls, body, challenge),
    memory: new CaseMemory(),
  };
}

const ad = (text: string): InboundMessage => ({
  threadId: THREAD,
  text,
  imageUrls: [],
  receivedAt: "2026-11-14T23:40:00Z",
});

// --- 1. the reply is a short report ------------------------------------------------------------

test("the reply is a short report: verdict, two reasons, one next step, the link", () => {
  const text = reportText(summarised, LINK);
  const lines = text.split("\n");
  assert.equal(lines[0], "Hold off for now"); // the locked headline, never our own words
  assert.match(text, /Payment ask: Zelle before a viewing\. Red flag\./);
  assert.match(text, /Allowed to rent it: NOT SHOWN/);
  assert.doesNotMatch(text, /Rent vs record/, "only the top two reasons");
  assert.match(text, /Next: Two rules: never pay before a signed lease and a viewing/);
  assert.match(text, new RegExp(`Full result: ${LINK}`));
  assert.ok(text.length < 700, `short enough for one message (${text.length})`);
});

test("the reasons come from the card, not from the sidecar", () => {
  const text = reportText({ ...summarised, does_not: ["X: line one.", "Y: line two."] }, LINK);
  assert.match(text, /X: line one\./);
  assert.match(text, /Y: line two\./);
});

test("checks passed: the reasons are what checked out", () => {
  const verified = { ...summarised, state: "verified", does_not: [] };
  const text = reportText(verified, LINK);
  assert.match(text.split("\n")[0] ?? "", /^Checks passed\./);
  assert.match(text, /Real: Taken in this building/);
});

test("a card from before #250 (no summary fields) still gets a report from its own lines", () => {
  const text = reportText(card, LINK);
  assert.match(text, /Payment ask: Zelle before a viewing/); // red flag first
  assert.match(text, /Full result:/);
});

test("with a challenge, the next step is to send it to the poster", () => {
  const text = reportText(summarised, LINK, "Hold up the code 7Q2M.");
  assert.match(text, /Next: send the poster this message: Hold up the code 7Q2M\./);
});

test("no case token and no phone digits in the report", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("2 bed, call 713-555-0199, Zelle $500 to hold"), c, config(calls));
  const text = c.texts.join("\n");
  assert.ok(!text.includes(TOKEN));
  assert.doesNotMatch(text, /\d{3}[-.\s]?\d{4}/);
});

// --- 2. the card picture ---------------------------------------------------------------------

test("the card picture is sent after the text, to the same thread", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("2 bed $900, Zelle first"), c, config(calls));
  assert.equal(c.texts.length, 1);
  assert.deepEqual(c.images, [{ threadId: THREAD, mimeType: "image/png", bytes: 9 }]);
  assert.ok(calls.some((x) => x.url.endsWith(`/cases/${card.case_id}/card.png`)));
});

test("if the picture fails, the text still went out", async () => {
  const calls: Call[] = [];
  const c = { ...client(), image: async () => Promise.reject(new Error("upload failed")) };
  await handleMessage(ad("2 bed $900, Zelle first"), c, config(calls));
  assert.equal(c.texts.length, 1);
});

// --- 3. follow-ups in the same thread --------------------------------------------------------

test("'why?' after a check lists the reasons from the same case, with no new check", async () => {
  const calls: Call[] = [];
  const c = client();
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), c, cfg);
  await handleMessage(ad("why?"), c, cfg);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1, "no second check");
  const why = c.texts[1] ?? "";
  assert.match(why, /Rent vs record: Not checked/); // all the reasons now, not just two
  assert.match(why, /Not checked: ID, lease, ownership/);
  assert.match(why, /Full result:/);
});

test("'what should I do?' gives the next steps from the same case", async () => {
  const calls: Call[] = [];
  const c = client();
  const cfg = config(calls, summarised, "Hold up the code 7Q2M.");
  await handleMessage(ad("2 bed $900, Zelle first"), c, cfg);
  await handleMessage(ad("What should I do?"), c, cfg);
  const steps = c.texts[1] ?? "";
  assert.match(steps, /Hold up the code 7Q2M\./);
  assert.match(steps, /Two rules:/);
  assert.match(steps, /never texts first/);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

test("'why?' with no earlier check in this thread is read as text and checked", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("why?"), c, config(calls));
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

test("a follow-up only reads this thread's own case", async () => {
  const calls: Call[] = [];
  const cfg = { ...config(calls), allowedThreads: new Set([THREAD, "fx-thread-other"]) };
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const other = client();
  await handleMessage({ ...ad("why?"), threadId: "fx-thread-other" }, other, cfg);
  assert.equal(
    calls.filter((x) => x.method === "POST").length,
    2,
    "the other thread's 'why?' is a new check",
  );
});

test("a follow-up after the case expires is a new check", async () => {
  let now = Date.parse("2026-11-14T12:00:00Z");
  const calls: Call[] = [];
  const cfg = { ...config(calls), memory: new CaseMemory(() => now) };
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  now += 25 * 60 * 60 * 1000;
  await handleMessage(ad("why?"), client(), cfg);
  assert.equal(calls.filter((x) => x.method === "POST").length, 2);
});

test("through Photon, the card picture goes to the same thread right after the text", async () => {
  const { runPhoton } = await import("./photon");
  const calls: Call[] = [];
  const sent: unknown[] = [];
  const renter = { id: THREAD, send: async (content: unknown) => void sent.push(content) };
  const messages = (async function* () {
    yield [
      renter,
      { direction: "inbound", content: { type: "text", text: "2 bed $900, Zelle first" } },
    ] as const;
  })();
  await runPhoton(
    { messages: messages as AsyncIterable<[typeof renter, never]> },
    {
      ...config(calls),
      quietMs: 5,
      makeImage: (bytes: Uint8Array, mimeType: string) => ({
        picture: mimeType,
        bytes: bytes.length,
      }),
    },
  );
  assert.equal(typeof sent[0], "string");
  assert.deepEqual(sent[1], { picture: "image/png", bytes: 9 });
});
