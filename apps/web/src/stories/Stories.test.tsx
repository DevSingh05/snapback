import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { matchRoute } from "../App";
import { OneBox } from "../home/OneBox";
import { playsFor, STORIES } from "./stories";
import { StoriesPage } from "./StoriesPage";

const beatOn = () => document.querySelector(".st-stage")!.getAttribute("data-beat");
const play = () => screen.getByTestId("st-play");
const forward = () => screen.getByRole("button", { name: "Forward one step" });
const back = () => screen.getByRole("button", { name: "Back one step" });
const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

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
    const link = screen.getByTestId("ob-stories-link");
    expect(link).toHaveAttribute("href", "/stories");
    expect(link).toHaveTextContent("See it happen: 3 stories");
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
    fireEvent.click(screen.getByRole("button", { name: "Beat 4: Verdict" }));
    expect(beatOn()).toBe("verdict");
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
    fireEvent.click(screen.getByRole("button", { name: "Beat 4: Verdict" }));
    expect(screen.getByTestId("ob-verdict")).toHaveTextContent("Hold off for now");
    expect(screen.getByTestId("ob-verdict")).toHaveTextContent("Zelle before a viewing. Red flag.");
    fireEvent.click(screen.getByRole("button", { name: "Beat 5: Walk it" }));
    expect(screen.getByTestId("walk-player")).toBeInTheDocument();
    expect(screen.getAllByText(/Sample photo/).length).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole("button", { name: "Beat 6: Proof" }));
    expect((screen.getByLabelText("Message to send") as HTMLTextAreaElement).value).toContain(
      "code K7P4",
    );
    fireEvent.click(screen.getByRole("tab", { name: /master's student/i }));
    fireEvent.click(screen.getByRole("button", { name: "Beat 2: Ask" }));
    expect(screen.getByTestId("voice-listening")).toHaveTextContent("Is this landlord real?");
    fireEvent.click(screen.getByRole("button", { name: "Beat 5: Safer places" }));
    expect(screen.getAllByRole("link", { name: "Walk it first" }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("tab", { name: /just looking/i }));
    fireEvent.click(screen.getByRole("button", { name: "Beat 5: Tour request" }));
    expect((screen.getByLabelText("Tour request draft") as HTMLTextAreaElement).value).toContain(
      "I will not pay before I have seen the place",
    );
  });

  it("says how long each story plays, read from its script", () => {
    expect(STORIES.map(playsFor)).toEqual(
      STORIES.map((s) => Math.round(s.beats.slice(0, -1).reduce((t, b) => t + b.ms, 0) / 1000)),
    );
    expect(playsFor(STORIES[0]!)).toBe(39);
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
