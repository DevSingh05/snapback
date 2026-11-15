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

import { howCheckedText, type Timeline } from "./howchecked";
import {
  PHONE_LIKE,
  learnFrom,
  profileCommand,
  type Lang,
  type Profile,
  type ProfileStore,
} from "./profile";

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
  headline?: string; // #256: the card's own headline, built by code
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
  /** Adaptive memory (D2): what each renter told us about themselves. Without it, nothing. */
  profiles?: ProfileStore;
};

const CASE_TTL_MS = 2 * 60 * 60 * 1000; // a follow-up answers from a case up to 2 h old

type Remembered = { caseId: string; challenge?: string | null; readToken?: string | null };

/** Each thread's last case, keyed by the thread's keyed hash (never the thread id), in memory
 * only. Expired entries are dropped when read. */
export class CaseMemory {
  private last = new Map<string, Remembered & { at: number }>();
  private running = new Set<string>();
  private offers = new Map<string, Lang>(); // D6: a copy-alert draft offered on the last case

  constructor(private now: () => number = Date.now) {}

  remember(
    key: string,
    caseId: string,
    challenge?: string | null,
    readToken?: string | null,
  ): void {
    this.last.set(key, { caseId, challenge, readToken, at: this.now() });
    this.offers.delete(key); // a new case closes the last one's offer
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

  /** "forget me": the thread's remembered case goes too. */
  forget(key: string): void {
    this.last.delete(key);
    this.offers.delete(key);
  }

  /** D6: the last check offered to draft a note to the office on record. */
  offer(key: string, lang: Lang): void {
    this.offers.set(key, lang);
  }

  /** The open offer's language, consumed: a second "yes" is not a draft. */
  takeOffer(key: string): Lang | null {
    const lang = this.offers.get(key) ?? null;
    this.offers.delete(key);
    return lang;
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

/** Locked Spanish headlines: the `state.*` strings in card/strings.py (es), word for word. */
const HEADLINES_ES: Record<string, string> = {
  hold: "Espere por ahora",
  unverified: "No se pudieron ubicar estas fotos",
  dont_pay: "No pague. Algo aquí no coincide.",
  verified: "Las revisiones pasaron. Siga igual las dos reglas.",
};
// #280: the card's red-flag headlines (strings.py state.hold_red_*), in Spanish word for word.
const RED_HEADLINES_ES: Record<string, string> = {
  "Hold off: it asks for money before you've seen the place":
    "Espere: pide dinero antes de que usted haya visto el lugar",
  "Hold off: it asks for personal papers before you've seen the place":
    "Espere: pide documentos personales antes de que haya visto el lugar",
  "Hold off: it pushes you to act before you've seen the place":
    "Espere: le presiona para actuar antes de ver el lugar",
  "Hold off: something in this ad is a red flag":
    "Espere: algo en este anuncio es una señal de alerta",
};

/** The reply's own few words, in each language. The verdict and reasons come from the card. */
const WORDS = {
  en: {
    before: "Before you pay:",
    why: "Why:",
    next: "Next:",
    full: "Full report:",
    notChecked: "Not checked:",
    ask: 'Ask me "why?" or "what should I do?"',
    photos: "Send the ad's photos too and I can check where they were taken.",
    call: (who: string, host: string) => `Call ${who} through ${host}, not the number in the ad.`,
    send: (msg: string) => `send the poster this message: ${msg}`,
    sendTitle: "Send the poster this message:",
    rules: "Two rules",
    checking:
      "Got it. Checking this against CoStar's record before you pay anyone. About a minute.",
    adFirst: "Send me the ad first and I'll check it.",
    stillChecking: "Still checking, one moment.",
    noOffice: "CoStar's record has no office on file for this building, so I can't name one.",
  },
  es: {
    before: "Antes de pagar:",
    why: "Por qué:",
    next: "Siguiente:",
    full: "Informe completo:",
    notChecked: "Sin revisar:",
    ask: 'Pregúnteme "¿por qué?" o "¿qué hago?"',
    photos: "Mándeme también las fotos del anuncio y reviso dónde se tomaron.",
    call: (who: string, host: string) =>
      `Llame a ${who} a través de ${host}, no al número del anuncio.`,
    send: (msg: string) => `mándele este mensaje a quien publica: ${msg}`,
    sendTitle: "Mándele este mensaje a quien publica:",
    rules: "Dos reglas",
    checking:
      "Recibido. Lo reviso con el registro de CoStar antes de que pague a nadie. Cerca de un minuto.",
    adFirst: "Mándeme primero el anuncio y lo reviso.",
    stillChecking: "Sigo revisando, un momento.",
    noOffice:
      "El registro de CoStar no tiene una oficina para este edificio, así que no puedo nombrar una.",
  },
} as const;
export const STILL_CHECKING = "Still checking, one moment.";

type Intent = "why" | "now" | "call" | "safe" | "places" | "how";
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

const SPANISH_INTENTS: [Intent, RegExp][] = [
  ["why", /^\s*por\s*qu[eé]\s*[?.!]*\s*$/i],
  ["now", /^\s*(qu[eé] (hago|debo hacer|puedo hacer)( ahora)?)\s*[?.!]*\s*$/i],
  ["call", /^\s*(a qui[eé]n (llamo|le llamo|contacto))\s*[?.!]*\s*$/i],
  ["safe", /^\s*(es (seguro|real|una estafa|confiable))\s*[?.!]*\s*$/i],
];
const HOW =
  /^\s*(how did you (check|know|do that|figure (it|that) out|work (it|that) out)|how do you know|how does (it|this) work|show (me )?your work|c[oó]mo lo (revisaste|revis[oó]|sabes|supiste|hiciste))\s*[?.!]*\s*$/i;
const PLACES =
  /^\s*(show me( some| other| real| safer)? (places|homes|apartments|listings)|(other|safer|real) (places|homes|apartments)|find me (a place|places|a home|homes)|mu[eé]strame (lugares|opciones|casas|departamentos)|otras opciones|busca(me)? (un lugar|lugares|departamentos))\s*[?.!]*\s*$/i;

/** The follow-up a short message asks, or null if it is an ad. Curly quotes count; any "why ..."
 * under 40 characters with no link is a "why". */
export function intentOf(raw: string): Intent | null {
  const text = raw
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[¿¡]/g, "")
    .trim();
  if (PLACES.test(text)) return "places";
  if (HOW.test(text)) return "how";
  for (const [intent, pattern] of SPANISH_INTENTS) if (pattern.test(text)) return intent;
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

/** The card's own headline (#256: an honest ad reads differently) when set, else the locked
 * headline for its state. Both are code-owned; the sidecar never writes one. */
export function headlineOf(card: Card, lang: Lang = "en"): string {
  const own = card.headline?.trim();
  if (own) return lang === "es" ? (RED_HEADLINES_ES[own] ?? own) : own;
  if (lang === "es") return HEADLINES_ES[card.state] ?? HEADLINES_ES.hold ?? HEADLINES.hold;
  return HEADLINES[card.state] ?? HEADLINES.hold;
}

export function cardText(card: Card, link: string, challenge?: string | null): string {
  const lines = [headlineOf(card), `SNAPBACK check ${card.case_id} (${card.source.toUpperCase()})`];
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
function nextStep(
  card: Card,
  challenge?: string | null,
  office?: OfficeOnRecord | null,
  lang: Lang = "en",
): string {
  const w = WORDS[lang];
  if (office?.manager_company && office.website_host) {
    return w.call(office.manager_company, office.website_host);
  }
  if (challenge) return w.send(challenge);
  return card.footer.find((line) => line.startsWith(w.rules)) ?? card.footer[0] ?? "";
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
  lang: Lang = "en",
): string {
  const w = WORDS[lang];
  const lines = [
    headlineOf(card, lang),
    `SNAPBACK check ${card.case_id} (${card.source.toUpperCase()})`,
  ];
  const top = topReasons(card);
  if (top.length) lines.push("", w.before, ...top.map((line) => `- ${line}`));
  const step = nextStep(card, challenge, office, lang);
  if (step) lines.push("", `${w.next} ${step}`);
  if (askPhotos) lines.push("", w.photos);
  lines.push("", `${w.full} ${link}`, w.ask);
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
function whyText(card: Card, link: string, lang: Lang = "en"): string {
  const w = WORDS[lang];
  const lines = [headlineOf(card, lang), "", w.why];
  lines.push(...reasons(card).map((line) => `- ${line}`));
  if (card.not_checked.length) lines.push("", `${w.notChecked} ${card.not_checked.join(", ")}`);
  lines.push("", `${w.full} ${link}`);
  return lines.join("\n");
}

/** "what should I do?": the challenge to send (if any), then the card's own footer rules. */
function whatNowText(
  card: Card,
  link: string,
  challenge?: string | null,
  lang: Lang = "en",
): string {
  const w = WORDS[lang];
  const lines = [headlineOf(card, lang), ""];
  if (challenge) lines.push(w.sendTitle, challenge, "");
  lines.push(...card.footer, "", `${w.full} ${link}`);
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

async function fetchCard(
  config: SidecarConfig,
  caseId: string,
  lang: Lang = "en",
): Promise<Card | null> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  const query = lang === "es" ? "?lang=es" : "";
  const res = await get(`${api}/cases/${encodeURIComponent(caseId)}/card${query}`);
  return res.ok ? ((await res.json()) as Card) : null;
}

function noPhotosIn(msg: InboundMessage): boolean {
  return (msg.images?.length ?? 0) === 0 && msg.imageUrls.length === 0;
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
  profile: Profile | null = null,
): Promise<string> {
  const lang: Lang = profile?.lang ?? learnFrom(msg.text ?? "").lang ?? "en";
  const w = WORDS[lang];
  if (intent === "places") return saferHomes(config, profile, lang);
  const key = renterId(msg.threadId, config.renterSalt);
  if (config.memory?.checking(key)) return lang === "es" ? w.stillChecking : STILL_CHECKING;
  const last = config.memory?.recall(key);
  if (!last) return lang === "es" ? w.adFirst : SEND_THE_AD_FIRST;
  const card = await fetchCard(config, last.caseId, lang);
  if (!card) return COULD_NOT_CHECK;
  const link = caseLink(config, last.caseId);
  if (intent === "why") return whyText(card, link, lang);
  if (intent === "now") return whatNowText(card, link, last.challenge, lang);
  if (intent === "safe") return reportText(card, link, last.challenge, null, false, lang);
  if (intent === "how") {
    const timeline = last.readToken
      ? await fetchTimeline(config, last.caseId, last.readToken, lang)
      : null;
    if (!timeline) return COULD_NOT_CHECK;
    return howCheckedText(timeline, card, link, lang, headlineOf(card, lang));
  }
  const office = last.readToken ? await officeOnRecord(config, last.caseId, last.readToken) : null;
  return whoToCall(card, link, office, lang);
}

/** "who do I call?": the office on record and its own site (#250); never a phone number. */
function whoToCall(
  card: Card,
  link: string,
  office: OfficeOnRecord | null,
  lang: Lang = "en",
): string {
  const w = WORDS[lang];
  const lines = [headlineOf(card, lang), ""];
  if (office?.manager_company && office.website_host) {
    lines.push(w.call(office.manager_company, office.website_host));
  } else {
    lines.push(w.noOffice);
    lines.push(...card.footer.filter((line) => line.startsWith(w.rules)));
  }
  lines.push("", `${w.full} ${link}`);
  return lines.join("\n");
}

/** The part of /search's PlaceMatch this reply reads. It carries no hand-off link (that is
 * on /alternatives), and its rents are never read, so they can never reach a reply. */
type PlaceMatch = {
  kind?: string;
  floor_plan?: string | null;
  office_on_record?: string | null;
};

/** "show me safer homes": researched places that fit the remembered budget and beds, from our
 * own search (POST /search). Asks only for what it does not know yet. Never prints a rent. */
async function saferHomes(
  config: SidecarConfig,
  profile: Profile | null,
  lang: Lang,
): Promise<string> {
  const es = lang === "es";
  const missing: string[] = [];
  if (profile?.budget === undefined) {
    missing.push(es ? "¿Cuál es su presupuesto al mes?" : "What's your monthly budget?");
  }
  if (profile?.beds === undefined) {
    missing.push(es ? "¿Cuántas recámaras necesita?" : "How many bedrooms do you need?");
  }
  if (missing.length) {
    return [
      es ? "Para buscarle lugares más seguros:" : "To find you safer homes:",
      ...missing,
    ].join("\n");
  }
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  const res = await get(`${api}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      max_rent_month: profile?.budget,
      beds_min: profile?.beds,
      max_results: 3,
    }),
  });
  if (!res.ok) return COULD_NOT_CHECK;
  const found = (await res.json()) as { matches?: PlaceMatch[] };
  const places = (found.matches ?? []).slice(0, 3);
  const budget = `$${(profile?.budget ?? 0).toLocaleString("en-US")}`;
  const fit = es
    ? `${profile?.beds} recámaras, hasta ${budget}`
    : `${profile?.beds} beds, up to ${budget}`;
  if (places.length === 0) {
    return es
      ? `Ahora no hay lugares investigados que encajen (${fit}).`
      : `No researched places fit ${fit} right now.`;
  }
  const lines = [es ? `Lugares más seguros para ${fit}:` : `Safer homes for ${fit}:`];
  for (const place of places) {
    const what = place.floor_plan ?? place.kind ?? "";
    const who = place.office_on_record ? ` · ${place.office_on_record}` : "";
    lines.push(`- ${what}${who}`);
  }
  lines.push(es ? "(según la última investigación de CoStar)" : "(as of CoStar's last research)");
  const map = `${config.webUrl.replace(/\/$/, "")}/map`;
  lines.push(es ? `Véalos en el mapa: ${map}` : `See them on the map: ${map}`);
  return lines.join("\n");
}

const AD_CUES =
  /zelle|deposit|dep[oó]sito|venmo|cash ?app|wire|for rent|se renta|tenant|inquilino|text me|call me|avail(able)?\b|disponible|move[- ]in|\bbath|ba[nñ]o|\$\s?\d{3,5}\s*(a|per|\/)\s*(month|mo)/i;
const A_LINK = /https?:|www\./i;
const MONEY = /\$\s?\d/;
const BEDS =
  /\b\d{1,2}\s*(?:-|\s)?(?:beds?|bedrooms?|br|bd|rec[aá]maras?|habitaciones?|cuartos?)\b/i;

/** A message that only tells us about the renter (budget, beds, city), not an ad to check: no ad
 * wording, no phone-like digits, no link, and it states something about them. */
function onlyAboutThem(text: string, learned: Profile): boolean {
  if (text.length > 160 || AD_CUES.test(text) || PHONE_LIKE.test(text) || A_LINK.test(text)) {
    return false;
  }
  // A price or "2 bed" is an ad's unless the renter said it about themselves ("my budget is",
  // "I need 2 beds"); a city alone never makes a message theirs.
  if (MONEY.test(text) && learned.budget === undefined) return false;
  if (BEDS.test(text) && learned.beds === undefined) return false;
  return learned.budget !== undefined || learned.beds !== undefined || learned.city !== undefined;
}

function rememberedText(profile: Profile, lang: Lang): string {
  const es = lang === "es";
  const parts: string[] = [];
  if (profile.budget !== undefined) {
    parts.push(`${es ? "presupuesto" : "budget"} $${profile.budget.toLocaleString("en-US")}`);
  }
  if (profile.beds !== undefined) parts.push(`${profile.beds} ${es ? "recámaras" : "beds"}`);
  if (profile.city) parts.push(profile.city);
  return es
    ? `Anotado: ${parts.join(", ")}. Lo recuerdo 30 días. Escriba "muéstrame lugares" para ver lugares más seguros que encajen, o "olvídame" para borrarlo.`
    : `Got it: ${parts.join(", ")}. I'll remember that for 30 days. Text "show me places" for safer homes that fit, or "forget me" to delete it.`;
}

type CopyAlert = {
  fires: boolean;
  manager_company?: string | null;
  website_host?: string | null;
  draft_subject?: string | null;
  draft_body?: string | null;
};

const OFFER = {
  en: 'Want me to draft a note to the real leasing office? Reply "draft".',
  es: '¿Quiere que le redacte una nota a la oficina de arrendamiento real? Responda "borrador".',
};
const DRAFT_YES =
  /^\s*(draft( it| the note)?|yes( please)?|yeah|sure|ok(ay)?|y|borrador|s[ií]( por favor)?|claro|dale)\s*[.!]*\s*$/i;

/** D6: the draft note for the office on record (#250), with the read token in a header. */
async function fetchCopyAlert(
  config: SidecarConfig,
  caseId: string,
  readToken: string,
  lang: Lang,
): Promise<CopyAlert | null> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  const query = lang === "es" ? "?lang=es" : "";
  try {
    const res = await get(`${api}/cases/${encodeURIComponent(caseId)}/copy-alert${query}`, {
      headers: { Authorization: `Bearer ${readToken}` },
    });
    return res.ok ? ((await res.json()) as CopyAlert) : null;
  } catch {
    return null;
  }
}

/** The draft as the renter gets it: marked as not sent, addressed to the office on record. */
function draftText(alert: CopyAlert, lang: Lang): string {
  const es = lang === "es";
  const to = [alert.manager_company, alert.website_host ? `(${alert.website_host})` : ""]
    .filter(Boolean)
    .join(" ");
  return [
    es ? "Borrador, no enviado. Usted lo envía." : "Draft, not sent. You send it.",
    `${es ? "Para" : "To"}: ${to}`,
    `${es ? "Asunto" : "Subject"}: ${alert.draft_subject ?? ""}`,
    "",
    alert.draft_body ?? "",
  ].join("\n");
}

/** D5: the case's own timeline (#267), with the read token in a header. Null if it fails. */
async function fetchTimeline(
  config: SidecarConfig,
  caseId: string,
  readToken: string,
  lang: Lang,
): Promise<Timeline | null> {
  const get = config.fetch ?? fetch;
  const api = config.apiUrl.replace(/\/$/, "");
  const query = lang === "es" ? "?lang=es" : "";
  try {
    const res = await get(`${api}/cases/${encodeURIComponent(caseId)}/timeline${query}`, {
      headers: { Authorization: `Bearer ${readToken}` },
    });
    return res.ok ? ((await res.json()) as Timeline) : null;
  } catch {
    return null;
  }
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

async function check(
  msg: InboundMessage,
  config: SidecarConfig,
  lang: Lang = "en",
): Promise<Checked> {
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
  const card = await fetchCard(config, caseId, lang);
  if (!card) return { text: `${HEADLINES.hold}\nSNAPBACK check ${caseId} started.\n${link}` };
  const office = readToken ? await officeOnRecord(config, caseId, readToken) : null;
  let text = reportText(card, link, challenge, office, images.length === 0, lang);
  const redFlag = card.rows.some((row) => row.lines.some((line) => line.tone === "red_flag"));
  if (redFlag && readToken && config.memory) {
    const alert = await fetchCopyAlert(config, caseId, readToken, lang);
    if (alert?.fires) {
      config.memory.offer(renterId(msg.threadId, config.renterSalt), lang);
      text += `\n\n${OFFER[lang]}`;
    }
  }
  return { text, caseId };
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
  onChecking?: (text?: string) => Promise<void>,
): Promise<boolean> {
  if (!isAllowed(msg.threadId, config)) return false;
  const key = renterId(msg.threadId, config.renterSalt);
  const text = msg.text ?? "";
  // Adaptive memory (D2): commands first, then learn from what the renter says.
  let profile: Profile | null = null;
  if (config.profiles) {
    const command = profileCommand(text, key, config.profiles);
    if (command !== null) {
      if (command.kind === "forget") config.memory?.forget(key); // only "forget me" wipes the case
      await client.reply(msg.threadId, command.text);
      return true;
    }
    const learned = learnFrom(text);
    const noPhotos = (msg.images?.length ?? 0) === 0 && msg.imageUrls.length === 0;
    if (noPhotos && onlyAboutThem(text, learned)) {
      profile = config.profiles.learn(key, text);
      await client.reply(msg.threadId, rememberedText(profile, profile.lang ?? "en"));
      return true;
    }
    // Anything else (an ad, a follow-up) teaches nothing. Its language answers this one reply
    // when the renter has not set one; a Spanish renter is never flipped to English.
    profile = config.profiles.get(key);
    if (!profile?.lang && learned.lang) profile = { ...(profile ?? {}), lang: learned.lang };
  }
  const lang: Lang = profile?.lang ?? learnFrom(text).lang ?? "en";
  if (config.memory && noPhotosIn(msg) && DRAFT_YES.test(text)) {
    // D6: never auto-sent. Only an open offer drafts, and only once; otherwise no check either.
    const offered = config.memory.takeOffer(key);
    const last = config.memory.recall(key);
    let answer: string;
    if (offered && last?.readToken) {
      const alert = await fetchCopyAlert(config, last.caseId, last.readToken, offered);
      answer = alert?.fires ? draftText(alert, offered) : COULD_NOT_CHECK;
    } else {
      answer = last
        ? lang === "es"
          ? "No hay nada que redactar para esta revisión."
          : "There's nothing to draft for this check."
        : lang === "es"
          ? WORDS.es.adFirst
          : SEND_THE_AD_FIRST;
    }
    await client.reply(msg.threadId, answer);
    return true;
  }
  const intent = followUpIntent(msg);
  if (intent !== null) {
    // Ruling (#255 review): a follow-up never creates a case, whatever happens here.
    let answer: string;
    try {
      answer = await answerFollowUp(intent, msg, config, profile);
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
  let checked: Checked;
  config.memory?.begin(key);
  try {
    try {
      await onChecking?.(WORDS[lang].checking);
    } catch {
      // a failed "checking" reply never skips the check
    }
    checked = await check(msg, config, lang);
  } catch {
    checked = { text: COULD_NOT_CHECK };
  } finally {
    config.memory?.end(key);
  }
  await client.reply(msg.threadId, checked.text);
  if (checked.caseId) await sendCardPicture(client, msg, config, checked.caseId);
  return true;
}
