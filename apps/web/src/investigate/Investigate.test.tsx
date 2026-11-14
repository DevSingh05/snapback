import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { matchRoute } from "../App";
import { InvestigateView, RingGraph, TimelineStrip, percent } from "./InvestigatePage";
import { layoutGraph, timeScale } from "./layout";
import type { Answer, RingResponse, RingsResponse } from "./types";

const score = {
  ad_precision: 1,
  ad_recall: 1,
  ring_precision: 1,
  ring_recall: 1,
  rings_found: 2,
  rings_recovered: 2,
};

const rings: RingsResponse = {
  label: "SYNTHETIC DATA",
  synthetic: true,
  source: "FIXTURE",
  n_ads: 301,
  rings: [
    {
      id: "A",
      label: "Ring A",
      n_ads: 3,
      n_phones: 2,
      first_seen: "2026-02-04",
      last_seen: "2026-03-01",
      score: 0.6,
      finding_kinds: [],
    },
    {
      id: "B",
      label: "Ring B",
      n_ads: 2,
      n_phones: 2,
      first_seen: "2026-03-12",
      last_seen: "2026-04-01",
      score: 0.5,
      finding_kinds: [],
    },
  ],
  metrics: {
    n_ads: 301,
    n_true_rings: 4,
    pipeline: score,
    keyword_baseline: { ...score, ring_recall: 0, ad_recall: 0.19, rings_recovered: 0 },
  },
  example_questions: ["When did ring A start?"],
};

const ring: RingResponse = {
  label: "SYNTHETIC DATA",
  synthetic: true,
  source: "FIXTURE",
  ring: {
    id: "A",
    label: "Ring A",
    ad_ids: [4, 9, 12],
    phones: ["555-1111", "555-2222"],
    photo_sets: ["photo-aaaa"],
    first_seen: "2026-02-04",
    last_seen: "2026-03-01",
    score: 0.6,
    sources: [2],
    findings: [
      {
        id: "phone_rotation",
        kind: "phone_rotation",
        title: "Contact numbers rotate",
        summary: "2 different numbers across 3 ads.",
        score: 0.33,
        evidence: [
          {
            ad_id: 4,
            span: null,
            note: null,
            photo_ids: [],
            phone: "555-1111",
            rule_id: null,
            score: null,
          },
          {
            ad_id: 9,
            span: "Pay the booking fee ahead of the key handover.",
            note: null,
            photo_ids: ["ph-0123456789abcdef"],
            phone: null,
            rule_id: null,
            score: 0.91,
          },
        ],
      },
    ],
    timeline: [
      { date: "2026-02-04", ad_id: 4, kind: "first_ad", detail: "first ad, number 555-1111" },
      { date: "2026-02-20", ad_id: 9, kind: "new_phone", detail: "new number 555-2222" },
    ],
    weekly: [
      ["2026-02-02", 1],
      ["2026-02-16", 1],
      ["2026-02-23", 1],
    ],
  },
  graph: {
    nodes: [
      { id: "ad-4", type: "ad", label: "4", date: "2026-02-04" },
      { id: "ad-9", type: "ad", label: "9", date: "2026-02-20" },
      { id: "ad-12", type: "ad", label: "12", date: "2026-03-01" },
      { id: "phone-555-1111", type: "phone", label: "555-1111" },
      { id: "photo-aaaa", type: "photo", label: "photos" },
    ],
    edges: [
      { source: "ad-4", target: "phone-555-1111" },
      { source: "ad-9", target: "phone-555-1111" },
      { source: "ad-9", target: "photo-aaaa" },
      { source: "ad-12", target: "photo-aaaa" },
    ],
  },
  ads: [
    {
      id: 4,
      posted_at: "2026-02-04",
      phone: "555-1111",
      hood: "Alder Flats",
      rent: 900,
      text: "Sunny.",
      photos: ["ph-0123456789abcdef"],
    },
    {
      id: 9,
      posted_at: "2026-02-20",
      phone: "555-2222",
      hood: "Millrace",
      rent: 950,
      text: "Pay the booking fee ahead of the key handover.",
      photos: ["ph-0123456789abcdef"],
    },
    {
      id: 12,
      posted_at: "2026-03-01",
      phone: "555-2222",
      hood: "Oakbend",
      rent: 990,
      text: "Cozy.",
      photos: [],
    },
  ],
};

const noAnswer: Answer = {
  question: "q",
  answer: "I have no evidence in the graph for that.",
  grounded: false,
  intent: "unknown",
  evidence: [],
  mode: "fixture",
  synthetic: true,
};

function view(ask = vi.fn().mockResolvedValue(noAnswer), selected: number | null = null) {
  const onRing = vi.fn();
  const onPick = vi.fn();
  render(
    <InvestigateView
      rings={rings}
      ring={ring}
      ringId="A"
      onRing={onRing}
      selected={selected}
      onPick={onPick}
      ask={ask}
    />,
  );
  return { onRing, onPick, ask };
}

describe("/investigate", () => {
  it("is routed", () => {
    expect(matchRoute("/investigate")).toEqual({ name: "investigate" });
    expect(matchRoute("/investigate/")).toEqual({ name: "investigate" });
  });

  it("says SYNTHETIC DATA and FIXTURE on the page", () => {
    view();
    expect(screen.getAllByText("SYNTHETIC DATA").length).toBeGreaterThan(0);
    expect(screen.getByText("FIXTURE")).toBeInTheDocument();
  });

  it("shows the measured numbers for both methods with n", () => {
    view();
    const measure = screen.getByLabelText("Measured result");
    expect(within(measure).getByText(/301 synthetic ads with 4 seeded rings/)).toBeInTheDocument();
    expect(within(measure).getByText("This pipeline")).toBeInTheDocument();
    expect(within(measure).getByText(/Keyword search/)).toBeInTheDocument();
    expect(percent(0.193)).toBe("19%");
  });

  it("switches rings from the tabs", () => {
    const { onRing } = view();
    fireEvent.click(screen.getByRole("button", { name: /Ring B/ }));
    expect(onRing).toHaveBeenCalledWith("B");
  });

  it("every finding has a show-the-evidence expander that lists the cited ads", () => {
    const { onPick } = view();
    const findings = screen.getByLabelText("Findings");
    const summary = within(findings).getByText(/Show the evidence \(2\)/);
    fireEvent.click(summary);
    expect(
      within(findings).getByText("Pay the booking fee ahead of the key handover."),
    ).toBeInTheDocument();
    fireEvent.click(within(findings).getByRole("button", { name: "ad 9" }));
    expect(onPick).toHaveBeenCalledWith(9);
  });

  it("an ad in the graph can be selected by click and key", () => {
    const { onPick } = view();
    fireEvent.click(screen.getByRole("button", { name: /ad 4,/ }));
    expect(onPick).toHaveBeenCalledWith(4);
    fireEvent.keyDown(screen.getByRole("button", { name: /ad 12,/ }), { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(12);
  });

  it("shows the chosen ad and says honest source ads are not members", () => {
    view(undefined, 9);
    expect(screen.getByRole("heading", { name: /Ad 9/ })).toBeInTheDocument();
    expect(screen.getByText(/first posted in honest ads 2/)).toBeInTheDocument();
  });

  it("an answer with no evidence says so and shows no evidence list", async () => {
    const ask = vi.fn().mockResolvedValue(noAnswer);
    view(ask);
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "Who owns it?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(screen.getByText(noAnswer.answer)).toBeInTheDocument());
    expect(screen.getByText(/Nothing in the graph backs an answer/)).toBeInTheDocument();
    expect(ask).toHaveBeenCalledWith("Who owns it?");
  });

  it("a grounded answer lists its evidence", async () => {
    const grounded: Answer = {
      ...noAnswer,
      answer: "Ring A started on 2026-02-04, with ad 4.",
      grounded: true,
      evidence: [
        {
          ad_id: 4,
          span: null,
          note: null,
          photo_ids: [],
          phone: "555-1111",
          rule_id: null,
          score: null,
        },
      ],
    };
    view(vi.fn().mockResolvedValue(grounded));
    fireEvent.click(screen.getByRole("button", { name: "When did ring A start?" }));
    await waitFor(() => expect(screen.getByText(grounded.answer)).toBeInTheDocument());
    expect(screen.getAllByText("555-1111").length).toBeGreaterThan(0);
  });
});

describe("graph and timeline", () => {
  it("lays ads on a circle in posting order and shared nodes inside it", () => {
    const placed = layoutGraph(ring.graph.nodes, ring.graph.edges, 560);
    const first = placed.get("ad-4")!;
    expect(first.y).toBeLessThan(280);
    const phone = placed.get("phone-555-1111")!;
    const dist = (p: { x: number; y: number }) => Math.hypot(p.x - 280, p.y - 280);
    expect(dist(phone)).toBeLessThan(dist(first));
    expect(layoutGraph(ring.graph.nodes, ring.graph.edges, 560)).toEqual(placed);
  });

  it("scales dates into 0..1", () => {
    const at = timeScale("2026-02-04", "2026-03-01");
    expect(at("2026-02-04")).toBeGreaterThan(0);
    expect(at("2026-03-01")).toBeLessThan(1);
    expect(at("2026-02-10")).toBeLessThan(at("2026-02-20"));
  });

  it("draws one mark per ad and per shared node, with an accessible name", () => {
    render(<RingGraph data={ring} selected={9} onPick={() => {}} />);
    expect(screen.getByRole("img", { name: /Ring A: 3 ads/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("the timeline marks a new number and lets an ad be picked", () => {
    const onPick = vi.fn();
    const { container } = render(<TimelineStrip data={ring} selected={null} onPick={onPick} />);
    expect(container.querySelectorAll(".inv-phone-mark").length).toBe(2);
    fireEvent.click(container.querySelectorAll(".inv-tick")[1]!);
    expect(onPick).toHaveBeenCalledWith(9);
  });
});
