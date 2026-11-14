/**
 * Renter message in -> one POST /cases -> one reply in the same thread with the verdict
 * headline, the card as plain text and the link to the result page.
 *
 * Hard rules this file enforces:
 * - Only threads on the allowlist get anything back (the renter's own thread). An empty
 *   allowlist answers nobody.
 * - SNAPBACK never texts first: `reply` is only ever called with the thread of the message
 *   being handled. There is no other send path.
 * - The API never sees a phone number or handle: the renter id is a keyed hash (HMAC-SHA256)
 *   of the thread id, so it cannot be reversed by hashing guessed numbers.
 * - Case tokens from the API are never put in a reply.
 */

import { createHmac } from "node:crypto";

/** One inbound message from a renter, whatever channel it arrived on. */
export type InboundMessage = {
  threadId: string;
  text?: string;
  imageUrls: string[];
  /** Photos already in hand (Photon hands over attachment bytes, not links). */
  images?: Blob[];
  receivedAt: string;
};

/** The part of a Photon client the sidecar uses. The real one is wired in index.ts. */
export interface MessageClient {
  reply(threadId: string, text: string): Promise<void>;
}

type VerdictState = "verified" | "hold" | "dont_pay" | "unverified";
type CardLine = { label: string; text: string; tone: string };
type Card = {
  case_id: string;
  source: "live" | "fixture";
  state: VerdictState;
  rows: { kind: string; lines: CardLine[] }[];
  not_checked: string[];
  footer: string[];
};
type CreateCaseResponse = { case_id: string; challenge_text?: string | null };

export type SidecarConfig = {
  apiUrl: string;
  webUrl: string;
  allowedThreads: ReadonlySet<string>;
  renterSalt: string;
  maxPhotos?: number;
  fetch?: typeof fetch;
};

const MAX_PHOTOS = 10;

/** Locked headlines: the `state.*` strings in src/snapback/card/strings.py, word for word. */
export const HEADLINES: Record<VerdictState, string> = {
  hold: "Hold off for now",
  unverified: "Could not place these photos",
  dont_pay: "Don't pay. Something here doesn't match.",
  verified: "Checks passed. Still follow the two rules.",
};
export const COULD_NOT_CHECK = "We couldn't check this right now. Don't pay anyone yet.";
export const LIMIT_REACHED =
  "You have used today's checks. Try again tomorrow. Don't pay anyone yet.";

export function renterId(threadId: string, salt: string): string {
  return "imsg-" + createHmac("sha256", salt).update(threadId).digest("hex").slice(0, 24);
}

/** The allowlist holds a thread id, or its keyed hash (so no handle needs to sit in the env). */
export function isAllowed(threadId: string, config: SidecarConfig): boolean {
  return (
    config.allowedThreads.has(threadId) ||
    config.allowedThreads.has(renterId(threadId, config.renterSalt))
  );
}

export function cardText(card: Card, link: string, challenge?: string | null): string {
  const lines = [
    HEADLINES[card.state] ?? HEADLINES.hold,
    `SNAPBACK check ${card.case_id} (${card.source.toUpperCase()})`,
  ];
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

async function check(msg: InboundMessage, config: SidecarConfig): Promise<string> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");

  const form = new FormData();
  form.set("renter_id", renterId(msg.threadId, config.renterSalt));
  form.set("text", msg.text ?? "");
  const max = config.maxPhotos ?? MAX_PHOTOS;
  const images = [...(msg.images ?? []), ...(await photos(msg.imageUrls, max, get))].slice(0, max);
  images.forEach((blob, i) => form.append("photos", blob, `photo-${i + 1}.jpg`));

  const created = await get(`${api}/cases`, { method: "POST", body: form });
  if (created.status === 429) return LIMIT_REACHED;
  if (!created.ok) return COULD_NOT_CHECK;
  // Only the public id is read from the response; the case token never leaves this function.
  const { case_id: caseId, challenge_text: challenge } =
    (await created.json()) as CreateCaseResponse;
  const link = `${config.webUrl.replace(/\/$/, "")}/case/${encodeURIComponent(caseId)}`;
  const cardRes = await get(`${api}/cases/${encodeURIComponent(caseId)}/card`);
  if (!cardRes.ok) return `${HEADLINES.hold}\nSNAPBACK check ${caseId} started.\n${link}`;
  return cardText((await cardRes.json()) as Card, link, challenge);
}

/** Handle one inbound message. Returns false when the thread is not allowed (nothing is sent). */
export async function handleMessage(
  msg: InboundMessage,
  client: MessageClient,
  config: SidecarConfig,
): Promise<boolean> {
  if (!isAllowed(msg.threadId, config)) return false;
  let text: string;
  try {
    text = await check(msg, config);
  } catch {
    text = COULD_NOT_CHECK;
  }
  await client.reply(msg.threadId, text);
  return true;
}
