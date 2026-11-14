import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FIXTURE_TOUR } from "../tour/fixtureTour";
import { seeingLine, waysOut } from "../walk/seeing";
import { AppShell } from "./AppShell";
import { FinderPage } from "./FinderPage";
import { loadFinderEvents, recordFinderEvent } from "./finderStore";
import { clean, DEFAULT_PREFS, loadPrefs } from "./prefs";
import { defaultTheme, initialChoice, savedTheme, THEME_KEY } from "./theme";
import { YourChecks } from "./YourChecks";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete document.documentElement.dataset.theme;
});
afterEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

const tabs = () =>
  within(screen.getByRole("navigation", { name: "Main" }))
    .getAllByRole("link")
    .map((a) => a.textContent);

describe("the app shell", () => {
  it("shows the views as tabs, marks the current one, and has no sign-in", () => {
    render(<AppShell section="listings">page</AppShell>);
    expect(tabs()).toEqual(["Home", "Listings", "Map", "Finder", "Replays"]);
    expect(screen.getByRole("link", { name: "Listings" })).toHaveAttribute("aria-current", "page");
    expect(document.body.textContent).not.toMatch(/sign in|log in|account/i);
  });

  it("adds a tab for where you are inside a place", () => {
    render(
      <AppShell section={null} context={{ label: "Walk", href: "/tour/x" }}>
        page
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "Walk" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
  });

  it("opens the map in dark and every other page in light, until the person picks", () => {
    expect(defaultTheme(true)).toBe("dark");
    expect(defaultTheme(false)).toBe("light");
    const { unmount } = render(<AppShell section="map">map</AppShell>);
    expect(document.documentElement.dataset.theme).toBe("dark");
    unmount();
    render(<AppShell section="home">home</AppShell>);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("remembers a picked theme and uses it on every page, the map included", () => {
    const { unmount } = render(<AppShell section="home">home</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute("aria-pressed", "true");
    expect(savedTheme()).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Light" }));
    unmount();
    render(<AppShell section="map">map</AppShell>);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("shares one key with the website and takes the theme from the address", () => {
    expect(THEME_KEY).toBe("snapback-theme");
    expect(initialChoice("?theme=dark")).toBe("dark");
    expect(window.localStorage.getItem("snapback-theme")).toBe("dark");
    expect(initialChoice("?theme=purple")).toBe("dark"); // not a theme: the saved one stands
    window.localStorage.clear();
    expect(initialChoice("")).toBeNull();
    // A link from the website carries its theme into the map too.
    window.history.replaceState(null, "", "/map?theme=light");
    render(<AppShell section="map">map</AppShell>);
    expect(document.documentElement.dataset.theme).toBe("light");
    window.history.replaceState(null, "", "/");
  });

  it("Auto follows the device: no theme is forced", () => {
    render(<AppShell section="home">home</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Auto" }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(savedTheme()).toBe("system");
  });

  it("Customize hides a tab and picks the one that opens first, and remembers both", () => {
    render(<AppShell section="home">home</AppShell>);
    fireEvent.click(screen.getByRole("button", { name: "Customize" }));
    const panel = screen.getByTestId("customize");
    fireEvent.click(within(panel).getByRole("checkbox", { name: "Replays" }));
    expect(tabs()).toEqual(["Home", "Listings", "Map", "Finder"]);
    const firsts = within(panel).getAllByRole("radio", { name: "Opens first" });
    fireEvent.click(firsts[2]!); // Map
    expect(loadPrefs()).toEqual({ hidden: ["replays"], first: "map" });
    // Home can never be hidden, and a hidden tab cannot open first.
    expect(within(panel).getByRole("checkbox", { name: "Home" })).toBeDisabled();
    fireEvent.click(within(panel).getByRole("checkbox", { name: "Map" }));
    expect(loadPrefs().first).toBe("home");
  });

  it("ignores a broken or unknown saved choice", () => {
    expect(clean("nonsense")).toEqual(DEFAULT_PREFS);
    expect(clean({ hidden: ["home", "map", "zzz"], first: "map" })).toEqual({
      hidden: ["map"],
      first: "home",
    });
    window.localStorage.setItem("snapback.space", "{not json");
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
  });
});

describe("Home: your checks", () => {
  it("with no live server shows the team's sample case, labelled, with its verdict", async () => {
    render(<YourChecks />);
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /Case 7Q2M/ })).toBeInTheDocument(),
    );
    expect(screen.getByTestId("your-checks")).toHaveTextContent("A sample case made by the team");
    expect(screen.getByRole("link", { name: /Case 7Q2M/ })).toHaveAttribute("href", "/case/7Q2M");
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getByRole("link", { name: "Check another ad" })).toHaveAttribute(
      "href",
      "#listing",
    );
  });
});

describe("Finder", () => {
  it("starts empty and says where events come from", () => {
    render(<FinderPage />);
    expect(screen.getByTestId("finder-empty")).toHaveTextContent("Open a place on the map");
  });

  it("shows this visit's events and what was remembered", () => {
    recordFinderEvent("passed", "Passed on a walk-up");
    recordFinderEvent("remembered", "Remembered: no walk-ups. Added to your brief.");
    render(<FinderPage />);
    expect(screen.getByText("Passed on a walk-up")).toBeInTheDocument();
    expect(screen.getAllByText("Remembered: no walk-ups. Added to your brief.")).toHaveLength(2);
  });

  it("saves a note and never answers it: no reply is made up", () => {
    render(<FinderPage />);
    fireEvent.change(screen.getByLabelText("Tell the finder what matters"), {
      target: { value: "Ground floor only" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(loadFinderEvents()[0]).toMatchObject({ kind: "note", text: "Ground floor only" });
    expect(screen.getByText("Ground floor only")).toBeInTheDocument();
    // Exactly one new line appears: the note itself, labelled as the renter's.
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("listitem")).toHaveTextContent("Your note");
    expect(screen.getByTestId("finder-honest")).toHaveTextContent("Nothing replies yet");
    expect(screen.getByTestId("finder-honest")).toHaveTextContent("Picked by policy");
  });
});

describe("the walk's plain words", () => {
  const stop = (key: string) => FIXTURE_TOUR.stops.find((s) => s.key === key)!;

  it("says what you are seeing at each kind of stop, drawing or real", () => {
    expect(seeingLine(stop("arrive"), FIXTURE_TOUR, false)).toMatch(/^You are outside/);
    expect(seeingLine(stop("room-3"), FIXTURE_TOUR, false)).toBe(
      "You are in the kitchen, looking at a drawing of this kind of room. A photo from the ad was taken here, and it is shown where it was taken.",
    );
    expect(seeingLine(stop("room-4"), FIXTURE_TOUR, true)).toBe(
      "You are in the bathroom, looking at the real 3D scan. The ad showed no photo of this room, so look closely.",
    );
    expect(seeingLine(stop("outro"), FIXTURE_TOUR, false)).toMatch(/see the place in person/);
    for (const s of FIXTURE_TOUR.stops)
      expect(seeingLine(s, FIXTURE_TOUR, false)).not.toMatch(/sweep|pose|inlier|[–—]/i);
  });

  it("always offers a way back and a way to check an ad", () => {
    expect(waysOut(FIXTURE_TOUR, "ab12").back).toEqual({
      href: "/case/ab12",
      label: "Back to your result",
    });
    expect(waysOut(FIXTURE_TOUR, null).back.href).toBe("/map?place=fixture-bldg-1");
    expect(waysOut(FIXTURE_TOUR, null).check.href).toBe("/home#listing");
  });
});
