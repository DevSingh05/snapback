import { readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { matchRoute } from "../App";
import { ADS, CARD_LINES, adText, mood, score, scoreLine, type Call } from "./model";
import { SpotPage } from "./SpotPage";

window.scrollTo = () => undefined;

const REPO = path.resolve(import.meta.dirname, "../../../..");

describe("the composed ads", () => {
  it("are four: two honest, two with patterns, all labelled and clearly fake", () => {
    expect(ADS).toHaveLength(4);
    expect(ADS.filter((a) => a.kind === "honest")).toHaveLength(2);
    expect(ADS.filter((a) => a.kind === "pattern")).toHaveLength(2);
    for (const a of ADS) {
      expect(a.phone).toMatch(/^555-010-01\d\d$/);
      expect(adText(a)).not.toMatch(/https?:\/\/(?![^ ]*\.example)/);
    }
  });

  it("quote the card's reason lines verbatim from the card's own strings", () => {
    const strings = readFileSync(path.join(REPO, "src/snapback/card/strings.py"), "utf8");
    for (const [rule, line] of Object.entries(CARD_LINES)) {
      expect(strings, rule).toContain(`"rule.${rule}"`);
      // long lines are wrapped over two string literals in the Python source
      const flat = strings.replace(/"\s*\n\s*"/g, "");
      expect(flat, rule).toContain(line);
    }
  });

  it("show a reason line for every flagged stretch and none for the honest ads", () => {
    for (const a of ADS) {
      const flagged = a.segs.filter((s) => s.rules);
      if (a.kind === "honest") {
        expect(flagged).toEqual([]);
        expect(a.lines).toEqual([]);
        expect(a.verdict).toBe("fine");
      } else {
        expect(flagged.length).toBeGreaterThan(0);
        expect(a.lines.length).toBeGreaterThan(0);
        expect(a.verdict).toBe("hold");
      }
    }
  });
});

describe("scoring", () => {
  const ans = (s: string): Call[] => [...s].map((c) => (c === "h" ? "hold" : "fine"));
  // order of ADS: honest, pattern, honest, pattern

  it("counts a perfect round as 2 of 2 with no false alarms", () => {
    const s = score(ans("fhfh"));
    expect(s).toMatchObject({ caught: 2, cleared: 2, snapbackCaught: 2, snapbackCleared: 2, n: 4 });
    expect(scoreLine(s)).toBe("You caught 2 of 2; SNAPBACK caught 2 of 2 (n=4 composed ads)");
    expect(mood(s)).toMatch(/Clean sweep/);
  });

  it("counts only held-off pattern ads as caught, and holding off an honest ad is a false alarm", () => {
    const s = score(ans("hhhh"));
    expect(s.caught).toBe(2);
    expect(s.cleared).toBe(0);
    expect(mood(s)).toMatch(/2 honest ads held off too/);
  });

  it("scores zero when every ad is waved through", () => {
    const s = score(ans("ffff"));
    expect(s.caught).toBe(0);
    expect(s.cleared).toBe(2);
    expect(scoreLine(s)).toContain("You caught 0 of 2");
    expect(mood(s)).toMatch(/slipped past/);
  });

  it("scores one pattern caught", () => {
    expect(score(ans("fhff")).caught).toBe(1);
    expect(score(ans("ffff")).snapbackCaught).toBe(2);
  });
});

describe("/spot", () => {
  it("is routed", () => {
    expect(matchRoute("/spot").name).toBe("spot");
    expect(matchRoute("/spot/").name).toBe("spot");
  });

  function play(calls: Array<"fine" | "hold">) {
    render(<SpotPage />);
    fireEvent.click(screen.getByTestId("spot-start"));
    for (const c of calls) fireEvent.click(screen.getByTestId(`spot-${c}`));
  }

  it("shows one ad per screen with big Looks fine and Hold off buttons", () => {
    render(<SpotPage />);
    fireEvent.click(screen.getByTestId("spot-start"));
    expect(screen.getByText("Ad 1 of 4")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText("SYNTHETIC")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Looks fine" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hold off" })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("spot-fine"));
    expect(screen.getByText("Ad 2 of 4")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("does not show the flags while the player is still deciding", () => {
    render(<SpotPage />);
    fireEvent.click(screen.getByTestId("spot-start"));
    fireEvent.click(screen.getByTestId("spot-fine"));
    expect(document.querySelector("mark")).toBeNull();
    expect(screen.queryByText(/Red flag/)).toBeNull();
  });

  it("reveals the score line, every verdict and the card's reason lines", () => {
    play(["fine", "hold", "fine", "fine"]);
    expect(screen.getByTestId("spot-line")).toHaveTextContent(
      "You caught 1 of 2; SNAPBACK caught 2 of 2 (n=4 composed ads)",
    );
    expect(screen.getAllByRole("article")).toHaveLength(4);
    const bad = within(screen.getByTestId("spot-row-spot-4"));
    expect(bad.getByText(CARD_LINES["data.ssn_before_viewing"])).toBeInTheDocument();
    expect(bad.getByText(/This ad shows scam patterns/)).toBeInTheDocument();
    expect(bad.getByText("You: Looks fine. Different call.")).toBeInTheDocument();
    const good = within(screen.getByTestId("spot-row-spot-3"));
    expect(good.getByText(/both come after the tour/)).toBeInTheDocument();
    expect(good.getByText("You: Looks fine. Match.")).toBeInTheDocument();
    expect(document.querySelectorAll("mark")).toHaveLength(4);
    expect(screen.getByTestId("spot-honest")).toHaveTextContent("n=4, SYNTHETIC ads, FIXTURE");
  });

  it("never calls anyone a scammer", () => {
    play(["hold", "hold", "hold", "hold"]);
    expect(document.body.textContent ?? "").not.toMatch(/scammer/i);
  });

  it("plays again from the first ad", () => {
    play(["fine", "fine", "fine", "fine"]);
    fireEvent.click(screen.getByTestId("spot-again"));
    expect(screen.getByText("Ad 1 of 4")).toBeInTheDocument();
  });
});
