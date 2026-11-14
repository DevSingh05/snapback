// What the case pieces read from a Card. Nothing here writes a sentence about a case: the
// headline comes from cardStrings.ts, and every line's text and tone come from the API as given.
import { toneWord } from "../cardStrings";
import type { Card, CardLine, CardRowKind, CardTone, DataSource, VerdictState } from "../contracts";
import { STATE_LABEL, type RecordSource, type StampKind, type StateKind } from "../ui";

/** The colour of the bar beside the headline. A check that failed to load is always slate. */
export type VerdictTone = "dont-pay" | "hold" | "ok" | "slate";

export const VERDICT_TONE: Record<VerdictState, VerdictTone> = {
  dont_pay: "dont-pay",
  hold: "hold",
  verified: "ok",
  unverified: "slate",
};

const KIND_OF_WORD = new Map<string, StateKind>(
  (Object.entries(STATE_LABEL) as [StateKind, string][]).map(([kind, word]) => [word, kind]),
);

/** The state square for a line: it follows the locked word, so one word always looks one way. */
export function stateKind(tone: CardTone, row: CardRowKind): StateKind {
  return KIND_OF_WORD.get(toneWord(tone, row)) ?? "unchecked";
}

// Worst first: a mismatch, then a warning, then something not confirmed.
const FAIL_ORDER: StateKind[] = ["mismatch", "warn", "unconfirmed"];

/** The lines that do not check out, worst first, then in card order. Shown as the API wrote them. */
export function flaggedLines(card: Card): CardLine[] {
  const found = card.rows.flatMap((row) =>
    row.lines.map((line) => ({ line, rank: FAIL_ORDER.indexOf(stateKind(line.tone, row.kind)) })),
  );
  return found
    .filter((f) => f.rank >= 0)
    .sort((x, y) => x.rank - y.rank)
    .map((f) => f.line);
}

/** True when the place check passed, so there are rooms on record to walk. */
export function photosPlaced(card: Card): boolean {
  return card.rows.some((row) => row.kind === "place" && row.lines.some((l) => l.tone === "ok"));
}

export function checkCount(card: Card): number {
  return card.rows.reduce((n, row) => n + row.lines.length, 0);
}

// Which record a line was read from, for the record line under it. The API does not name a
// line's source, so only the English labels whose source is fixed in strings.py are mapped;
// every other line prints no record line.
const RECORD_OF_LABEL: Record<string, RecordSource> = {
  Real: "scan",
  "Rent vs record": "costar",
  "Unit on record": "costar",
  "Contact on record": "costar",
  "Owner of record": "county",
  License: "license",
};

export function recordSourceOf(line: CardLine, lang: string): RecordSource | null {
  if (lang !== "en" || line.tone === "not_checked") return null;
  return RECORD_OF_LABEL[line.label] ?? null;
}

/** "NOV 13, 9:42 PM", from the card's own checked_at. */
export function checkedStamp(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${day}, ${time}`;
}

export function expiryText(expiresAt: string, now: Date = new Date()): string {
  const ms = new Date(expiresAt).getTime() - now.getTime();
  if (ms <= 0) return "Expired";
  const hours = Math.floor(ms / 3_600_000);
  if (hours >= 1) return `Expires in ${hours} h`;
  return `Expires in ${Math.max(1, Math.round(ms / 60_000))} min`;
}

// ---- what callers hand the pieces (the page reads these from the API; the Home thread from
// what the renter pasted) ----

export interface ProofShot {
  src: string | null;
  alt: string;
  stamp: StampKind;
}

/** One matched spot, in percent of each photo: (ad x, ad y, scan x, scan y). */
export interface ProofPin {
  ax: number;
  ay: number;
  sx: number;
  sy: number;
}

export interface ProofData {
  ad: ProofShot;
  scan: ProofShot;
  pins: ProofPin[];
  // "PHOTO 2 OF 6", counted from the evidence file. Left out when there is no such count.
  kicker?: string | null;
  caption: string;
}

/** Rents in whole dollars a month, as the API gave them. */
export interface PriceFigures {
  listed: number;
  min: number;
  max: number;
}

export interface AdMark {
  // Words exactly as they appear in the pasted ad.
  phrase: string;
  kind: "mismatch" | "warn";
}

export const dollars = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;

// ---- the proof API (plan/proof-plan.md 3.1 to 3.3). These fields are optional and additive:
// each block renders only when its field is present, so the page works before the API lands.
// The shapes move to contracts.ts when the XO adds them there. ----

/** Card.summary, Card.checks_out and Card.does_not: sentences written by code, never here. */
export type ProofCard = Card & {
  summary?: string[] | null;
  checks_out?: string[] | null;
  does_not?: string[] | null;
};

export interface RealListingPlan {
  name?: string | null;
  beds?: number | null;
  baths?: number | null;
  rent_min?: number | null;
  rent_max?: number | null;
  units_available?: number | null;
  availability_host?: string | null;
  availability_url?: string | null;
}

/** GET /cases/{id}/real-listing. No phone digits and no street address are ever in it. */
export interface RealListing {
  case_id: string;
  source: DataSource;
  property_id?: string | null;
  // "matched": the building the photos sit in; "claimed": the one the ad names.
  which?: "claimed" | "matched";
  building_name?: string | null;
  manager_company?: string | null;
  website_host?: string | null;
  plans?: RealListingPlan[];
  photos_in_scan?: number | null;
  photos_total?: number | null;
  ad_rent?: number | null;
  ad_asks_irreversible?: boolean;
  phone_is_office?: "yes" | "no" | "not_checked";
  // False on a LIVE run without the figures flag: rents are then left out.
  figures_shown?: boolean;
  as_of?: string | null;
}

/** A PlaceMatch from /alternatives that carries a way out to its own listing. */
export interface SaferPlace {
  property_id: string;
  floor_plan?: string | null;
  price_text?: string | null;
  availability_text?: string | null;
  scan_text?: string | null;
  office_on_record?: string | null;
  source: DataSource;
  handoff_url?: string | null;
  handoff_label?: string | null;
}

const HOST = /^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/i;

/** An https address we are willing to link out to, or null. Never a script or a bare path. */
export function outLink(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && HOST.test(parsed.hostname) ? parsed.href : null;
  } catch {
    return null;
  }
}

/** https://<host> for a bare host name from the record, or null when it is not one. */
export function hostLink(host: string | null | undefined): string | null {
  const name = host?.trim().toLowerCase();
  return name && HOST.test(name) ? `https://${name}` : null;
}
