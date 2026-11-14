// What the renter meant, read by code, not by a model. Every submission to the one box goes
// through route(): the result decides which feature runs, and the thread shows the guess in one
// line with a one-tap switch. Nothing here reads the words to a model.
import type { RenterBrief } from "../contracts";
import { classifyListingText } from "../upload/validate";

export type View = "map" | "listings" | "replays" | "walk" | "investigate" | "finder";

export type Intent =
  | { kind: "check" } // an ad: a link, pasted ad text or screenshots
  | { kind: "check-ask" } // wants a check but gave nothing to check yet
  | { kind: "check-fb" } // a Facebook link alone: it sits behind a login, so ask for the text
  | { kind: "find" } // a wish or a budget: the Finder
  | { kind: "ask" } // a question about the case on screen: the Finder answers
  | { kind: "open"; view: View } // "show me on the map", "replay a real case"
  | { kind: "unsure" } // could be either: two chips, one tap
  | { kind: "rules" }; // a question about paying: the two rules, written by code

export interface Submission {
  text: string;
  files: number;
  /** A case is already in the thread, so a question is about it. */
  caseOnScreen: boolean;
}

/** What the line under your message says. Plain words, present tense. */
export const ROUTE_LINE: Record<Intent["kind"], string> = {
  check: "Checking this as an ad",
  "check-ask": "Checking an ad",
  "check-fb": "Checking a Facebook ad",
  find: "Finding places",
  ask: "Answering about this case",
  open: "Opening",
  unsure: "Not sure what you meant",
  rules: "Answering from our two rules",
};

export const VIEW_NAME: Record<View, string> = {
  map: "the map",
  listings: "Listings",
  replays: "Replays",
  walk: "a walk-through",
  investigate: "the investigator",
  finder: "the Finder",
};

export const VIEW_HREF: Record<View, string> = {
  map: "/map",
  listings: "/listings",
  replays: "/replay",
  walk: "/tour/demo",
  investigate: "/investigate",
  finder: "/finder",
};

/** One of these alone marks an ad: a payment ask, a phone number, a monthly price. */
const STRONG_SIGNS: RegExp[] = [
  /\b(zelle|venmo|cash ?app|wire transfer|western union|gift ?cards?)\b/i,
  /\bdeposit\b/i,
  /\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b/,
  /\$\s?[\d,]{3,6}\s*(\/\s*mo|\/\s*month|a month|per month|monthly)\b/i,
];

/** A payment app or a phone number: a renter's wish almost never carries either. */
const PAY_OR_PHONE: RegExp[] = [STRONG_SIGNS[0]!, STRONG_SIGNS[2]!];

const AD_SIGNS: RegExp[] = [
  /\b(tenants?|sublet|sublease|take over (my|the) lease)\b/i,
  /\b(zelle|venmo|cash ?app|wire|western union|gift ?card|paypal)\b/i,
  /\bdeposit\b/i,
  /\$\s?[\d,]{3,6}\s*(\/\s*mo|\/\s*month|a month|per month|monthly)\b/i,
  /\b\d\s*(bd|br|bed)s?\s*\/?\s*\d(\.\d)?\s*(ba|bath)s?\b/i,
  /\b(sq\.? ?ft|square feet)\b/i,
  /\b(text|call|email|contact) me\b/i,
  /\b(available (now|immediately)|move[- ]in ready|utilities included|no credit check)\b/i,
  /\b(landlord|owner) (is|will be) (away|abroad|out of)/i,
  /\b(listing|posted|ad)\b.*\b(craigslist|facebook|zillow|marketplace)\b/i,
];

const WISH =
  /^\s*(please\s+)?(find|search|look(ing)? for|i('m| am) looking|i want|i need|we need|we want|need a|want a|help me find|get me|any|show me (places|homes|apartments|something))\b/i;
const WISH_WORDS =
  /\bbudget(?: is| of)?\s*\$?\s*\d|\b(under|below|max|budget|up to)\s*\$?\s*\d|\$\s?\d|\bbeds?\b|\bbedroom|\bstudio\b|\b\d\s*br\b|\bparking\b|walk-?ups?|\bpets?\b|\bdogs?\b|\bcats?\b|\bnear\b|\bdowntown\b|\bapartments?\b|\bplaces?\b|\bhomes?\b/i;
const CHECK_WORDS =
  /\bpaste\b.*\b(ad|listing)\b|\b(check|verify|scan)\b.*\b(ad|listing|post|this)\b|\b(scam|legit|fake|real)\b.*\??|\bis (this|it|the) (landlord|ad|listing|place) (real|legit|a scam|fake)\b/i;
const PAYING =
  /\b(pay|paying|zelle|venmo|cash ?app|wire|western union|gift ?cards?|deposit|holding fee|crypto|bitcoin)\b/i;
const QUESTION = /\?\s*$|^\s*(is|are|does|do|did|should|can|could|what|why|how|who|when|will)\b/i;

/** A command to open a view, read from the words. Null: not a command. */
export function viewFrom(text: string): View | null {
  const t = text.toLowerCase();
  if (/\b(on|open|show( me)?|see|take me to) (it on )?(the )?map\b|\bmap view\b|^map$/.test(t))
    return "map";
  if (/\breplays?\b|\breal (case|scam)s?\b|\bpast cases?\b/.test(t)) return "replays";
  if (
    /\bwalk (me )?(through|around|it)\b|\b3d (tour|walk)|\bwalk-?through\b|\bvirtual tour\b/.test(t)
  )
    return "walk";
  if (/\binvestigat|\bforensic/.test(t)) return "investigate";
  if (/\b(open|show( me)?|see|browse)( all| the)? listings\b|^listings$/.test(t)) return "listings";
  if (/\b(open|show( me)?)( the)? finder\b|\bwhat (have you|did you) learn/.test(t))
    return "finder";
  return null;
}

/** A facebook.com (or fb.com) address. Its page is never fetched. */
export function isFacebook(text: string): boolean {
  // Any subdomain (www., m., l.) and fb.com / fb.me, with or without a scheme.
  return /(^|[\s/@(<"':])(?:[a-z0-9-]+\.)*(facebook\.com|fb\.com|fb\.me)\b/i.test(text);
}

/** Removes Facebook addresses from pasted text, so only the renter's own words are sent. */
export function withoutFacebookLinks(text: string): string {
  return text
    .replace(/\S*\b(facebook\.com|fb\.com|fb\.me)\b\S*/gi, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

/** How many signs of a rental ad the text carries. */
export function adSigns(text: string): number {
  return AD_SIGNS.filter((r) => r.test(text)).length;
}

export function route(s: Submission): Intent {
  const text = s.text.trim();
  if (s.files > 0) return { kind: "check" };
  if (!text) return { kind: "check-ask" };
  // Facebook keeps listings behind a login and its terms forbid scraping: its address is never
  // fetched or sent. With the address removed, ad text is checked; anything else asks for it.
  if (isFacebook(text)) {
    const rest = withoutFacebookLinks(text);
    const restSigns = adSigns(rest);
    // A short question about the link ("legit? he wants a deposit first") is not the ad.
    if (QUESTION.test(rest) && rest.length < 140 && restSigns < 2) return { kind: "check-fb" };
    const isAd = restSigns > 0 || STRONG_SIGNS.some((r) => r.test(rest)) || rest.length >= 120;
    return { kind: isAd ? "check" : "check-fb" };
  }
  const kind = classifyListingText(text).kind;
  if (kind === "link") return { kind: "check" };
  // A link inside longer text is an ad pasted with its address.
  if (/https?:\/\/\S+/i.test(text)) return { kind: "check" };

  const view = viewFrom(text);
  const long = text.length >= 220;
  const signs = adSigns(text);
  const wish = WISH.test(text);

  const question = QUESTION.test(text) && text.length < 140;
  const strong = STRONG_SIGNS.some((r) => r.test(text));
  // Pasted ad text: long, a strong ad marker, or two or more signs of an ad; never a short wish
  // or a short question ("Is $600 by Zelle normal?" is a question, not an ad).
  if (!wish && !question && (strong || signs >= 2 || long)) return { kind: "check" };
  if (!wish && (signs >= 3 || text.length >= 400)) return { kind: "check" };
  // "Looking for a responsible tenant... deposit by Zelle": a wish opener does not hide an ad.
  // A monthly price or a deposit alone stays a wish; a payment app or a phone number, with
  // another sign or a long text, is an ad; so are three signs of any kind.
  const payOrPhone = PAY_OR_PHONE.some((r) => r.test(text));
  if (wish && ((payOrPhone && (signs >= 2 || text.length >= 80)) || signs >= 3))
    return { kind: "check" };
  if (view && text.length < 120) return { kind: "open", view };
  if (wish) return { kind: "find" };
  if (CHECK_WORDS.test(text) && text.length < 120)
    return s.caseOnScreen && QUESTION.test(text) ? { kind: "ask" } : { kind: "check-ask" };
  if (s.caseOnScreen && QUESTION.test(text)) return { kind: "ask" };
  if (question && PAYING.test(text)) return { kind: "rules" };
  if (question && (strong || signs > 0)) return { kind: "unsure" };
  if (WISH_WORDS.test(text) && !strong) return { kind: "find" };
  return s.caseOnScreen ? { kind: "ask" } : { kind: "unsure" };
}

/** The other reading of the same words, offered as a one-tap switch. Null: none fits. */
export function switchOf(intent: Intent): Intent | null {
  if (intent.kind === "check") return { kind: "find" };
  if (intent.kind === "find" || intent.kind === "ask" || intent.kind === "open")
    return { kind: "check" };
  return null; // "unsure" asks with two chips; "rules" answers from code
}

export const SWITCH_LABEL: Record<Intent["kind"], string> = {
  check: "It's an ad: check it",
  "check-ask": "It's an ad: check it",
  "check-fb": "It's an ad: check it",
  find: "I'm looking for a place",
  ask: "It's a question",
  open: "Open it",
  unsure: "Choose",
  rules: "Answer",
};

// ---------------------------------------------------------------------------------------------
// Reading a wish: the budget and must-haves, by code.

/** The max rent in the renter's words, or null. "1500", "$1,500", "1.5k". */
export function rentFrom(text: string): number | null {
  const t = text.toLowerCase();
  const patterns = [
    /(?:under|below|max|up to|at most|less than|budget(?: is| of)?|around|about)\s*\$?\s*([\d,.]+)\s*(k)?\b/g,
    /\$\s*([\d,.]+)\s*(k)?\b/g,
    /^\s*([\d,.]+)\s*(k)?\s*(?:a month|\/mo|per month)?\s*$/g, // a bare amount
  ];
  // Every candidate in order; the first that reads as a monthly rent wins ("about 2 beds $1200").
  for (const re of patterns) {
    for (const m of t.matchAll(re)) {
      let n = Number(m[1]!.replace(/,/g, ""));
      if (m[2]) n *= 1000;
      if (!Number.isFinite(n)) continue;
      n = Math.round(n);
      if (n >= 300 && n <= 20000) return n;
    }
  }
  return null;
}

export function briefFromWords(text: string): RenterBrief {
  const t = text.toLowerCase();
  const brief: RenterBrief = {};
  const rent = rentFrom(t);
  if (rent) brief.max_rent_month = rent;
  // A range ("2-3 bedroom", "2 to 3 beds") keeps its lower end.
  const beds =
    /(\d)\s*(?:-|to)\s*\d\s*(?:bed|br|bd|bedroom)s?\b/.exec(t) ??
    /(\d)\s*(?:\+\s*)?(?:bed|br|bd|bedroom)s?\b/.exec(t);
  if (beds) brief.beds_min = Number(beds[1]);
  else if (/\bstudio\b/.test(t)) brief.beds_min = 0;
  if (/\bno walk-?ups?\b|\belevator\b|\bground floor\b|\bno stairs\b/.test(t))
    brief.needs_no_walkup = true;
  if (/\bparking\b|\bgarage\b/.test(t)) brief.needs_parking = true;
  if (/\bpets?\b|\bdogs?\b|\bcats?\b/.test(t) && !/\bno (pets?|dogs?|cats?)\b/.test(t))
    brief.pets = true;
  return brief;
}

/** What the thread still needs to ask before it can search. Null: nothing. */
export function missingFor(text: string, knownRent: number | null): "max_rent" | null {
  if (knownRent !== null) return null;
  if (rentFrom(text) !== null) return null;
  if (/\bno (limit|budget|max)\b|\bany (price|budget)\b/i.test(text)) return null;
  return "max_rent";
}

/** Quick replies for "What's your max rent?". "No limit" searches without one. */
export const RENT_REPLIES = ["$1,200", "$1,500", "$2,000", "$2,500", "No limit"] as const;
