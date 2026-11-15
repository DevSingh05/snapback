import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory, handleMessage, renterId, type InboundMessage } from "./handler";
import { ProfileStore } from "./profile";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";
const SALT = "fx-salt";
const KEY = renterId(THREAD, SALT);

type Call = { url: string; method: string; body?: unknown };

const PLACES = {
  source: "fixture",
  n_considered: 40,
  n_matches: 2,
  matches: [
    {
      property_id: "fx-1",
      kind: "apartment",
      floor_plan: "2 bed / 2 bath",
      rent_min: 1400,
      rent_max: 1490,
      price_text: "$1,400 to $1,490 a month",
      office_on_record: "Fixture Living LLC",
      budget_fit: "within",
      availability_text: "as of CoStar's last research",
    },
    {
      property_id: "fx-2",
      kind: "apartment",
      floor_plan: "2 bed / 1 bath",
      rent_min: 1300,
      price_text: "$1,300 a month",
      office_on_record: "Sample Homes Co",
      budget_fit: "within",
      availability_text: "as of CoStar's last research",
    },
  ],
};

function api(calls: Call[]) {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body });
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json({ case_id: card.case_id, read_token: "fx-read" }, { status: 201 });
    }
    if (url.includes(`/cases/${card.case_id}/card`) && !url.endsWith(".png")) {
      return Response.json(card);
    }
    if (url.endsWith("/search") && init?.method === "POST") return Response.json(PLACES);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function client() {
  const texts: string[] = [];
  return { texts, reply: async (_t: string, text: string) => void texts.push(text) };
}

function config(calls: Call[], profiles = new ProfileStore()) {
  return {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set([THREAD]),
    renterSalt: SALT,
    fetch: api(calls),
    memory: new CaseMemory(),
    profiles,
  };
}

const said = (text: string): InboundMessage => ({
  threadId: THREAD,
  text,
  imageUrls: [],
  receivedAt: "2026-11-15T01:00:00Z",
});
const posts = (calls: Call[], path = "/cases") =>
  calls.filter((c) => c.method === "POST" && c.url.endsWith(path));

// --- it learns the renter's language --------------------------------------------------------------

test("an ad written in Spanish gets the report in Spanish, card and labels", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(
    said("Hola, busco departamento. Renta $900, mande el depósito por Zelle"),
    c,
    config(calls),
  );
  assert.ok(calls.some((x) => x.url.endsWith(`/cases/${card.case_id}/card?lang=es`)));
  assert.match(c.texts[0] ?? "", /^Espere por ahora/);
  assert.match(c.texts[0] ?? "", /Antes de pagar:/);
  assert.match(c.texts[0] ?? "", /Informe completo:/);
});

test("once it knows Spanish, a short follow-up is answered in Spanish too", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(
    said("Hola, busco departamento. Renta $900, mande el depósito por Zelle"),
    client(),
    cfg,
  );
  const c = client();
  await handleMessage(said("¿por qué?"), c, cfg);
  assert.equal(posts(calls).length, 1, "a follow-up never makes a case");
  assert.match(c.texts[0] ?? "", /^Espere por ahora/);
});

test("the 'checking' reply is in the renter's language", async () => {
  const calls: Call[] = [];
  const sent: string[] = [];
  await handleMessage(
    said("Hola, busco departamento. Renta $900, mande el depósito por Zelle"),
    client(),
    config(calls),
    async (text?: string) => void sent.push(text ?? ""),
  );
  assert.match(sent[0] ?? "", /^Recibido\./);
});

// --- it remembers, and says what it remembers -------------------------------------------------------

test("a message that only states a budget and beds is remembered, not checked", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  const c = client();
  await handleMessage(said("My budget is $1,500 and I need 2 beds"), c, cfg);
  assert.equal(posts(calls).length, 0);
  assert.match(c.texts[0] ?? "", /\$1,500/);
  assert.match(c.texts[0] ?? "", /2 beds/);
  assert.deepEqual(cfg.profiles.get(KEY), { lang: "en", budget: 1500, beds: 2 });
});

test("'what do you remember?' lists it and never makes a case", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("My budget is $1,500 and I need 2 beds"), client(), cfg);
  const c = client();
  await handleMessage(said("what do you remember?"), c, cfg);
  assert.match(c.texts[0] ?? "", /budget: \$1,500/);
  assert.equal(posts(calls).length, 0);
});

test("'forget me' wipes the profile and the remembered case", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("My budget is $1,500 and I need 2 beds"), client(), cfg);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  const c = client();
  await handleMessage(said("forget me"), c, cfg);
  assert.match(c.texts[0] ?? "", /forgot/i);
  assert.equal(cfg.profiles.get(KEY), null);
  const after = client();
  await handleMessage(said("why?"), after, cfg);
  assert.equal(after.texts[0], "Send me the ad first and I'll check it.");
});

// --- it uses what it remembers ----------------------------------------------------------------------

test("'show me safer homes' searches with the remembered budget and beds", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("My budget is $1,500 and I need 2 beds"), client(), cfg);
  const c = client();
  await handleMessage(said("show me safer homes"), c, cfg);
  const search = posts(calls, "/search")[0];
  assert.ok(search, "searched");
  const brief = JSON.parse(String(search?.body)) as Record<string, number>;
  assert.equal(brief.max_rent_month, 1500);
  assert.equal(brief.beds_min, 2);
  const reply = c.texts[0] ?? "";
  assert.match(reply, /Fixture Living LLC/);
  assert.match(reply, /http:\/\/web\.test\/map/); // /search carries no hand-off link: the map
  assert.doesNotMatch(reply, /1,?400|1,?490|1,?300/, "record rents never in a reply");
  assert.equal(posts(calls).length, 0, "no check");
});

test("'show me places' asks only for what it doesn't know, and skips what it does", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  const first = client();
  await handleMessage(said("show me places"), first, cfg);
  assert.match(first.texts[0] ?? "", /budget/i);
  assert.match(first.texts[0] ?? "", /beds|bedrooms/i);
  await handleMessage(said("I need 2 beds"), client(), cfg);
  const second = client();
  await handleMessage(said("show me places"), second, cfg);
  assert.match(second.texts[0] ?? "", /budget/i);
  assert.doesNotMatch(second.texts[0] ?? "", /how many (beds|bedrooms)/i, "beds already answered");
  assert.equal(posts(calls, "/search").length, 0);
});

test("with no profile store, nothing is learned and the old behavior stands", async () => {
  const calls: Call[] = [];
  const plain = { ...config(calls), profiles: undefined };
  const c = client();
  await handleMessage(said("My budget is $1,500 and I need 2 beds"), c, plain);
  assert.equal(posts(calls).length, 1, "checked like any text");
});

// --- XO review of #264 ----------------------------------------------------------------------------

test("[High] a short ad with no photos is checked, and nothing is learned from it", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(
    said("Need a tenant for my 3 bedroom house near downtown. Text me at 555-0100"),
    client(),
    cfg,
  );
  assert.equal(posts(calls).length, 1);
  assert.equal(cfg.profiles.get(KEY), null);
});

test("[High] 'my budget is' with a phone number is not a budget, and the ad is checked", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("my budget is 713-555-0100"), client(), cfg);
  assert.equal(cfg.profiles.get(KEY)?.budget, undefined);
});

test("[Med] an English ad never flips a Spanish renter, nor sets their city or beds", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("Hola, mi presupuesto es $1,200 y necesito 2 recámaras"), client(), cfg);
  const c = client();
  await handleMessage(
    said("Enjoy living in Houston! 3 bed / 2 bath, $1,500 a month, I need a deposit by Zelle"),
    c,
    cfg,
  );
  assert.equal(posts(calls).length, 1, "the ad was checked");
  assert.deepEqual(cfg.profiles.get(KEY), { lang: "es", budget: 1200, beds: 2 });
  assert.match(c.texts[0] ?? "", /^Espere por ahora/, "still answered in Spanish");
});

test("[Med] 'what do you remember?' with nothing kept never wipes the case", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  await handleMessage(said("what do you remember?"), client(), cfg);
  const c = client();
  await handleMessage(said("why?"), c, cfg);
  assert.doesNotMatch(c.texts[0] ?? "", /Send me the ad first/);
});

test("[High] a phone-like number makes a short message an ad to check, not a profile", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("I need 2 beds 713-555-0100"), client(), cfg);
  assert.equal(posts(calls).length, 1);
  assert.equal(cfg.profiles.get(KEY), null);
});

// --- XO review of #264, round 2: a city alone never makes an ad profile-only ----------------------

for (const ad of [
  "3 bedroom house, $1200 monthly, pay first month to get the keys, living in Houston is great",
  "Spacious 1 bed in a quiet complex. Enjoy living in Houston!",
  "Casa de 2 recamaras en Houston, 900 al mes, solo efectivo",
]) {
  test(`[Med] an ad that names a city is checked and teaches nothing: ${ad.slice(0, 40)}…`, async () => {
    const calls: Call[] = [];
    const cfg = config(calls);
    await handleMessage(said(ad), client(), cfg);
    assert.equal(posts(calls).length, 1);
    assert.equal(cfg.profiles.get(KEY), null);
  });
}

test("[Med] a first-person city is still remembered", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("I'm moving to Houston in January"), client(), cfg);
  assert.equal(posts(calls).length, 0);
  assert.equal(cfg.profiles.get(KEY)?.city, "Houston");
});

for (const [why, text] of [
  ["a price without 'my budget'", "$900, I'm moving to Houston"],
  ["beds without 'I need'", "2 beds near the park, I'm moving to Houston"],
  ["a bare 'living in' city", "Enjoy living in Houston!"],
] as const) {
  test(`[Med] ${why} is checked, never remembered`, async () => {
    const calls: Call[] = [];
    const cfg = config(calls);
    await handleMessage(said(text), client(), cfg);
    assert.equal(posts(calls).length, 1, text);
    assert.equal(cfg.profiles.get(KEY), null, text);
  });
}
