import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import tile from "../../../../fixtures/contracts/aerial_tile.json";
import record from "../../../../fixtures/contracts/property_record.json";
import type { AerialTileInfo, PropertyFacts } from "../contracts";
import { AerialTile, aerialFact } from "./AerialTile";

const fixtureTile = tile as AerialTileInfo;
const fixtureRecord = record as PropertyFacts;

describe("AerialTile", () => {
  it("renders the neutral fact: record floors and year built next to the capture date", () => {
    render(<AerialTile tile={fixtureTile} record={fixtureRecord} />);
    const fact = screen.getByTestId("aerial-fact");
    expect(fact).toHaveTextContent("4 floors");
    expect(fact).toHaveTextContent("built 2015");
    expect(fact).toHaveTextContent("2025-06-01");
  });

  it("falls back to the synthetic placeholder in fixture mode and shows a FIXTURE chip", () => {
    render(<AerialTile tile={fixtureTile} record={fixtureRecord} />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    const img = screen.getByRole("img", { name: /north-facing aerial view/i });
    expect(img.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
  });

  it("uses the runtime image url and a LIVE chip for a live tile", () => {
    render(
      <AerialTile
        tile={{ ...fixtureTile, source: "live" }}
        record={fixtureRecord}
        imageUrl="blob:http://localhost/abc"
      />,
    );
    expect(screen.getByTestId("source-chip")).toHaveTextContent("LIVE");
    expect(screen.getByRole("img").getAttribute("src")).toBe("blob:http://localhost/abc");
  });

  it("says what is missing instead of inventing facts", () => {
    const text = aerialFact(
      { ...fixtureRecord, floors: null, year_built: null },
      { ...fixtureTile, captured_on: null },
    );
    expect(text).toMatch(/floors not on record/);
    expect(text).toMatch(/year built not on record/);
    expect(text).toMatch(/capture date unknown/);
  });

  it("never uses safety, crime or neighbourhood-score words", () => {
    const { container } = render(<AerialTile tile={fixtureTile} record={fixtureRecord} />);
    const attrs = Array.from(container.querySelectorAll("[alt],[title]")).map(
      (e) => `${e.getAttribute("alt") ?? ""} ${e.getAttribute("title") ?? ""}`,
    );
    const text = [container.textContent, ...attrs].join(" ");
    expect(text).not.toMatch(/safe|danger|crime|score|rating|risk|neighbou?rhood/i);
  });
});
