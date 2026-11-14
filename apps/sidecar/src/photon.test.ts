import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { cardText, renterId } from "./handler";
import {
  connectPhoton,
  runPhoton,
  type PhotonApp,
  type PhotonMessage,
  type PhotonSpace,
} from "./photon";

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const SALT = "fx-sidecar-salt";
const RENTER = "fx-space-renter";
const STRANGER = "fx-space-stranger";
const SECRET = "fx-photon-secret-do-not-log";

type Call = { url: string; method: string; body?: FormData };

function api(calls: Call[]): typeof fetch {
  return (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body as FormData | undefined });
    if (url.endsWith("/cases") && init?.method === "POST") {
      return Response.json({ case_id: card.case_id, token: "fx-token" }, { status: 201 });
    }
    if (url.endsWith(`/cases/${card.case_id}/card`)) return Response.json(card);
    return new Response("not found", { status: 404 });
  }) as typeof fetch;
}

function space(id: string): PhotonSpace & { sent: string[] } {
  const sent: string[] = [];
  return { id, sent, send: async (text: string) => void sent.push(text) };
}

const text = (body: string, direction: "inbound" | "outbound" = "inbound"): PhotonMessage => ({
  direction,
  content: { type: "text", text: body },
});
const photo = (): PhotonMessage => ({
  direction: "inbound",
  content: {
    type: "attachment",
    mimeType: "image/jpeg",
    read: async () => Buffer.from("jpeg-bytes"),
  },
});

function app(items: [PhotonSpace, PhotonMessage][]): PhotonApp {
  return {
    messages: (async function* () {
      for (const item of items) yield item;
    })(),
  };
}

function config(calls: Call[], allowed: string[] = [RENTER]) {
  return {
    apiUrl: "http://api.test",
    webUrl: "http://web.test",
    allowedThreads: new Set(allowed),
    renterSalt: SALT,
    fetch: api(calls),
    quietMs: 5,
  };
}

function logs(): { lines: string[]; log: (line: string) => void } {
  const lines: string[] = [];
  return { lines, log: (line: string) => void lines.push(line) };
}

test("a renter's text and photo in their own thread -> one case -> the card in that thread", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(
    app([
      [renter, text("Is this real? fx-listing")],
      [renter, photo()],
    ]),
    config(calls),
  );

  const posts = calls.filter((c) => c.method === "POST");
  assert.equal(posts.length, 1, "the text and its photo are one check, not two");
  assert.equal(posts[0]?.body?.get("text"), "Is this real? fx-listing");
  assert.equal(posts[0]?.body?.getAll("photos").length, 1);
  assert.equal(posts[0]?.body?.get("renter_id"), renterId(RENTER, SALT));
  assert.equal(renter.sent.length, 1);
  // the reply is the API's card as plain text plus its link, line for line
  const link = `http://web.test/case/${card.case_id}`;
  assert.equal(renter.sent[0], cardText(card, link));
});

test("SNAPBACK never texts first: no inbound message, no send", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  // only our own outbound echo arrives: nothing is checked and nothing is sent
  await runPhoton(app([[renter, text("Hold off for now", "outbound")]]), config(calls));
  assert.equal(calls.length, 0);
  assert.equal(renter.sent.length, 0);
});

test("a thread not on the allowlist gets nothing, and its id and words are not logged", async () => {
  const calls: Call[] = [];
  const stranger = space(STRANGER);
  const out = logs();
  await runPhoton(app([[stranger, text("fx-private-words")]]), config(calls), out.log);
  assert.equal(calls.length, 0);
  assert.equal(stranger.sent.length, 0);
  const said = out.lines.join("\n");
  assert.ok(!said.includes(STRANGER) && !said.includes("fx-private-words"), said);
  // the log names the thread only by its keyed hash, which is what the allowlist may hold
  assert.ok(said.includes(renterId(STRANGER, SALT)), said);
});

test("the allowlist may hold the keyed hash instead of the raw thread id", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  await runPhoton(app([[renter, text("fx-listing")]]), config(calls, [renterId(RENTER, SALT)]));
  assert.equal(renter.sent.length, 1);
});

test("the reply goes only to the thread the message came from", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  const other = space("fx-space-other-renter");
  await runPhoton(
    app([
      [renter, text("fx-listing-1")],
      [other, text("fx-listing-2")],
    ]),
    config(calls, [RENTER, "fx-space-other-renter"]),
  );
  assert.equal(renter.sent.length, 1);
  assert.equal(other.sent.length, 1);
});

test("connecting never logs the secret, and a missing project id says so without it", async () => {
  const out = logs();
  const seen: Record<string, unknown>[] = [];
  const load = async () => ({
    Spectrum: async (options: Record<string, unknown>) => {
      seen.push(options);
      return app([]);
    },
    imessage: { config: () => ({ provider: "imessage" }) },
  });
  await connectPhoton(
    { SPECTRUM_PROJECT_ID: "fx-project", SPECTRUM_PROJECT_SECRET: SECRET },
    load,
    out.log,
  );
  assert.equal(seen[0]?.projectSecret, SECRET);
  assert.equal(seen[0]?.projectId, "fx-project");

  await assert.rejects(
    connectPhoton({ SPECTRUM_PROJECT_SECRET: SECRET }, load, out.log),
    (error: Error) => !error.message.includes(SECRET) && /SPECTRUM_PROJECT_ID/.test(error.message),
  );
  assert.ok(!out.lines.join("\n").includes(SECRET));
});

test("a message that fails to read does not stop the loop", async () => {
  const calls: Call[] = [];
  const renter = space(RENTER);
  const broken: PhotonMessage = {
    direction: "inbound",
    content: {
      type: "attachment",
      mimeType: "image/jpeg",
      read: async () => {
        throw new Error("download failed");
      },
    },
  };
  await runPhoton(
    app([
      [renter, broken],
      [renter, text("fx-listing")],
    ]),
    config(calls),
  );
  assert.equal(renter.sent.length, 1);
});
