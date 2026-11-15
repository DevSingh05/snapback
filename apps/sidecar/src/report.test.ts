import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  COULD_NOT_CHECK,
  CaseMemory,
  handleMessage,
  renterId,
  reportText,
  type InboundMessage,
} from "./handler";
import { stageOptions } from "./photon";

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

type Call = { url: string; method: string; auth?: string | null };

const READ = "fx-secret-read-token";
const REAL = {
  case_id: card.case_id,
  source: "fixture",
  property_id: "fx-prop-1",
  which: "claimed",
  manager_company: "Fixture Living LLC",
  website_host: "oakcourt.example",
  plans: [{ beds: 2, rent_min: 1450, rent_max: 1600 }], // record rents: never in a reply
};

function api(
  calls: Call[],
  body: object = summarised,
  challenge: string | null = null,
  real: object | null = REAL,
) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({
      url,
      method: init?.method ?? "GET",
      auth: new Headers(init?.headers).get("authorization"),
    });
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json(
        { case_id: card.case_id, token: TOKEN, read_token: READ, challenge_text: challenge },
        { status: 201 },
      );
    }
    if (url.endsWith(`/cases/${card.case_id}/real-listing`)) {
      return real ? Response.json(real) : new Response("no record", { status: 404 });
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

function config(
  calls: Call[],
  body?: object,
  challenge: string | null = null,
  real: object | null = REAL,
) {
  return {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set([THREAD]),
    renterSalt: "fx-salt",
    fetch: api(calls, body, challenge, real),
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

test("U2: headline, 'Before you pay:' with two reasons, one next step, 'Full report:'", () => {
  const text = reportText(summarised, LINK);
  const lines = text.split("\n");
  assert.equal(lines[0], "Hold off for now"); // the locked headline, never our own words
  assert.ok(lines.includes("Before you pay:"));
  // Card.summary first: it has one line, so the first does_not fills the second reason
  assert.match(text, /- The poster asks for Zelle before a viewing\./);
  assert.match(text, /- Payment ask: Zelle before a viewing\. Red flag\./);
  assert.doesNotMatch(text, /Allowed to rent it/, "only two reasons");
  assert.match(text, /Next: Two rules: never pay before a signed lease and a viewing/);
  assert.match(text, new RegExp(`Full report: ${LINK}`));
  assert.ok(text.length < 600, `short enough for one message (${text.length})`);
});

test("U2: with the office on record (#250), the next step is to call it through its own site", () => {
  const text = reportText(summarised, LINK, null, {
    manager_company: "Fixture Living LLC",
    website_host: "oakcourt.example",
  });
  assert.match(
    text,
    /Next: Call Fixture Living LLC through oakcourt\.example, not the number in the ad\./,
  );
});

test("U2: record rents never appear in the reply", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("2 bed $900, Zelle first"), c, config(calls));
  const text = c.texts.join("\n");
  assert.doesNotMatch(text, /1,?450|1,?600/);
  assert.match(text, /Call Fixture Living LLC through oakcourt\.example/);
  // the read token went to our API in a header, never into the reply
  const real = calls.find((x) => x.url.endsWith("/real-listing"));
  assert.equal(real?.auth, `Bearer ${READ}`);
  assert.ok(!text.includes(READ));
});

test("U2: with no real listing (404), the next step falls back to the card", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("2 bed $900, Zelle first"), c, config(calls, summarised, null, null));
  assert.match(c.texts[0] ?? "", /Next: Two rules:/);
});

test("the reasons come from the card, not from the sidecar", () => {
  const text = reportText(
    { ...summarised, summary: [], does_not: ["X: line one.", "Y: line two."] },
    LINK,
  );
  assert.match(text, /X: line one\./);
  assert.match(text, /Y: line two\./);
});

test("checks passed: the reasons are what checked out", () => {
  const verified = { ...summarised, state: "verified", summary: [], does_not: [] };
  const text = reportText(verified, LINK);
  assert.match(text.split("\n")[0] ?? "", /^Checks passed\./);
  assert.match(text, /Real: Taken in this building/);
});

test("a card from before #250 (no summary fields) still gets a report from its own lines", () => {
  const text = reportText(card, LINK);
  assert.match(text, /Payment ask: Zelle before a viewing/); // red flag first
  assert.match(text, /Full report:/);
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
  assert.match(why, /Full report:/);
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

test("[H] 'why?' with no case in this thread never makes one: 'send me the ad first'", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("why?"), c, config(calls));
  assert.equal(calls.filter((x) => x.method === "POST").length, 0);
  assert.equal(c.texts[0], "Send me the ad first and I'll check it.");
});

test("a follow-up only reads this thread's own case", async () => {
  const calls: Call[] = [];
  const cfg = { ...config(calls), allowedThreads: new Set([THREAD, "fx-thread-other"]) };
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const other = client();
  await handleMessage({ ...ad("why?"), threadId: "fx-thread-other" }, other, cfg);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1, "no case for the other thread");
  assert.equal(other.texts[0], "Send me the ad first and I'll check it.");
});

test("[L] a follow-up more than 2 hours after the check never makes a case", async () => {
  let now = Date.parse("2026-11-14T12:00:00Z");
  const calls: Call[] = [];
  const cfg = { ...config(calls), memory: new CaseMemory(() => now) };
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  now += 2 * 60 * 60 * 1000 + 1;
  const late = client();
  await handleMessage(ad("why?"), late, cfg);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
  assert.equal(late.texts[0], "Send me the ad first and I'll check it.");
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

// --- U3: ask for what is missing ------------------------------------------------------------------

test("U3: an ad with no photos gets asked for them, in the same reply", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("2 bed $900, Zelle first"), c, config(calls));
  assert.match(
    c.texts[0] ?? "",
    /Send the ad's photos too and I can check where they were taken\./,
  );
});

test("U3: an ad with photos is not asked for them", async () => {
  const calls: Call[] = [];
  const c = client();
  const withPhoto = { ...ad("2 bed $900"), images: [new Blob(["jpeg"], { type: "image/jpeg" })] };
  await handleMessage(withPhoto, c, config(calls));
  assert.doesNotMatch(c.texts[0] ?? "", /Send the ad's photos/);
});

test("U3: only a Marketplace link gets 'paste the words and screenshots', and no check is used", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("https://www.facebook.com/marketplace/item/123456789/"), c, config(calls));
  assert.equal(calls.filter((x) => x.method === "POST").length, 0);
  assert.equal(c.texts[0], "I can't open Marketplace links. Paste the ad's words and screenshots.");
});

test("U3: a Marketplace link with the ad's words is checked as usual", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(
    ad("https://www.facebook.com/marketplace/item/1/ 2 bed $900, Zelle first"),
    c,
    config(calls),
  );
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

// --- U1: one "checking" reply per batch ---------------------------------------------------------

test("U1: through Photon, one 'checking' reply goes out before the report", async () => {
  const { runPhoton } = await import("./photon");
  const calls: Call[] = [];
  const sent: unknown[] = [];
  const renter = { id: THREAD, send: async (content: unknown) => void sent.push(content) };
  const messages = (async function* () {
    // the ad and its photo arrive as two messages: one batch, one "checking" reply
    yield [
      renter,
      { direction: "inbound", content: { type: "text", text: "2 bed $900, Zelle first" } },
    ] as const;
    yield [
      renter,
      {
        direction: "inbound",
        content: {
          type: "attachment",
          mimeType: "image/jpeg",
          read: async () => new Uint8Array([1, 2]),
        },
      },
    ] as const;
  })();
  await runPhoton(
    { messages: messages as AsyncIterable<[typeof renter, never]> },
    { ...config(calls), quietMs: 5, acknowledge: true },
  );
  assert.equal(
    sent[0],
    "Got it. Checking this against CoStar's record before you pay anyone. About a minute.",
  );
  assert.equal(sent.filter((x) => typeof x === "string" && x.startsWith("Got it.")).length, 1);
  assert.match(String(sent[1]), /^Hold off for now/);
});

test("U1: a follow-up gets no 'checking' reply", async () => {
  const { runPhoton } = await import("./photon");
  const calls: Call[] = [];
  const cfg = { ...config(calls), quietMs: 5, acknowledge: true };
  cfg.memory.remember(THREAD, card.case_id, null);
  const sent: unknown[] = [];
  const renter = { id: THREAD, send: async (content: unknown) => void sent.push(content) };
  const messages = (async function* () {
    yield [renter, { direction: "inbound", content: { type: "text", text: "why?" } }] as const;
  })();
  await runPhoton({ messages: messages as AsyncIterable<[typeof renter, never]> }, cfg);
  assert.ok(!sent.some((x) => typeof x === "string" && x.startsWith("Got it.")));
});

// --- XO review of #255 (Sat 18:59) -----------------------------------------------------------------

test("[H] if the card cannot be read, a follow-up says it couldn't check and makes no case", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const broken = {
    ...cfg,
    fetch: (async () => new Response("down", { status: 500 })) as typeof fetch,
  };
  const c = client();
  await handleMessage(ad("why?"), c, broken);
  assert.equal(c.texts[0], COULD_NOT_CHECK);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

test("[H] if the follow-up reply throws, it never falls through to a check", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const throwing = {
    ...cfg,
    fetch: (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch,
  };
  const c = client();
  await handleMessage(ad("why?"), c, throwing);
  assert.equal(c.texts[0], COULD_NOT_CHECK);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

for (const said of [
  "Why?",
  "why’s that",
  "why is it on hold",
  "what should I do now?",
  "what do I do then",
  "What now",
]) {
  test(`[M] '${said}' is a follow-up`, async () => {
    const calls: Call[] = [];
    const cfg = config(calls);
    await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
    await handleMessage(ad(said), client(), cfg);
    assert.equal(calls.filter((x) => x.method === "POST").length, 1, said);
  });
}

test("[M] a long 'why' sentence or one with a link is an ad, not a follow-up", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  await handleMessage(
    ad("why would the landlord ask for Zelle before I even see the 2 bed place"),
    client(),
    cfg,
  );
  await handleMessage(ad("why https://example.com/listing"), client(), cfg);
  assert.equal(calls.filter((x) => x.method === "POST").length, 3);
});

test("[M] 'who do I call?' names the office on record and its site, never digits", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const c = client();
  await handleMessage(ad("Who do I call?"), c, cfg);
  assert.match(c.texts[0] ?? "", /Fixture Living LLC/);
  assert.match(c.texts[0] ?? "", /oakcourt\.example/);
  assert.doesNotMatch(c.texts[0] ?? "", /\d{3}[-.\s]?\d{4}/);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

test("[M] 'is it safe?' gives the headline and the top reasons from the card", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const c = client();
  await handleMessage(ad("is it safe?"), c, cfg);
  assert.match(c.texts[0] ?? "", /^Hold off for now/);
  assert.match(c.texts[0] ?? "", /Zelle before a viewing/);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
});

test("[M] 'why?' sent while a check is running says 'still checking', not the old ad", async () => {
  const calls: Call[] = [];
  let release = () => {};
  const gate = new Promise<void>((done) => (release = done));
  const slow = api(calls);
  const cfg = {
    ...config(calls),
    fetch: (async (input: string | URL | Request, init?: RequestInit) => {
      if (String(input).endsWith("/cases") && init?.method === "POST") await gate;
      return slow(input, init);
    }) as typeof fetch,
  };
  const running = handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  const c = client();
  await handleMessage(ad("why?"), c, cfg);
  assert.equal(c.texts[0], "Still checking, one moment.");
  release();
  await running;
});

test("[L] a failed 'checking' reply never skips the check", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(ad("2 bed $900, Zelle first"), c, config(calls), async () => {
    throw new Error("send failed");
  });
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
  assert.match(c.texts[0] ?? "", /^Hold off for now/);
});

test("[L] memory is keyed by the keyed hash, never the thread id", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(ad("2 bed $900, Zelle first"), client(), cfg);
  assert.equal(cfg.memory.recall(THREAD), null);
  assert.ok(cfg.memory.recall(renterId(THREAD, "fx-salt")));
});

test("[M] stage switches: card picture and checking reply are on only when set to 1", () => {
  assert.deepEqual(stageOptions({}), { sendCardImage: false, acknowledge: false });
  assert.deepEqual(stageOptions({ SNAPBACK_SEND_CARD_IMAGE: "1", SNAPBACK_SEND_CHECKING: "1" }), {
    sendCardImage: true,
    acknowledge: true,
  });
  assert.deepEqual(stageOptions({ SNAPBACK_SEND_CARD_IMAGE: "0" }).sendCardImage, false);
});
