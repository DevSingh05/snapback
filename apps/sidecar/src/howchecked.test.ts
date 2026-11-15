import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory, handleMessage, type InboundMessage } from "./handler";
import { howCheckedText } from "./howchecked";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";

// GET /cases/{id}/timeline, as #267 builds it (labels and results from strings, by code)
const TIMELINE = {
  case_id: card.case_id,
  source: "fixture",
  mode: "deepagents",
  fell_back: false,
  steps: [
    {
      step: 0,
      label: "Read the ad",
      started_ms: 0,
      took_ms: 40,
      result: "Read what the ad says it is.",
      source: "fixture",
      by: "code",
    },
    {
      step: 1,
      label: "Wrote its plan (5 of 5 done)",
      started_ms: 40,
      took_ms: 10,
      result: "Done.",
      source: "fixture",
      by: "agent",
    },
    {
      step: 1,
      label: "Handed the record checks to a sub-agent",
      started_ms: 45,
      took_ms: 5,
      result: "Done.",
      source: "fixture",
      by: "agent",
    },
    {
      step: 2,
      label: "Found the building on CoStar's record",
      started_ms: 50,
      took_ms: 300,
      result: "Oak Court, 3 floor plans on record.",
      source: "fixture",
      by: "agent",
    },
    {
      step: 3,
      label: "Checked the phone against the leasing office",
      started_ms: 350,
      took_ms: 90,
      result: "Not the office's number (713-555-0199).",
      source: "fixture",
      by: "agent",
    },
    {
      step: 4,
      label: "Compared the rent with 3 floor plans",
      started_ms: 440,
      took_ms: 60,
      result: "$1,150 is under $1,450 on record.",
      source: "fixture",
      by: "agent",
    },
    {
      step: 5,
      label: "Placed 3 of 3 photos in its 3D scan",
      started_ms: 500,
      took_ms: 18000,
      result: "Taken in this building.",
      source: "fixture",
      by: "agent",
    },
    {
      step: 6,
      label: "Compared the ad's claims with the record",
      started_ms: 18500,
      took_ms: 20,
      result: "Zelle before a viewing.",
      source: "fixture",
      by: "agent",
    },
    {
      step: 7,
      label: "Code worked out the result",
      started_ms: 18520,
      took_ms: 0,
      result: "Hold off for now.",
      source: "fixture",
      by: "code",
    },
  ],
  todos: [],
  plan: ["record", "office", "place"],
};

type Call = { url: string; method: string; auth?: string | null };

function api(calls: Call[], timeline: object | null = TIMELINE) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({
      url,
      method: init?.method ?? "GET",
      auth: new Headers(init?.headers).get("authorization"),
    });
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json({ case_id: card.case_id, read_token: "fx-read" }, { status: 201 });
    }
    if (url.includes(`/cases/${card.case_id}/timeline`)) {
      return timeline ? Response.json(timeline) : new Response("no", { status: 404 });
    }
    if (url.includes(`/cases/${card.case_id}/card`) && !url.endsWith(".png"))
      return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function client() {
  const texts: string[] = [];
  return { texts, reply: async (_t: string, text: string) => void texts.push(text) };
}

function config(calls: Call[], timeline: object | null = TIMELINE) {
  return {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set([THREAD]),
    renterSalt: "fx-salt",
    fetch: api(calls, timeline),
    memory: new CaseMemory(),
  };
}

const said = (text: string): InboundMessage => ({
  threadId: THREAD,
  text,
  imageUrls: [],
  receivedAt: "2026-11-15T02:00:00Z",
});

test("one line per agent, in the timeline's own words, red flags first, then the verdict", () => {
  const text = howCheckedText(TIMELINE, card, "http://web.test/case/7Q2M");
  const lines = text.split("\n");
  assert.equal(lines[0], "Hold off for now");
  const flag = lines.findIndex((l) => /Red flag/.test(l));
  const rules = lines.findIndex((l) => l.startsWith("- Rules agent:"));
  const record = lines.findIndex((l) => l.startsWith("- Record agent:"));
  const phone = lines.findIndex((l) => l.startsWith("- Phone agent:"));
  const photo = lines.findIndex((l) => l.startsWith("- Photo agent:"));
  const verdict = lines.findIndex((l) => l.startsWith("- Result:"));
  assert.ok(flag > 0 && flag < Math.min(rules, record, phone, photo), "red flags first");
  assert.ok(
    [rules, record, phone, photo].every((i) => i > 0 && i < verdict),
    "verdict last",
  );
  assert.match(text, /Phone agent: Checked the phone against the leasing office/);
  assert.match(text, /\(FIXTURE\)/);
});

test("never a phone digit or a rent figure, even if the timeline carried one", () => {
  const text = howCheckedText(TIMELINE, card, "http://web.test/case/7Q2M");
  assert.doesNotMatch(text, /555|0199/);
  assert.doesNotMatch(text, /\$\s?\d|1,?150|1,?450/);
});

test("meta steps (the plan, notes, waiting) are left out", () => {
  const text = howCheckedText(TIMELINE, card, "http://web.test/case/7Q2M");
  assert.doesNotMatch(text, /Wrote its plan/);
  assert.doesNotMatch(text, /Handed the record checks/);
});

test("'how did you check?' reads the timeline with the read token and makes no case", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  const c = client();
  await handleMessage(said("How did you check?"), c, cfg);
  const timeline = calls.find((x) => x.url.includes("/timeline"));
  assert.equal(timeline?.auth, "Bearer fx-read");
  assert.equal(calls.filter((x) => x.method === "POST").length, 1);
  assert.match(c.texts[0] ?? "", /Record agent:/);
});

test("in Spanish, '¿cómo lo revisaste?' asks the timeline in Spanish", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  await handleMessage(said("¿Cómo lo revisaste?"), client(), cfg);
  assert.ok(calls.some((x) => x.url.endsWith(`/cases/${card.case_id}/timeline?lang=es`)));
});

test("with no case, or no timeline, it never makes one", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(said("how did you check?"), c, config(calls));
  assert.equal(c.texts[0], "Send me the ad first and I'll check it.");
  const missing: Call[] = [];
  const cfg = config(missing, null);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  const m = client();
  await handleMessage(said("how did you check"), m, cfg);
  assert.equal(missing.filter((x) => x.method === "POST").length, 1);
  assert.match(m.texts[0] ?? "", /couldn't|Full report/i);
});
