import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HouseGlyph, Wordmark } from "../components/HouseGlyph";
import { SourceChip } from "../components/SourceChip";
import {
  ChapterStrip,
  DEFAULT_MARK,
  EmptyRows,
  Loading,
  MARK_PATHS,
  Mark,
  PathRail,
  Photo,
  Problem,
  RecordLine,
  STOCK,
  State,
  chapterColumns,
  photoFor,
  recordLineText,
} from ".";
import { Story } from "./Story";

const WEB = join(__dirname, "..", "..");

describe("the mark", () => {
  it("is the offset house by default, with the other options one prop away", () => {
    expect(DEFAULT_MARK).toBe("a");
    const { container } = render(<Mark />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveClass("ui-mark-a");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect([...svg.querySelectorAll("path")].map((p) => p.getAttribute("d"))).toEqual(
      MARK_PATHS.a.map((p) => p.d),
    );
    for (const v of ["b", "c"] as const) {
      const other = render(<Mark variant={v} />).container.querySelector("svg")!;
      expect(other).toHaveClass(`ui-mark-${v}`);
      expect(other.querySelectorAll("path")).toHaveLength(MARK_PATHS[v].length);
    }
  });

  it("is what the old HouseGlyph and Wordmark names now draw", () => {
    const glyph = render(<HouseGlyph className="notice-house" lit={false} />).container;
    expect(glyph.querySelector("svg")).toHaveClass(
      "ui-mark",
      "house",
      "notice-house",
      "ui-mark-off",
    );
    const word = render(<Wordmark />).container;
    expect(word.querySelector(".wordmark svg.ui-mark-a")).not.toBeNull();
    expect(word).toHaveTextContent("SNAPBACK");
  });

  it("ships as a favicon that switches its ink half in a dark tab", () => {
    const icon = readFileSync(join(WEB, "public", "favicon.svg"), "utf8");
    for (const p of MARK_PATHS.a) expect(icon).toContain(p.d);
    expect(icon).toMatch(/prefers-color-scheme:\s*dark/);
    expect(readFileSync(join(WEB, "index.html"), "utf8")).toContain('href="/favicon.svg"');
  });
});

describe("LIVE or FIXTURE", () => {
  it("keeps the source chip's words and hook for every screen that uses it", () => {
    render(<SourceChip source="live" />);
    const chip = screen.getByTestId("source-chip");
    expect(chip).toHaveTextContent("LIVE");
    expect(chip).toHaveClass("ui-tag", "ui-tag-live");
    expect(render(<SourceChip source="fixture" />).container).toHaveTextContent("FIXTURE");
  });
});

describe("state and record line", () => {
  it("always prints the state word beside the square", () => {
    render(<State kind="mismatch" />);
    expect(screen.getByText("Doesn't match")).toHaveAttribute("data-state", "mismatch");
    expect(render(<State kind="ok">Checks passed</State>).container).toHaveTextContent(
      "Checks passed",
    );
  });

  it("names the source, prints a date only when one was given, then LIVE or FIXTURE", () => {
    expect(recordLineText({ source: "costar", date: "Nov 2026", live: true })).toBe(
      "COSTAR RECORD · AS OF Nov 2026 · LIVE",
    );
    expect(recordLineText({ source: "license", date: null, live: "fixture" })).toBe(
      "TEXAS LICENSE LIST · FIXTURE",
    );
    expect(recordLineText({ source: "scan", date: "  " })).toBe("3D SCAN");
    render(<RecordLine source="county" live={false} />);
    expect(screen.getByTestId("record-line")).toHaveTextContent("COUNTY RECORD · FIXTURE");
  });
});

describe("photo", () => {
  it("stamps every photo with where it came from", () => {
    const { container } = render(<Photo src="/x.webp" alt="A kitchen" stamp="sample" />);
    expect(screen.getByAltText("A kitchen")).toHaveAttribute("src", "/x.webp");
    expect(container.querySelector(".ui-stamp")).toHaveTextContent("SAMPLE PHOTO");
    const live = render(<Photo src="/api/frame" alt="Scan" stamp="scan" stampNote="Oct 2026" />);
    expect(live.container.querySelector(".ui-stamp-live")).toHaveTextContent(
      "FROM THE 3D SCAN · LIVE · Oct 2026",
    );
  });

  it("says drawn stand-in when there is no photo, whatever stamp was asked for", () => {
    const { container } = render(<Photo src={null} alt="A drawing" stamp="record" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector(".ui-stamp")).toHaveTextContent("DRAWN STAND-IN");
    expect(screen.getByRole("img", { name: "A drawing" })).toBeInTheDocument();
  });

  it("picks by priority: upload, scan frame, kit photo, stock, drawing", () => {
    const all = {
      upload: "blob:u",
      scanFrame: "/api/s",
      kitPhoto: "/api/k",
      source: "live",
    } as const;
    expect(photoFor(all)).toMatchObject({ src: "blob:u", stamp: "ad" });
    expect(photoFor({ ...all, upload: null })).toMatchObject({ src: "/api/s", stamp: "scan" });
    expect(photoFor({ ...all, upload: null, scanFrame: null })).toMatchObject({
      src: "/api/k",
      stamp: "record",
    });
    expect(photoFor({ source: "live", seed: "p1" })).toMatchObject({ stamp: "sample" });
    expect(photoFor({ stock: null })).toMatchObject({ src: null, stamp: "drawn", credit: null });
  });

  it("never shows sponsor imagery on a FIXTURE run, and keeps one stock photo per seed", () => {
    const fixture = photoFor({
      scanFrame: "/api/s",
      kitPhoto: "/api/k",
      source: "fixture",
      seed: 7,
    });
    expect(fixture.stamp).toBe("sample");
    expect(STOCK.interior.map((p) => p.src)).toContain(fixture.src);
    expect(photoFor({ seed: 7 }).src).toBe(fixture.src);
    expect(photoFor({ stock: "exterior", seed: "a" }).credit).toBeTruthy();
  });
});

describe("path rail", () => {
  it("marks steps done, next and later, with one accent step", () => {
    render(
      <PathRail next={2} hrefs={{ 1: "/case/1" }}>
        Case 7Q2M
      </PathRail>,
    );
    const rail = screen.getByRole("navigation", { name: "Your path" });
    const items = within(rail).getAllByRole("listitem");
    expect(items.map((li) => li.dataset.status)).toEqual(["done", "next", "later", "later"]);
    expect(items.map((li) => li.textContent)).toEqual([
      "01Check (done)",
      "02Walk it first (next step)",
      "03Safer places",
      "04Tour request",
    ]);
    expect(within(rail).getByRole("link", { name: /Check/ })).toHaveAttribute("href", "/case/1");
    expect(rail.querySelectorAll('[aria-current="step"]')).toHaveLength(1);
    expect(rail).toHaveTextContent("Case 7Q2M");
  });

  it("shows all four done when nothing is next", () => {
    const { container } = render(<PathRail next={null} />);
    expect(container.querySelectorAll(".ui-rail-done")).toHaveLength(4);
    expect(container.querySelector('[aria-current="step"]')).toBeNull();
  });
});

describe("chapter strip", () => {
  const rooms = [
    { id: "a", label: "Living room", duration: 30 },
    { id: "b", label: "Kitchen", duration: 10 },
  ];

  it("sizes segments by duration only when every chapter has one", () => {
    expect(chapterColumns(rooms)).toBe("minmax(0, 30fr) minmax(0, 10fr)");
    expect(chapterColumns([rooms[0]!, { id: "b", label: "Kitchen" }])).toBe(
      "minmax(0, 1fr) minmax(0, 1fr)",
    );
  });

  it("marks the current chapter and reports a pick", () => {
    const onSelect = vi.fn();
    render(<ChapterStrip chapters={rooms} current="b" onSelect={onSelect} />);
    expect(screen.getByRole("button", { name: "Kitchen" })).toHaveAttribute("aria-current", "step");
    fireEvent.click(screen.getByRole("button", { name: "Living room" }));
    expect(onSelect).toHaveBeenCalledWith("a");
  });

  it("is a plain list when nothing can be picked", () => {
    render(<ChapterStrip chapters={rooms} current="a" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Living room")).toHaveAttribute("aria-current", "step");
  });
});

describe("empty, loading and problem", () => {
  it("shows an empty list as a sentence, two example rows and one action", () => {
    const onExample = vi.fn();
    const onClick = vi.fn();
    render(
      <EmptyRows
        message="No researched places fit these filters."
        examples={["One", "Two", "Three"]}
        onExample={onExample}
        action={{ label: "Clear filters", onClick }}
      />,
    );
    expect(screen.getByText("No researched places fit these filters.")).toBeInTheDocument();
    expect(screen.queryByText("Three")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Two" }));
    expect(onExample).toHaveBeenCalledWith("Two");
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClick).toHaveBeenCalled();
  });

  it("says what is loading in words, with no spinner and no number", () => {
    render(<Loading label="Reading the ad" rows={4} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Reading the ad");
    expect(status.textContent).not.toMatch(/\d|%/);
    expect(status.querySelectorAll(".ui-loading-row")).toHaveLength(4);
  });

  it("shows a problem as Not checked, never as a pass or a warning", () => {
    render(
      <Problem
        message="We can't reach the record right now. Nothing was checked. Try again."
        action={{ label: "Try again", href: "/retry" }}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("Not checked")).toHaveAttribute("data-state", "unchecked");
    expect(alert.querySelector(".ui-state-ok, .ui-state-warn")).toBeNull();
    expect(within(alert).getByRole("link", { name: "Try again" })).toHaveAttribute(
      "href",
      "/retry",
    );
  });
});

describe("the primitives page", () => {
  it("renders every primitive, in Day and in Dusk", () => {
    for (const theme of ["light", "dark"]) {
      document.documentElement.dataset.theme = theme;
      const { container, unmount } = render(<Story />);
      for (const cls of [
        "ui-mark-a",
        "ui-mark-b",
        "ui-mark-c",
        "ui-lockup",
        "ui-tag-live",
        "ui-tag-fixture",
        "ui-state-ok",
        "ui-state-unchecked",
        "ui-record",
        "ui-photo",
        "ui-stamp",
        "ui-pin",
        "ui-rail",
        "ui-chapters",
        "ui-empty",
        "ui-loading",
        "ui-problem",
      ])
        expect(container.querySelector(`.${cls}`), `${theme} .${cls}`).not.toBeNull();
      unmount();
    }
    delete document.documentElement.dataset.theme;
  });
});

describe("stock photos", () => {
  it("credits every committed photo and commits no kit photo", () => {
    const credits = readFileSync(join(WEB, "src", "assets", "CREDITS.md"), "utf8");
    const tracked = execFileSync("git", ["ls-files", "--", "src/assets", "public"], {
      cwd: WEB,
      encoding: "utf8",
    })
      .split("\n")
      .filter(Boolean);
    const photos = tracked.filter((f) => /\.(webp|jpe?g|png|avif)$/i.test(f));
    expect(photos.length).toBeGreaterThan(0);
    for (const f of photos) expect(credits, f).toContain(f.split("/").pop()!);
    expect(tracked.filter((f) => /kit|costar|matterport|vexcel/i.test(f))).toEqual([]);
    expect(credits).not.toMatch(/[\u2013\u2014]/);
  });
});
