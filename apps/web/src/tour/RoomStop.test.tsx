import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../twin/useReducedMotion", () => ({ usePrefersReducedMotion: () => false }));

import type { TourPlan, TourStop } from "../contracts";
import { FIXTURE_TOUR } from "./fixtureTour";
import { emptyFrameText, landingOfStop } from "./RoomStop";
import { TourView } from "./TourPage";

const stopOf = (title: string): TourStop => FIXTURE_TOUR.stops.find((s) => s.title === title)!;

function planWith(patch: Partial<TourPlan>): TourPlan {
  return { ...FIXTURE_TOUR, ...patch };
}

async function open(plan: TourPlan, name: string) {
  render(<TourView plan={plan} />);
  await userEvent.setup().click(screen.getByRole("button", { name }));
}

describe("emptyFrameText (the honest wording for a room with no placed photo)", () => {
  const bath = stopOf("Bathroom");
  it("says the ad showed no photo only when every ad photo was placed", () => {
    expect(emptyFrameText(bath, FIXTURE_TOUR)).toBe("The ad showed no photo of this room.");
  });

  it("never says that when any photo could not be placed", () => {
    const plan = planWith({ coverage: { ...FIXTURE_TOUR.coverage!, unplaced: 2 } });
    const unknown = { ...bath, ad_view: "unknown" as const };
    expect(emptyFrameText(unknown, plan)).toBe(
      "None of the placed photos are from this room (2 photos could not be placed).",
    );
    expect(emptyFrameText({ ...unknown }, plan)).not.toMatch(/ad showed no photo/);
  });

  it("says nothing for a stop with a photo, or with no locate result", () => {
    expect(emptyFrameText(stopOf("Kitchen"), FIXTURE_TOUR)).toBeNull();
    expect(
      emptyFrameText({ ...bath, ad_view: "unknown" }, planWith({ coverage: null })),
    ).toBeNull();
  });
});

describe("the room stop screen", () => {
  it("lands the placed photo over the scan, labels it, and toggles photo and scan", async () => {
    await open(FIXTURE_TOUR, "Kitchen");
    expect(screen.getByTestId("photo-label")).toHaveTextContent("The photo you sent, taken here.");
    const overlay = screen.getByTestId("photo-overlay");
    expect(overlay).toHaveStyle({ opacity: "0.6" });
    const toggle = screen.getByRole("button", { name: "Show the scan" });
    await userEvent.setup().click(toggle);
    expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0" });
    expect(screen.getByRole("button", { name: "Show the photo" })).toBeInTheDocument();
    expect(screen.queryByTestId("empty-frame")).toBeNull();
  });

  it("shows the dashed no-photo frame for a hidden room and no overlay", async () => {
    await open(FIXTURE_TOUR, "Bathroom");
    expect(screen.getByTestId("empty-frame")).toHaveTextContent(
      "The ad showed no photo of this room.",
    );
    expect(screen.queryByTestId("photo-overlay")).toBeNull();
    expect(screen.queryByTestId("photo-label")).toBeNull();
  });

  it("opens the director's dwell stops expanded and the others closed, claims included", async () => {
    await open(FIXTURE_TOUR, "Living room");
    expect(screen.getByTestId("stop-details")).toHaveAttribute("open");
    expect(screen.getByText(/Not confirmed\. The ad says hardwood floors/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Kitchen" }));
    expect(screen.getByTestId("stop-details")).not.toHaveAttribute("open");
  });

  it("leaves a slot for the agent rail and renders what it is given", () => {
    render(<TourView plan={FIXTURE_TOUR} rail={<p>trace here</p>} />);
    expect(screen.getByTestId("agent-rail-slot")).toHaveTextContent("trace here");
  });

  it("shows the coverage line and, when photos were taken elsewhere, the banner", () => {
    const plan = planWith({
      coverage: {
        ...FIXTURE_TOUR.coverage!,
        elsewhere: 1,
        line: "The ad showed 1 of the 5 rooms in this scan.",
      },
    });
    render(<TourView plan={plan} />);
    expect(screen.getByTestId("coverage-line")).toHaveTextContent("The ad showed 1 of the 5 rooms");
    expect(screen.getByTestId("elsewhere-banner")).toHaveTextContent(
      "1 of the ad's photos was taken in a different building. It is not shown in these rooms.",
    );
    expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("FIXTURE");
  });
});

describe("landingOfStop", () => {
  it("builds a match from the photo's pose and is null without one", () => {
    const m = landingOfStop(stopOf("Kitchen"));
    expect(m).toMatchObject({
      kind: "match",
      photoId: "photo-1",
      position: [8, 1.4, -2],
      fovDeg: 70,
    });
    expect(landingOfStop(stopOf("Bathroom"))).toBeNull();
  });
});

describe("the walk of the building the photos were taken in (X1)", () => {
  it("shows the heading and the office line, and never the no-photo wording", () => {
    const plan = planWith({
      mode: "elsewhere",
      mode_line:
        "The home in these photos is listed by Sample Property Group on CoStar's record. We can't tell you if it is offered, or at this price.",
      coverage: { counted: "none", total: 0, with_photo: 0, placed: 1, elsewhere: 0, unplaced: 0 },
      stops: FIXTURE_TOUR.stops.map((s) =>
        s.ad_view === "none_placed" ? { ...s, ad_view: "unknown" as const } : s,
      ),
    });
    render(<TourView plan={plan} />);
    expect(screen.getByTestId("elsewhere-heading")).toHaveTextContent(
      "Where the photos were taken",
    );
    expect(screen.getByTestId("mode-line")).toHaveTextContent("We can't tell you if it is offered");
    expect(screen.queryByTestId("coverage-line")).toBeNull();
    expect(screen.queryByText(/The ad showed no photo of this room/)).toBeNull();
  });
});

describe("landingOfStop on a z-up live stop (#244 follow-up)", () => {
  it("takes the photo's viewer angles and the viewer floor point", () => {
    const stop: TourStop = {
      ...stopOf("Kitchen"),
      photos: [
        {
          photo_id: "l1",
          sweep_id: "z1",
          position: [4, 5, 1.4],
          rotation_quat: [0.5, 0.5, 0.5, 0.5],
          fov_deg: 62,
          yaw_deg: 30,
          pitch_deg: -5,
        },
      ],
    };
    const m = landingOfStop(stop, "z");
    expect(m).toMatchObject({ kind: "match", yaw: 30, pitch: -5, floor: [4, -5], fovDeg: 62 });
  });
});
