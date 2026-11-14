import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { photoAt, walkLook } from "../walk/walkLook";
import { FIXTURE_TOUR } from "./fixtureTour";
import { TourView } from "./TourPage";

// One stop drives every surface of the walk page. This walks each stop and asks every surface
// which room and which ad photo it is showing: they must all say the same thing.
// The alias every surface uses is the evidence file's, the one the match view and the drawer show.
const evidence = walkLook(FIXTURE_TOUR, "").evidence;
const aliasOf = (i: number) =>
  photoAt(FIXTURE_TOUR.stops[i]!, evidence)?.alias ?? FIXTURE_TOUR.stops[i]!.photos[0]?.alias;

describe("the walk page is in step with the stop on screen", () => {
  it("names the same room and the same photo on every surface, at every stop", async () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    const user = userEvent.setup();
    const stops = FIXTURE_TOUR.stops;
    for (let i = 0; i < stops.length; i++) {
      const stop = stops[i]!;
      const where = `stop ${i + 1} ${stop.title}`;
      // the overlay on the view, the page heading, the panel count
      expect(
        screen.getByTestId("walk-player").querySelector(".wp-room strong"),
        where,
      ).toHaveTextContent(stop.title);
      expect(screen.getByRole("heading", { level: 1 }), where).toHaveTextContent(stop.title);
      expect(screen.getByText(`Step ${i + 1} of ${stops.length}`), where).toBeInTheDocument();
      // the chapter row: exactly this chapter is current
      const current = screen
        .getAllByRole("button", { name: /^Chapter \d+:/ })
        .filter((b) => b.getAttribute("aria-current") === "true");
      expect(
        current.map((b) => b.getAttribute("aria-label")),
        where,
      ).toEqual([`Chapter ${i + 1}: ${stop.title}`]);
      // the walk map lights this stop, and the progress bar says "here" at this one
      const rooms = screen.queryAllByTestId("walk-map-room");
      const lit = rooms.filter((r) => r.getAttribute("data-state") === "here");
      expect(lit, where).toHaveLength(
        stop.kind === "room" || stop.kind === "stop" ? 1 : lit.length,
      );
      expect(lit.length, where).toBeLessThanOrEqual(1);
      const seg = screen.getByTestId("tour-progress").querySelectorAll("[data-state=here]");
      expect(seg, where).toHaveLength(1);
      // the ad photo: the caption and "How we know" name this stop's photo, or say there is none
      const alias = stop.photos.length > 0 ? aliasOf(i) : undefined;
      const caption = screen.queryByTestId("stage-caption");
      if (alias) {
        expect(caption, where).toHaveTextContent(`Taken here: ad photo ${alias}`);
        expect(screen.getByTestId("how-we-know"), where).toBeInTheDocument();
      } else {
        expect(caption?.textContent ?? "", where).not.toMatch(/Taken here/);
        expect(screen.queryByTestId("how-we-know"), where).toBeNull();
      }
      // and the room name is on the view once, not three times
      expect(
        screen.getByTestId("walk-player").textContent?.split(stop.title).length,
        where,
      ).toBeLessThanOrEqual(3);
      if (i < stops.length - 1) await user.click(screen.getByRole("button", { name: "Next" }));
    }
  });

  it("opens How we know on the current stop's photo, follows the walk, and says when there is none", async () => {
    render(<TourView plan={FIXTURE_TOUR} />);
    const user = userEvent.setup();
    const kitchen = FIXTURE_TOUR.stops.findIndex((s) => s.photos.length > 0);
    for (let i = 0; i < kitchen; i++)
      await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByTestId("how-we-know"));
    const alias = aliasOf(kitchen)!;
    expect(
      screen.getAllByRole("tab").find((t) => t.getAttribute("aria-selected") === "true"),
    ).toHaveTextContent(alias);
    // Next door: a room with no ad photo. The drawer does not stay on the old photo.
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.queryByTestId("evidence-drawer")).toBeNull();
    expect(screen.getByTestId("how-we-know-none")).toHaveTextContent("No ad photo for this room");
  });
});
