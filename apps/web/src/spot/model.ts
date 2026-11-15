// Spot the scam: the four composed ads and the scoring. Pure data and functions, no React.
//
// Every ad here is SYNTHETIC: the team composed it from the sentences in fixtures/rules/cases.json
// and the staged-listing format of fixtures/demo/*/listing.txt. Phones are 555-01xx, links end in
// .example, and no address or person is real. The verdicts are FIXTURE results precomputed by
// running the real rules engine (src/snapback/agent/rules/apply.py, apply_rules) on each ad's
// text; the reason lines are the card's own words from src/snapback/card/strings.py. Nothing is
// computed in the browser, so what the reveal shows is what the card would say about the text.
// A text check only: the full card also reads the building's record and the photos.

export type Call = "fine" | "hold";
export type AdKind = "honest" | "pattern";

/** A stretch of the ad. `rules` is set on the stretches the rules engine flagged. */
export interface Seg {
  text: string;
  rules?: string[];
}

export interface SpotAd {
  id: string;
  kind: AdKind;
  place: string;
  price: string;
  segs: Seg[];
  phone: string;
  /** What the card says about the text, for the reveal. */
  verdict: Call;
  headline: string;
  /** Card reason lines, one per rule that fired (empty when none did). */
  lines: string[];
  /** For an honest ad only: why it looks risky but is not, in the card's logic. */
  note?: string;
}

/** The card's own lines, copied verbatim from src/snapback/card/strings.py (tested). */
export const CARD_LINES = {
  "payment.zelle_and_deposit_before_viewing":
    "Zelle and a deposit or holding fee before a viewing. Red flag.",
  "pressure.cannot_show": "They say they cannot show the unit in person. Red flag.",
  "data.ssn_before_viewing": "Social Security number before a viewing. Red flag.",
  "fee.holding_deposit_before_viewing": "A deposit or holding fee before a viewing. Red flag.",
  "link.payment_link": "A payment link sent by the poster. Red flag.",
} as const;

export const CARD_HEADLINE = "Hold off: it asks for money before you've seen the place";
export const NO_FLAG_HEADLINE = "No red flags in the text";

const join = (segs: Seg[]) => segs.map((s) => s.text).join("");

export const ADS: SpotAd[] = [
  {
    id: "spot-1",
    kind: "honest",
    place: "Fixture Court, Unit 12",
    price: "$1,450 a month",
    segs: [
      {
        text: "2 bed / 2 bath. Quiet street near the park, with a bus stop on the corner. Pets welcome. Two parking spots. Laundry in unit. Tours daily from 9 to 5. Call the leasing office to book a showing.",
      },
    ],
    phone: "555-010-0142",
    verdict: "fine",
    headline: NO_FLAG_HEADLINE,
    lines: [],
  },
  {
    id: "spot-2",
    kind: "pattern",
    place: "Fixture Row, house",
    price: "$900 a month",
    segs: [
      { text: "3 bedroom house for rent. " },
      {
        text: "I am out of the country for work, so I cannot show the apartment in person.",
        rules: ["pressure.cannot_show"],
      },
      { text: " " },
      {
        text: "Send the deposit by Zelle and I will mail the keys.",
        rules: ["payment.zelle_and_deposit_before_viewing"],
      },
      { text: " Many people are interested, so the first to pay gets it. Act fast." },
    ],
    phone: "555-010-0188",
    verdict: "hold",
    headline: CARD_HEADLINE,
    lines: [
      CARD_LINES["payment.zelle_and_deposit_before_viewing"],
      CARD_LINES["pressure.cannot_show"],
    ],
  },
  {
    id: "spot-3",
    kind: "honest",
    place: "Fixture Lane, Unit 4",
    price: "$1,150 a month",
    segs: [
      {
        text: "Studio. There is a $45 application fee per adult, paid on the resident portal after your tour. After your tour, the application on our portal asks for your Social Security number for the credit check.",
      },
    ],
    phone: "555-010-0166",
    verdict: "fine",
    headline: NO_FLAG_HEADLINE,
    lines: [],
    note: "It names a fee and a Social Security number, but both come after the tour, so no rule fires.",
  },
  {
    id: "spot-4",
    kind: "pattern",
    place: "Fixture Court, Unit 31",
    price: "$1,050 a month",
    segs: [
      { text: "Sunny 1 bed. " },
      {
        text: "Before I can show it, text me your full name, SSN and date of birth.",
        rules: ["data.ssn_before_viewing"],
      },
      { text: " " },
      {
        text: "Pay the deposit here to lock it in: https://pay.example.com/hold/123",
        rules: ["fee.holding_deposit_before_viewing", "link.payment_link"],
      },
      { text: "." },
    ],
    phone: "555-010-0199",
    verdict: "hold",
    headline: CARD_HEADLINE,
    lines: [
      CARD_LINES["data.ssn_before_viewing"],
      CARD_LINES["fee.holding_deposit_before_viewing"],
      CARD_LINES["link.payment_link"],
    ],
  },
];

/** The ad as plain text, the exact string the rules engine was run on (plus price and phone). */
export function adText(ad: SpotAd): string {
  return `${join(ad.segs)} ${ad.price}. Text ${ad.phone}.`;
}

export interface Score {
  /** Scam-pattern ads the player held off on. */
  caught: number;
  patterns: number;
  /** Honest ads the player let through. */
  cleared: number;
  honest: number;
  /** Scam-pattern ads SNAPBACK's text rules held off on. */
  snapbackCaught: number;
  snapbackCleared: number;
  /** Composed ads in the round (the n behind every number). */
  n: number;
}

export function score(answers: readonly Call[], ads: readonly SpotAd[] = ADS): Score {
  const patterns = ads.filter((a) => a.kind === "pattern");
  const honest = ads.filter((a) => a.kind === "honest");
  const mine = (a: SpotAd): Call | undefined => answers[ads.indexOf(a)];
  return {
    caught: patterns.filter((a) => mine(a) === "hold").length,
    patterns: patterns.length,
    cleared: honest.filter((a) => mine(a) === "fine").length,
    honest: honest.length,
    snapbackCaught: patterns.filter((a) => a.verdict === "hold").length,
    snapbackCleared: honest.filter((a) => a.verdict === "fine").length,
    n: ads.length,
  };
}

/** The line under the big number. Never calls a poster a scammer: an ad shows patterns. */
export function scoreLine(s: Score): string {
  return `You caught ${s.caught} of ${s.patterns}; SNAPBACK caught ${s.snapbackCaught} of ${s.patterns} (n=${s.n} composed ads)`;
}

export function mood(s: Score): string {
  const falseAlarms = s.honest - s.cleared;
  if (s.caught === s.patterns && falseAlarms === 0)
    return "Clean sweep. Both patterns, no false alarms.";
  if (s.caught === s.patterns)
    return `Both patterns caught, but ${falseAlarms} honest ${falseAlarms === 1 ? "ad" : "ads"} held off too.`;
  if (s.caught === 0) return "Both ads with patterns slipped past you. They are built to.";
  return "One pattern slipped past. This is why a second look helps.";
}

/** Did the player's call match the text check's, for one ad. */
export function agrees(ad: SpotAd, call: Call): boolean {
  return ad.verdict === call;
}
