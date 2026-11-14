import { AS_OF } from "../contracts";

const n = (x: number) => x.toLocaleString("en-US");

// Every word on the map screen. The honesty rules live here: places are "researched", units are
// "reported available as of CoStar's last research", a scan "may be a model unit", and nothing
// says a place can be rented today.
export const S = {
  city: "Houston",
  eyebrow: "The city",
  // Fixture places are team-made samples, so the count never credits them to CoStar.
  countNoun: (count: number, source: "live" | "fixture") =>
    source === "fixture"
      ? `sample ${count === 1 ? "place" : "places"}, made by the team`
      : `${count === 1 ? "place" : "places"} CoStar has researched`,
  fitLine: (fit: number, total: number) => `${n(fit)} of ${n(total)} fit your brief`,
  noBrief: "Set a brief to narrow them down",
  asOf: AS_OF,
  loading: "Reading the record...",
  loadError: "The places feed did not answer.",
  retry: "Try again",
  mapError: "The 3D map could not start in this browser. The list below has every place.",
  rasterNote: "Flat street map shown: the 3D tiles did not load.",
  attribution: "OpenFreeMap © OpenMapTiles. Data from OpenStreetMap contributors.",
  legendFit: "Fits your brief",
  legendOther: "On record",
  legendScan: "3D scan",
  legendHeight: "Taller: more plans",
  legendChip: (source: "live" | "fixture") =>
    source === "fixture"
      ? "Chip: lowest asking rent (sample)"
      : "Chip: lowest asking rent, as of last research",
  everyFigure: (source: "live" | "fixture") =>
    source === "fixture" ? "Every figure is a sample" : `Every figure ${AS_OF}`,
  cardAsOf: (source: "live" | "fixture") =>
    source === "fixture" ? "sample figure" : "as of last research",
  mapLabel: "Map of the places. The same places are in the list below.",
  // the brief
  criteria: "Your brief",
  criteriaCoStar: "On CoStar's record",
  criteriaMap: "On this map",
  criteriaOwn: "Your own",
  budget: "Most rent a month",
  beds: "Bedrooms",
  any: "Any",
  studio: "Studio",
  noWalkup: "No walk-up",
  parking: "Parking",
  pets: "Pets",
  scanOnly: "Has a 3D scan",
  unitsOnly: "Units reported",
  ownLabel: "Add your own must-have",
  ownPlaceholder: "Morning light, a quiet street...",
  ownHint: "Kept as a note for your visit. We can't check it on the record.",
  ownAdd: "Add",
  ownDrop: (t: string) => `Drop "${t}"`,
  clear: "Clear the brief",
  // the ledger
  ledger: "Places on record",
  ledgerSample: "Sample places",
  ledgerEmpty: "Nothing on record fits this brief. Loosen one line.",
  kind: (k: "apartment" | "house") => (k === "house" ? "Rental home" : "Apartment community"),
  kindShort: (k: "apartment" | "house") => (k === "house" ? "Home" : "Apartments"),
  rentFrom: (rent: number | null) => (rent == null ? "No asking price on record" : `$${n(rent)}`),
  rentLead: "from",
  rentTail: "a month",
  plans: (count: number) => `${count} floor ${count === 1 ? "plan" : "plans"}`,
  plansShort: (count: number) => `${count} ${count === 1 ? "plan" : "plans"}`,
  units: (count: number | null) =>
    count == null ? "units not on record" : `${count} ${count === 1 ? "unit" : "units"} reported`,
  scanTag: "3D scan",
  fits: "Fits",
  passedTag: "Passed",
  // the sheet
  sheetClose: "Close this place",
  sheetLoading: "Reading this place's record...",
  sheetError: "This place's record did not load.",
  plansOnRecord: "Floor plans on record",
  company: "Management company on record",
  notOnRecord: "not on record",
  scanBadge: "3D scan in this building",
  scanNote: "It may be a model unit, not the one you'd rent.",
  walk: "Walk it first",
  checkAd: "Check an ad for this place",
  pass: "Not this one",
  aerialStandIn: "Drawn stand-in (fixture)",
  aerialNone: "No aerial photo on record for this place",
  aerialAlt: "Aerial photo of this building",
  aerialAge: (months: number) =>
    months < 1
      ? "captured this month"
      : months < 12
        ? `${months} ${months === 1 ? "month" : "months"} old`
        : `${Math.floor(months / 12)} yr ${months % 12} mo old`,
  noBuilding: "Nothing on CoStar's record for this building.",
  // the finder
  finder: "Finder",
  finderSub: "What you do here, live in this browser",
  finderEmpty:
    "Open a place or pass on one. The finder watches what you pass on, and asks before it remembers.",
  finderStamp: "Renter event",
  proposalStamp: "Picked by policy",
  proposal: (count: number) => `You passed on ${count} walk-ups. Remember: no walk-ups?`,
  proposalYes: "Yes, remember",
  proposalNo: "Not now",
  remembered: "Remembered: no walk-ups. Added to your brief.",
  evOpened: (pid: string) => `Opened ${pid}`,
  evPassed: (pid: string) => `Passed on ${pid}`,
  evCriteria: "Changed the brief",
  collapse: (what: string) => `Collapse ${what}`,
  expand: (what: string) => `Expand ${what}`,
} as const;

// Words that must never appear on this screen (decisions.md copy rules).
export const BANNED = /available now|open listings?|for rent now|vacan(t|cy)/i;
