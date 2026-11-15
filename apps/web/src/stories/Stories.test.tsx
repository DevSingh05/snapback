import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { matchRoute } from "../App";
import { OneBox } from "../home/OneBox";
import { PATH_STEPS } from "../ui";
import { chaptersOf, playsFor, STORIES } from "./stories";
import { StoriesPage } from "./StoriesPage";

const beatOn = () => document.querySelector(".st-stage")!.getAttribute("data-beat");
const play = () => screen.getByTestId("st-play");
const forward = () => screen.getByRole("button", { name: "Forward one step" });
const back = () => screen.getByRole("button", { name: "Back one step" });
const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));
const chapter = (name: string) => screen.getByRole("button", { name });
/** Steps forward to the beat with this key. */
function goTo(key: string) {
  for (let i = 0; i < 12 && beatOn() !== key; i++) fireEvent.click(forward());
  expect(beatOn()).toBe(key);
}

function open(slug: string, reduced: boolean) {
  window.history.replaceState(null, "", `/stories?story=${slug}`);
  return render(<StoriesPage reduced={reduced} />);
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  window.history.replaceState(null, "", "/");
});

describe("the Stories page", () => {
  it("is its own route, linked once from Home", () => {
    expect(matchRoute("/stories")).toEqual({ name: "stories" });
    vi.useRealTimers();
    render(<OneBox mode="fixture" />);
    const link = screen.getByRole("link", { name: "All stories" });
    expect(link).toHaveAttribute("href", "/stories");
  });

  it("plays: each beat moves on when its time runs out, and stops on the last", () => {
    open("sascha", false);
    const beats = STORIES[0]!.beats;
    expect(beatOn()).toBe(beats[0]!.key);
    expect(play()).toHaveAccessibleName("Pause");
    wait(beats[0]!.ms - 50);
    expect(beatOn()).toBe(beats[0]!.key);
    wait(100);
    expect(beatOn()).toBe(beats[1]!.key);
    for (const b of beats.slice(1)) wait(b.ms + 10);
    expect(beatOn()).toBe("end");
    expect(screen.getByTestId("st-end")).toBeInTheDocument();
    expect(play()).toHaveAccessibleName("Play again");
  });

  it("pauses, and picks up where it left off", () => {
    open("sascha", false);
    const first = STORIES[0]!.beats[0]!.ms;
    wait(first - 1000);
    fireEvent.click(play());
    expect(play()).toHaveAccessibleName("Play");
    wait(first * 3);
    expect(beatOn()).toBe("ad");
    fireEvent.click(play());
    wait(900);
    expect(beatOn()).toBe("ad");
    wait(200);
    expect(beatOn()).toBe("paste");
  });

  it("steps back and forward with the buttons and the keys, and restarts", () => {
    open("student", false);
    fireEvent.click(play());
    expect(back()).toBeDisabled();
    fireEvent.click(forward());
    expect(beatOn()).toBe("voice");
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(beatOn()).toBe("check");
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(beatOn()).toBe("voice");
    fireEvent.click(back());
    expect(beatOn()).toBe("ad");
    fireEvent.keyDown(window, { key: " " });
    expect(play()).toHaveAccessibleName("Pause");
    fireEvent.keyDown(window, { key: " " });
    expect(play()).toHaveAccessibleName("Play");
    fireEvent.click(chapter("Safer places"));
    expect(beatOn()).toBe("places");
    expect(chapter("Safer places")).toHaveAttribute("aria-current", "step");
    fireEvent.click(chapter("Check"));
    expect(beatOn()).toBe("ad");
    fireEvent.click(chapter("Tour request"));
    expect(beatOn()).toBe("draft");
    fireEvent.keyDown(window, { key: "r" });
    expect(beatOn()).toBe("ad");
    expect(play()).toHaveAccessibleName("Pause");
  });

  it("never plays on its own with reduced motion", () => {
    open("browsing", true);
    expect(play()).toHaveAccessibleName("Play");
    wait(60_000);
    expect(beatOn()).toBe("ask");
    expect(screen.getByText(/Reduced motion: press play or step/)).toBeInTheDocument();
    // Typed words show whole at once.
    expect(screen.getByLabelText(/paste an ad, a link/i)).toHaveValue(
      "A 1 bed under $1,400 near Montrose. No walk-ups please.",
    );
  });

  it("switches stories from the tabs", () => {
    open("sascha", true);
    fireEvent.click(screen.getByRole("tab", { name: /just looking/i }));
    expect(screen.getByRole("tab", { name: /just looking/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(document.querySelector(".st-stage")).toHaveAttribute("data-story", "browsing");
    expect(window.location.search).toBe("?story=browsing");
  });

  for (const story of STORIES) {
    it(`${story.slug}: renders every beat, framed as imagined, with FIXTURE on screen`, () => {
      open(story.slug, true);
      expect(story.imagine).toMatch(/^Imagine /);
      expect(document.querySelector(".st-imagine")).toHaveTextContent(story.imagine);
      expect(screen.getByRole("tab", { selected: true })).toHaveTextContent(
        `Plays in ${playsFor(story)} seconds`,
      );
      for (const [i, b] of story.beats.entries()) {
        expect(beatOn()).toBe(b.key);
        expect(screen.getByTestId("st-line")).toHaveTextContent(b.say);
        if (b.key === "end") expect(screen.getByTestId("st-end")).toHaveTextContent(story.did);
        else expect(screen.getByTestId(`st-beat-${b.key}`)).toBeInTheDocument();
        expect(screen.getAllByTestId("source-chip").length).toBeGreaterThan(0);
        if (i < story.beats.length - 1) fireEvent.click(forward());
      }
      expect(forward()).toBeDisabled();
    });
  }

  it("shows the app's own screens: the verdict, the voice box, the walk and the drafts", () => {
    open("sascha", true);
    goTo("verdict");
    expect(screen.getByTestId("ob-verdict")).toHaveTextContent("Hold off for now");
    expect(screen.getByTestId("ob-verdict")).toHaveTextContent("Zelle before a viewing. Red flag.");
    goTo("proof");
    expect((screen.getByLabelText("Message to send") as HTMLTextAreaElement).value).toContain(
      "code K7P4",
    );
    goTo("walk");
    expect(screen.getByTestId("walk-player")).toBeInTheDocument();
    expect(screen.getByTestId("st-walk")).toHaveTextContent("SAMPLE PHOTO");
    goTo("places");
    expect(screen.getAllByRole("link", { name: "Walk it first" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("tab", { name: /master's student/i }));
    goTo("voice");
    expect(screen.getByTestId("voice-listening")).toHaveTextContent("Is this landlord real?");
    goTo("places");
    expect(screen.getAllByRole("link", { name: "Walk it first" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("tab", { name: /just looking/i }));
    goTo("draft");
    expect((screen.getByLabelText("Tour request draft") as HTMLTextAreaElement).value).toContain(
      "I will not pay before I have seen the place",
    );
  });

  it("shows the path as chapters, timed from the beats in the script", () => {
    for (const story of STORIES) {
      const chapters = chaptersOf(story);
      for (const c of chapters) expect(PATH_STEPS).toContain(c.label);
      expect(new Set(chapters.map((c) => c.id)).size).toBe(chapters.length);
      expect(Math.round(chapters.reduce((t, c) => t + c.seconds, 0))).toBe(playsFor(story));
    }
    // Sascha and the student go through all four steps.
    expect(chaptersOf(STORIES[0]!).map((c) => c.label)).toEqual([...PATH_STEPS]);
    expect(
      chaptersOf(STORIES[1]!)
        .map((c) => c.label)
        .sort(),
    ).toEqual([...PATH_STEPS].sort());
    open("sascha", true);
    expect(
      within(screen.getByRole("list", { name: /the path/i })).getAllByRole("button"),
    ).toHaveLength(4);
    // On the end card every step is done: no chapter is the current one.
    goTo("end");
    expect(document.querySelector(".st-chapters [aria-current]")).toBeNull();
  });

  it("every photo is stamped, and the page has one accent button at the end", () => {
    open("sascha", true);
    for (const photo of document.querySelectorAll(".ui-photo"))
      expect(photo).toHaveAttribute("data-stamp", "sample");
    expect(document.querySelectorAll(".st-pick .ui-photo")).toHaveLength(3);
    // The shell lays its bar over the hero photograph when the page marks it.
    expect(document.querySelector(".st-hero")).toHaveAttribute("data-bar", "photo");
    goTo("end");
    expect(document.querySelectorAll(".st-btn-primary")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Check your own ad" })).toHaveAttribute(
      "href",
      "/home",
    );
    expect(document.querySelector(".st-end .ui-photo")).toHaveAttribute("data-stamp", "sample");
  });

  it("says only what the voice box does: hold the mic and talk in the browser", () => {
    open("student", true);
    goTo("voice");
    expect(screen.getByTestId("st-voice")).toHaveTextContent(
      "Hold the mic and talk, right in the browser.",
    );
    expect(document.body.textContent).not.toMatch(/any phone|time zone/i);
  });

  it("the walk's own Play and Pause follows the story's", () => {
    open("sascha", false);
    goTo("walk");
    const walkPlay = () => screen.getByTestId("wp-play");
    expect(walkPlay()).toHaveAccessibleName("Pause");
    fireEvent.click(play());
    expect(play()).toHaveAccessibleName("Play");
    expect(walkPlay()).toHaveAccessibleName("Play");
    fireEvent.click(play());
    expect(walkPlay()).toHaveAccessibleName("Pause");
  });

  it("says how long each story plays, read from its script", () => {
    expect(STORIES.map(playsFor)).toEqual(
      STORIES.map((s) => Math.round(s.beats.slice(0, -1).reduce((t, b) => t + b.ms, 0) / 1000)),
    );
    expect(playsFor(STORIES[0]!)).toBe(48);
  });

  it("uses only 555 phone numbers and never calls anyone a scammer", () => {
    const words = JSON.stringify(STORIES.map((s) => s.beats.map((b) => b.say).concat(s.did)));
    expect(words).not.toMatch(/scam/i);
    open("sascha", true);
    expect(document.body.textContent).not.toMatch(/scammer/i);
    for (const n of (document.body.textContent ?? "").match(/\b\d{3}-\d{3}-\d{4}\b/g) ?? [])
      expect(n.slice(4, 7)).toBe("555");
  });
});
