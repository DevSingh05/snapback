import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BarGauges } from "./BarGauges";
import { ConfidenceChip } from "./ConfidenceChip";
import { EvidenceDrawer, RENDER_NOTE } from "./EvidenceDrawer";
import { EVIDENCE_FIXTURE_A, EVIDENCE_FIXTURE_B } from "./fixture";
import { FilesTree } from "./FilesTree";
import { MatchSpots } from "./MatchSpots";
import {
  SPOT_GAP,
  SPOT_MAX,
  barLabel,
  coverage,
  fitPairs,
  pairTiers,
  pickOutcome,
  pickSpots,
  pointsSentence,
} from "./match";
import { PickCard } from "./PickCard";
import { chipState, failedLine, gauges, placeLine, searchLine } from "./read";
import type { EvidencePhoto } from "./types";

const file = EVIDENCE_FIXTURE_A;
const bars = file.bars;
const photo = (alias: string): EvidencePhoto => file.photos.find((p) => p.alias === alias)!;
const strongBars = { ...bars, stop_at_inliers: 150 };

describe("ConfidenceChip: three states only", () => {
  it("Placed: every bar passed", () => {
    render(<ConfidenceChip photo={photo("P1")} bars={bars} />);
    const chip = screen.getByTestId("confidence-chip");
    expect(chip).toHaveTextContent("Placed");
    expect(chip).toHaveAttribute("data-state", "placed");
    expect(screen.queryByTestId("confidence-why")).toBeNull();
  });

  it("Strong match: every bar passed and at least stop_at_inliers points, read from the bars", () => {
    const many = { ...photo("P1"), inliers: 150 };
    render(<ConfidenceChip photo={many} bars={strongBars} />);
    expect(screen.getByTestId("confidence-chip")).toHaveTextContent("Strong match");
    expect(chipState({ ...many, inliers: 149 }, strongBars)).toBe("placed");
  });

  it("never says Strong match when the evidence file carries no stop_at_inliers bar", () => {
    expect(chipState({ ...photo("P1"), inliers: 9999 }, bars)).toBe("placed");
  });

  it("Could not place: names the bar that was missed, with both numbers from the file", () => {
    render(<ConfidenceChip photo={photo("P4")} bars={bars} />);
    expect(screen.getByTestId("confidence-chip")).toHaveTextContent("Could not place");
    expect(screen.getByTestId("confidence-why")).toHaveTextContent(
      "24 matched points, the bar is 30",
    );
  });

  it("names each kind of missed bar and never calls a photo fake", () => {
    const p = photo("P4");
    expect(failedLine({ ...p, bar_failed: "ratio" }, bars)).toBe(
      "0.18 of its points agreed, the bar is 0.25",
    );
    expect(failedLine({ ...p, bar_failed: "spread" }, bars)).toBe(
      "the points cover 0.03 of the photo, the bar is 0.05",
    );
    expect(failedLine({ ...p, bar_failed: "ambiguity" }, bars)).toMatch(/another building/);
    for (const failed of ["inliers", "ratio", "spread", "ambiguity"] as const)
      expect(failedLine({ ...p, bar_failed: failed }, bars)).not.toMatch(/fake|scam|fraud/i);
  });

  it("prints a calibration row only when given one, always with its n", () => {
    const { rerender } = render(<ConfidenceChip photo={photo("P1")} bars={bars} />);
    expect(screen.queryByTestId("confidence-cal")).toBeNull();
    rerender(
      <ConfidenceChip
        photo={photo("P1")}
        bars={bars}
        calibration={{ k: 30, n: 30, on: "renders" }}
      />,
    );
    expect(screen.getByTestId("confidence-cal")).toHaveTextContent("on renders: 30 of 30 (n=30)");
  });
});

describe("BarGauges", () => {
  it("draws three gauges against the bars in the evidence file", () => {
    render(<BarGauges photo={photo("P3")} bars={bars} thresholdsVersion="fixture-synthetic" />);
    expect(screen.getByTestId("gauge-points-plain")).toHaveTextContent("88 of 30 needed");
    expect(screen.getByTestId("gauge-spread-plain")).toHaveTextContent("0.31 of 0.05 needed");
    expect(screen.getByTestId("gauge-rival-plain")).toHaveTextContent("0.05x, must stay under 3x");
    expect(screen.getByTestId("gauge-points")).toHaveTextContent("Met");
    expect(screen.getByText(/thresholds fixture-synthetic/)).toBeInTheDocument();
  });

  it("follows the bars: a changed bar changes the gauge, nothing is typed in the web", () => {
    const g = gauges(photo("P3"), { ...bars, min_inliers: 100 });
    expect(g[0]).toMatchObject({ bar: 100, pass: false, barText: "bar 100" });
  });

  it("marks a missed bar in words, and holds a photo from another building to the strict bars", () => {
    render(<BarGauges photo={photo("P4")} bars={bars} thresholdsVersion="v" />);
    expect(screen.getByTestId("gauge-points")).toHaveAttribute("data-pass", "false");
    expect(screen.getByTestId("gauge-points")).toHaveTextContent("Short of the bar");
    expect(screen.getByTestId("gauge-points-plain")).toHaveTextContent("24 of 30 needed");
    const strict = gauges(EVIDENCE_FIXTURE_B.photos[0]!, bars);
    expect(strict[0]!.bar).toBe(bars.elsewhere_min_inliers);
    expect(strict[1]!.bar).toBe(bars.elsewhere_min_spread);
  });

  it("leaves out a measure the row does not carry instead of drawing a zero", () => {
    const g = gauges({ ...photo("P1"), spread: null, rival_ratio: undefined }, bars);
    expect(g.map((x) => x.key)).toEqual(["points"]);
  });
});

describe("pickSpots: a few matched spots, spread out", () => {
  const spread = (alias: string) => {
    const pairs = photo(alias).points!.sampled;
    return { pairs, spots: pickSpots(pairs) };
  };

  it("picks 6 to 8 of the drawn pairs for every fixture photo, each one once", () => {
    for (const alias of ["P1", "P2", "P3", "P4"]) {
      const { pairs, spots } = spread(alias);
      expect(spots.length, alias).toBeGreaterThanOrEqual(6);
      expect(spots.length, alias).toBeLessThanOrEqual(SPOT_MAX);
      expect(new Set(spots).size).toBe(spots.length);
      for (const i of spots) expect(pairs[i]).toBeDefined();
    }
  });

  it("keeps every two spots apart in both pictures, so no rings touch", () => {
    for (const alias of ["P1", "P2", "P3", "P4"]) {
      const { pairs, spots } = spread(alias);
      for (const i of spots)
        for (const j of spots) {
          if (i >= j) continue;
          const [ax, ay, bx, by] = pairs[i]!;
          const [cx, cy, dx, dy] = pairs[j]!;
          expect(Math.hypot(ax - cx, (ay - cy) * 0.75), alias).toBeGreaterThanOrEqual(SPOT_GAP);
          expect(Math.hypot(bx - dx, (by - dy) * 0.75), alias).toBeGreaterThanOrEqual(SPOT_GAP);
        }
    }
  });

  it("covers the picture: the spots reach across at least half its width", () => {
    const { pairs, spots } = spread("P1");
    const xs = spots.map((i) => pairs[i]![0]);
    expect(Math.max(...xs) - Math.min(...xs)).toBeGreaterThan(0.5);
  });

  it("numbers them left to right, leaves out the loosest third, and is the same every time", () => {
    const { pairs, spots } = spread("P1");
    const xs = spots.map((i) => pairs[i]![0]);
    expect(xs).toEqual([...xs].sort((a, b) => a - b));
    const tiers = pairTiers(pairs);
    for (const i of spots) expect(tiers[i]).not.toBe("faint");
    expect(pickSpots(pairs)).toEqual(spots);
  });

  it("makes no spot from nothing, and never more than there are pairs", () => {
    expect(pickSpots([])).toEqual([]);
    expect(pickSpots([[0.2, 0.2, 0.2, 0.2]])).toEqual([0]);
    expect(
      pickSpots([
        [0.2, 0.2, 0.2, 0.2],
        [0.21, 0.2, 0.21, 0.2],
      ]),
    ).toHaveLength(1);
  });
});

describe("fitPairs: lining the ad photo up on the scan view", () => {
  it("finds the map the drawn pairs agree on", () => {
    const fit = fitPairs(photo("P1").points!.sampled);
    expect(fit.xx).toBeCloseTo(0.999, 2);
    expect(fit.yy).toBeCloseTo(1.014, 2);
    expect(fit.x0).toBeCloseTo(-0.005, 2);
    expect(fit.y0).toBeCloseTo(-0.008, 2);
  });

  it("recovers an exact stretch and shift", () => {
    const at = [
      [0.1, 0.2],
      [0.8, 0.3],
      [0.4, 0.9],
      [0.6, 0.6],
    ] as const;
    const fit = fitPairs(at.map(([x, y]) => [x, y, 1.1 * x + 0.05, 0.9 * y - 0.02]));
    expect(fit.xx).toBeCloseTo(1.1);
    expect(fit.xy).toBeCloseTo(0);
    expect(fit.x0).toBeCloseTo(0.05);
    expect(fit.yy).toBeCloseTo(0.9);
    expect(fit.y0).toBeCloseTo(-0.02);
  });

  it("falls back to the typical shift with too few pairs or pairs on one line", () => {
    expect(fitPairs([])).toEqual({ xx: 1, xy: 0, x0: 0, yx: 0, yy: 1, y0: 0 });
    const line = fitPairs([
      [0.1, 0.1, 0.2, 0.1],
      [0.2, 0.2, 0.3, 0.2],
      [0.3, 0.3, 0.4, 0.3],
    ]);
    expect(line.xx).toBe(1);
    expect(line.x0).toBeCloseTo(0.1);
    expect(line.y0).toBeCloseTo(0);
  });
});

describe("MatchSpots", () => {
  it("circles a few numbered spots on both pictures, with no lines, and says how many of how many", () => {
    const { container } = render(<MatchSpots photo={photo("P1")} reduced={false} />);
    const spots = screen.getAllByTestId("match-spot");
    expect(spots.length).toBeGreaterThanOrEqual(6);
    expect(spots.length).toBeLessThanOrEqual(SPOT_MAX);
    for (const [k, spot] of spots.entries()) {
      expect(spot.querySelectorAll(".ml-ring")).toHaveLength(2);
      expect([...spot.querySelectorAll("text")].map((t) => t.textContent)).toEqual([
        String(k + 1),
        String(k + 1),
      ]);
    }
    expect(container.querySelectorAll("svg line")).toHaveLength(0);
    expect(screen.getByTestId("match-count")).toHaveTextContent(
      `${spots.length} of 142 matched points shown`,
    );
  });

  it("lights one pair on hover or tap, with the only connector, and lets go again", () => {
    const { container } = render(<MatchSpots photo={photo("P1")} reduced />);
    const spots = screen.getAllByTestId("match-spot");
    fireEvent.mouseEnter(spots[2]!);
    expect(spots[2]).toHaveAttribute("data-on", "true");
    expect(container.querySelectorAll("svg line")).toHaveLength(1);
    expect(screen.getByTestId("match-hint")).toHaveTextContent("Spot 3: the same place");
    fireEvent.mouseLeave(spots[2]!);
    expect(screen.queryByTestId("match-link")).toBeNull();

    const chip = screen.getByRole("button", { name: "Spot 5" });
    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "true");
    expect(spots[4]).toHaveAttribute("data-on", "true");
    expect(screen.getAllByTestId("match-link")).toHaveLength(1);
    fireEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("match-link")).toBeNull();
  });

  it("keeps every matched point behind a small switch, still with no web of lines", () => {
    const { container } = render(<MatchSpots photo={photo("P1")} reduced />);
    expect(screen.queryAllByTestId("match-pair")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Show all 48 points" }));
    const pairs = screen.getAllByTestId("match-pair");
    expect(pairs).toHaveLength(48);
    expect(screen.getByTestId("match-count")).toHaveTextContent("48 of 142 matched points drawn");
    expect(screen.queryByRole("button", { name: "Spot 1" })).toBeNull();
    expect(container.querySelectorAll("svg line")).toHaveLength(0);
    fireEvent.mouseEnter(pairs[7]!);
    expect(container.querySelectorAll("svg line")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /Back to \d spots/ }));
    expect(screen.queryAllByTestId("match-pair")).toHaveLength(0);
    expect(screen.getAllByTestId("match-spot").length).toBeGreaterThanOrEqual(6);
  });

  it("is static under reduced motion: no stagger delays, and it says so", () => {
    render(<MatchSpots photo={photo("P1")} reduced />);
    expect(screen.getByTestId("match-view")).toHaveAttribute("data-motion", "reduced");
    for (const spot of screen.getAllByTestId("match-spot")) {
      expect(spot.getAttribute("style")).toBeNull();
      expect(spot.querySelector(".ml-ring")!.getAttribute("style")).toBeNull();
    }
  });

  it("staggers the circling when motion is allowed", () => {
    render(<MatchSpots photo={photo("P1")} reduced={false} />);
    expect(screen.getAllByTestId("match-spot")[2]!.style.animationDelay).toBe("220ms");
  });

  it("stacks for phones and marks a photo that fell short, in words too", () => {
    render(<MatchSpots photo={photo("P4")} reduced stacked />);
    const fig = screen.getByTestId("match-view");
    expect(fig).toHaveAttribute("data-layout", "stacked");
    expect(fig).toHaveAttribute("data-weak", "true");
    expect(screen.getByTestId("match-count")).toHaveTextContent(/^\d of 24 matched points shown$/);
    expect(screen.getByTestId("match-hint")).toHaveTextContent("too few points");
  });

  it("lays the ad photo over the scan view as far as the slider says, and says what it is", () => {
    const { container } = render(<MatchSpots photo={photo("P1")} reduced />);
    expect(screen.queryByTestId("match-over")).toBeNull();
    const slider = screen.getByRole("slider", { name: "Lay the ad photo over the scan view" });
    fireEvent.change(slider, { target: { value: "60" } });
    const over = screen.getByTestId("match-over");
    expect(Number(over.querySelector("clipPath rect")!.getAttribute("width"))).toBeCloseTo(264);
    expect(over.querySelector("g[transform]")!.getAttribute("transform")).toMatch(/^matrix\(/);
    expect(screen.getByTestId("match-hint")).toHaveTextContent(
      "The ad photo, laid over the scan view and lined up by the matched points.",
    );
    // The numbered spots stay on top as the proof, and still no web of lines.
    expect(screen.getAllByTestId("match-spot").length).toBeGreaterThanOrEqual(6);
    expect(container.querySelectorAll("svg line")).toHaveLength(0);
    fireEvent.change(slider, { target: { value: "0" } });
    expect(screen.queryByTestId("match-over")).toBeNull();
  });

  it("lays the real ad photo over when our server gave it", () => {
    const img = "data:image/png;base64,AA==";
    const { container } = render(
      <MatchSpots photo={photo("P1")} adSrc={img} scanSrc={img} reduced />,
    );
    fireEvent.change(screen.getByRole("slider"), { target: { value: "100" } });
    expect(container.querySelectorAll(".ml-svg image")).toHaveLength(3);
  });

  it("is a small still for the rail: four numbered pins a side, no lines, no controls", () => {
    const { container } = render(<MatchSpots photo={photo("P3")} reduced mini />);
    const spots = screen.getAllByTestId("match-spot");
    expect(spots.length).toBeGreaterThanOrEqual(3);
    expect(spots.length).toBeLessThanOrEqual(4);
    expect(container.querySelectorAll(".ml-pin")).toHaveLength(spots.length * 2);
    expect(container.querySelectorAll("svg line")).toHaveLength(0);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("slider")).toBeNull();
    fireEvent.mouseEnter(spots[0]!);
    expect(container.querySelectorAll("svg line")).toHaveLength(0);
  });
});

describe("The meter: count, bar and one plain sentence", () => {
  it("says a just-short photo is not called this room, with both numbers from the file", () => {
    render(<BarGauges photo={photo("P4")} bars={bars} thresholdsVersion="v" />);
    expect(screen.getByTestId("points-sentence")).toHaveTextContent(
      "24 matching points. We need 30 to be sure, so we don't say it's this room.",
    );
    expect(screen.getByTestId("bar-label")).toHaveTextContent("30 needed to say it's this room");
    expect(screen.getByTestId("gauge-points")).toHaveTextContent("6 short");
    expect(screen.getByTestId("gauge-points")).toHaveAttribute("data-crossed", "false");
  });

  it("says a placed photo is this room, and follows a changed bar", () => {
    expect(pointsSentence(photo("P3"), bars)).toBe(
      "88 matching points. We need 30 to be sure, so we say it's this room.",
    );
    expect(pointsSentence(photo("P3"), { ...bars, min_inliers: 100 })).toMatch(/We need 100/);
    expect(pointsSentence({ ...photo("P3"), bar_failed: "spread" }, bars)).toMatch(
      /past the 30 we need. Another check fell short/,
    );
    const other = EVIDENCE_FIXTURE_B.photos[0]!;
    expect(pointsSentence(other, bars)).toMatch(/We need 50 to be sure it's a different building/);
    expect(barLabel(other, bars)).toBe("50 needed to say it's a different building");
    expect(pointsSentence({ ...photo("P3"), inliers: null }, bars)).toBeNull();
  });

  it("rises with the spots in the drawer, and is final at once under reduced motion", () => {
    render(<EvidenceDrawer file={file} alias="P4" onClose={() => {}} reduced />);
    const meter = screen.getByTestId("gauge-points");
    expect(meter).toHaveAttribute("data-done", "true");
    expect(meter.querySelector(".pm-num")).toHaveTextContent("24");
  });
});

describe("Replay", () => {
  it("offers to circle the spots again, and not under reduced motion", () => {
    const { unmount } = render(
      <EvidenceDrawer file={file} alias="P3" onClose={() => {}} reduced={false} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Spot 2" }));
    expect(screen.getByRole("button", { name: "Spot 2" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Replay" }));
    expect(screen.getAllByTestId("match-spot").length).toBeGreaterThanOrEqual(6);
    expect(screen.getByRole("button", { name: "Spot 2" })).toHaveAttribute("aria-pressed", "false");
    unmount();
    render(<EvidenceDrawer file={file} alias="P3" onClose={() => {}} reduced />);
    expect(screen.queryByRole("button", { name: "Replay" })).toBeNull();
  });
});

describe("Spread and rivals as pictures", () => {
  it("shades the drawn pairs in three teal strengths, a third each", () => {
    const tiers = pairTiers(photo("P1").points!.sampled);
    expect(tiers).toHaveLength(48);
    for (const t of ["strong", "mid", "faint"] as const)
      expect(tiers.filter((x) => x === t)).toHaveLength(16);
    expect(pairTiers([])).toEqual([]);
  });

  it("counts every drawn point into the coverage squares and boxes them", () => {
    const cov = coverage(photo("P1").points!.sampled);
    expect(cov.cells.reduce((a, b) => a + b, 0)).toBe(48);
    expect(cov.box!.w).toBeGreaterThan(0.5);
    expect(coverage([]).box).toBeNull();
  });

  it("draws this home beside the next best building", () => {
    render(<BarGauges photo={photo("P4")} bars={bars} thresholdsVersion="v" />);
    const rival = screen.getByTestId("gauge-rival");
    expect(rival).toHaveTextContent("This home");
    expect(rival).toHaveTextContent("Another building matched 1.8 times as strongly.");
    expect(rival).toHaveTextContent("A match is blocked at 3 times.");
    expect(screen.getByTestId("gauge-spread")).toHaveAttribute("data-pass", "false");
  });
});

describe("PickCard", () => {
  it("shows the options as chips, the picked one marked, why, and the outcome on file", () => {
    render(
      <PickCard
        options={["focus_scan:S2", "wider_index", "deeper_claimed", "stop"]}
        pick="focus_scan:S2"
        by="model"
        why="P3 was not placed by the base search."
        result={pickOutcome(photo("P3"), "focus_scan:S2")}
      />,
    );
    const chips = screen.getAllByTestId("pick-option");
    expect(chips.map((c) => c.textContent)).toEqual([
      "Look closer at scan S2 (picked)",
      "Search more buildings",
      "Search deeper in this home",
      "Stop here",
    ]);
    expect(chips[0]).toHaveAttribute("data-picked", "true");
    expect(screen.getByTestId("rail-stamp")).toHaveTextContent("Picked by the model");
    expect(screen.getByTestId("pick-outcome")).toHaveTextContent("Placed");
  });

  it("never guesses an outcome the evidence file does not carry", () => {
    expect(pickOutcome(photo("P3"), "wider_index")).toBeNull();
    expect(pickOutcome(undefined, "stop")).toBeNull();
    render(<PickCard options={[]} pick="stop" by="policy" />);
    expect(screen.getByTestId("rail-stamp")).toHaveTextContent("Picked by our rules");
    expect(screen.queryByTestId("pick-outcome")).toBeNull();
    expect(screen.getAllByTestId("pick-option")).toHaveLength(1);
  });
});

describe("FilesTree", () => {
  it("badges each file by who wrote it", () => {
    render(
      <FilesTree
        files={[
          { path: "/evidence/photos.json", written_by: "code" },
          { path: "/notes/place.md", written_by: "agent" },
        ]}
      />,
    );
    const rows = screen.getAllByTestId("files-file");
    expect(rows[0]).toHaveTextContent("photos.json");
    expect(rows[0]).toHaveTextContent("written by code");
    expect(rows[1]).toHaveTextContent("place.md");
    expect(rows[1]).toHaveTextContent("written by the agent");
  });

  it("has an empty state", () => {
    render(<FilesTree files={[]} />);
    expect(screen.getByTestId("files-empty")).toBeInTheDocument();
  });
});

describe("EvidenceDrawer", () => {
  it("opens on the asked photo with the render label, the room label caveat and its searches", () => {
    render(<EvidenceDrawer file={file} alias="P3" onClose={() => {}} reduced={false} />);
    expect(screen.getByTestId("render-note")).toHaveTextContent(RENDER_NOTE);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getByTestId("place-line")).toHaveTextContent("Taken here: Bedroom");
    expect(screen.getByText("Matterport's label, can be wrong")).toBeInTheDocument();
    const steps = screen.getByTestId("search-steps");
    const [first, second] = within(steps).getAllByRole("listitem");
    expect(first).toHaveTextContent("First search of this home");
    expect(first).toHaveTextContent("Picked by our rules");
    expect(first).toHaveTextContent("Still not placed 1.3 s");
    expect(second).toHaveTextContent("Look closer at scan S2");
    expect(second).toHaveTextContent("Picked by the model");
    expect(second).toHaveTextContent("Placed 2.1 s");
  });

  it("switches photos by tab, and a photo that fell short is not placed, not fake", () => {
    render(<EvidenceDrawer file={file} alias="P1" onClose={() => {}} reduced />);
    fireEvent.click(screen.getByRole("tab", { name: /P4/ }));
    expect(screen.getByRole("tab", { name: /P4/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("place-line")).toHaveTextContent("Not placed in this scan");
    expect(screen.getByTestId("confidence-chip")).toHaveTextContent("Could not place");
    expect(screen.getByTestId("evidence-drawer")).not.toHaveTextContent(/fake|scam/i);
  });

  it("says a photo was taken in a different building, on the stricter bar", () => {
    render(<EvidenceDrawer file={EVIDENCE_FIXTURE_B} onClose={() => {}} reduced />);
    expect(screen.getByTestId("place-line")).toHaveTextContent("Taken in a different building");
    expect(screen.getByTestId("gauge-points-plain")).toHaveTextContent("64 of 50 needed");
    expect(placeLine(EVIDENCE_FIXTURE_B.photos[0]!)).not.toMatch(/real one|for rent|available/i);
  });

  it("closes on the button and on Escape, and is static under reduced motion", () => {
    const onClose = vi.fn();
    render(<EvidenceDrawer file={file} onClose={onClose} reduced />);
    const drawer = screen.getByTestId("evidence-drawer");
    expect(drawer).toHaveAttribute("data-motion", "reduced");
    expect(within(drawer).getByTestId("match-view")).toHaveAttribute("data-motion", "reduced");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.keyDown(drawer, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("leads with the real images when our server gave them, and can switch to the drawing", () => {
    const img = "data:image/png;base64,AA==";
    const { container } = render(
      <EvidenceDrawer
        file={file}
        alias="P1"
        onClose={() => {}}
        reduced
        images={{ P1: { ad: img, scan: img } }}
      />,
    );
    const real = within(screen.getByTestId("view-toggle")).getByRole("button", { name: "Real" });
    expect(real).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelectorAll(".ml-svg image")).toHaveLength(2);
    expect(screen.getAllByTestId("match-spot").length).toBeGreaterThanOrEqual(6);
    expect(screen.queryByText(/stand-in drawing/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Drawing" }));
    expect(container.querySelectorAll(".ml-svg image")).toHaveLength(0);
    expect(screen.getByTestId("view-note")).toHaveTextContent("Drawn stand-in");
    // A photo with no real image falls back to the drawing, labelled, with Real switched off.
    fireEvent.click(screen.getByRole("tab", { name: /P2/ }));
    expect(screen.getByRole("button", { name: "Real" })).toBeDisabled();
    expect(screen.getByTestId("view-note")).toHaveTextContent(
      "Drawn stand-in: no real image is here for this photo.",
    );
    expect(screen.getAllByText(/stand-in drawing/)).toHaveLength(2);
  });

  it("has an empty state when no photo was measured", () => {
    render(<EvidenceDrawer file={{ ...file, photos: [] }} onClose={() => {}} reduced />);
    expect(screen.getByTestId("evidence-empty")).toBeInTheDocument();
  });

  it("words a skipped search without a time", () => {
    expect(searchLine(photo("P4").searches[1]!, 1)).toBe("2 stopped (picked by rules)");
  });
});
