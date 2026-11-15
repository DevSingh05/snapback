import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory, handleMessage, type InboundMessage } from "./handler";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";

// GET /cases/{id}/copy-alert (#250): a DRAFT for the office on record; nothing is ever sent
const FIRES = {
  case_id: card.case_id,
  source: "fixture",
  fires: true,
  manager_company: "Fixture Living LLC",
  website_host: "oakcourt.example",
  photos_in_scan: 3,
  photos_total: 3,
  phone_is_office: "no",
  draft_only: true,
  sent: false,
  draft_subject: "Your listing at Oak Court may be copied",
  draft_body:
    "Hello Fixture Living LLC,\n\nA renter sent us an ad with 3 photos placed in your building's 3D scan, and its number is not your office's on record.\n\nSNAPBACK (draft)",
};
const QUIET = {
  ...FIRES,
  fires: false,
  why_not: "phone_is_office",
  draft_subject: null,
  draft_body: null,
};

type Call = { url: string; method: string; auth?: string | null };

function api(calls: Call[], alert: object) {
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
    if (url.includes(`/cases/${card.case_id}/copy-alert`)) return Response.json(alert);
    if (url.includes(`/cases/${card.case_id}/card`) && !url.endsWith(".png"))
      return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function client() {
  const texts: string[] = [];
  return { texts, reply: async (_t: string, text: string) => void texts.push(text) };
}

function config(calls: Call[], alert: object = FIRES) {
  return {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set([THREAD]),
    renterSalt: "fx-salt",
    fetch: api(calls, alert),
    memory: new CaseMemory(),
  };
}

const said = (text: string): InboundMessage => ({
  threadId: THREAD,
  text,
  imageUrls: [],
  receivedAt: "2026-11-15T02:30:00Z",
});

test("after a red-flag result whose copy alert fires, the report offers the draft", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(said("2 bed $900, Zelle first"), c, config(calls));
  assert.match(
    c.texts[0] ?? "",
    /Want me to draft a note to the real leasing office\? Reply "draft"\./,
  );
  const alert = calls.find((x) => x.url.includes("/copy-alert"));
  assert.equal(alert?.auth, "Bearer fx-read", "read token in a header");
});

test("no offer when the copy alert does not fire", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(said("2 bed $900, Zelle first"), c, config(calls, QUIET));
  assert.doesNotMatch(c.texts[0] ?? "", /draft a note/);
});

test("on 'draft', the API's own draft comes back, marked as not sent", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  const c = client();
  await handleMessage(said("draft"), c, cfg);
  const draft = c.texts[0] ?? "";
  assert.match(draft, /^Draft, not sent\. You send it\./);
  assert.match(draft, /To: Fixture Living LLC \(oakcourt\.example\)/);
  assert.match(draft, /Subject: Your listing at Oak Court may be copied/);
  assert.match(draft, /3 photos placed in your building's 3D scan/);
  assert.equal(calls.filter((x) => x.method === "POST").length, 1, "no new case");
});

test("'yes' after the offer means the draft, once; a second 'yes' is not a draft", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  const first = client();
  await handleMessage(said("yes"), first, cfg);
  assert.match(first.texts[0] ?? "", /^Draft, not sent/);
  const second = client();
  await handleMessage(said("yes"), second, cfg);
  assert.doesNotMatch(second.texts[0] ?? "", /^Draft, not sent/);
});

test("'draft' with no offer open drafts nothing", async () => {
  const calls: Call[] = [];
  const c = client();
  await handleMessage(said("draft"), c, config(calls));
  assert.doesNotMatch(c.texts[0] ?? "", /^Draft, not sent/);
  assert.ok(!calls.some((x) => x.url.includes("/copy-alert")));
});

test("nothing is ever sent to the office: the only send is the reply in the renter's thread", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  await handleMessage(said("2 bed $900, Zelle first"), client(), cfg);
  await handleMessage(said("draft"), client(), cfg);
  assert.ok(calls.every((x) => x.method === "GET" || x.url.endsWith("/cases")));
});

test("in Spanish, the offer and the draft label are in Spanish", async () => {
  const calls: Call[] = [];
  const cfg = config(calls);
  const c = client();
  await handleMessage(
    said("Hola, busco departamento. Renta $900, mande el depósito por Zelle"),
    c,
    cfg,
  );
  assert.match(c.texts[0] ?? "", /borrador/);
  const d = client();
  await handleMessage(said("borrador"), d, cfg);
  assert.match(d.texts[0] ?? "", /^Borrador, no enviado\. Usted lo envía\./);
});
