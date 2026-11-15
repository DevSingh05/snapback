// "How we got this answer": one message per CHECK (record, photos, rules, phone, owner, for sale),
// each carrying the finding the card and the real-listing read already hold for it, with the
// timeline giving only the timing and the source. Then the verdict, in the card's own words, and
// each reason tied to the message that produced it. Nothing here decides anything.
//
// What never shows as a finding: a step's own `result` text, because for a choice step it is the
// reason an option was picked ("Only one option was open"), which is plumbing. The one place a
// step's text is used is a skipped check, whose text says why it did not run.
import type {
  Card,
  CardLine,
  CardTone,
  CaseTimeline,
  RealListing,
  TimelineStep,
} from "../contracts";
import { headlineOf } from "../cardStrings";

export type CheckId = "record" | "photos" | "rules" | "phone" | "owner" | "forsale";

export const CHECK_ORDER: readonly CheckId[] = [
  "record",
  "photos",
  "rules",
  "phone",
  "owner",
  "forsale",
];

// Which check wrote each card line, by the line's label key (the same in every language).
const LINE_CHECK: Record<string, CheckId> = {
  "label.real": "photos",
  "label.matched_home": "photos",
  "label.seen_before": "photos",
  "label.here_now": "photos",
  "label.for_sale": "forsale",
  "label.recently_rented": "record",
  "label.unit": "record",
  "label.rent_vs_record": "record",
  "label.ad_claim": "record",
  "label.aerial": "record",
  "label.ad_pretext": "rules",
  "label.payment_ask": "rules",
  "label.data_ask": "rules",
  "label.pressure": "rules",
  "label.link": "rules",
  "label.contact": "phone",
  "label.office": "phone",
  "label.allowed": "phone", // from the record's manager and office match, not the owner step
  "label.license": "owner",
  "label.owner": "owner",
  "label.owner_rule": "owner",
};

// Which check a timeline step belongs to. A step with no entry (reading the ad, the report, a
// retry, the verdict) is not a check and never shows.
const STEP_CHECK: Record<string, CheckId> = {
  record: "record",
  rent: "record",
  locate: "photos",
  place: "photos",
  claims: "rules",
  phone: "phone",
  "office-and-licence": "phone",
  owner: "owner",
  license: "owner",
  ask_license: "owner",
  for_sale: "forsale",
};

export interface Finding {
  label: string | null;
  text: string;
}

export interface Bubble {
  id: string; // the check id
  check: CheckId;
  tone: CardTone | "none";
  findings: Finding[];
  source: "live" | "fixture";
  tookMs: number | null; // null when no step timed this check
}

export interface NotChecked {
  check: CheckId;
  text: string;
}

export interface Reason {
  text: string;
  // The check message that produced it, or null when no link can be made.
  bubbleId: CheckId | null;
}

export interface AnswerView {
  bubbles: Bubble[];
  notChecked: NotChecked[];
  verdict: string;
  reasons: Reason[];
}

const TONE_RANK: Record<CardTone | "none", number> = {
  red_flag: 0,
  hold: 1,
  not_shown: 1,
  ok: 2,
  not_checked: 3,
  none: 3,
};

function worst(tones: CardTone[]): CardTone | "none" {
  return tones.reduce<CardTone | "none">(
    (best, t) => (TONE_RANK[t] < TONE_RANK[best] ? t : best),
    "none",
  );
}

/** The card's reasons: what it flagged, else what checked out, else its summary sentences. */
export function reasonLines(card: Card): string[] {
  const flagged = card.does_not ?? [];
  const passed = card.checks_out ?? [];
  if (flagged.length > 0) return flagged;
  if (passed.length > 0) return passed;
  return card.summary ?? [];
}

function allLines(card: Card): CardLine[] {
  return card.rows.flatMap((row) => row.lines);
}

/** The check a reason came from: its "label: text" is one of the card's own lines. */
export function checkOfReason(card: Card, reason: string): CheckId | null {
  for (const line of allLines(card)) {
    if (reason === `${line.label}: ${line.text}` && line.key) return LINE_CHECK[line.key] ?? null;
  }
  const cut = reason.indexOf(": ");
  if (cut < 1) return null;
  const label = reason.slice(0, cut);
  const hit = allLines(card).find((line) => line.label === label);
  return hit?.key ? (LINE_CHECK[hit.key] ?? null) : null;
}

// "Skipped TREC license: the ad names no license." -> "the ad names no license"
function whySkipped(result: string): string {
  // A card line "Not checked (no listing photos were sent)." keeps only what is in the brackets.
  const inner = /^[^(:]*\((.*)\)\.?$/.exec(result);
  if (inner) result = inner[1]!;
  const cut = result.indexOf(": ");
  const body = cut > 0 && cut < 70 ? result.slice(cut + 2) : result;
  return body.replace(/\.$/, "").replace(/^[A-ZÁÉÍÓÚ](?![A-ZÁÉÍÓÚ])/, (c) => c.toLowerCase());
}

function extras(check: CheckId, listing: RealListing | null): string[] {
  if (!listing) return [];
  if (check === "record") return [listing.headline];
  if (check === "photos") return [listing.provenance ?? ""];
  if (check === "phone") return [listing.phone_line ?? ""];
  return [];
}

/** The panel's content, or null when there is nothing to show (it then hides). */
export function answerView(
  card: Card,
  timeline: CaseTimeline | null,
  listing: RealListing | null = null,
): AnswerView | null {
  if (!timeline || !Array.isArray(timeline.steps) || timeline.steps.length === 0) return null;
  const lines = allLines(card);
  const bubbles: Bubble[] = [];
  const notChecked: NotChecked[] = [];

  for (const check of CHECK_ORDER) {
    const mine = lines.filter((l) => l.key && LINE_CHECK[l.key] === check);
    const steps = timeline.steps.filter((s) => s.kind && STEP_CHECK[s.kind] === check);
    const ran = steps.filter((s) => !s.skipped);
    const skipped = steps.filter((s) => s.skipped);
    const findings: Finding[] = mine
      .filter((l) => l.tone !== "not_checked")
      .map((l) => ({ label: l.label, text: l.text }));
    // The phone line only restates what a card line already says: the card's own line wins.
    const more = check === "phone" && findings.length > 0 ? [] : extras(check, listing);
    for (const text of more) {
      if (text && !findings.some((f) => f.text === text)) findings.push({ label: null, text });
    }
    // A check the plan left out is one quiet line, never a message, even if the card has a line.
    if (ran.length === 0 && skipped.length > 0) {
      notChecked.push({ check, text: whySkipped(skipped[0]!.result) });
      continue;
    }
    if (findings.length === 0) {
      const quiet = mine.find((l) => l.tone === "not_checked");
      if (quiet) notChecked.push({ check, text: whySkipped(quiet.text) });
      continue;
    }
    bubbles.push({
      id: check,
      check,
      tone: worst(mine.map((l) => l.tone)),
      findings,
      source: ran[0]?.source ?? mine.find((l) => l.source)?.source ?? card.source,
      tookMs: ran.length > 0 ? ran.reduce((sum, s) => sum + s.took_ms, 0) : null,
    });
  }
  if (bubbles.length === 0) return null;
  bubbles.sort((a, b) => TONE_RANK[a.tone] - TONE_RANK[b.tone]); // stable: red flag, hold, ok

  const shown = new Set<CheckId>(bubbles.map((b) => b.check));
  return {
    bubbles,
    notChecked,
    verdict: headlineOf(card),
    reasons: reasonLines(card).map((text) => {
      const check = checkOfReason(card, text);
      return { text, bubbleId: check && shown.has(check) ? check : null };
    }),
  };
}

/** "0.4 s", or "under 0.1 s" for a step too quick to time. */
export function tookText(ms: number, lang: string): string {
  const under = lang === "es" ? "menos de 0,1 s" : "under 0.1 s";
  if (ms < 100) return under;
  const text = (ms / 1000).toFixed(1);
  return `${lang === "es" ? text.replace(".", ",") : text} s`;
}

export type { TimelineStep };
