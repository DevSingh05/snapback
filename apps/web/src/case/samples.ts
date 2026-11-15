// Sample values in the API's own shapes, for the pieces page and the tests. Synthetic and
// team-made: the sentences are copies of what the API's code writes for the fixture record,
// never text about a real building.
import type { CopyAlert, PlaceMatch, RealListing, ReportPack } from "../contracts";

export function sampleListing(over: Partial<RealListing> = {}): RealListing {
  return {
    case_id: "7Q2M",
    source: "fixture",
    property_id: "fx-court",
    which: "claimed",
    building_name: "Fixture Court",
    manager_company: "Fixture Living LLC",
    website_host: "fixtureliving.example",
    plans: [{ name: "2 bed / 2 bath", beds: 2, baths: 2, rent_min: 1600, rent_max: 1900 }],
    photos_in_scan: 3,
    photos_total: 3,
    ad_rent: 900,
    ad_asks_irreversible: true,
    phone_is_office: "no",
    figures_shown: true,
    as_of: "as of CoStar's last research",
    headline:
      "The ad asks $900 a month. Its Apartments.com listing on CoStar's record says $1,600 to $1,900 a month for a 2 bed / 2 bath.",
    provenance: "3 of 3 of the ad's photos are in CoStar's own scan of this building.",
    phone_line: "The ad's number is not the office's on record.",
    cta_label: "See the real listing",
    cta_url: "https://www.apartments.com/fixture-court/",
    ...over,
  };
}

export function samplePlace(n: number, over: Partial<PlaceMatch> = {}): PlaceMatch {
  return {
    property_id: `fx-${n}`,
    kind: "apartment",
    floor_plan: "1 bed / 1 bath",
    budget_fit: "within",
    price_text: "$1,450 to $1,600 a month as of CoStar's last research",
    availability_text: "2 units reported available",
    must_haves: [],
    musts_met: 0,
    has_3d_scan: false,
    source: "fixture",
    handoff_url: `https://www.apartments.com/fx-${n}/`,
    handoff_label: "Its listing on Apartments.com",
    ...over,
  };
}

export function sampleAlert(over: Partial<CopyAlert> = {}): CopyAlert {
  return {
    case_id: "7Q2M",
    source: "fixture",
    fires: true,
    which: "claimed",
    property_id: "fx-court",
    manager_company: "Fixture Living LLC",
    website_host: "fixtureliving.example",
    photos_in_scan: 3,
    photos_total: 3,
    phone_is_office: "no",
    draft_only: true,
    sent: false,
    draft_subject: "An ad using photos of your building was checked",
    draft_body: [
      "To the leasing office at Fixture Living LLC,",
      "SNAPBACK checked an ad today. 3 of its 3 photos sit in CoStar's own 3D scan of your building. The number in the ad is not the office's number on record.",
      "This may be a copy of your listing, or an agent you work with. Please confirm whether you posted it.",
      "This is a draft. Nothing has been sent.",
    ].join("\n\n"),
    report_url: "/cases/7Q2M/report",
    report_ready: false,
    as_of: "as of CoStar's last research",
    ...over,
  };
}

export function samplePack(over: Partial<ReportPack> = {}): ReportPack {
  return {
    case_id: "7Q2M",
    source: "fixture",
    lang: "en",
    checked_at: "2026-11-13T21:42:00Z",
    state: "dont_pay",
    reportable: true,
    proof_lines: ["The photos were located in a different property than the one the ad names."],
    platforms: [
      {
        platform: "craigslist",
        name: "Craigslist",
        steps: ["Open the post.", "Choose the flag at the top of the post."],
      },
    ],
    not_checked: ["ID", "lease", "ownership"],
    ...over,
  };
}
