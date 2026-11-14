import { readFileSync } from "node:fs";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FIXTURE_TOUR } from "./fixtureTour";
import { TourView } from "./TourPage";

describe("as of CoStar's last research sits beside every fact and claim", () => {
  it("shows plan.as_of with every CoStar source, and only with those", async () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    const user = userEvent.setup();
    for (const stop of FIXTURE_TOUR.stops) {
      if (stop.facts.length + stop.claims.length === 0) continue;
      await user.click(screen.getByRole("button", { name: stop.title }));
      const sources = document.querySelectorAll(".tour-src");
      expect(sources.length).toBe(stop.facts.length + stop.claims.length);
      for (const el of sources) {
        // Only CoStar's own lines carry it; a Vexcel or Matterport source must not.
        const costar = (el.textContent ?? "").startsWith("CoStar");
        expect(el.textContent?.includes("as of CoStar's last research")).toBe(costar);
      }
    }
  });
});

describe("fetchTour (case walk)", () => {
  afterEach(() => {
    vi.resetModules();
    vi.doUnmock("../api");
  });

  async function load(caseRes: Response | null, placeRes: Response | null = null) {
    vi.resetModules();
    vi.doMock("../api", () => ({
      apiBase: () => "/api",
      apiFetchRead: () => (caseRes ? Promise.resolve(caseRes) : null),
      apiFetch: () => Promise.resolve(placeRes ?? new Response("{}", { status: 500 })),
    }));
    return (await import("./api")).fetchTour;
  }

  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

  it("returns the walk's model id so the browser loads that scan", async () => {
    const fetchTour = await load(json({ plan: FIXTURE_TOUR, model_id: "m-123" }));
    const r = await fetchTour({ propertyId: "p", caseId: "C1" });
    expect(r).toMatchObject({ modelId: "m-123", fromCase: true, notice: null });
  });

  it("in elsewhere mode a failed case walk is an error, never another home's public tour", async () => {
    const fetchTour = await load(json({}, 500), json(FIXTURE_TOUR));
    await expect(fetchTour({ propertyId: "p", caseId: "C1", mode: "elsewhere" })).rejects.toThrow(
      "The building where the photos were taken could not be loaded.",
    );
  });

  it("in claimed mode a failed case walk says the case's photos could not be loaded", async () => {
    const fetchTour = await load(json({}, 401), json(FIXTURE_TOUR));
    const r = await fetchTour({ propertyId: "p", caseId: "C1" });
    expect(r.fromCase).toBe(false);
    expect(r.notice).toBe(
      "The case's photos could not be loaded, so none are placed in these rooms.",
    );
  });
});

describe("the notice and the placeholder photo", () => {
  it("shows the notice above the tour", () => {
    render(<TourView plan={FIXTURE_TOUR} notice="The case's photos could not be loaded." />);
    expect(screen.getByTestId("tour-notice")).toHaveTextContent("could not be loaded");
  });

  it("writes no hex colours into the page's placeholder picture", () => {
    const src = readFileSync(`${process.cwd()}/src/tour/TourPage.tsx`, "utf8");
    expect(src).not.toMatch(/#[0-9a-fA-F]{6}\b/);
  });
});
