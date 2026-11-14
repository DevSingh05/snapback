import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { FIXTURE_TOUR } from "../../tour/fixtureTour";
import { ARRIVE_MS, LAND_MS, PAN_MS } from "./timeline";
import { fakeClock } from "./transport";
import { REDUCED_NOTE, WalkPlayer } from "./WalkPlayer";

const STOPS = FIXTURE_TOUR.stops;
const PLAIN = ARRIVE_MS + PAN_MS;

// A stand-in for the tour page: a stage, the player in it, and a Next button outside it.
function Host({
  reduced = false,
  clock,
}: {
  reduced?: boolean;
  clock: ReturnType<typeof fakeClock>;
}) {
  const [index, setIndex] = useState(0);
  return (
    <div className="tour-page">
      <section className="tour-stage">
        <WalkPlayer
          stops={STOPS}
          index={index}
          onIndex={setIndex}
          reduced={reduced}
          clock={clock}
          endAction={{ label: "Tour prep: what to ask", href: "/prep/place/x" }}
          summary="The ad showed 1 of the 5 rooms in this scan."
        />
      </section>
      <h1>{STOPS[index]!.title}</h1>
      <button type="button" onClick={() => setIndex((i) => i + 1)}>
        Next
      </button>
    </div>
  );
}

function mount(reduced = false) {
  const clock = fakeClock();
  render(<Host reduced={reduced} clock={clock} />);
  const tick = (ms: number) => act(() => clock.advance(ms));
  const title = () => screen.getByRole("heading", { level: 1 }).textContent;
  return { tick, title, player: () => screen.getByTestId("walk-player") };
}

describe("WalkPlayer", () => {
  it("plays on arrival like a video, moves the page through the stops, and can be paused", () => {
    const { tick, title, player } = mount();
    expect(player()).toHaveAttribute("data-mode", "playing");
    tick(PLAIN + 100);
    expect(title()).toBe("Front door");
    expect(screen.getByTestId("wp-caption")).toHaveTextContent("A room the ad left out.");
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    tick(30_000);
    expect(title()).toBe("Front door");
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("shows one chapter per stop with the current one marked, and a chapter jumps there", () => {
    const { title } = mount();
    const chapters = screen.getAllByRole("button", { name: /^Chapter \d+:/ });
    expect(chapters).toHaveLength(STOPS.length);
    fireEvent.click(screen.getByRole("button", { name: "Chapter 4: Kitchen" }));
    expect(title()).toBe("Kitchen");
    expect(screen.getByRole("button", { name: "Chapter 4: Kitchen" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("slider", { name: "Tour timeline" })).toHaveAttribute(
      "aria-valuetext",
      expect.stringContaining("Kitchen"),
    );
  });

  it("space plays and pauses, and the arrow keys step a chapter", () => {
    const { title, player } = mount();
    fireEvent.keyDown(window, { key: " ", code: "Space" });
    expect(player()).toHaveAttribute("data-mode", "paused");
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(title()).toBe("Front door");
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(title()).toBe("Arrive outside");
    fireEvent.keyDown(window, { key: " ", code: "Space" });
    expect(player()).toHaveAttribute("data-mode", "playing");
  });

  it("the speed button switches between 1x and 1.5x", () => {
    const { tick } = mount();
    fireEvent.click(screen.getByTestId("wp-speed"));
    expect(screen.getByTestId("wp-speed")).toHaveTextContent("1.5x");
    tick(2000);
    expect(screen.getByTestId("wp-time")).toHaveTextContent("0:03");
  });

  it("any touch on the stage hands over to explore; Resume tour returns to the timeline", () => {
    const { tick, title, player } = mount();
    tick(PLAIN + 500);
    fireEvent.pointerDown(screen.getByTestId("wp-shield"));
    expect(player()).toHaveAttribute("data-mode", "exploring");
    tick(60_000);
    expect(title()).toBe("Front door");
    // On the drawn stage, a room is one tap away.
    fireEvent.click(screen.getByRole("button", { name: "Bedroom" }));
    expect(title()).toBe("Bedroom");
    expect(player()).toHaveAttribute("data-mode", "exploring");
    fireEvent.click(screen.getByTestId("wp-resume"));
    expect(player()).toHaveAttribute("data-mode", "playing");
    expect(screen.getByTestId("wp-time")).toHaveTextContent("0:26");
    tick(1000);
    expect(title()).toBe("Bedroom");
  });

  it("the Explore button does the same, and a press elsewhere on the page only pauses", () => {
    const { player } = mount();
    fireEvent.pointerDown(screen.getByRole("heading", { level: 1 }));
    expect(player()).toHaveAttribute("data-mode", "paused");
    fireEvent.click(screen.getByTestId("wp-explore-toggle"));
    expect(player()).toHaveAttribute("data-mode", "exploring");
    expect(screen.getByText(/Drag to look around/)).toBeInTheDocument();
  });

  it("follows a stop change made outside the player", () => {
    const { tick, title } = mount();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(title()).toBe("Front door");
    expect(screen.getByTestId("wp-time")).toHaveTextContent("0:02");
    tick(PLAIN);
    expect(title()).toBe("Living room");
  });

  it("says when the ad photo lands", () => {
    const { tick } = mount();
    fireEvent.click(screen.getByRole("button", { name: "Chapter 4: Kitchen" }));
    tick(ARRIVE_MS + 200);
    expect(screen.getByTestId("wp-pin")).toHaveTextContent("The ad photo lands here");
    tick(LAND_MS);
    expect(screen.queryByTestId("wp-pin")).toBeNull();
  });

  it("ends on a card with one thing to do next", () => {
    const { tick } = mount();
    tick(120_000);
    expect(screen.getByTestId("wp-end")).toHaveTextContent(
      "The ad showed 1 of the 5 rooms in this scan.",
    );
    expect(screen.getByRole("link", { name: "Tour prep: what to ask" })).toHaveAttribute(
      "href",
      "/prep/place/x",
    );
    fireEvent.click(screen.getByRole("button", { name: "Watch again" }));
    expect(screen.queryByTestId("wp-end")).toBeNull();
    expect(screen.getByTestId("wp-time")).toHaveTextContent("0:00");
  });

  it("reduced motion: starts paused, says why, and still steps through the stops", () => {
    const { tick, title, player } = mount(true);
    expect(player()).toHaveAttribute("data-mode", "paused");
    expect(screen.getByTestId("wp-reduced")).toHaveTextContent(REDUCED_NOTE);
    tick(20_000);
    expect(title()).toBe("Arrive outside");
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    tick(PLAIN + 100);
    expect(title()).toBe("Front door");
  });
});

describe("WalkPlayer on the real scan", () => {
  it("hands over when the person's first touch lands in the scan, and the scan keeps the tap", async () => {
    const clock = fakeClock();
    const sdk = {
      disconnect: () => {},
      Sweep: {
        moveTo: () => Promise.resolve(),
        data: { subscribe: () => ({ cancel: () => {} }) },
      },
    };
    render(
      <div className="tour-page">
        <section className="tour-stage">
          <div className="sv" data-main="real">
            <iframe title="3D view" />
          </div>
          <WalkPlayer
            stops={STOPS}
            index={0}
            onIndex={() => {}}
            reduced={false}
            clock={clock}
            sdk={sdk}
            sweeps={["fx-sweep-00"]}
          />
        </section>
      </div>,
    );
    const player = screen.getByTestId("walk-player");
    await waitFor(() => expect(player).toHaveAttribute("data-surface", "scan"));
    expect(player).toHaveAttribute("data-mode", "playing");
    // The shield is out of the way on the scan, so a tap reaches it; the tap shows as a focus move.
    screen.getByTitle("3D view").focus();
    fireEvent.blur(window);
    await waitFor(() => expect(player).toHaveAttribute("data-mode", "exploring"));
  });
});
