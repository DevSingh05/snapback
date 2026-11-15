import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CaseMemory } from "./handler";
import { runPhoton, type PhotonMessage, type PhotonSpace } from "./photon";
import { SPOKEN_MAX_WORDS, spokenReply } from "./voice";

// P4 (#11, Photon v2): the spoken reply is the verdict, the top reason and who to call, in the
// card's own words, 15 s or less. Never a phone digit, a rent figure or a link.

const REPORT = [
  "Hold off for now",
  "SNAPBACK check 7Q2M (FIXTURE)",
  "",
  "Before you pay:",
  "- We could not confirm who is allowed to rent this unit.",
  "- A fresh photo proved someone was inside the unit, which is not authority.",
  "",
  "Next: Call Fixture Living LLC through oakcourt.example, not the number in the ad.",
  "",
  "Send the ad's photos too and I can check where they were taken.",
  "",
  "Full report: http://w/case/7Q2M",
  'Ask me "why?" or "what should I do?"',
].join("\n");

const REPORT_ES = [
  "Espere por ahora",
  "SNAPBACK check 7Q2M (FIXTURE)",
  "",
  "Antes de pagar:",
  "- No pudimos confirmar quién puede rentar esta unidad.",
  "",
  "Siguiente: Llame a Fixture Living LLC a través de oakcourt.example, no al número del anuncio.",
  "",
  "Informe completo: http://w/case/7Q2M",
].join("\n");

const words = (s: string) => s.split(/\s+/).filter(Boolean).length;

test("P4: verdict, then the top reason, then who to call, in the card's own words", () => {
  const said = spokenReply(REPORT);
  assert.equal(
    said,
    "Hold off for now. We could not confirm who is allowed to rent this unit. " +
      "Call Fixture Living LLC through oakcourt.example, not the number in the ad. " +
      "The details and a link are in the text.",
  );
});

test("P4: 15 seconds or less (the word budget), and never a link", () => {
  assert.ok(SPOKEN_MAX_WORDS <= 40, "about 150 words a minute");
  const long = REPORT.replace(
    "- We could not confirm who is allowed to rent this unit.",
    `- ${"This reason goes on and on ".repeat(8)}.`,
  );
  for (const text of [REPORT, long, REPORT_ES]) {
    const said = spokenReply(text);
    assert.ok(words(said) <= SPOKEN_MAX_WORDS, `${words(said)} words: ${said}`);
    assert.doesNotMatch(said, /https?:|\/case\//);
  }
  // the long reason is the part that goes; the verdict and who to call stay
  const said = spokenReply(long);
  assert.match(said, /^Hold off for now\./);
  assert.match(said, /Call Fixture Living LLC/);
  assert.doesNotMatch(said, /on and on/);
});

test("P4: in Spanish, the spoken reply is in Spanish", () => {
  assert.equal(
    spokenReply(REPORT_ES),
    "Espere por ahora. No pudimos confirmar quién puede rentar esta unidad. " +
      "Llame a Fixture Living LLC a través de oakcourt.example, no al número del anuncio. " +
      "Los detalles y el enlace están en el texto.",
  );
});

test("P4: a reason or call line with a phone number or a rent is never spoken", () => {
  const leaky = REPORT.replace(
    "- We could not confirm who is allowed to rent this unit.",
    "- The ad asks $1,150 and the number is 713-555-0199.",
  ).replace("Call Fixture Living LLC", "Call 713-555-0100 at Fixture Living LLC");
  const said = spokenReply(leaky);
  assert.doesNotMatch(said, /\d{3}|\$/);
  assert.match(said, /^Hold off for now\. A fresh photo proved/);
});

test("P4: a reply with no card (a plain line) is spoken as that line", () => {
  assert.equal(
    spokenReply("Send me the ad first and I'll check it."),
    "Send me the ad first and I'll check it.",
  );
});

// --- through Photon: "who do I call?" as a voice memo gets a spoken answer -------------------

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const RENTER = "fx-space-renter";

test("P4: 'who do I call?' by voice gets a spoken answer, and no new case", async () => {
  const calls: { url: string; method: string; body?: unknown }[] = [];
  const sent: { kind: string; text?: string }[] = [];
  const renter: PhotonSpace = {
    id: RENTER,
    send: async (content: unknown) =>
      void sent.push(
        typeof content === "string" ? { kind: "text", text: content } : (content as never),
      ),
  };
  const fetchFn = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body });
    if (url.endsWith("/voice/stt")) return Response.json({ text: "Who do I call?" });
    if (url.endsWith("/voice/tts"))
      return new Response(new Blob(["mp3"], { type: "audio/mpeg" }), {
        headers: { "content-type": "audio/mpeg" },
      });
    if (url.includes("/real-listing"))
      return Response.json({
        manager_company: "Fixture Living LLC",
        website_host: "oakcourt.example",
      });
    if (url.includes(`/cases/${card.case_id}/card`)) return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
  const memory = new CaseMemory();
  const { renterId } = await import("./handler");
  memory.remember(renterId(RENTER, "fx-salt"), card.case_id, null, "fx-read");
  const memo: PhotonMessage = {
    direction: "inbound",
    content: {
      type: "voice",
      mimeType: "audio/x-caf",
      duration: 2,
      read: async () => Buffer.from("caf"),
    },
  };
  await runPhoton(
    {
      messages: (async function* () {
        yield [renter, memo] as [PhotonSpace, PhotonMessage];
      })(),
    },
    {
      apiUrl: "http://api.test",
      webUrl: "https://snapback.example",
      allowedThreads: new Set([RENTER]),
      renterSalt: "fx-salt",
      quietMs: 5,
      fetch: fetchFn,
      memory,
      makeVoice: (bytes: Uint8Array) => ({ kind: "voice", bytes: bytes.length }),
      convertVoice: async (bytes: Uint8Array) => ({ bytes, mimeType: "audio/mp4", seconds: 2 }),
    },
  );
  assert.deepEqual(
    sent.map((s) => s.kind),
    ["text", "voice"],
  );
  assert.equal(calls.filter((c) => c.method === "POST" && c.url.endsWith("/cases")).length, 0);
  const tts = calls.find((c) => c.url.endsWith("/voice/tts"));
  const said = (JSON.parse(String(tts?.body)) as { text: string }).text;
  assert.match(said, /Call Fixture Living LLC through oakcourt\.example/);
  assert.doesNotMatch(said, /https?:/);
});

test("#281 review: unseparated numbers and street addresses are never spoken", () => {
  const leaky = REPORT.replace(
    "- We could not confirm who is allowed to rent this unit.",
    "- The poster asks you to text 7135550100 first.",
  ).replace("Call Fixture Living LLC", "Call Fixture Living LLC at 2100 Travis St");
  const said = spokenReply(leaky);
  assert.doesNotMatch(said, /7135550100|2100|Travis/);
  assert.match(said, /^Hold off for now\. A fresh photo proved/);
});

test("#281 review: a reply with nothing safe to say speaks nothing", () => {
  assert.equal(spokenReply("Case 7135550100"), "");
});
