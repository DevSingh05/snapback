// The three stories' sample data. All of it is team-made: no real listing, no real person's
// words, no sponsor data. Card lines copy the wording the card code writes
// (src/snapback/card/strings.py) so a story shows what the app really says. Phone numbers are
// 555 test numbers. Every photo is a licensed Unsplash stand-in (docs/CREDITS.md).
import type {
  Card,
  FinderPick,
  FinderProposal,
  TourDraft,
  TourStop,
  TraceEvent,
} from "../contracts";
import airportWindow from "../assets/stories/airport-window.webp";
import bedroomBright from "../assets/stories/bedroom-bright.webp";
import citySidewalk from "../assets/stories/city-sidewalk.webp";
import citySkyline from "../assets/stories/city-skyline.webp";
import cityStreet from "../assets/stories/city-street.webp";
import kitchenIsland from "../assets/stories/kitchen-island.webp";
import kitchenWhite from "../assets/stories/kitchen-white.webp";
import livingBalcony from "../assets/stories/living-balcony.webp";
import livingRoom from "../assets/stories/living-room.webp";
import livingSectional from "../assets/stories/living-sectional.webp";
import studioDesk from "../assets/stories/studio-desk.webp";

export const PHOTOS = {
  airportWindow,
  bedroomBright,
  citySidewalk,
  citySkyline,
  cityStreet,
  kitchenIsland,
  kitchenWhite,
  livingBalcony,
  livingRoom,
  livingSectional,
  studioDesk,
};

// --- Ads, as the renter saw them ---------------------------------------------------------------

export interface Ad {
  where: string;
  title: string;
  price: string;
  place: string;
  body: string;
  photo: string;
  photoAlt: string;
  photos: number;
}

/** Sascha's ad: the text from pitch-v2 section 3, word for word. */
export const SASCHA_AD: Ad = {
  where: "Marketplace listing",
  title: "1 bed 1 bath apartment",
  price: "$1,150 / month",
  place: "Midtown, Houston",
  body:
    "1 bed 1 bath in Midtown Houston, $1,150/mo. I'm the owner, working abroad until spring so " +
    "no showings right now. Send $600 by Zelle to hold it and I'll mail the keys. Three other " +
    "people are asking. Text 713-555-0188.",
  photo: livingRoom,
  photoAlt: "A bright living room with a grey sofa and a round wooden table",
  photos: 3,
};

export const STUDENT_AD: Ad = {
  where: "Listing in a student housing group",
  title: "Furnished studio near campus",
  price: "$950 / month",
  place: "Near the university, Houston",
  body:
    "Furnished studio, 10 minutes' walk to campus, bills included. I'm abroad for work so no " +
    "viewings, but I can hold it for you until the semester starts. Wire the $800 deposit this " +
    "week to hold it. WhatsApp 713-555-0142.",
  photo: studioDesk,
  photoAlt: "A small furnished studio with a bed, a desk and a pink chair",
  photos: 3,
};

export const AD_FILES = ["listing-1.jpg", "listing-2.jpg", "listing-3.jpg"];

// --- Sascha: the check ---------------------------------------------------------------------------

function trace(caseId: string, lines: [TraceEvent["kind"], string | null, string, boolean?][]) {
  const start = Date.parse("2026-11-14T22:00:00Z");
  return lines.map(([kind, pick, reason, model], i): TraceEvent => ({
    case_id: caseId,
    seq: i,
    at: new Date(start + i * 6000).toISOString(),
    kind,
    options: [],
    pick,
    reason,
    source: "fixture",
    chosen_by: model ? "model" : "policy",
  }));
}

export const SASCHA_TRACE: TraceEvent[] = [
  ...trace("ST-SASCHA", [
    [
      "todo",
      null,
      "Plan: read the record, place the 3 photos, check the payment ask, check the contact.",
    ],
    ["agent", "record", "Reading CoStar's record for the building the ad names."],
  ]),
  {
    case_id: "ST-SASCHA",
    seq: 2,
    at: "2026-11-14T22:00:12Z",
    kind: "choice",
    choice: "next_check",
    options: ["place_photos", "contact", "rules"],
    pick: "place_photos",
    reason: "The building has a 3D scan, so place the ad's photos in it first.",
    source: "fixture",
    chosen_by: "model",
  },
  ...trace("ST-SASCHA", [
    ["tool", "locate_photos", "Placing 3 listing photos in the scan."],
    ["agent", "rules", "Reading the ad's words against the payment and pressure rules."],
    ["verdict", "hold", "Code set the verdict from the checks."],
  ]).map((e, i) => ({ ...e, seq: 3 + i, at: new Date(Date.parse(e.at) + 18000).toISOString() })),
];

export const SASCHA_CARD: Card = {
  case_id: "H4SC",
  source: "fixture",
  state: "hold",
  checked_at: "2026-11-14T17:02:00-05:00",
  expires_at: "2026-11-15T17:02:00-05:00",
  rows: [
    {
      kind: "place",
      lines: [{ label: "Real", text: "Taken in this building (3 of 3 photos).", tone: "ok" }],
    },
    {
      kind: "person",
      lines: [
        {
          label: "Contact on record",
          text: "Not confirmed. This number is not the leasing office's on record. Agents often use their own. Call the office on record yourself to confirm.",
          tone: "not_shown",
        },
      ],
    },
    {
      kind: "price",
      lines: [
        { label: "Payment ask", text: "Zelle before a viewing. Red flag.", tone: "red_flag" },
        {
          label: "Pressure",
          text: "They say they cannot show the unit in person. Red flag.",
          tone: "red_flag",
        },
      ],
    },
  ],
  not_checked: ["ID", "lease", "ownership"],
  footer: [],
  lang: "en",
};

export const SASCHA_CHALLENGE =
  "Before you pay, ask them to send a photo of the north window frame in the living room with the code K7P4 written on paper.";

// --- The student: the check and the safer places -----------------------------------------------

export const STUDENT_QUESTION = "Is this landlord real?";

export const STUDENT_CARD: Card = {
  case_id: "M2ST",
  source: "fixture",
  state: "dont_pay",
  checked_at: "2026-11-14T17:05:00-05:00",
  expires_at: "2026-11-15T17:05:00-05:00",
  rows: [
    {
      kind: "place",
      lines: [
        {
          label: "Real",
          text: "Taken in a different building (2 of 3 photos). Red flag.",
          tone: "red_flag",
        },
      ],
    },
    {
      kind: "price",
      lines: [
        {
          label: "Payment ask",
          text: "Wire transfer before a viewing. Red flag.",
          tone: "red_flag",
        },
        {
          label: "Pressure",
          text: "They say they cannot show the unit in person. Red flag.",
          tone: "red_flag",
        },
      ],
    },
    {
      kind: "person",
      lines: [
        {
          label: "Contact on record",
          text: "Not confirmed. This number is not the leasing office's on record. Agents often use their own. Call the office on record yourself to confirm.",
          tone: "not_shown",
        },
      ],
    },
  ],
  not_checked: ["ID", "lease", "ownership"],
  footer: [],
  lang: "en",
};

const AS_OF = "as of CoStar's last research";

export const STUDENT_PICKS: FinderPick[] = [
  {
    pid: "st-pick-1",
    rank: 1,
    kind: "apartment",
    has_scan: true,
    line: "Studio, from $1,020/mo, 0.6 mi from campus, leasing office on record",
    why: "Closest to campus of the places you can walk first, and you can call its office.",
    chosen_by: "model",
    as_of: AS_OF,
  },
  {
    pid: "st-pick-2",
    rank: 2,
    kind: "apartment",
    has_scan: true,
    line: "Studio, from $985/mo, 1.3 mi from campus, on a bus line",
    why: "Under your budget, with a 3D scan and an office on record.",
    chosen_by: "model",
    as_of: AS_OF,
  },
  {
    pid: "st-pick-3",
    rank: 3,
    kind: "apartment",
    has_scan: false,
    line: "1 bed, from $1,090/mo, 1.0 mi from campus",
    why: "Fits the area; no scan yet, so visit before you sign.",
    chosen_by: "policy",
    as_of: AS_OF,
  },
];

// --- Browsing: the Finder keeps a preference ----------------------------------------------------

export const BROWSE_WORDS = "A 1 bed under $1,400 near Montrose. No walk-ups please.";

export const BROWSE_OFFER: FinderProposal = {
  id: "st-offer-1",
  key: "propose_no_walkup",
  update: { no_walkup: true },
  text: "Only show places with an elevator from now on?",
  evidence: "you said “no walk-ups”",
  reason: "The renter asked for no walk-ups in their own words.",
  chosen_by: "policy",
  status: "proposed",
  at: "2026-11-14T22:10:00Z",
};

export const BROWSE_PICKS: FinderPick[] = [
  {
    pid: "br-pick-1",
    rank: 1,
    kind: "apartment",
    has_scan: true,
    line: "1 bed / 1 bath, from $1,365/mo, elevator, leasing office on record",
    why: "Fits your budget and your no walk-ups rule, and you can walk it first.",
    chosen_by: "model",
    as_of: AS_OF,
    walkup: false,
  },
  {
    pid: "br-pick-2",
    rank: 2,
    kind: "apartment",
    has_scan: true,
    line: "1 bed / 1 bath, from $1,310/mo, elevator, garage parking",
    why: "A little cheaper, one more block from Montrose.",
    chosen_by: "model",
    as_of: AS_OF,
    walkup: false,
  },
  {
    pid: "br-pick-3",
    rank: 3,
    kind: "apartment",
    has_scan: false,
    line: "1 bed / 1 bath, from $1,395/mo, elevator",
    why: "In budget; no scan, so it ranks after the ones you can walk.",
    chosen_by: "policy",
    as_of: AS_OF,
    walkup: false,
  },
];

/** Built the way search.py draft_tour_request builds it, to a sample office. */
export const BROWSE_DRAFT: TourDraft = {
  property_id: "br-pick-1",
  addressee: "Sample Leasing Office (made by the team)",
  text: [
    "To: Sample Leasing Office (made by the team)",
    "",
    "Hello,",
    "",
    "I am a renter interested in the 1 bed / 1 bath floor plan, listed at from $1,365/mo. I would like to arrange a tour.",
    "",
    "Before I apply, could you tell me:",
    "1. The application fee, and any other amount due when I apply.",
    "2. Whether a place like this is available.",
    "",
    "Please reply with times that work for a tour. I have not paid anything, and I will not pay before I have seen the place.",
  ].join("\n"),
  status: "draft",
  sent: false,
  source: "fixture",
};

// --- The walks ---------------------------------------------------------------------------------

const Q: [number, number, number, number] = [0, 0, 0, 1];

function stop(over: Partial<TourStop> & Pick<TourStop, "kind" | "key" | "title">): TourStop {
  return {
    sweep_count: 1,
    sweep_ids: [],
    photos: [],
    ad_view: "unknown",
    claims: [],
    facts: [],
    ...over,
  };
}

export interface WalkSet {
  stops: TourStop[];
  /** The stand-in view at each stop, by stop key. */
  views: Record<string, { src: string; alt: string }>;
  /** The ad photo that lands at a stop, by stop key. */
  photos: Record<string, { alias: string; src: string }>;
  verdict: string;
  /** Which stop a paused (reduced-motion) walk shows first. */
  still: number;
}

const OUTSIDE = stop({ kind: "arrive", key: "arrive", title: "Arrive outside" });

export const SASCHA_WALK: WalkSet = {
  stops: [
    OUTSIDE,
    stop({
      kind: "room",
      key: "living",
      title: "Living room",
      room_label: "Living room",
      ad_view: "placed",
      photos: [
        {
          photo_id: "st-p1",
          alias: "P1",
          sweep_id: "st-sweep-1",
          position: [0, 1.4, 0],
          rotation_quat: Q,
          fov_deg: 70,
        },
      ],
    }),
    stop({ kind: "room", key: "kitchen", title: "Kitchen", ad_view: "none_placed" }),
    stop({ kind: "room", key: "bedroom", title: "Bedroom", ad_view: "none_placed" }),
  ],
  views: {
    arrive: { src: cityStreet, alt: "A street of tall buildings" },
    living: { src: livingRoom, alt: "The living room" },
    kitchen: { src: kitchenWhite, alt: "A white kitchen with a dark floor" },
    bedroom: { src: bedroomBright, alt: "A bright bedroom with a window" },
  },
  photos: { living: { alias: "P1", src: livingRoom } },
  verdict: "Hold off for now",
  still: 1,
};

export const STUDENT_WALK: WalkSet = {
  stops: [
    OUTSIDE,
    stop({ kind: "room", key: "living", title: "Main room" }),
    stop({ kind: "room", key: "kitchen", title: "Kitchen" }),
  ],
  views: {
    arrive: { src: cityStreet, alt: "A street of tall buildings" },
    living: { src: livingBalcony, alt: "A living room with a sofa and a balcony door" },
    kitchen: { src: kitchenWhite, alt: "A white kitchen" },
  },
  photos: {},
  verdict: "Walk it first, then visit",
  still: 1,
};

export const BROWSE_WALK: WalkSet = {
  stops: [
    OUTSIDE,
    stop({ kind: "room", key: "living", title: "Living room" }),
    stop({ kind: "room", key: "kitchen", title: "Kitchen" }),
  ],
  views: {
    arrive: { src: cityStreet, alt: "A street of tall buildings" },
    living: { src: livingSectional, alt: "A living room with a sectional sofa" },
    kitchen: { src: kitchenIsland, alt: "A kitchen with an island and yellow stools" },
  },
  photos: {},
  verdict: "Walk it first, then visit",
  still: 1,
};
