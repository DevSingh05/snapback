/**
 * Renter message in -> one POST /cases -> one reply in the same thread with the card as plain
 * text and the link to the result page.
 *
 * Hard rules this file enforces:
 * - Only threads on the allowlist get anything back (the renter's own thread). An empty
 *   allowlist answers nobody.
 * - SNAPBACK never texts first: `reply` is only ever called with the thread of the message
 *   being handled. There is no other send path.
 * - The API never sees a phone number or handle: the renter id is a hash of the thread id.
 */

import { createHash } from "node:crypto";

/** One inbound message from a renter, whatever channel it arrived on. */
export type InboundMessage = {
  threadId: string;
  text?: string;
  imageUrls: string[];
  receivedAt: string;
};

/** The part of a Photon client the sidecar uses. The real one is wired in index.ts. */
export interface MessageClient {
  reply(threadId: string, text: string): Promise<void>;
}

type CardLine = { label: string; text: string; tone: string };
type Card = {
  case_id: string;
  source: "live" | "fixture";
  rows: { kind: string; lines: CardLine[] }[];
  not_checked: string[];
  footer: string[];
};
type CreateCaseResponse = { case_id: string; challenge_text?: string | null };

export type SidecarConfig = {
  apiUrl: string;
  webUrl: string;
  allowedThreads: ReadonlySet<string>;
  maxPhotos?: number;
  fetch?: typeof fetch;
};

const MAX_PHOTOS = 10;

export function renterId(threadId: string): string {
  return "imsg-" + createHash("sha256").update(threadId).digest("hex").slice(0, 16);
}

export function cardText(card: Card, link: string, challenge?: string | null): string {
  const lines = [`SNAPBACK check ${card.case_id} (${card.source.toUpperCase()})`];
  for (const row of card.rows) {
    for (const line of row.lines) lines.push(`${line.label}: ${line.text}`);
  }
  if (challenge) lines.push("", "Message to send to the poster:", challenge);
  if (card.not_checked.length) lines.push("", `Not checked: ${card.not_checked.join(", ")}`);
  lines.push("", `Full result: ${link}`);
  if (card.footer.length) lines.push(...card.footer);
  return lines.join("\n");
}

async function photos(urls: string[], max: number, get: typeof fetch): Promise<Blob[]> {
  const out: Blob[] = [];
  for (const url of urls.slice(0, max)) {
    const res = await get(url);
    if (res.ok) out.push(await res.blob());
  }
  return out;
}

/** Handle one inbound message. Returns false when the thread is not allowed (nothing is sent). */
export async function handleMessage(
  msg: InboundMessage,
  client: MessageClient,
  config: SidecarConfig,
): Promise<boolean> {
  if (!config.allowedThreads.has(msg.threadId)) return false;
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");

  const form = new FormData();
  form.set("renter_id", renterId(msg.threadId));
  form.set("text", msg.text ?? "");
  const images = await photos(msg.imageUrls, config.maxPhotos ?? MAX_PHOTOS, get);
  images.forEach((blob, i) => form.append("photos", blob, `photo-${i + 1}.jpg`));

  const created = await get(`${api}/cases`, { method: "POST", body: form });
  if (!created.ok) {
    const detail =
      created.status === 429 ? "You have used today's checks. Try again tomorrow." : "";
    await client.reply(msg.threadId, detail || "SNAPBACK could not start this check. Try again.");
    return true;
  }
  const body = (await created.json()) as CreateCaseResponse;
  const cardRes = await get(`${api}/cases/${encodeURIComponent(body.case_id)}/card`);
  const link = `${config.webUrl.replace(/\/$/, "")}/case/${encodeURIComponent(body.case_id)}`;
  if (!cardRes.ok) {
    await client.reply(msg.threadId, `SNAPBACK check ${body.case_id} started.\n${link}`);
    return true;
  }
  const card = (await cardRes.json()) as Card;
  await client.reply(msg.threadId, cardText(card, link, body.challenge_text));
  return true;
}
