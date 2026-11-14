// The words on the card rows. Mirrors src/snapback/card/strings.py; when the card API sends a line,
// that line wins and this file is not used. The locked wording is in plan/decisions.md (22:40).
// No string here says safe, verified or scam, and none carries a phone number.

import type {
  CardLine,
  CardProofs,
  CardRow,
  CardRowKind,
  CardTone,
  ForSaleMatch,
  VerdictState,
} from "./contracts";

// TODO(#67): the proof sentences below move to src/snapback/card/strings.py and arrive as card lines.
// Mirrors strings.py tone_word: one word per tone, except where the row changes the meaning.
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

function dollars(n: number): string {
  return `$${n.toLocaleString("en-US")}`;
}

const line = (label: string, text: string, tone: CardTone): CardLine => ({ label, text, tone });

function forSaleLines(fs: ForSaleMatch | null | undefined, officeIsTheContact = false): CardLine[] {
  if (fs === undefined) return [];
  if (fs === null)
    return [line("For sale", "Not checked (no for-sale lookup for this home).", "not_checked")];
  if (fs.status === "active") {
    // A warning, not a mismatch, and never "not for rent" (red team H5, Sat 03:25). Mirrors
    // the place.for_sale strings in strings.py: what the record says, and who to ask.
    const brokerage = (fs.offices ?? [])
      .map((name) => name.split(/\s+/).filter(Boolean).join(" ").slice(0, 80))
      .find((name) => name.length > 0);
    const by = brokerage ? ` by ${brokerage}` : "";
    const since = fs.listed_on ? ` since ${fs.listed_on.slice(0, 10)}` : "";
    const record = `Listed for sale on ${fs.site}${by}${since}.`;
    // The ad's phone is the office's on record: the brokerage itself is offering the home.
    // Information only, and it holds nothing (ruling, Sat 03:36).
    if (officeIsTheContact)
      return [
        line(
          "For sale",
          `${record} The contact in this listing is the office on record, so ask them whether it is also offered for lease.`,
          "not_shown",
        ),
      ];
    const ask = brokerage ? "that brokerage" : "the listing brokerage";
    return [
      line(
        "For sale",
        `${record} Homes for sale are sometimes also offered for lease, so confirm with ${ask} before you pay.`,
        "hold",
      ),
    ];
  }
  if (fs.status === "recently_rented") {
    const when = fs.changed_on ? ` on ${shortDate(fs.changed_on)}` : " recently";
    return [line("Rental history", `This home was rented${when}.`, "red_flag")];
  }
  return [line("For sale", `Not listed for sale on ${fs.site}.`, "ok")];
}

function unitLine(p: CardProofs): CardLine[] {
  if (!p.price) return [];
  const label = "Unit";
  const who = p.unit_label ? `Unit ${p.unit_label}` : "This unit";
  switch (p.price.unit) {
    case "on_record":
      return [line(label, `${who} is on this building's list.`, "ok")];
    case "not_on_record":
      return [line(label, `${who} is not on this building's list.`, "red_flag")];
    case "beds_mismatch":
      return [
        line(
          label,
          "The bedrooms in the listing do not match this unit on the building's list.",
          "red_flag",
        ),
      ];
    default:
      return [
        line(
          label,
          "Not checked (the listing names no unit, or the record has none).",
          "not_checked",
        ),
      ];
  }
}

function personLines(p: CardProofs): CardLine[] {
  const a = p.authority;
  if (!a) return [];
  const out: CardLine[] = [];
  const phone = "Phone in listing";
  // Not a red flag (ruling, Sat 02:10, #121): agents and locators often post with their own
  // number. Mirrors contact.phone_mismatch and contact.phone_mismatch_unnamed in strings.py.
  // With a manager on record, "Next step" below is the one line that says who to call. With
  // none, nothing else does, so this line carries the call step.
  if (a.office_phone_match === "no")
    out.push(
      line(
        phone,
        a.manager_on_record
          ? "This number is not the leasing office's on record. Agents often use their own, so check it with the office."
          : "This number is not the leasing office's on record. Agents often use their own. Call the office on record yourself to confirm.",
        "not_shown",
      ),
    );
  else if (a.office_phone_match === "yes")
    out.push(line(phone, "The phone in the listing is the leasing office on record.", "ok"));
  else
    out.push(
      line(phone, "Not checked (the listing or the record has no phone number).", "not_checked"),
    );
  const link = "Link in listing";
  if (a.link_domain === "lookalike")
    out.push(
      line(
        link,
        "This link looks like the building's site but is a different address.",
        "red_flag",
      ),
    );
  else if (a.link_domain === "matches")
    out.push(line(link, "This link is the building's own site.", "ok"));
  else if (a.link_domain === "other")
    out.push(
      line(link, "This link is some other site, which says nothing either way.", "not_shown"),
    );
  else
    out.push(
      line(
        link,
        "Not checked (the listing has no link, or the record has no website).",
        "not_checked",
      ),
    );
  if (a.manager_on_record)
    out.push(line("Next step", `Call ${a.manager_on_record} yourself.`, "not_shown"));
  return out;
}

function priceLines(p: CardProofs): CardLine[] {
  const pr = p.price;
  if (!pr) return [];
  const label = "Rent vs record";
  if (pr.per_bed)
    return [line(label, "Priced per bed here, so the rent was not compared.", "not_checked")];
  const band =
    pr.listed_rent != null && pr.record_min != null && pr.record_max != null
      ? ` Listed ${dollars(pr.listed_rent)}; the record shows ${dollars(pr.record_min)} to ${dollars(pr.record_max)}.`
      : "";
  if (pr.status === "within_range")
    return [line(label, `In line with the rents on record for this building.${band}`, "ok")];
  if (pr.status === "below_range")
    return [
      line(
        label,
        `Below the rents on record for this building. Ask why; discounts happen.${band}`,
        "hold",
      ),
    ];
  return [line(label, "Not checked (our data has no rent for this building).", "not_checked")];
}

/** The proof lines to add under each row. Rows with no lines are left out. */
export function proofLines(p: CardProofs, forSale?: ForSaleMatch | null): CardRow[] {
  const rows: [CardRowKind, CardLine[]][] = [
    [
      "place",
      [...forSaleLines(forSale, p.authority?.office_phone_match === "yes"), ...unitLine(p)],
    ],
    ["person", personLines(p)],
    ["price", priceLines(p)],
  ];
  return rows.filter(([, lines]) => lines.length > 0).map(([kind, lines]) => ({ kind, lines }));
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
