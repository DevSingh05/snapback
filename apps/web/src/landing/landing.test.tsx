import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FIXTURE_TOUR } from "../tour/fixtureTour";
import { WalkMap, walkCells } from "../walk/WalkMap";
import { HeroStreet } from "./HeroStreet";
import { HowItWorks } from "./HowItWorks";

describe("the first screen's drawings", () => {
  it("the street scene is decoration only: hidden from readers, no text, no outside file", () => {
    const { container } = render(<HeroStreet />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.textContent).toBe("");
    expect(container.innerHTML).not.toMatch(/href|url\(|<image|<use/);
    // One lit home, with three photos traced to it.
    expect(container.querySelectorAll(".hs-lit")).toHaveLength(1);
    expect(container.querySelectorAll(".hs-photo")).toHaveLength(3);
    expect(container.querySelectorAll(".hs-trace")).toHaveLength(3);
  });

  it("how it works is three real steps in order, each with a drawing", () => {
    render(<HowItWorks />);
    const steps = screen.getAllByRole("listitem");
    expect(steps.map((s) => s.querySelector("h3")!.textContent)).toEqual([
      "Paste the ad",
      "We check it against the record",
      "Walk it, then contact the office on record",
    ]);
    for (const step of steps) expect(step.querySelector("svg")).not.toBeNull();
    const copy = screen.getByTestId("how-it-works").textContent ?? "";
    expect(copy).not.toMatch(/available|book now|guarantee|[–—]/i);
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
    expect(screen.getByTestId("walk-map")).toHaveTextContent("Kitchen");
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
