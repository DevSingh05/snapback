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

function forSaleLines(fs: ForSaleMatch | null | undefined): CardLine[] {
  if (fs === undefined) return [];
  if (fs === null)
    return [line("For sale", "Not checked (no for-sale lookup for this home).", "not_checked")];
  if (fs.status === "active")
    return [
      line("For sale", `This home is listed for sale on ${fs.site}, not for rent.`, "red_flag"),
    ];
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

const LICENSE_ROLES = ["agent", "broker", "locator"];
const LOOK_IT_UP = "look it up yourself at trec.texas.gov.";

// Mirrors the license.* strings in strings.py (A18, #124). A role of ours, a yes/no and at most
// a sponsoring company: never a person's name, a license number, or the poster's own words.
function licenseLines(p: CardProofs): CardLine[] {
  const found = p.license;
  if (!found) return []; // never looked up: no line
  const label = "License";
  const role = found.claimed_role ?? "";
  if (found.status === "not_found") {
    if (role === "company")
      return [
        line(
          label,
          `Says a brokerage lists this home. We found no active Texas license under that company's name. Ask for its license number and ${LOOK_IT_UP}`,
          "red_flag",
        ),
      ];
    const says = LICENSE_ROLES.includes(role)
      ? `Says they're a licensed ${role}.`
      : "Says they're licensed.";
    return [
      line(
        label,
        `${says} We found no active Texas license under that name. Ask for their license number and ${LOOK_IT_UP}`,
        "red_flag",
      ),
    ];
  }
  if (found.status === "licensed") {
    if (role === "company")
      return [line(label, "The brokerage they named is licensed in Texas.", "ok")];
    const sponsor = (found.sponsor_broker ?? "")
      .split(/\s+/)
      .filter(Boolean)
      .join(" ")
      .slice(0, 80);
    return [
      line(
        label,
        sponsor ? `Licensed in Texas, sponsored by ${sponsor}.` : "Licensed in Texas.",
        "ok",
      ),
    ];
  }
  return [
    line(
      label,
      role
        ? "Not checked (we could not look the poster up in the Texas license list)."
        : "Not checked (the poster did not say they are an agent, broker or locator).",
      "not_checked",
    ),
  ];
}

const oneLine = (text: string | null | undefined, most: number): string =>
  (text ?? "").split(/\s+/).filter(Boolean).join(" ").slice(0, most);

// Mirrors the owner.* strings in strings.py (A19, #125). A company is named. A person never
// is: the line says "a private owner" and whether the name given matches. Never a red flag.
function ownerLines(p: CardProofs): CardLine[] {
  const owner = p.owner;
  if (!owner) return []; // no owner data: the card's "not checked: ownership" says so
  const label = "Owner of record";
  if (owner.kind === "person") {
    if (owner.poster_matches === "yes")
      return [
        line(label, "The owner of record is a private owner, and the name given matches.", "ok"),
      ];
    if (!owner.poster_says_owner)
      return [
        line(
          label,
          "Not checked (a private owner is on record, and the poster does not say they are the owner).",
          "not_checked",
        ),
      ];
    if (owner.poster_matches === "no")
      return [
        line(
          label,
          "The owner of record is a private owner, and the name given doesn't match. Owners can rent through family or a trust; check with the owner of record or the county records yourself.",
          "not_shown",
        ),
      ];
    return [
      line(
        label,
        "Not checked (a private owner is on record, and the poster gave no name to compare).",
        "not_checked",
      ),
    ];
  }
  const company = oneLine(owner.company, 80);
  if (!company) return [];
  if (owner.poster_matches === "yes")
    return [line(label, `The company they named is the owner of record: ${company}.`, "ok")];
  if (owner.poster_says_owner && owner.poster_matches === "no")
    return [line(label, `Owner of record: ${company}, not the poster.`, "not_shown")];
  return [line(label, `Owner of record: ${company}.`, "not_shown")];
}

// The owner's own published rule, quoted with its source and the day it was read. Here it
// always sits in the price row, under the same label the card API uses, so it shows once.
function ownerRuleLines(p: CardProofs): CardLine[] {
  const rule = p.owner?.kind === "company" ? p.owner.published_rule : null;
  if (!rule) return [];
  const source = rule.source_url
    .replace(/^[a-z][a-z0-9+.-]*:\/\//i, "")
    .replace(/^www\./, "")
    .replace(/\/+$/, "");
  return [
    line(
      "Owner's rule",
      `${oneLine(rule.company, 80)}, the owner of record, says: "${oneLine(rule.rule, 200)}" (${oneLine(source, 80)}, read ${rule.checked_on.slice(0, 10)}).`,
      "hold",
    ),
  ];
}

function personLines(p: CardProofs): CardLine[] {
  const a = p.authority;
  if (!a) return [...licenseLines(p), ...ownerLines(p)];
  const out: CardLine[] = [];
  const phone = "Phone in listing";
  // Not a red flag (ruling, Sat 02:10, #121): agents and locators often post with their own
  // number. Mirrors contact.phone_mismatch and contact.phone_mismatch_unnamed in strings.py.
  // With a manager on record, "Next step" below is the one line that says who to call. With
  // none, nothing else does, so this line carries the call step.
  if (a.office_phone_match === "no" && p.license?.status === "not_found")
    // A poster who claims a license they do not hold has no agent's reason for another number,
    // so this is a mismatch again. Mirrors contact.phone_mismatch_unlicensed in strings.py.
    out.push(
      line(
        phone,
        a.manager_on_record
          ? "This number is not the leasing office's on record, and we found no active Texas license under the name they gave."
          : "This number is not the leasing office's on record, and we found no active Texas license under the name they gave. Call the office on record yourself.",
        "red_flag",
      ),
    );
  else if (a.office_phone_match === "no")
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
  out.push(...licenseLines(p), ...ownerLines(p));
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
    ["place", [...forSaleLines(forSale), ...unitLine(p)]],
    ["person", personLines(p)],
    ["price", [...ownerRuleLines(p), ...priceLines(p)]],
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
