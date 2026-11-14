import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { STATE_WORD } from "../cardStrings";
import { HouseGlyph } from "../components/HouseGlyph";
import type { Card, VerdictState } from "../contracts";
import { CardView } from "../pages/CardPage";
import { PlacesStrip } from "../search/PlacesStrip";

const card = cardHold as Card;
const SRC = join(__dirname, "..");

// The motion this pass adds. Each may run only inside prefers-reduced-motion: no-preference.
const ZING = [
  "sky-sweep",
  "band-in",
  "house-down",
  "land",
  "stamp",
  "underline-in",
  "strip-in",
  "row-in",
  "scan-pass",
  "scan-pass-again",
  "draft-in",
];

// Every `animation:` declaration with the at-rules it sits inside.
function animations(css: string): Array<{ value: string; inside: string[] }> {
  const found: Array<{ value: string; inside: string[] }> = [];
  const stack: string[] = [];
  let head = "";
  for (const ch of css.replace(/\/\*[\s\S]*?\*\//g, "")) {
    if (ch === "{") {
      stack.push(head.trim());
      head = "";
    } else if (ch === "}") {
      stack.pop();
      head = "";
    } else if (ch === ";") {
      const m = /^\s*animation:\s*(.+)$/s.exec(head);
      if (m) found.push({ value: m[1]!, inside: [...stack] });
      head = "";
    } else head += ch;
  }
  return found;
}

describe("zing pass", () => {
  it("gives each verdict its own band and keeps the locked headline", () => {
    // Design v4 ticket 3: the band is matte and the verdict colour is the bar beside the headline.
    const band: Record<VerdictState, string> = {
      dont_pay: "dont-pay",
      hold: "hold",
      verified: "ok",
      unverified: "slate",
    };
    for (const state of Object.keys(band) as VerdictState[]) {
      const { unmount } = render(<CardView card={{ ...card, state }} variant="result" />);
      expect(screen.getByTestId("case-band")).toHaveAttribute("data-verdict", band[state]);
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(STATE_WORD[state]);
      unmount();
    }
  });

  it("colours each state square by the word it shows, so one word always looks one way", () => {
    const { container } = render(<CardView card={card} variant="result" />);
    const kinds = new Map<string, Set<string>>();
    for (const chip of container.querySelectorAll<HTMLElement>(".case-row .ui-state")) {
      const word = chip.textContent!;
      kinds.set(word, (kinds.get(word) ?? new Set()).add(chip.dataset.state!));
    }
    expect(kinds.size).toBeGreaterThan(1);
    for (const [word, set] of kinds) expect([...set], word).toHaveLength(1);
    expect(new Set([...kinds.values()].map((v) => [...v][0])).size).toBe(kinds.size);
    expect([...kinds.get("Warning")!]).toEqual(["warn"]);
  });

  it("numbers the evidence lines in order so they land one after another", () => {
    const { container } = render(<CardView card={card} variant="result" />);
    const order = Array.from(container.querySelectorAll<HTMLElement>(".case-ledger tbody tr")).map(
      (tr) => tr.style.getPropertyValue("--i"),
    );
    expect(order.length).toBeGreaterThan(1);
    expect(order).toEqual(order.map((_, i) => String(i)));
  });

  it("draws the house as decoration only: hidden from readers, no text, no outside file", () => {
    const { container } = render(<HouseGlyph />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.textContent).toBe("");
    expect(container.innerHTML).not.toMatch(/href|url\(|<image|<use/);
    expect(svg).toHaveClass("house-lit");
    expect(render(<HouseGlyph lit={false} />).container.querySelector(".house-lit")).toBeNull();
  });

  it("keys each researched place by how it sits against the budget", async () => {
    render(<PlacesStrip caseId={null} brief={{ max_rent_month: 2000 }} />);
    await waitFor(() => expect(screen.getAllByTestId("place-row").length).toBe(2));
    expect(screen.getAllByTestId("place-row").map((r) => r.dataset.fit)).toEqual([
      "within",
      "starts_within",
    ]);
  });

  it("runs its motion only when the reader has not asked for less", () => {
    for (const file of ["styles/app.css", "upload/upload.css", "search/search.css"]) {
      const mine = animations(readFileSync(join(SRC, file), "utf8")).filter((a) =>
        ZING.some((name) => new RegExp(`(^|\\s)${name}(\\s|$)`).test(a.value)),
      );
      expect(mine.length, file).toBeGreaterThan(0);
      for (const a of mine)
        expect(
          a.inside.some((rule) => /prefers-reduced-motion:\s*no-preference/.test(rule)),
          `${file}: ${a.value}`,
        ).toBe(true);
    }
  });
});
