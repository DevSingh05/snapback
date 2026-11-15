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
  /** Send a picture (the card PNG) to the same thread. Optional: without it, text only. */
  image?(threadId: string, bytes: Uint8Array, mimeType: string): Promise<void>;
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
  // #250: built by code in verdict.build_card. Optional: a card from before has none.
  summary?: string[];
  checks_out?: string[];
  does_not?: string[];
};
type CreateCaseResponse = {
  case_id: string;
  read_token?: string | null;
  challenge_text?: string | null;
};
/** #250's real-listing panel, as far as the reply reads it: who is on record, and where.
 * Its record rents (`plans`) are never read here, so they can never reach a reply. */
export type OfficeOnRecord = { manager_company?: string | null; website_host?: string | null };

export type SidecarConfig = {
  apiUrl: string;
  webUrl: string;
  allowedThreads: ReadonlySet<string>;
  renterSalt: string;
  maxPhotos?: number;
  fetch?: typeof fetch;
  /** Each thread's last case, for "why?" and "what should I do?". Without it, no follow-ups. */
  memory?: CaseMemory;
};

const CASE_TTL_MS = 2 * 60 * 60 * 1000; // a follow-up answers from a case up to 2 h old

type Remembered = { caseId: string; challenge?: string | null; readToken?: string | null };

/** Each thread's last case, keyed by the thread's keyed hash (never the thread id), in memory
 * only. Expired entries are dropped when read. */
export class CaseMemory {
  private last = new Map<string, Remembered & { at: number }>();
  private running = new Set<string>();

  constructor(private now: () => number = Date.now) {}

  remember(
    key: string,
    caseId: string,
    challenge?: string | null,
    readToken?: string | null,
  ): void {
    this.last.set(key, { caseId, challenge, readToken, at: this.now() });
  }

  /** This thread's own case, if it is still fresh. Never another thread's. */
  recall(key: string): Remembered | null {
    const found = this.last.get(key);
    if (!found) return null;
    if (this.now() - found.at > CASE_TTL_MS) {
      this.last.delete(key);
      return null;
    }
    return found;
  }

  /** A check is running for this thread: a follow-up must not answer from the older case. */
  begin(key: string): void {
    this.running.add(key);
  }
  end(key: string): void {
    this.running.delete(key);
  }
  checking(key: string): boolean {
    return this.running.has(key);
  }
}

export const SEND_THE_AD_FIRST = "Send me the ad first and I'll check it.";
export const STILL_CHECKING = "Still checking, one moment.";

type Intent = "why" | "now" | "call" | "safe";
const TAIL = String.raw`(\s+(now|then))?\s*[?.!]*\s*$`;
const INTENTS: [Intent, RegExp][] = [
  [
    "why",
    new RegExp(
      String.raw`^\s*(why( not)?|how come|what did you find|what's wrong|whats wrong)` + TAIL,
      "i",
    ),
  ],
  [
    "now",
    new RegExp(
      String.raw`^\s*(what (should|do|can) i do|what now|now what|what next|next steps?|what do i do)` +
        TAIL,
      "i",
    ),
  ],
  [
    "call",
    new RegExp(
      String.raw`^\s*(who (do|should|can) i (call|contact|talk to)|who('s| is) the (manager|landlord|office))` +
        TAIL,
      "i",
    ),
  ],
  [
    "safe",
    new RegExp(
      String.raw`^\s*(is (it|this|that) (safe|real|legit|a scam|ok|okay)|can i (pay|trust (it|this)))` +
        TAIL,
      "i",
    ),
  ],
];

/** The follow-up a short message asks, or null if it is an ad. Curly quotes count; any "why ..."
 * under 40 characters with no link is a "why". */
export function intentOf(raw: string): Intent | null {
  const text = raw.replace(/[\u2018\u2019]/g, "'").trim();
  for (const [intent, pattern] of INTENTS) if (pattern.test(text)) return intent;
  if (/^why\b/i.test(text) && text.length < 40 && !/https?:|www\./i.test(text)) return "why";
  return null;
}

const MAX_PHOTOS = 10;

/** Locked headlines: the `state.*` strings in src/snapback/card/strings.py, word for word. */
export const HEADLINES: Record<VerdictState, string> = {
  hold: "Hold off for now",
  unverified: "Could not place these photos",
  dont_pay: "Don't pay. Something here doesn't match.",
  verified: "Checks passed. Still follow the two rules.",
};
export const CHECKING =
  "Got it. Checking this against CoStar's record before you pay anyone. About a minute.";
export const ASK_PHOTOS = "Send the ad's photos too and I can check where they were taken.";
export const ONLY_A_LINK = "I can't open Marketplace links. Paste the ad's words and screenshots.";
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
  lines.push("", `Full report: ${link}`);
  if (card.footer.length) lines.push(...card.footer);
  return lines.join("\n");
}

const BAD_TONES = new Set(["red_flag", "hold", "not_shown"]);

/** Every card line as "label: text", in the card's own order. */
function cardLines(card: Card, tones: (tone: string) => boolean): string[] {
  return card.rows.flatMap((row) =>
    row.lines.filter((line) => tones(line.tone)).map((line) => `${line.label}: ${line.text}`),
  );
}

/** The lines that explain the verdict, all of them, from the card (never written here). */
function reasons(card: Card): string[] {
  if (card.state === "verified") {
    return card.checks_out?.length ? card.checks_out : cardLines(card, (t) => t === "ok");
  }
  if (card.does_not?.length) return card.does_not;
  // a card from before #250: red flags first, then hold and not-shown lines
  const red = cardLines(card, (t) => t === "red_flag");
  return [...red, ...cardLines(card, (t) => BAD_TONES.has(t) && t !== "red_flag")];
}

/** One next step: call the office on record through its own site (#250), else send the
 * challenge, else the card's own two rules. */
function nextStep(card: Card, challenge?: string | null, office?: OfficeOnRecord | null): string {
  if (office?.manager_company && office.website_host) {
    return `Call ${office.manager_company} through ${office.website_host}, not the number in the ad.`;
  }
  if (challenge) return `send the poster this message: ${challenge}`;
  return card.footer.find((line) => line.startsWith("Two rules")) ?? card.footer[0] ?? "";
}

/** The top two reasons: Card.summary first, then the first lines that do not check out. */
function topReasons(card: Card): string[] {
  const fromSummary = card.state === "verified" ? [] : (card.summary ?? []);
  return [...fromSummary, ...reasons(card)].slice(0, 2);
}

/** The reply (U2): the locked headline, "Before you pay:" with the top two reasons, one next
 * step and the link. Every word of the verdict and the reasons comes from the card; the
 * sidecar writes no verdict. */
export function reportText(
  card: Card,
  link: string,
  challenge?: string | null,
  office?: OfficeOnRecord | null,
  askPhotos = false,
): string {
  const lines = [
    HEADLINES[card.state] ?? HEADLINES.hold,
    `SNAPBACK check ${card.case_id} (${card.source.toUpperCase()})`,
  ];
  const top = topReasons(card);
  if (top.length) lines.push("", "Before you pay:", ...top.map((line) => `- ${line}`));
  const step = nextStep(card, challenge, office);
  if (step) lines.push("", `Next: ${step}`);
  if (askPhotos) lines.push("", ASK_PHOTOS);
  lines.push("", `Full report: ${link}`, 'Ask me "why?" or "what should I do?"');
  return lines.join("\n");
}

const LINK_ONLY = /^\s*(https?:\/\/\S+)\s*$/i;
const MARKETPLACE = /(^|\.)(facebook\.com|fb\.com|fb\.me|m\.facebook\.com)$/i;

/** U3: true when the message is nothing but a Marketplace link (no words, no photos). */
export function onlyAMarketplaceLink(msg: InboundMessage): boolean {
  if ((msg.images?.length ?? 0) > 0 || msg.imageUrls.length > 0) return false;
  const m = LINK_ONLY.exec(msg.text ?? "");
  if (!m?.[1]) return false;
  try {
    return MARKETPLACE.test(new URL(m[1]).hostname);
  } catch {
    return false;
  }
}

/** "why?": every reason on this case's card, what was not checked, and the link. */
function whyText(card: Card, link: string): string {
  const lines = [HEADLINES[card.state] ?? HEADLINES.hold, "", "Why:"];
  lines.push(...reasons(card).map((line) => `- ${line}`));
  if (card.not_checked.length) lines.push("", `Not checked: ${card.not_checked.join(", ")}`);
  lines.push("", `Full report: ${link}`);
  return lines.join("\n");
}

/** "what should I do?": the challenge to send (if any), then the card's own footer rules. */
function whatNowText(card: Card, link: string, challenge?: string | null): string {
  const lines = [HEADLINES[card.state] ?? HEADLINES.hold, ""];
  if (challenge) lines.push("Send the poster this message:", challenge, "");
  lines.push(...card.footer, "", `Full report: ${link}`);
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

type Checked = { text: string; caseId?: string };

function caseLink(config: SidecarConfig, caseId: string): string {
  return `${config.webUrl.replace(/\/$/, "")}/case/${encodeURIComponent(caseId)}`;
}

async function fetchCard(config: SidecarConfig, caseId: string): Promise<Card | null> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  const res = await get(`${api}/cases/${encodeURIComponent(caseId)}/card`);
  return res.ok ? ((await res.json()) as Card) : null;
}

/** The follow-up a message asks, or null when it is an ad (or carries photos). */
function followUpIntent(msg: InboundMessage): Intent | null {
  if ((msg.images?.length ?? 0) > 0 || msg.imageUrls.length > 0) return null;
  return intentOf(msg.text ?? "");
}

/** The answer to a follow-up. It never makes a case: no fresh case gives "send me the ad
 * first", a check still running gives "still checking", and a card that cannot be read gives
 * COULD_NOT_CHECK. */
async function answerFollowUp(
  intent: Intent,
  msg: InboundMessage,
  config: SidecarConfig,
): Promise<string> {
  const key = renterId(msg.threadId, config.renterSalt);
  if (config.memory?.checking(key)) return STILL_CHECKING;
  const last = config.memory?.recall(key);
  if (!last) return SEND_THE_AD_FIRST;
  const card = await fetchCard(config, last.caseId);
  if (!card) return COULD_NOT_CHECK;
  const link = caseLink(config, last.caseId);
  if (intent === "why") return whyText(card, link);
  if (intent === "now") return whatNowText(card, link, last.challenge);
  if (intent === "safe") return reportText(card, link, last.challenge);
  const office = last.readToken ? await officeOnRecord(config, last.caseId, last.readToken) : null;
  return whoToCall(card, link, office);
}

/** "who do I call?": the office on record and its own site (#250); never a phone number. */
function whoToCall(card: Card, link: string, office: OfficeOnRecord | null): string {
  const lines = [HEADLINES[card.state] ?? HEADLINES.hold, ""];
  if (office?.manager_company && office.website_host) {
    lines.push(
      `Call ${office.manager_company} through ${office.website_host}, not the number in the ad.`,
    );
  } else {
    lines.push("CoStar's record has no office on file for this building, so I can't name one.");
    lines.push(...card.footer.filter((line) => line.startsWith("Two rules")));
  }
  lines.push("", `Full report: ${link}`);
  return lines.join("\n");
}

/** Who is on record and where (#250), with the read token in a header. Only the company and
 * the host are kept: never a phone, an address or a rent. Null when there is no record. */
async function officeOnRecord(
  config: SidecarConfig,
  caseId: string,
  readToken: string,
): Promise<OfficeOnRecord | null> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  try {
    const res = await get(`${api}/cases/${encodeURIComponent(caseId)}/real-listing`, {
      headers: { Authorization: `Bearer ${readToken}` },
    });
    if (!res.ok) return null;
    const panel = (await res.json()) as OfficeOnRecord;
    return { manager_company: panel.manager_company, website_host: panel.website_host };
  } catch {
    return null;
  }
}

async function check(msg: InboundMessage, config: SidecarConfig): Promise<Checked> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");

  const form = new FormData();
  form.set("renter_id", renterId(msg.threadId, config.renterSalt));
  form.set("text", msg.text ?? "");
  const max = config.maxPhotos ?? MAX_PHOTOS;
  const images = [...(msg.images ?? []), ...(await photos(msg.imageUrls, max, get))].slice(0, max);
  images.forEach((blob, i) => form.append("photos", blob, `photo-${i + 1}.jpg`));

  const created = await get(`${api}/cases`, { method: "POST", body: form });
  if (created.status === 429) return { text: LIMIT_REACHED };
  if (!created.ok) return { text: COULD_NOT_CHECK };
  // Only the public id is read from the response; the case token never leaves this function.
  const {
    case_id: caseId,
    read_token: readToken,
    challenge_text: challenge,
  } = (await created.json()) as CreateCaseResponse;
  config.memory?.remember(renterId(msg.threadId, config.renterSalt), caseId, challenge, readToken);
  const link = caseLink(config, caseId);
  const card = await fetchCard(config, caseId);
  if (!card) return { text: `${HEADLINES.hold}\nSNAPBACK check ${caseId} started.\n${link}` };
  const office = readToken ? await officeOnRecord(config, caseId, readToken) : null;
  return { text: reportText(card, link, challenge, office, images.length === 0), caseId };
}

/** The card as a picture, sent after the text. A failure here never undoes the text. */
async function sendCardPicture(
  client: MessageClient,
  msg: InboundMessage,
  config: SidecarConfig,
  caseId: string,
): Promise<void> {
  if (!client.image) return;
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  try {
    const res = await get(`${api}/cases/${encodeURIComponent(caseId)}/card.png`);
    if (!res.ok) return;
    const bytes = new Uint8Array(await res.arrayBuffer());
    await client.image(msg.threadId, bytes, res.headers.get("content-type") ?? "image/png");
  } catch {
    // the text reply already went out
  }
}

/** Handle one inbound message. Returns false when the thread is not allowed (nothing is sent). */
export async function handleMessage(
  msg: InboundMessage,
  client: MessageClient,
  config: SidecarConfig,
  onChecking?: () => Promise<void>,
): Promise<boolean> {
  if (!isAllowed(msg.threadId, config)) return false;
  const intent = followUpIntent(msg);
  if (intent !== null) {
    // Ruling (#255 review): a follow-up never creates a case, whatever happens here.
    let answer: string;
    try {
      answer = await answerFollowUp(intent, msg, config);
    } catch {
      answer = COULD_NOT_CHECK;
    }
    await client.reply(msg.threadId, answer);
    return true;
  }
  if (onlyAMarketplaceLink(msg)) {
    await client.reply(msg.threadId, ONLY_A_LINK); // nothing to check, so no check is used
    return true;
  }
  const key = renterId(msg.threadId, config.renterSalt);
  let checked: Checked;
  config.memory?.begin(key);
  try {
    try {
      await onChecking?.();
    } catch {
      // a failed "checking" reply never skips the check
    }
    checked = await check(msg, config);
  } catch {
    checked = { text: COULD_NOT_CHECK };
  } finally {
    config.memory?.end(key);
  }
  await client.reply(msg.threadId, checked.text);
  if (checked.caseId) await sendCardPicture(client, msg, config, checked.caseId);
  return true;
}
