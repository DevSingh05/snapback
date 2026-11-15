import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import real from "../../../../fixtures/forensics/stream_timeline.json";
import { EvidencePanel, StreamView } from "./StreamView";
import {
  KINDS,
  caseFile,
  caseFileText,
  clampDay,
  dayNo,
  frameAt,
  layoutStream,
  linksOf,
  otherDots,
  playFrom,
  readQuery,
  signalRows,
  stepDay,
} from "./stream";
import type { StreamGroup, StreamTimeline } from "./stream";

const timeline = real as unknown as StreamTimeline;

// A hand-made stream of 10 days. One group: ads on days 2, 3, 3, 5 and 8 (zero-based), flagged
// on day 5 when its fourth ad arrives. Two numbers; one wording on four ads; one site on two.
const group: StreamGroup = {
  id: "A",
  label: "Ring A",
  n_ads: 5,
  n_phones: 2,
  score: 0.7,
  first_day: 2,
  flag_day: 5,
  gap_days: 3,
  ads_before_flag: 3,
  ad_days_before_flag: 7,
  renters_est: 210,
  ads: [
    { id: 11, day: 2, flag_day: 5, phone: "555-0101", hood: "Elm Flats", rent: 900 },
    { id: 12, day: 3, flag_day: 5, phone: "555-0101", hood: "Elm Flats", rent: 950 },
    { id: 13, day: 3, flag_day: 5, phone: "555-0102", hood: "Mill Row", rent: 880 },
    { id: 14, day: 5, flag_day: 5, phone: "555-0102", hood: "Mill Row", rent: 870 },
    { id: 15, day: 8, flag_day: 8, phone: "555-0102", hood: "Mill Row", rent: 860 },
  ],
  signals: [
    { kind: "phone", key: "555-0101", label: "555-0101", weight: 2, n_ads: 2, ad_ids: [11, 12] },
    {
      kind: "phone",
      key: "555-0102",
      label: "555-0102",
      weight: 2,
      n_ads: 3,
      ad_ids: [13, 14, 15],
    },
    {
      kind: "wording",
      key: "phrase-1",
      label: "Send the deposit before the tour.",
      weight: 2,
      n_ads: 4,
      ad_ids: [11, 12, 13, 14],
    },
    {
      kind: "site",
      key: "fast-deposit-11.example",
      label: "fast-deposit-11.example",
      weight: 0,
      n_ads: 2,
      ad_ids: [14, 15],
    },
  ],
  by_kind: {
    phone: { values: 2, ads: 5, weight: 2 },
    wording: { values: 1, ads: 4, weight: 2 },
    site: { values: 1, ads: 2, weight: 0 },
  },
  findings: [
    { kind: "phone_rotation", title: "Contact numbers rotate", summary: "2 numbers.", score: 0.33 },
  ],
  answer_key: { R01: 5 },
};

const small: StreamTimeline = {
  label: "SYNTHETIC DATA",
  synthetic: true,
  source: "FIXTURE",
  seed: 7,
  start: "2026-08-17",
  days: 10,
  n_ads: 25,
  min_ads: 4,
  views_per_ad_day: 30,
  weights: { phone: 2, photo: 3, wording: 2, site: 0 },
  groups: [group],
  other_ads_by_day: [2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
  flagged_ads_by_day: [0, 0, 0, 0, 0, 4, 4, 4, 5, 5],
  groups_by_day: [0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
  summary: { groups_found: 1, median_gap_days: 3, n_gap: 1, renters_est: 210 },
  answer_key: {
    n_seeded: 1,
    seeded_flagged: 1,
    seeded_separated: 1,
    median_gap_days: 3,
    n_gap: 1,
    single_group_median_gap_days: 3,
    n_single_group_gap: 1,
    ring_ads: 5,
    ring_ads_flagged: 5,
    honest_flagged: 0,
    n_honest: 20,
    seeded: [
      {
        name: "R01",
        n_ads: 5,
        flagged_ads: 5,
        separated: true,
        single_group_flag_day: 5,
        single_group_gap_days: 3,
        first_day: 2,
        flag_day: 5,
        gap_days: 3,
        ads_before_flag: 3,
        ad_days_before_flag: 7,
        renters_est: 210,
      },
    ],
  },
};

describe("the day slider", () => {
  it("shows nothing at position 0 and everything at the last position", () => {
    const empty = frameAt(small, 0);
    expect(empty.adsPosted).toBe(0);
    expect(empty.adsFlagged).toBe(0);
    expect(empty.groups[0]).toMatchObject({ shown: 0, flagged: false, started: false });
    const full = frameAt(small, 10);
    expect(full.adsPosted).toBe(25);
    expect(full.adsFlagged).toBe(5);
    expect(full.groups[0]).toMatchObject({ shown: 5, linked: 5, flagged: true, started: true });
  });

  it("puts an ad on the board from the position after its zero-based day", () => {
    expect(frameAt(small, 2).groups[0]?.shown).toBe(0); // first ad is zero-based day 2 = day 3
    expect(frameAt(small, 3).groups[0]).toMatchObject({ shown: 1, started: true });
    expect(frameAt(small, 4).groups[0]?.shown).toBe(3);
    expect(frameAt(small, 4).adsPosted).toBe(8 + 3);
  });

  it("raises the flag at the position after the flag day, not before", () => {
    expect(frameAt(small, 5).groups[0]).toMatchObject({ flagged: false, linked: 0 });
    expect(frameAt(small, 5).groupsFlagged).toBe(0);
    const at = frameAt(small, 6);
    expect(at.groups[0]).toMatchObject({ flagged: true, shown: 4, linked: 4 });
    expect(at.groupsFlagged).toBe(1);
    expect(at.seededFlagged).toBe(1);
    expect(at.adsFlagged).toBe(4);
    expect(dayNo(group.flag_day as number)).toBe(6);
  });

  it("clamps, steps and stops on the last day", () => {
    expect(clampDay(-3, 90)).toBe(0);
    expect(clampDay(200, 90)).toBe(90);
    expect(clampDay(44.6, 90)).toBe(45);
    expect(clampDay(Number.NaN, 90)).toBe(90);
    expect(stepDay(10, 90)).toEqual({ pos: 11, playing: true });
    expect(stepDay(89, 90)).toEqual({ pos: 90, playing: false });
    expect(stepDay(90, 90)).toEqual({ pos: 90, playing: false });
    expect(playFrom(90, 90)).toBe(0);
    expect(playFrom(31, 90)).toBe(31);
  });

  it("reads the day and the group from the address", () => {
    expect(readQuery("?day=45&ring=a", small)).toEqual({ pos: 10, ring: "A" });
    expect(readQuery("?day=4", small)).toEqual({ pos: 4, ring: null });
    expect(readQuery("?ring=Z", small)).toEqual({ pos: 10, ring: null });
    expect(readQuery("", small)).toEqual({ pos: 10, ring: null });
  });
});

describe("links and signals", () => {
  it("chains each shared value, and a link exists from its later ad's day", () => {
    const links = linksOf(group);
    expect(links).toHaveLength(1 + 2 + 3 + 1);
    expect(links.filter((l) => l.kind === "phone" && l.key === "555-0102")).toEqual([
      { kind: "phone", key: "555-0102", from: 13, to: 14, day: 5 },
      { kind: "phone", key: "555-0102", from: 14, to: 15, day: 8 },
    ]);
  });

  it("counts only ads already posted", () => {
    expect(signalRows(group, 3)).toEqual([]);
    const mid = signalRows(group, 4); // ads 11, 12, 13 are up
    expect(mid.map((r) => [r.kind, r.values, r.ads, r.weight])).toEqual([
      ["phone", 1, 2, 2],
      ["wording", 1, 3, 2],
    ]);
  });

  it("matches the backend's count for every group of the real stream on the last day", () => {
    expect(timeline.groups.length).toBeGreaterThan(0);
    for (const g of timeline.groups) {
      const rows = signalRows(g, timeline.days);
      const mine = Object.fromEntries(
        rows.map((r) => [r.kind, { values: r.values, ads: r.ads, weight: r.weight }]),
      );
      expect(mine).toEqual(g.by_kind);
      for (const r of rows) expect(r.weight).toBe(timeline.weights[r.kind]);
    }
  });

  it("gives every ad of the real stream a place on the board, in both layouts", () => {
    for (const narrow of [false, true]) {
      const layout = layoutStream(timeline, narrow);
      for (const g of timeline.groups) {
        for (const ad of g.ads) {
          const p = layout.ads.get(ad.id);
          expect(p).toBeDefined();
          expect(p!.x).toBeGreaterThan(0);
          expect(p!.x).toBeLessThan(layout.width);
          expect(p!.y).toBeGreaterThan(0);
          expect(p!.y).toBeLessThan(layout.height);
        }
      }
      const dots = otherDots(timeline, layout.width, layout.height);
      expect(dots.map((d) => d.length)).toEqual(timeline.other_ads_by_day);
      expect(otherDots(timeline, layout.width, layout.height)).toEqual(dots);
    }
  });
});

describe("the case file", () => {
  const file = caseFile(small, group, 6);

  it("has the shape an investigator hands on, labelled synthetic", () => {
    expect(Object.keys(file)).toEqual([
      "case_file_version",
      "label",
      "source",
      "synthetic",
      "notice",
      "stream",
      "as_of_day",
      "group",
      "detection",
      "method",
      "signals",
      "findings",
      "answer_key_check",
      "ads",
    ]);
    expect(file).toMatchObject({
      case_file_version: 1,
      label: "SYNTHETIC DATA",
      source: "FIXTURE",
      synthetic: true,
      as_of_day: 6,
      group: { id: "A", n_ads: 5, n_ads_as_of_day: 4, n_phones: 2 },
    });
    expect(file.notice).toMatch(/^SYNTHETIC DATA/);
  });

  it("carries the time to detect in day numbers and dates", () => {
    expect(file.detection).toMatchObject({
      first_ad_day: 3,
      first_ad_date: "2026-08-19",
      flagged_day: 6,
      flagged_date: "2026-08-22",
      days_to_detect: 3,
      ads_up_before_flag: 3,
      ad_days_before_flag: 7,
      renters_estimate: 210,
    });
    expect(file.detection.renters_estimate_basis).toMatch(/ESTIMATE, not measured/);
  });

  it("lists every signal with its weight, its count and the ads it links", () => {
    expect(file.signals.map((s) => [s.kind, s.weight, s.shared_values, s.ads_linked])).toEqual([
      ["phone", 2, 2, 5],
      ["wording", 2, 1, 4],
      ["site", 0, 1, 2],
    ]);
    expect(file.signals[0]?.values).toEqual([
      { key: "555-0101", label: "555-0101", ad_ids: [11, 12] },
      { key: "555-0102", label: "555-0102", ad_ids: [13, 14, 15] },
    ]);
    expect(file.ads).toHaveLength(5);
    expect(file.ads[0]).toEqual({
      id: 11,
      day: 3,
      date: "2026-08-19",
      phone: "555-0101",
      area: "Elm Flats",
      rent: 900,
    });
  });

  it("holds only 555 numbers and .example sites on the real stream", () => {
    for (const g of timeline.groups) {
      const made = caseFile(timeline, g, timeline.days);
      expect(made.ads.every((a) => /^555-\d{4}$/.test(a.phone))).toBe(true);
      const sites = made.signals.filter((s) => s.kind === "site").flatMap((s) => s.values);
      expect(sites.every((v) => v.key.endsWith(".example"))).toBe(true);
      expect(KINDS).toEqual(expect.arrayContaining(made.signals.map((s) => s.kind)));
    }
  });

  it("prints as plain text that opens with the label", () => {
    const text = caseFileText(file);
    expect(text.split("\n")[0]).toBe("SYNTHETIC DATA · FIXTURE");
    expect(text).toContain("Flagged: day 6 (2026-08-22), 3 days after the first ad");
    expect(text).toContain("- Same phone number: 2 shared, linking 5 ads (weight 2)");
    expect(text).toContain("ESTIMATE, not measured");
    expect(text).toContain("ADS (5)");
  });
});

describe("the stream view", () => {
  it("keeps the SYNTHETIC DATA and FIXTURE chips on screen and states n beside the median", () => {
    render(<StreamView data={small} />);
    expect(screen.getAllByText("SYNTHETIC DATA").length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("FIXTURE").length).toBeGreaterThanOrEqual(2);
    const strip = screen.getByRole("region", { name: /Measured on the synthetic stream/ });
    expect(within(strip).getByText("1 of 1", { selector: ".sw-tile-hero b" })).toBeInTheDocument();
    expect(within(strip).getByText("3 days")).toBeInTheDocument();
    expect(within(strip).getByText(/n = 1 seeded rings/)).toBeInTheDocument();
    expect(
      within(strip).getByText(
        /flagged = at least 4 of its ads inside reported groups \(any group\)/,
      ),
    ).toBeInTheDocument();
    const lanes = screen.getByRole("region", { name: "Time to detect, per group" });
    expect(lanes.querySelector(".sw-fine")).toHaveTextContent(
      "Single-group rule for seeded rings: median 3 days, n = 1.",
    );
    expect(within(strip).getByText(/0 of 20 honest ads flagged/)).toBeInTheDocument();
  });

  it("moves the board with the slider", () => {
    const { container } = render(<StreamView data={small} />);
    const slider = screen.getByRole("slider", { name: "Day of the stream" });
    expect(container.querySelectorAll(".sw-ad")).toHaveLength(5);
    fireEvent.change(slider, { target: { value: "4" } });
    expect(container.querySelectorAll(".sw-ad")).toHaveLength(3);
    expect(container.querySelector(".sw-group")).toHaveAttribute("data-flagged", "false");
    expect(container.querySelector(".sw-halo")).toBeNull();
    fireEvent.change(slider, { target: { value: "6" } });
    expect(container.querySelectorAll(".sw-ad[data-linked='true']")).toHaveLength(4);
    expect(container.querySelector(".sw-group")).toHaveAttribute("data-flagged", "true");
    expect(container.querySelector(".sw-label")).toHaveTextContent(/Ring A\s*caught in 3 days/);
    fireEvent.change(slider, { target: { value: "0" } });
    expect(container.querySelector(".sw-group")).toBeNull();
    expect(screen.getByText("before the first ad")).toBeInTheDocument();
  });

  it("restarts from the empty board when Play is pressed on the last day", () => {
    render(<StreamView data={small} />);
    fireEvent.click(screen.getByRole("button", { name: "Play 90 days" }));
    expect(screen.getByRole("slider")).toHaveValue("0");
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
  });

  it("opens the evidence panel from the list with the time to detect and the signals", () => {
    render(<StreamView data={small} initialPos={10} />);
    expect(screen.queryByRole("region", { name: "Ring A: evidence" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Ring A.*first ad day 3/ }));
    const panel = screen.getByRole("region", { name: "Ring A: evidence" });
    expect(within(panel).getByText("day 3")).toBeInTheDocument();
    expect(within(panel).getByText("day 6")).toBeInTheDocument();
    expect(within(panel).getByText("3 days")).toBeInTheDocument();
    expect(within(panel).getByText("SYNTHETIC ESTIMATE")).toBeInTheDocument();
    expect(within(panel).getByText(/About 210 renters/)).toBeInTheDocument();
    expect(panel.querySelector(".sw-estimate")).toHaveTextContent(
      "7 ad-days times 30 renters per ad per day, an assumption and not a measurement",
    );
    expect(within(panel).getByText("Same phone number")).toBeInTheDocument();
    expect(panel.querySelector("[data-kind='phone'] .sw-weight")).toHaveTextContent("weight 2");
    expect(within(panel).getByText("context · weight 0")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: /Download case file/ })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Print summary" })).toBeInTheDocument();
    expect(within(panel).getByTestId("case-print")).toHaveTextContent("CASE FILE: Ring A");
  });

  it("shows in the panel exactly the counts the backend computed, for the real stream", () => {
    const g = timeline.groups[1] as StreamGroup;
    render(<EvidencePanel data={timeline} group={g} pos={timeline.days} onClose={() => {}} />);
    for (const [kind, count] of Object.entries(g.by_kind)) {
      const row = document.querySelector(`.sw-signals li[data-kind="${kind}"]`);
      expect(row).not.toBeNull();
      expect(row!.querySelector("p")!.textContent).toMatch(
        new RegExp(`^${count.values} \\S+ shared, linking ${count.ads} of ${g.n_ads} ads$`),
      );
    }
    expect(document.querySelectorAll(".sw-signals > li")).toHaveLength(
      Object.keys(g.by_kind).length,
    );
  });
});
