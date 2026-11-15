import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FIXTURE_TOUR } from "../tour/fixtureTour";
import { WalkMap, walkCells } from "../walk/WalkMap";
import { HeroStreet } from "./HeroStreet";
import { HowItWorks } from "./HowItWorks";
import { RealtorQuote } from "./RealtorQuote";

describe("Home's photographs", () => {
  it("the hero is one real daylight photograph, described and stamped as a sample", () => {
    render(<HeroStreet />);
    const day = screen.getByTestId("hero-photo");
    expect(screen.queryByTestId("hero-photo-dusk")).toBeNull();
    expect(day).toHaveAttribute("alt", expect.stringMatching(/apartment building.*daylight/i));
    // Stock, never passed off as a listed home or as Houston.
    const hero = screen.getByTestId("hero-street");
    expect(hero).toHaveTextContent("Sample photo · Unsplash");
    expect(day.getAttribute("alt")).not.toMatch(/houston|listed/i);
  });

  it("collapsed behind the thread it keeps the photographs and drops the stamp line", () => {
    render(<HeroStreet strip />);
    expect(screen.getByTestId("hero-street")).toHaveClass("hs-strip");
    expect(screen.getByTestId("hero-photo")).toBeInTheDocument();
    expect(screen.getByTestId("hero-street")).not.toHaveTextContent("Sample photo");
  });

  it("the path is four steps in order, each with a stamped sample photo", () => {
    render(<HowItWorks />);
    const steps = screen.getAllByRole("listitem").filter((li) => li.classList.contains("hiw-step"));
    expect(steps.map((s) => s.querySelector(".hiw-step-title")!.textContent)).toEqual([
      "Check the ad",
      "Walk it first",
      "Find safer places",
      "Ask for a tour",
    ]);
    for (const step of steps) {
      const photo = step.querySelector(".ui-photo")!;
      expect(photo).toHaveAttribute("data-stamp", "sample");
      expect(photo).toHaveTextContent("SAMPLE PHOTO");
      expect(within(step as HTMLElement).getByRole("img")).toHaveAttribute(
        "alt",
        expect.stringMatching(/\w/),
      );
    }
    // Walk it first reads as a player: the rooms, as a strip.
    const rooms = within(steps[1] as HTMLElement).getByRole("list", { name: "Rooms in the walk" });
    expect(
      within(rooms)
        .getAllByRole("listitem")
        .map((r) => r.textContent),
    ).toEqual(["Living room", "Kitchen", "Bedroom", "Bath"]);
    // No number that is not measured, no sales words, no dashes.
    const copy = screen.getByTestId("how-it-works").textContent ?? "";
    expect(copy.replace(/0[1-4]|3D/g, "")).not.toMatch(/\d/);
    expect(copy).not.toMatch(/available|book now|guarantee|[–—]/i);
  });

  it("a step runs only when the page gives it something to run", () => {
    const check = vi.fn();
    render(<HowItWorks actions={{ check }} />);
    const buttons = within(screen.getByTestId("how-it-works")).getAllByRole("button");
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]!);
    expect(check).toHaveBeenCalledTimes(1);
    expect(buttons[0]).toHaveTextContent("Check the ad");
  });
});

describe("the walk map", () => {
  const stops = FIXTURE_TOUR.stops;

  it("draws one block per stop inside the home, in walking order, and lights the current one", () => {
    const inside = stops.filter((s) => s.kind !== "arrive" && s.kind !== "outro");
    const current = stops.findIndex((s) => s.title === "Kitchen");
    render(<WalkMap stops={stops} current={current} onPick={() => {}} />);
    const rooms = screen.getAllByTestId("walk-map-room");
    expect(rooms).toHaveLength(inside.length);
    expect(rooms.filter((r) => r.dataset.state === "here")).toHaveLength(1);
    expect(rooms[inside.findIndex((s) => s.title === "Kitchen")]).toHaveAttribute(
      "data-state",
      "here",
    );
    expect(rooms[0]).toHaveAttribute("data-state", "seen");
    expect(rooms.at(-1)).toHaveAttribute("data-state", "ahead");
    // The stop's name is on the view and in the chapter row; the map says how far in you are.
    expect(screen.getByTestId("walk-map")).toHaveTextContent(
      `Stop ${inside.findIndex((s) => s.title === "Kitchen") + 1} of ${inside.length} inside`,
    );
    expect(screen.getByTestId("walk-map")).not.toHaveTextContent("Kitchen");
    expect(screen.getByTestId("walk-map")).toHaveTextContent("Walking order, not a floor plan.");
  });

  it("picks a stop by its index in the plan", () => {
    const onPick = vi.fn();
    render(<WalkMap stops={stops} current={0} onPick={onPick} />);
    fireEvent.click(screen.getAllByTestId("walk-map-room")[1]!);
    expect(onPick).toHaveBeenCalledWith(walkCells(stops)[1]!.index);
  });

  it("keeps each stop next to the one before it, and draws nothing for a single stop", () => {
    const cells = walkCells(stops);
    for (let i = 1; i < cells.length; i++) {
      const step =
        Math.abs(cells[i]!.x - cells[i - 1]!.x) + Math.abs(cells[i]!.y - cells[i - 1]!.y);
      expect(step).toBe(46);
    }
    const { container } = render(
      <WalkMap stops={stops.slice(0, 2)} current={0} onPick={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("The realtor's words", () => {
  const QUOTE =
    "If he can add in additional safety features for preventing further scams and financial scams, I think this would be a very good app to have in the marketplace.";

  it("shows the context line, his quote word for word and the attribution", () => {
    render(<RealtorQuote lang="en" />);
    const box = screen.getByTestId("realtor-quote");
    expect(box).toHaveTextContent("Rental tour prep, with scam safety built in.");
    expect(within(box).getByText(`“${QUOTE}”`)).toBeInTheDocument();
    expect(box).toHaveTextContent("Ashwin Veeravalli, Realtor, The Agency, Los Gatos CA");
    expect(screen.queryByTestId("realtor-quote-es")).toBeNull();
  });

  it("in Spanish the context line is translated, the quote stays English with a translation under it", () => {
    render(<RealtorQuote lang="es" />);
    const box = screen.getByTestId("realtor-quote");
    expect(box).toHaveTextContent("Preparación de visitas a alquileres");
    expect(within(box).getByText(`“${QUOTE}”`)).toBeInTheDocument();
    expect(screen.getByTestId("realtor-quote-es")).toHaveTextContent(/fraudes financieros/);
    expect(box).toHaveTextContent("Ashwin Veeravalli");
  });
});
