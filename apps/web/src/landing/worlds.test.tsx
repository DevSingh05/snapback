import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { matchRoute } from "../App";
import WorldsLanding, { LANDING_BEATS, LANDING_MEASURED } from "./WorldsLanding";

describe("SNAPBACK Worlds front door", () => {
  it("is the page at / and the app moved to /home", () => {
    expect(matchRoute("/")).toEqual({ name: "landing" });
    expect(matchRoute("/home")).toEqual({ name: "home" });
    expect(matchRoute("/case/7Q2M")).toEqual({ name: "result", id: "7Q2M" });
  });

  it("has one clear way into the app and a Stories link in the bar", () => {
    render(<WorldsLanding />);
    const bar = document.querySelector<HTMLElement>(".wl-bar")!;
    expect(within(bar).getByRole("link", { name: "Open SNAPBACK" })).toHaveAttribute(
      "href",
      "/home",
    );
    expect(within(bar).getByRole("link", { name: "Stories" })).toHaveAttribute("href", "/stories");
    expect(screen.getByRole("link", { name: "Check an ad" })).toHaveAttribute("href", "/home");
  });

  it("draws the 3D hero first, then the labelled sample verdict", () => {
    render(<WorldsLanding />);
    const canvas = screen.getByTestId("wl-canvas");
    const verdict = screen.getByTestId("wl-verdict");
    expect(canvas.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(verdict).toHaveTextContent("Hold off: it asks for money before you’ve seen the place");
    expect(verdict).toHaveTextContent("SYNTHETIC");
    expect(canvas).toHaveAttribute("aria-label", expect.stringMatching(/drawing, not a real home/));
  });

  it("tells the scroll story in three beats over the drawing", () => {
    render(<WorldsLanding />);
    const beats = screen.getAllByTestId("wl-beat");
    expect(beats.map((b) => within(b).getByRole("heading").textContent)).toEqual(
      LANDING_BEATS.map((b) => b.title),
    );
    expect(beats[2]).toHaveTextContent("never an accusation");
    // the hero's one h1 comes before the beats
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.compareDocumentPosition(beats[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("labels the Taken here drawing as a synthetic sample and offers three photos", () => {
    render(<WorldsLanding />);
    const taken = document.querySelector<HTMLElement>("#taken")!;
    expect(taken).toHaveTextContent("Drawn sample · SYNTHETIC");
    const picks = within(taken).getAllByRole("button");
    expect(picks.map((b) => b.textContent)).toEqual(["Photo 1", "Photo 2", "Another home"]);
    expect(picks[0]).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("wl-res")).toHaveTextContent("in this drawn sample");
    expect(screen.getByTestId("wl-twin")).toHaveAttribute(
      "aria-label",
      expect.stringMatching(/drawn sample, not a real home/),
    );
  });

  it("states the measured number with its n and label, and nothing stronger", () => {
    render(<WorldsLanding />);
    const line = screen.getByTestId("wl-measured");
    expect(line).toHaveTextContent("LIVE, re-measured Nov 15");
    expect(line).toHaveTextContent(LANDING_MEASURED);
    expect(LANDING_MEASURED).toContain("43 of 48");
    expect(LANDING_MEASURED).toContain("78 real listing photos");
  });

  it("ends in the three-way row, with the realtor quote under the reviews", () => {
    render(<WorldsLanding />);
    const stories = screen.getByTestId("wl-col-stories");
    const reviews = screen.getByTestId("wl-col-reviews");
    expect(within(stories).getByRole("link")).toHaveAttribute("href", "/stories");
    expect(within(reviews).getByRole("link", { name: "Read the reviews" })).toHaveAttribute(
      "href",
      "/reviews",
    );
    expect(within(reviews).getByRole("link", { name: "Open a sample report" })).toHaveAttribute(
      "href",
      "/case/7Q2M",
    );
    expect(within(reviews).getByTestId("realtor-quote")).toHaveTextContent("Ashwin Veeravalli");
    expect(within(reviews).getByTestId("realtor-quote")).toHaveTextContent("The Agency, Los Gatos");
  });

  it("keeps copy honest: no AWS claim, no Apartments.com detection claim, no em dashes", () => {
    const { container } = render(<WorldsLanding />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/aws|amazon web/i);
    expect(text).not.toMatch(/apartments\.com/i);
    expect(text).not.toMatch(/[–—]/);
  });

  it("is Day only: no theme switch and no theme attribute", () => {
    render(<WorldsLanding />);
    expect(screen.queryByRole("button", { name: /^(Day|Dusk)$/ })).toBeNull();
    expect(screen.getByTestId("worlds-landing")).not.toHaveAttribute("data-theme");
  });
});
