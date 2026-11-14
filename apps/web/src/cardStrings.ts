// UI chrome for the card: the headline words, the row-state words and dates. The text and tone of
// every card line come from the API and are rendered as given (plan/decisions.md, Sat 03:25).
// Nothing here rewords or re-tones an API line. The locked wording is in decisions.md (22:40).

import type { CardRowKind, CardTone, ForSaleMatch, VerdictState } from "./contracts";

// The one table from a line's API tone to its row-state word. Mirrors strings.py tone_word.
const TONE_WORD: Record<CardTone, string> = {
  ok: "Matches",
  red_flag: "Doesn't match",
  not_shown: "Not confirmed",
  hold: "Warning",
  not_checked: "Not checked",
};

export const STATE_WORD: Record<VerdictState, string> = {
  hold: "Hold off for now",
  dont_pay: "Don't pay. Something here doesn't match.",
  unverified: "Could not place these photos",
  verified: "Checks passed. Still follow the two rules.",
};

// Same two row exceptions as strings.py tone_word; they pick the word, never the line text or tone.
export function toneWord(tone: CardTone, row?: CardRowKind): string {
  if (tone === "red_flag" && row === "price") return "Warning"; // a risky ask, not a mismatch
  if (tone === "hold" && row === "person") return "Not confirmed"; // not heard from yet
  return TONE_WORD[tone];
}

export function shortDate(iso: string): string {
  // Dates are plain calendar days: parse as local noon so no zone moves the day.
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export interface HistoryStep {
  what: string;
  on: string;
}

/** The dates the record gives for a home: listed, then how it ended up. */
export function historySteps(fs: ForSaleMatch | null | undefined): HistoryStep[] {
  if (!fs) return [];
  const steps: HistoryStep[] = [];
  if (fs.listed_on) steps.push({ what: "Listed", on: fs.listed_on });
  if (fs.changed_on)
    steps.push({
      what: fs.status === "recently_rented" ? "Rented" : "Last change",
      on: fs.changed_on,
    });
  return steps;
}
