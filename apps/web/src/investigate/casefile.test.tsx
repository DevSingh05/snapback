import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { matchRoute } from "../App";
import {
  CaseAttachment,
  CaseFileBody,
  CaseStudyView,
  evidenceText,
  exportJson,
  exportName,
  gapText,
  money,
} from "./CaseFile";
import type { CaseFile, CaseStudy } from "./types";

const cf: CaseFile = {
  schema: "snapback.case_file.v1",
  label: "SYNTHETIC DATA",
  synthetic: true,
  source: "FIXTURE",
  ring: {
    id: "D",
    label: "Ring D",
    n_ads: 2,
    n_phones: 2,
    first_seen: "2026-05-19",
    last_seen: "2026-05-26",
    score: 0.5,
  },
  detection: {
    first_ad_id: 1,
    first_ad_date: "2026-05-19",
    flagged_on: "2026-05-31",
    flag_ad_id: 2,
    days_first_ad_to_flag: 12,
    ads_up_before_flag: 1,
    ads_total: 2,
    method: "Replayed day by day.",
  },
  timeline: [
    {
      id: 1,
      posted_at: "2026-05-19",
      phone: "555-0101",
      hood: "Tern Point",
      beds: 2,
      rent: 900,
      title: "t",
      text: "x",
      photos: [],
      amount_asked: {
        sentence: "Wire the first month's rent.",
        item: "first month's rent",
        usd: 900,
        basis: "equals the listed monthly rent",
      },
    },
    {
      id: 2,
      posted_at: "2026-05-26",
      phone: "555-0102",
      hood: "Oakbend",
      beds: 2,
      rent: 800,
      title: "t",
      text: "x",
      photos: [],
      amount_asked: {
        sentence: "Booking amount first.",
        item: "deposit or booking amount",
        usd: null,
        basis: "amount not stated",
      },
    },
  ],
  contacts: [
    { phone: "555-0101", ad_ids: [1] },
    { phone: "555-0102", ad_ids: [2] },
  ],
  links: [
    {
      from_ad: 1,
      to_ad: 2,
      kind: "photo",
      weight: 3,
      evidence: { photo_sets: 2, closest_bits: 1, strong: true },
    },
  ],
  signals: [
    { kind: "phone", label: "shared phone", weight: 2, n_links: 0, strength: 0, ads: [] },
    { kind: "photo", label: "shared photo hash", weight: 3, n_links: 1, strength: 3, ads: [1, 2] },
    { kind: "wording", label: "shared wording", weight: 2, n_links: 0, strength: 0, ads: [] },
    { kind: "link", label: "shared link", weight: 0, n_links: 0, strength: 0, ads: [] },
  ],
  strongest: ["photo"],
  findings: [],
  sources: [],
  not_known: ["Who operates the ring."],
};

describe("case file", () => {
  it("export is the JSON of the case file, named SYNTHETIC", () => {
    expect(JSON.parse(exportJson(cf))).toEqual(cf);
    expect(exportName(cf)).toBe("case-file-ring-D-SYNTHETIC.json");
  });

  it("states the gap, the amounts and the evidence in words", () => {
    expect(gapText(cf)).toBe("12 days from the first ad to the flag");
    expect(
      gapText({
        ...cf,
        detection: { ...cf.detection, flagged_on: null, days_first_ad_to_flag: null },
      }),
    ).toBe("Never flagged by the detector");
    expect(money(null)).toBe("not stated");
    expect(money(1200)).toBe("$1,200");
    expect(evidenceText(cf.links[0]!)).toContain("closest pair 1 of 64 bits apart");
  });

  it("shows every ad in order with its tie, the strongest signal and what is not known", () => {
    render(<CaseFileBody cf={cf} />);
    expect(screen.getByText("First ad of the ring.")).toBeTruthy();
    expect(screen.getByText(/Shared photo hash/, { selector: "b" })).toBeTruthy();
    expect(screen.getAllByText(/shared photo hash/).length).toBeGreaterThan(0);
    expect(screen.getByText("Who operates the ring.")).toBeTruthy();
    expect(screen.getByText(/2026-05-31/)).toBeTruthy();
  });

  it("the printable attachment lists the fields a complaint asks for", () => {
    render(<CaseAttachment cf={cf} />);
    expect(screen.getByText(/SYNTHETIC DATA\. Every ad/)).toBeTruthy();
    for (const h of ["The ads", "Contact identifiers", "Links between ads", "Not known"]) {
      expect(screen.getByText(new RegExp(h))).toBeTruthy();
    }
    expect(screen.getAllByText("555-0102").length).toBeGreaterThan(0);
    expect(screen.getByText(/Booking amount first\./)).toBeTruthy();
  });

  it("routes the attachment page", () => {
    expect(matchRoute("/investigate/case/D")).toEqual({ name: "investigate-case", ringId: "D" });
  });
});

describe("case study", () => {
  const cs: CaseStudy = {
    schema: "snapback.case_study.v1",
    label: "SYNTHETIC DATA",
    synthetic: true,
    source: "FIXTURE",
    ring: { id: "D", label: "Ring D", n_ads: 2 },
    flagged_on: "2026-05-31",
    days_first_ad_to_flag: 12,
    steps: [
      {
        step: 1,
        date: "2026-05-19",
        day_no: 1,
        ad_ids: [1],
        ring_ads_so_far: 1,
        numbers_so_far: 1,
        ties: [],
        lines: ["Ad 1 goes up from 555-0101."],
        detector: "Not flagged. one ad",
        flagged: false,
      },
      {
        step: 2,
        date: "2026-05-31",
        day_no: 13,
        ad_ids: [2],
        ring_ads_so_far: 2,
        numbers_so_far: 2,
        ties: [{ from_ad: 1, to_ad: 2, kind: "photo", weight: 3, evidence: {} }],
        lines: ["Ad 2 reuses 5 photo set(s) from ad 1."],
        detector: "FLAGGED. group of 4",
        flagged: true,
      },
    ],
    after: { n_ads: 0, last_date: null, text: "No ad of this ring was posted after the flag." },
    strongest: ["photo"],
    not_known: ["Whether any renter paid."],
  };

  it("renders one card per step from the API data, flagged last", async () => {
    render(<CaseStudyView load={() => Promise.resolve(cs)} />);
    await waitFor(() => expect(screen.getByText("Ad 1 goes up from 555-0101.")).toBeTruthy());
    expect(screen.getByText("FLAGGED. group of 4")).toBeTruthy();
    expect(screen.getByText(/Flagged 12 days after the first ad/)).toBeTruthy();
    expect(screen.getByText("Whether any renter paid.")).toBeTruthy();
    expect(screen.getAllByText("SYNTHETIC DATA").length).toBeGreaterThan(0);
  });
});
