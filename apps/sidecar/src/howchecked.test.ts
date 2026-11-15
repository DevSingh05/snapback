import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory, handleMessage, type InboundMessage } from "./handler";
import { howCheckedText } from "./howchecked";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";

// GET /cases/{id}/timeline as main's create_app returns it right after the first reply
// (#275 review: a real build_timeline dump, fixture mode). No verdict step exists yet.
const TIMELINE = JSON.parse(
  readFileSync(new URL("../fixtures/timeline_hold_early.json", import.meta.url), "utf8"),
);
// The same case once it is done, plus steps a LIVE case can carry.
const DONE = {
  ...TIMELINE,
  steps: [
    ...TIMELINE.steps,
    { label: "Looked up the license the ad names", result: "TREC 0123456: no match.", by: "agent" },
    {
      label: "Checked the phone against the leasing office",
      result: "It is not the office's number.",
      by: "agent",
    },
    {
      label: "Compared the rent with 3 floor plans",
      result: "$1,150 is under $1,450 on record.",
      by: "agent",
    },
    {
      label: "The deep agent stopped: it waited too long behind other checks; code set the verdict",
      result: "Done.",
      by: "code",
    },
    {
      label: "Code worked out the result",
      result: "Worked out by code from the evidence. No model picks it.",
      by: "code",
    },
  ],
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

test("one line per agent from the real timeline, red flags first, the card's verdict last", () => {
  const text = howCheckedText(TIMELINE, card, "http://web.test/case/7Q2M");
  const lines = text.split("\n");
  // the card's own headline when it has one (#280's red-flag headlines), else the state's
  assert.equal(lines[0], card.headline ?? "Hold off for now");
  assert.equal(lines.at(-3), `- Result: ${lines[0]}`, "the verdict is the headline");
  const flag = lines.findIndex((l) => /Red flag/.test(l));
  const agents = ["Rules", "Record", "Photo"].map((a) =>
    lines.findIndex((l) => l.startsWith(`- ${a} agent:`)),
  );
  const verdict = lines.findIndex((l) => l.startsWith("- Result:"));
  assert.ok(
    agents.every((i) => i > 0),
    text,
  );
  assert.ok(flag > 0 && flag < Math.min(...agents), "red flags first");
  assert.ok(
    agents.every((i) => i < verdict),
    "verdict last",
  );
  assert.match(text, /\(FIXTURE\)/);
});

test("[Med] with no verdict step yet, the answer still ends with the card's headline", () => {
  const text = howCheckedText(
    TIMELINE,
    card,
    "http://web.test/case/7Q2M",
    "en",
    "Hold off for now",
  );
  assert.match(text, /- Result: Hold off for now\n/);
});

test("[Med] once done, the Result is the card's headline, never the verdict step's text", () => {
  const text = howCheckedText(DONE, card, "http://web.test/case/7Q2M", "en", "Hold off for now");
  assert.match(text, /- Result: Hold off for now\n/);
  assert.doesNotMatch(text, /Worked out by code/);
});

test("[Med] no raw trace jargon: only known result strings are shown, else the label alone", () => {
  const text = howCheckedText(DONE, card, "http://web.test/case/7Q2M");
  for (const jargon of [
    /inliers/,
    /Plan A/,
    /Only one option was open/,
    /Skipped listing brokerage/,
    /TREC/,
    /fx-spot/,
    /in the twin/,
    /data area/,
  ]) {
    assert.doesNotMatch(text, jargon);
  }
  assert.match(text, /Rules agent: Read the ad: Read what the ad says it is\./);
  assert.match(
    text,
    /Phone agent: Checked the phone against the leasing office: It is not the office's number\./,
  );
  assert.match(text, /Photo agent: Placed 3 of 3 photos in its 3D scan/);
});

test("[Low] license steps are the Record agent's, not the Rules agent's", () => {
  const text = howCheckedText(DONE, card, "http://web.test/case/7Q2M");
  const record = text.split("\n").find((l) => l.startsWith("- Record agent:")) ?? "";
  const rules = text.split("\n").find((l) => l.startsWith("- Rules agent:")) ?? "";
  assert.match(record, /Looked up the license the ad names/);
  assert.match(record, /Skipped the license lookup/);
  assert.doesNotMatch(rules, /license/);
});

test("[Low] the deep agent stopped line is shown as its own line", () => {
  const text = howCheckedText(DONE, card, "http://web.test/case/7Q2M");
  assert.match(
    text,
    /\n- The deep agent stopped: it waited too long behind other checks; code set the verdict\n/,
  );
});

test("never a phone digit or a rent figure, even if the timeline carried one", () => {
  const text = howCheckedText(DONE, card, "http://web.test/case/7Q2M");
  assert.doesNotMatch(text, /555|0199|0123456/);
  assert.doesNotMatch(text, /\$\s?\d|1,?150|1,?450/);
});

test("meta steps (the plan, notes, waiting, the random draw) are left out", () => {
  const text = howCheckedText(DONE, card, "http://web.test/case/7Q2M");
  assert.doesNotMatch(text, /Chose which checks|Drew a random spot|Waited for an answer/);
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
