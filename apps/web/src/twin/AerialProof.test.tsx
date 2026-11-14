import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AerialProof, type AerialSide } from "./AerialProof";
import { FIXTURE_CLAIMED, FIXTURE_MATCHED } from "./proofFixtures";

const live = (s: AerialSide): AerialSide => ({
  ...s,
  tile: s.tile && { ...s.tile, source: "live" },
  imageUrl: "blob:http://localhost/x",
});

describe("AerialProof mismatch", () => {
  it("shows two tiles side by side with the locked words and the distance under them", () => {
    render(<AerialProof mismatch claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />);
    expect(screen.getByText("The listing says here.")).toBeInTheDocument();
    expect(screen.getByText("This photo was taken here.")).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByTestId("aerial-distance")).toHaveTextContent("0.4 miles away");
  });

  it("leaves the distance out when a record has no lat/lon", () => {
    render(
      <AerialProof
        mismatch
        claimed={{ ...FIXTURE_CLAIMED, record: { ...FIXTURE_CLAIMED.record!, lat: null } }}
        matched={FIXTURE_MATCHED}
      />,
    );
    expect(screen.queryByTestId("aerial-distance")).toBeNull();
  });
});

describe("AerialProof match", () => {
  it("shows one oblique of the matched building and no fact text", () => {
    render(<AerialProof mismatch={false} claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />);
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.queryByText(/listing says/i)).toBeNull();
    expect(screen.queryByText(/taken here/i)).toBeNull();
    expect(screen.queryByTestId("aerial-distance")).toBeNull();
  });
});

describe("AerialProof missing tile", () => {
  it("shows No aerial image for this building yet, not an img, when a tile is missing", () => {
    render(
      <AerialProof mismatch claimed={{ tile: null, record: null }} matched={FIXTURE_MATCHED} />,
    );
    expect(screen.getByText("No aerial image for this building yet")).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.queryByTestId("aerial-distance")).toBeNull();
  });

  it("treats a live tile with no image url as unavailable", () => {
    render(
      <AerialProof
        mismatch={false}
        claimed={FIXTURE_CLAIMED}
        matched={{ ...live(FIXTURE_MATCHED), imageUrl: undefined }}
      />,
    );
    expect(screen.getByText("No aerial image for this building yet")).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("swaps a broken image for No aerial image for this building yet", () => {
    render(
      <AerialProof mismatch={false} claimed={FIXTURE_CLAIMED} matched={live(FIXTURE_MATCHED)} />,
    );
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByText("No aerial image for this building yet")).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("AerialProof source chip", () => {
  it("shows FIXTURE for fixture tiles and never LIVE", () => {
    render(<AerialProof mismatch claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />);
    const chip = screen.getByTestId("source-chip");
    expect(chip).toHaveTextContent("FIXTURE");
    expect(screen.queryByText(/^LIVE/)).toBeNull();
  });

  it("shows FIXTURE when only one of two tiles is live", () => {
    render(<AerialProof mismatch claimed={FIXTURE_CLAIMED} matched={live(FIXTURE_MATCHED)} />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });

  it("shows FIXTURE when the tiles are live but the records are fixture", () => {
    const tilesOnly = (s: AerialSide): AerialSide => ({ ...live(s), record: s.record });
    render(
      <AerialProof
        mismatch
        claimed={tilesOnly(FIXTURE_CLAIMED)}
        matched={tilesOnly(FIXTURE_MATCHED)}
      />,
    );
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });

  it("draws the two fixture buildings differently", () => {
    render(<AerialProof mismatch claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />);
    const [a, b] = screen.getAllByRole("img").map((i) => i.getAttribute("src"));
    expect(a).not.toEqual(b);
  });

  it("shows LIVE only when every shown tile and record is live", () => {
    const all = (s: AerialSide): AerialSide => ({
      ...live(s),
      record: s.record && { ...s.record, source: "live" },
    });
    render(<AerialProof mismatch claimed={all(FIXTURE_CLAIMED)} matched={all(FIXTURE_MATCHED)} />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("LIVE");
  });
});

describe("AerialProof privacy", () => {
  it("renders no street address from the fixtures", () => {
    const { container } = render(
      <AerialProof mismatch claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />,
    );
    const attrs = Array.from(container.querySelectorAll("[alt],[title],[src]")).map(
      (e) =>
        `${e.getAttribute("alt") ?? ""} ${e.getAttribute("title") ?? ""} ${decodeURIComponent(e.getAttribute("src") ?? "")}`,
    );
    const text = [container.textContent, ...attrs].join(" ");
    expect(text).not.toMatch(/\d+\s+\w+\s+(st|street|ave|avenue|rd|road|blvd|dr|drive|ln|lane)\b/i);
    expect(text).not.toMatch(/safe|danger|crime|score|neighbou?rhood/i);
  });
});

describe("AerialProof capture date and banner", () => {
  it("names the capture date and Vexcel under a live tile", () => {
    const side = live({
      ...FIXTURE_MATCHED,
      tile: { ...FIXTURE_MATCHED.tile!, captured_on: "2025-03-14" },
    });
    render(<AerialProof mismatch={false} claimed={side} matched={side} />);
    expect(screen.getByText("Aerial photo captured Mar 14, 2025 (Vexcel)")).toBeInTheDocument();
  });

  it("labels a fixture tile's date as a fixture, never as Vexcel", () => {
    render(<AerialProof mismatch={false} claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />);
    const line = screen.getByText(/Aerial photo captured Jun 1, 2025/);
    expect(line).toHaveTextContent("(fixture tile)");
    expect(line).not.toHaveTextContent("Vexcel");
  });

  it("says nothing about a date when the tile has none", () => {
    const side = { ...FIXTURE_MATCHED, tile: { ...FIXTURE_MATCHED.tile!, captured_on: null } };
    render(<AerialProof mismatch={false} claimed={side} matched={side} />);
    expect(screen.queryByText(/captured/)).toBeNull();
  });
});
