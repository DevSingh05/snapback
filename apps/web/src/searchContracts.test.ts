import { describe, expect, it } from "vitest";
import { AS_OF } from "./contracts";
import type { PlaceMatch, RenterBrief, SearchResponse, TourDraft } from "./contracts";

// Synthetic: mirrors what POST /search returns on the fixture kit.
const place: PlaceMatch = {
  property_id: "fx-prop-3",
  kind: "apartment",
  floor_plan: "1 bed / 1 bath",
  beds: 1,
  baths: 1,
  rent_min: 1700,
  rent_max: 1900,
  budget_fit: "within",
  price_text: `$1,700 to $1,900 a month ${AS_OF}`,
  availability_text: `2 units reported available ${AS_OF}`,
  must_haves: [{ key: "walkup", text: "Not a walk-up", met: true }],
  musts_met: 1,
  has_3d_scan: true,
  scan_text: "a 3D scan in this building",
  office_on_record: "Fixture Property Management Co",
  source: "fixture",
};

describe("search contracts", () => {
  it("a brief is all optional and a response labels its source", () => {
    const brief: RenterBrief = {};
    const response: SearchResponse = {
      source: "fixture",
      as_of: AS_OF,
      n_considered: 7,
      n_matches: 1,
      matches: [place],
    };
    expect(brief).toEqual({});
    expect(response.matches[0]?.price_text.endsWith(AS_OF)).toBe(true);
    expect(response.matches[0]?.availability_text ?? "").not.toMatch(/available now/i);
  });

  it("a tour draft is a draft and never sent", () => {
    const draft: TourDraft = {
      property_id: place.property_id,
      addressee: "Fixture Property Management Co",
      text: "To: Fixture Property Management Co",
      status: "draft",
      sent: false,
      source: "fixture",
    };
    expect(draft.sent).toBe(false);
    expect(draft.status).toBe("draft");
  });
});
