// The Finder's offers until the deep agent (M9) is wired: plain code rules that read the
// renter's own words and what they did, and offer to remember one thing. Every offer is
// stamped "Picked by our rules". Nothing here writes a reply, and nothing is remembered
// without a yes.
import type { RenterBrief } from "../contracts";
import type { FinderEvent } from "./finderStore";

export interface Chip {
  id: string; // stable: one chip per kind, or "note:<text>" for the renter's own
  label: string;
}

export const OFFER_STAMP = "Picked by our rules";

const money = (n: number) => `$${n.toLocaleString("en-US")}`;

/** What one line of the renter's words could mean, as a chip to offer. Null: no rule fits. */
export function chipFromWords(text: string): Chip | null {
  const t = text.toLowerCase();
  if (/walk-?ups?|stairs|ground floor|elevator/.test(t))
    return { id: "no_walkup", label: "no walk-ups" };
  if (/parking|garage|car\b/.test(t)) return { id: "parking", label: "needs parking" };
  if (/\bpets?\b|\bdogs?\b|\bcats?\b/.test(t)) return { id: "pets", label: "pets" };
  const rent =
    /(?:under|below|max|up to|at most)\s*\$?\s*([\d,]{3,6})/.exec(t) ?? /\$\s*([\d,]{3,6})/.exec(t);
  if (rent) {
    const n = Number(rent[1]!.replace(/,/g, ""));
    if (n >= 300 && n <= 20000) return { id: "max_rent", label: `under ${money(n)}` };
  }
  const beds = /(\d)\s*(?:\+\s*)?(?:bed|br)\b/.exec(t);
  if (beds) return { id: "beds", label: `${beds[1]}+ bedrooms` };
  return null;
}

/** The one offer to show: the newest event whose chip is not already kept or turned down. */
export function nextOffer(events: FinderEvent[], chips: Chip[], declined: string[]): Chip | null {
  for (const e of events) {
    const chip = chipFromWords(e.text);
    if (chip && !chips.some((c) => c.id === chip.id) && !declined.includes(chip.id)) return chip;
  }
  return null;
}

/** The search brief the kept chips stand for. A chip in the renter's own words filters nothing. */
export function briefFromChips(chips: Chip[]): RenterBrief {
  const brief: RenterBrief = {};
  for (const c of chips) {
    if (c.id === "no_walkup") brief.needs_no_walkup = true;
    if (c.id === "parking") brief.needs_parking = true;
    if (c.id === "pets") brief.pets = true;
    if (c.id === "max_rent") brief.max_rent_month = Number(c.label.replace(/[^\d]/g, ""));
    if (c.id === "beds") brief.beds_min = Number(c.label[0]);
  }
  return brief;
}

const KEY = "snapback.finder-learned";

export function loadLearned(): { chips: Chip[]; declined: string[] } {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as Record<string, unknown>;
    const chips = Array.isArray(raw.chips)
      ? (raw.chips as Chip[]).filter(
          (c) => typeof c?.id === "string" && typeof c?.label === "string",
        )
      : [];
    const declined = Array.isArray(raw.declined)
      ? (raw.declined as unknown[]).filter((d): d is string => typeof d === "string")
      : [];
    return { chips, declined };
  } catch {
    return { chips: [], declined: [] };
  }
}

export function saveLearned(state: { chips: Chip[]; declined: string[] }): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    // Storage is blocked: what was learned holds for this visit only.
  }
}
