import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BarGauges } from "./BarGauges";
import { ConfidenceChip } from "./ConfidenceChip";
import { EvidenceDrawer, RENDER_NOTE } from "./EvidenceDrawer";
import { EVIDENCE_FIXTURE_A, EVIDENCE_FIXTURE_B } from "./fixture";
import { FilesTree } from "./FilesTree";
import { MatchLines } from "./MatchLines";
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

describe("MatchLines", () => {
  it("draws the sampled pairs and says how many of how many", () => {
    render(<MatchLines photo={photo("P1")} reduced={false} />);
    expect(screen.getAllByTestId("match-pair")).toHaveLength(48);
    expect(screen.getByTestId("match-count")).toHaveTextContent("48 of 142 matched points drawn");
  });

  it("is static under reduced motion: no stagger delays, and it says so", () => {
    render(<MatchLines photo={photo("P1")} reduced />);
    const fig = screen.getByTestId("match-lines");
    expect(fig).toHaveAttribute("data-motion", "reduced");
    for (const pair of screen.getAllByTestId("match-pair")) {
      expect(pair.getAttribute("style")).toBeNull();
      expect(pair.querySelector("line")!.getAttribute("style")).toBeNull();
    }
  });

  it("staggers the draw-in when motion is allowed", () => {
    render(<MatchLines photo={photo("P1")} reduced={false} />);
    expect(screen.getAllByTestId("match-pair")[2]!.style.animationDelay).toBe("36ms");
  });

  it("stacks for phones and marks a photo that fell short", () => {
    render(<MatchLines photo={photo("P4")} reduced stacked />);
    const fig = screen.getByTestId("match-lines");
    expect(fig).toHaveAttribute("data-layout", "stacked");
    expect(fig).toHaveAttribute("data-weak", "true");
    expect(screen.getByTestId("match-count")).toHaveTextContent("24 of 24 matched points drawn");
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
    expect(steps).toHaveTextContent("1 base search (picked by rules, 1.3 s)");
    expect(steps).toHaveTextContent("2 scan S2 on its own (picked by model, 2.1 s)");
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
    expect(within(drawer).getByTestId("match-lines")).toHaveAttribute("data-motion", "reduced");
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
    expect(container.querySelectorAll("svg image")).toHaveLength(2);
    expect(screen.getAllByTestId("match-pair")).toHaveLength(48);
    expect(screen.queryByText(/stand-in drawing/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Drawing" }));
    expect(container.querySelectorAll("svg image")).toHaveLength(0);
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
