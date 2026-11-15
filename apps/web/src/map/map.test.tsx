import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { matchRoute } from "../App";
import { AS_OF } from "../contracts";
import type { CityMap } from "./CityMap";
import MapPage from "./MapPage";
import { monthsOld } from "./PlaceSheet";
import { SAMPLE_AS_OF, fixturePlacesMap, fixtureSheet } from "./fixture";
import { columnHeight, columns, hexagon, metresBetween, nearestPlace } from "./geometry";
import { BANNED } from "./strings";
import { EMPTY_CRITERIA, toBrief } from "./types";

// The map canvas needs WebGL, so the page is tested with a stand-in map; the list is the same
// one keyboards and screen readers use.
const NoMap: typeof CityMap = () => <div data-testid="map-stand-in" />;

describe("the map route", () => {
  it("matches /map and leaves the home route alone", () => {
    expect(matchRoute("/map")).toEqual({ name: "map" });
    expect(matchRoute("/map/")).toEqual({ name: "map" });
    expect(matchRoute("/")).toEqual({ name: "landing" });
    expect(matchRoute("/home")).toEqual({ name: "home" });
  });
});

describe("the fixture city", () => {
  const feed = fixturePlacesMap(EMPTY_CRITERIA);

  it("follows the M1 contract and carries no address, office or name", () => {
    expect(feed.source).toBe("fixture");
    expect(feed.n_places).toBe(feed.features.length);
    for (const f of feed.features) {
      expect(Object.keys(f.properties).sort()).toEqual(
        [
          "as_of",
          "fits_brief",
          "has_scan",
          "kind",
          "n_plans",
          "pid",
          "rent_from",
          "source",
          "units_reported",
        ].sort(),
      );
      expect(f.properties.pid).toMatch(/^fx-map-\d+$/);
      expect(f.properties.as_of).toBe(SAMPLE_AS_OF);
    }
  });

  it("is the same on every run", () => {
    expect(fixturePlacesMap(EMPTY_CRITERIA)).toEqual(feed);
  });

  it("narrows the fit with the brief, and counts it", () => {
    const tight = fixturePlacesMap({ ...EMPTY_CRITERIA, max_rent: 1200, scan_only: true });
    expect(tight.n_fit).toBeLessThan(feed.n_fit);
    expect(tight.n_fit).toBe(tight.features.filter((f) => f.properties.fits_brief).length);
    for (const f of tight.features.filter((x) => x.properties.fits_brief)) {
      expect(f.properties.has_scan).toBe(true);
      expect(f.properties.rent_from).toBeLessThanOrEqual(1200);
    }
  });

  it("gives the sheet the same price the pin shows", () => {
    for (const f of feed.features) {
      const sheet = fixtureSheet(f.properties.pid)!;
      const lowest = Math.min(...sheet.plans.map((p) => p.rent_min ?? Infinity));
      expect(lowest).toBe(f.properties.rent_from);
      expect(sheet.plans.length).toBe(f.properties.n_plans);
      expect(sheet.has_3d_scan).toBe(f.properties.has_scan);
      for (const p of sheet.plans) {
        expect(p.price_text).toContain("(sample figure)");
        expect(p.price_text).not.toContain("CoStar");
      }
    }
  });

  it("sends CoStar's fields as the brief", () => {
    expect(toBrief({ ...EMPTY_CRITERIA, max_rent: 1800, beds_min: 1, no_walkup: true })).toEqual({
      max_rent_month: 1800,
      beds_min: 1,
      needs_no_walkup: true,
      needs_parking: false,
      pets: false,
    });
  });
});

describe("map geometry", () => {
  const feed = fixturePlacesMap(EMPTY_CRITERIA);

  it("draws a closed six-sided footprint of the asked radius", () => {
    const ring = hexagon([-95.37, 29.76], 20);
    expect(ring).toHaveLength(7);
    expect(ring[0]).toEqual(ring[6]);
    for (const pt of ring.slice(0, 6)) {
      expect(metresBetween([-95.37, 29.76], pt)).toBeCloseTo(20, 0);
    }
  });

  it("makes columns taller for more floor plans, with a cap above", () => {
    expect(columnHeight(5, 1)).toBeGreaterThan(columnHeight(1, 1));
    const cols = columns(feed.features, 15, 1, new Set([feed.features[0]!.properties.pid]));
    expect(cols.features).toHaveLength(feed.features.length);
    expect(cols.features[0]!.properties.passed).toBe(true);
    for (const c of cols.features) expect(c.properties.cap).toBeGreaterThan(c.properties.h);
  });

  it("gives a clicked building to the nearest place within 40 m, or to none", () => {
    const f = feed.features[3]!;
    const [lon, lat] = f.geometry.coordinates;
    expect(nearestPlace(feed.features, [lon + 0.0002, lat])?.properties.pid).toBe(f.properties.pid);
    expect(nearestPlace(feed.features, [lon + 0.2, lat + 0.2])).toBeNull();
  });
});

describe("the map page", () => {
  it("shows the count, the source chip, the as-of line and the attribution", async () => {
    render(<MapPage MapView={NoMap} />);
    const count = await screen.findByTestId("count");
    expect(count).toHaveTextContent("64");
    expect(count).toHaveTextContent("sample places, made by the team");
    expect(count).not.toHaveTextContent("CoStar has researched");
    expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("FIXTURE");
    expect(screen.getAllByText(SAMPLE_AS_OF).length).toBeGreaterThan(0);
    expect(screen.queryByText(AS_OF)).toBeNull();
    const attribution = screen.getByTestId("attribution");
    expect(attribution).toHaveTextContent("OpenFreeMap");
    expect(attribution).toHaveTextContent("OpenMapTiles");
    expect(attribution).toHaveTextContent("OpenStreetMap contributors");
  });

  it("keeps its own Day and Night choice on the map wrapper, never on the root", async () => {
    window.localStorage.clear();
    const { container } = render(<MapPage MapView={NoMap} />);
    const city = container.querySelector<HTMLElement>(".city")!;
    expect(city).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Switch the map to Day" }));
    expect(city).toHaveAttribute("data-theme", "light");
    expect(window.localStorage.getItem("snapback-map-theme")).toBe("light");
    expect(document.documentElement.dataset.theme).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Switch the map to Night" }));
    expect(city).toHaveAttribute("data-theme", "dark");
    window.localStorage.clear();
  });

  it("lists every place as a button, so the map is not the only way in", async () => {
    render(<MapPage MapView={NoMap} />);
    const list = await screen.findByTestId("place-list");
    expect(within(list).getAllByRole("button")).toHaveLength(64);
  });

  it("never says a place can be rented today", async () => {
    const { container } = render(<MapPage MapView={NoMap} />);
    const list = await screen.findByTestId("place-list");
    fireEvent.click(within(list).getAllByRole("button")[0]!);
    await screen.findByText("Floor plans on record");
    expect(container.textContent).not.toMatch(BANNED);
    expect(container.textContent).not.toMatch(/[–—]/);
  });

  it("opens the sheet from the list with the record lines and both ways on", async () => {
    render(<MapPage MapView={NoMap} />);
    const list = await screen.findByTestId("place-list");
    const scanned = within(list)
      .getAllByRole("button")
      .find((b) => b.textContent?.includes("3D scan"))!;
    fireEvent.click(scanned);
    const sheet = await screen.findByTestId("place-sheet");
    await within(sheet).findByText("Floor plans on record");
    expect(within(sheet).getByText(SAMPLE_AS_OF)).toBeInTheDocument();
    expect(sheet.textContent).not.toContain(AS_OF);
    expect(within(sheet).getByText(/Management company on record/)).toBeInTheDocument();
    const badge = within(sheet).getByTestId("scan-badge");
    expect(badge).toHaveTextContent("3D scan in this building");
    expect(badge).toHaveTextContent("It may be a model unit");
    const walk = within(badge).getByRole("link", { name: "Walk it first" });
    expect(walk.getAttribute("href")).toMatch(/^\/tour\/fx-map-\d+$/);
    const ad = within(sheet).getByRole("link", { name: "Check an ad for this place" });
    expect(ad.getAttribute("href")).toMatch(/^\/home\?place=fx-map-\d+$/);
    expect(within(sheet).getByText("Drawn stand-in (fixture)")).toBeInTheDocument();
  });

  it("counts the fit when the brief changes", async () => {
    render(<MapPage MapView={NoMap} />);
    await screen.findByTestId("count");
    expect(screen.getByText("Set a brief to narrow them down")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Has a 3D scan"));
    await waitFor(() => expect(screen.getByText(/of 64 fit your brief/)).toBeInTheDocument());
  });

  it("offers to remember no walk-ups after two are passed on, stamped as policy", async () => {
    render(<MapPage MapView={NoMap} />);
    const walkups = fixturePlacesMap(EMPTY_CRITERIA)
      .features.map((f) => fixtureSheet(f.properties.pid)!)
      .filter((s) => s.plans[0]!.must_haves.find((m) => m.key === "walkup")?.met === false)
      .slice(0, 2);
    expect(walkups).toHaveLength(2);
    for (const s of walkups) {
      const list = await screen.findByTestId("place-list");
      const card = within(list)
        .getAllByRole("button")
        .find((b) => b.getAttribute("data-pid") === s.property_id)!;
      fireEvent.click(card);
      const sheet = await screen.findByTestId("place-sheet");
      await within(sheet).findByText("Floor plans on record");
      fireEvent.click(within(sheet).getByRole("button", { name: "Not this one" }));
    }
    const proposal = await screen.findByTestId("proposal");
    expect(proposal).toHaveTextContent("You passed on 2 walk-ups. Remember: no walk-ups?");
    expect(proposal).toHaveTextContent("Picked by policy");
    expect(screen.getByLabelText("No walk-up")).not.toBeChecked();
    fireEvent.click(within(proposal).getByRole("button", { name: "Yes, remember" }));
    expect(screen.getByLabelText("No walk-up")).toBeChecked();
  });
});

describe("aerial age", () => {
  it("counts whole months, so an old photo never passes for a live view", () => {
    expect(monthsOld("2025-03-14", new Date("2026-11-14T12:00:00"))).toBe(20);
    expect(monthsOld("not a date")).toBeNull();
  });
});
