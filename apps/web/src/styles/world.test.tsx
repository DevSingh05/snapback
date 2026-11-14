import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { KitArt } from "../components/KitArt";
import type { Card } from "../contracts";
import { CardView } from "../pages/CardPage";

const SRC = join(__dirname, "..");
const strip = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");

// The screens brought into the shared look. State there is teal, ink and slate.
const SHEETS = [
  "styles/world.css",
  "search/search.css",
  "tourprep/tourprep.css",
  "replay/replay.css",
];

describe("one world pass", () => {
  it("uses no red, amber or warn token on the screens it covers", () => {
    for (const file of SHEETS) {
      const css = strip(readFileSync(join(SRC, file), "utf8"));
      expect(
        css.match(/var\(--(coral|amber|warn|scan|v-dont-pay|v-hold|st-mismatch|st-warn)\b/g),
        file,
      ).toBeNull();
    }
  });

  it("keeps its own motion behind prefers-reduced-motion: no-preference", () => {
    for (const file of SHEETS.filter((f) => f !== "search/search.css")) {
      const css = strip(readFileSync(join(SRC, file), "utf8"));
      const [outside] = css.split(/@media \(prefers-reduced-motion: no-preference\)/);
      expect(outside, file).not.toMatch(/\banimation(-name)?:/);
    }
  });

  it("draws the pinned photo beside the place check and labels it a stand-in", () => {
    const { container } = render(<CardView card={cardHold as Card} variant="result" />);
    const place = container.querySelector(".group-place .cell-kind")!;
    expect(place.querySelector("svg.kit-art-scan .ka-pin")).not.toBeNull();
    expect(place).toHaveTextContent("Drawn stand-in");
    expect(screen.getAllByTestId("row-label").map((el) => el.textContent)).toEqual([
      "PLACE",
      "PERSON",
      "PRICE",
    ]);
  });

  it("draws every kit picture as decoration only", () => {
    for (const kind of [
      "pinned",
      "scan",
      "person",
      "price",
      "claims",
      "apartment",
      "prep",
    ] as const) {
      const { container, unmount } = render(<KitArt kind={kind} />);
      const svg = container.querySelector("svg")!;
      expect(svg, kind).toHaveAttribute("aria-hidden", "true");
      expect(svg.textContent, kind).toBe("");
      expect(container.innerHTML, kind).not.toMatch(/href|url\(|<image|<use/);
      unmount();
    }
  });
});
