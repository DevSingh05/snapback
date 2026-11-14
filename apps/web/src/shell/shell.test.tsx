import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FIXTURE_TOUR } from "../tour/fixtureTour";
import { seeingLine, waysOut } from "../walk/seeing";
import { AppShell, PURPOSE } from "./AppShell";
import { FinderPage } from "./FinderPage";
import { briefFromChips, chipFromWords, loadLearned } from "./finderRules";
import { loadFinderEvents, recordFinderEvent } from "./finderStore";
import { clean, DEFAULT_PREFS, loadPrefs } from "./prefs";
import { YourChecks } from "./YourChecks";

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
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

  it("is light only: no Day or Dusk switch, and nothing sets a theme on the root", () => {
    const { unmount } = render(<AppShell section="map">map</AppShell>);
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(screen.queryByRole("button", { name: /^(Day|Dusk|Light|Dark|Auto)$/ })).toBeNull();
    expect(screen.queryByRole("group", { name: /Day or Dusk/ })).toBeNull();
    unmount();
    // A stored or carried "dark" from an older build changes nothing.
    window.localStorage.setItem("snapback-theme", "dark");
    window.history.replaceState(null, "", "/home?theme=dusk");
    render(<AppShell section="home">home</AppShell>);
    expect(document.documentElement.dataset.theme).toBeUndefined();
    window.history.replaceState(null, "", "/");
  });

  it("has Stories as a link and orders the bar mark, tabs, Stories, Customize", () => {
    render(<AppShell section="home">page</AppShell>);
    expect(screen.getByRole("link", { name: "Stories" })).toHaveAttribute("href", "/stories");
    const order = [...document.querySelectorAll<HTMLElement>(".app-bar :is(a, button)")].map(
      (el) => el.getAttribute("aria-label") ?? el.textContent,
    );
    expect(order.slice(0, 1)).toEqual(["SNAPBACK home"]);
    expect(order.slice(1, 6)).toEqual(["Home", "Listings", "Map", "Finder", "Replays"]);
    expect(order.slice(6, 8)).toEqual(["Stories", "Customize"]);
  });

  it("on a phone there is no theme button, and Customize is in the footer", () => {
    const real = window.matchMedia;
    window.matchMedia = ((q: string) => ({
      matches: true,
      media: q,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
    try {
      render(<AppShell section="home">page</AppShell>);
      expect(screen.queryByRole("button", { name: /Switch to (Day|Dusk)/ })).toBeNull();
      expect(screen.queryByRole("button", { name: "Menu" })).toBeNull();
      expect(
        within(document.querySelector<HTMLElement>(".app-foot")!).getByRole("button", {
          name: "Customize",
        }),
      ).toBeInTheDocument();
      expect(tabs()).toEqual(["Home", "Listings", "Map", "Finder", "Replays"]);
    } finally {
      window.matchMedia = real;
    }
  });

  it("Customize moves focus in, closes on Escape back to its button, and has no Menu", () => {
    render(<AppShell section="home">page</AppShell>);
    expect(screen.queryByRole("button", { name: "Menu" })).toBeNull();
    const btn = screen.getByRole("button", { name: "Customize" });
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByTestId("customize");
    expect(panel.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByTestId("customize")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Customize" }));
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

describe("Finder: a conversation, what it learned, and what fits", () => {
  it("says honestly that nothing replies yet, and starts empty", () => {
    render(<FinderPage />);
    expect(screen.getByTestId("finder-honest")).toHaveTextContent("nothing answers your messages");
    expect(screen.getByTestId("finder-honest")).toHaveTextContent("Picked by our rules");
    expect(screen.getByTestId("finder-empty")).toBeInTheDocument();
    expect(screen.getByTestId("learned-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("finder-offer")).toBeNull();
  });

  it("a message is kept as yours and never answered: the only new line is the message", () => {
    render(<FinderPage />);
    fireEvent.change(screen.getByLabelText("Your message"), {
      target: { value: "I like big windows" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const msgs = screen.getAllByTestId("finder-msg");
    expect(msgs).toHaveLength(1);
    expect(msgs[0]).toHaveAttribute("data-kind", "note");
    expect(msgs[0]).toHaveTextContent("I like big windows");
    expect(loadFinderEvents()[0]).toMatchObject({ kind: "note", text: "I like big windows" });
    expect(screen.queryByTestId("finder-offer")).toBeNull(); // no rule fits: nothing is offered
  });

  it("offers to remember what a code rule reads in your words, stamped, and only keeps a yes", () => {
    render(<FinderPage />);
    fireEvent.change(screen.getByLabelText("Your message"), {
      target: { value: "no walk-ups please, under $1,500" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    const offer = screen.getByTestId("finder-offer");
    expect(offer).toHaveTextContent("Picked by our rules");
    expect(offer).toHaveTextContent("Remember: no walk-ups?");
    expect(screen.queryAllByTestId("learned-chip")).toHaveLength(0);
    fireEvent.click(within(offer).getByRole("button", { name: "Yes, remember" }));
    expect(screen.getAllByTestId("learned-chip").map((c) => c.textContent)).toEqual([
      "no walk-ups×",
    ]);
    expect(loadLearned().chips).toEqual([{ id: "no_walkup", label: "no walk-ups" }]);
    // A no is remembered too, so the same offer does not come back.
    render(<FinderPage />);
    expect(screen.queryAllByText("Remember: no walk-ups?")).toHaveLength(0);
  });

  it("chips can be added and removed by hand, and stand for a search brief", () => {
    render(<FinderPage />);
    fireEvent.change(screen.getByLabelText("Add something yourself"), {
      target: { value: "near downtown" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByTestId("learned-chip")).toHaveTextContent("near downtown");
    fireEvent.click(screen.getByRole("button", { name: "Forget near downtown" }));
    expect(screen.queryByTestId("learned-chip")).toBeNull();
    expect(
      briefFromChips([
        { id: "no_walkup", label: "no walk-ups" },
        { id: "max_rent", label: "under $1,500" },
        { id: "note:near downtown", label: "near downtown" },
      ]),
    ).toEqual({ needs_no_walkup: true, max_rent_month: 1500 });
    expect(chipFromWords("under $1,500")).toEqual({ id: "max_rent", label: "under $1,500" });
    expect(chipFromWords("I like big windows")).toBeNull();
  });

  it("shows what you did on the map in the same conversation", () => {
    recordFinderEvent("passed", "Passed on a place");
    render(<FinderPage />);
    expect(screen.getByTestId("finder-msg")).toHaveTextContent("You passed on");
  });
});

describe("one purpose per page", () => {
  it("says what the page is for in one line", () => {
    const { unmount } = render(<AppShell section="map">map</AppShell>);
    expect(screen.getByTestId("page-purpose")).toHaveTextContent("Find a home by where it is.");
    unmount();
    render(
      <AppShell section={null} context={{ label: "Walk", href: "/tour/x" }}>
        walk
      </AppShell>,
    );
    expect(screen.getByTestId("page-purpose")).toHaveTextContent("See the home, room by room");
    expect(Object.keys(PURPOSE)).toHaveLength(7);
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
