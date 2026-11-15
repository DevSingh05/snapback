import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory, handleMessage, intentOf, type InboundMessage } from "./handler";

// XO 02:17 (#11), from Jeffrey's C05 take (#10): the voice note "Is this a real listing?" was
// checked as a new ad. These forms of "is this real" are the same follow-up as "is it real".

for (const phrase of [
  "is this a real listing",
  "Is this a real listing?",
  "is this the real listing",
  "Is this the real listing?",
  "is it real",
  "Is it real?",
  "Is this a real listing.", // how speech-to-text often ends a voice note
  // XO 02:22: the wider set
  "is the listing real",
  "Is the listing real?",
  "Is this legit?",
  "is this a legit place",
  "is it a real apartment",
  "is this the real home",
  "Is that a real house?",
  "is this ok",
  "is this a scam",
  "is it a scam?",
]) {
  test(`'${phrase}' is the 'is this real' follow-up`, () => {
    assert.equal(intentOf(phrase), "safe");
  });
}

for (const phrase of [
  "es un anuncio real",
  "¿Es un lugar real?",
  "es una casa real",
  "es un departamento real",
]) {
  test(`Spanish '${phrase}' is the 'is this real' follow-up`, () => {
    assert.equal(intentOf(phrase), "safe");
  });
}

test("a longer ad that starts the same way is still an ad, not a follow-up", () => {
  assert.equal(intentOf("Is this a real listing? 2 bed $900, Zelle the deposit first"), null);
  assert.equal(
    intentOf("Is the listing real and available? Spacious 2 bed, $950, text me to tour"),
    null,
  );
  assert.equal(intentOf("Es un departamento real, 2 recámaras, $900, depósito por Zelle"), null);
});

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const THREAD = "fx-thread-renter";

test("'Is this a real listing?' after a check answers from that case and starts no new check", async () => {
  let posts = 0;
  const fetchFn = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/cases") && init?.method === "POST") {
      posts += 1;
      return Response.json({ case_id: card.case_id, read_token: "fx-read" }, { status: 201 });
    }
    if (url.includes(`/cases/${card.case_id}/card`) && !url.endsWith(".png"))
      return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
  const cfg = {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set([THREAD]),
    renterSalt: "fx-salt",
    fetch: fetchFn,
    memory: new CaseMemory(),
  };
  const said = (text: string): InboundMessage => ({
    threadId: THREAD,
    text,
    imageUrls: [],
    receivedAt: "2026-11-15T07:20:00Z",
  });
  const out: string[] = [];
  const client = { reply: async (_t: string, text: string) => void out.push(text) };
  await handleMessage(said("2 bed $900, Zelle first"), client, cfg);
  await handleMessage(said("Is this a real listing?"), client, cfg);
  assert.equal(posts, 1, "no new check");
  assert.match(out[1] ?? "", /^Hold off/);
});
