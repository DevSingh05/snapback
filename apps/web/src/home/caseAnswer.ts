// A follow-up about the case on screen, answered from that case's own card. No model, no Finder:
// the lines are the API's words, copied as they come. Only the short lead-in to each answer is
// written here, by code.
import { headlineOf } from "../cardStrings";
import type { Card } from "../contracts";
import type { CaseTopic } from "./intent";

export interface CaseAnswer {
  /** One line from code that says what follows. */
  lead: string;
  /** Lines copied from the card, untouched. */
  sections: { heading: string | null; lines: string[] }[];
  links: { label: string; href: string; external?: boolean }[];
}

/** Where to report it. The same two places the full report names. */
const REPORT_LINKS = [
  { label: "Report it to the FTC", href: "https://reportfraud.ftc.gov/", external: true },
  { label: "Report it to the FBI's IC3", href: "https://www.ic3.gov/", external: true },
] as const;

const HINT = "You can ask why, who to call, what to do now, or whether it is safe.";

/** True when the result is a red flag or a hold: something stands against the ad. */
export function isAgainst(card: Card): boolean {
  return (
    card.state === "dont_pay" ||
    card.state === "hold" ||
    card.rows.some((r) => r.lines.some((l) => l.tone === "red_flag"))
  );
}

function doesNot(card: Card): string[] {
  if (card.does_not?.length) return card.does_not;
  // An older card has no written list: the lines that are not ok, as the card words them.
  return card.rows.flatMap((r) =>
    r.lines.filter((l) => l.tone !== "ok").map((l) => `${l.label}: ${l.text}`),
  );
}

function checksOut(card: Card): string[] {
  if (card.checks_out?.length) return card.checks_out;
  return card.rows.flatMap((r) =>
    r.lines.filter((l) => l.tone === "ok").map((l) => `${l.label}: ${l.text}`),
  );
}

function section(heading: string | null, lines: string[]) {
  return lines.length ? [{ heading, lines }] : [];
}

export function answerAbout(card: Card, topic: CaseTopic): CaseAnswer {
  const id = encodeURIComponent(card.case_id);
  const full = { label: "Open the full report", href: `/case/${id}` };
  const against = isAgainst(card);
  switch (topic) {
    case "why":
      return {
        lead: `Why this is the result for case ${card.case_id}:`,
        sections: [
          ...section(null, card.summary ?? []),
          ...section("What does not check out", doesNot(card)),
        ],
        links: [full],
      };
    case "safe":
      return {
        lead: headlineOf(card),
        sections: [
          ...section("What checks out", checksOut(card)),
          ...section("What does not", doesNot(card)),
          ...section("Not checked", [card.not_checked.join(", ")].filter(Boolean)),
        ],
        links: [full],
      };
    case "next":
      return {
        lead: against ? "Do not pay yet. What to do now:" : "What to do now:",
        sections: [
          ...section(null, card.footer),
          ...section("What stands in the way", against ? doesNot(card) : []),
        ],
        links: [full],
      };
    case "who":
      return {
        lead: against
          ? "Not the number in the ad. The office on record, and where to report this:"
          : "The office on record is in the full report, with its own website to reach it.",
        sections: against
          ? [
              ...section(null, [
                "The full report lists the leasing office on record and its own website. Reach them there, not through the ad.",
              ]),
              ...section("What stands in the way", doesNot(card)),
            ]
          : [],
        links: against ? [full, ...REPORT_LINKS] : [full],
      };
    case "other":
      return {
        lead: HINT,
        sections: section(null, card.summary ?? []),
        links: [full],
      };
  }
}
