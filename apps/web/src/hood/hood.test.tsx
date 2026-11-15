import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { matchRoute } from "../App";
import { teamTabFromSearch } from "../proofroom/TeamPanel";
import { AppShell } from "../shell/AppShell";
import { HoodPage } from "./HoodPage";
import {
  MERGED,
  PANELS,
  shownPanel,
  shownPanels,
  type Panel,
  type ShowLink,
  type Switch,
  type Switches,
} from "./panels";

const REPO = path.resolve(import.meta.dirname, "../../../..");
const ALL_OFF = Object.fromEntries(Object.keys(MERGED).map((k) => [k, false])) as Switches;
const ALL_ON = Object.fromEntries(Object.keys(MERGED).map((k) => [k, true])) as Switches;
const only = (s: Switch): Switches => ({ ...ALL_OFF, [s]: true });

const links = (p: Panel): ShowLink[] => [p.show, ...p.more];
/** True when the router has a pattern of its own for the path (Home is the fallback). */
function routed(href: string): boolean {
  const pathname = new URL(href, "https://snapback.test").pathname;
  return matchRoute(pathname).name !== "home" || /^\/(home\/?)?$/.test(pathname);
}

describe("the panels", () => {
  it("has one panel per sponsor track, in the order the judges were promised", () => {
    expect(PANELS.map((p) => p.sponsor)).toEqual([
      "CoStar",
      "LangChain",
      "Arlequin",
      "Photon",
      "Amazon",
    ]);
    expect(new Set(PANELS.map((p) => p.id)).size).toBe(PANELS.length);
  });

  it("gives every panel one sentence, 2 to 4 things used and at most 3 numbers, as shipped", () => {
    for (const p of shownPanels()) {
      expect(p.does.trim().split(/[.!?]\s/).length, p.id).toBe(1);
      expect(p.used.length, p.id).toBeGreaterThanOrEqual(2);
      expect(p.used.length, p.id).toBeLessThanOrEqual(4);
      expect(p.numbers.length, p.id).toBeLessThanOrEqual(3);
    }
    // The same holds with every switch on, so flipping one can never overfill a panel.
    for (const p of shownPanels(ALL_ON)) {
      expect(p.used.length, p.id).toBeLessThanOrEqual(4);
      expect(p.numbers.length, p.id).toBeLessThanOrEqual(3);
    }
  });

  it("every number, shown or waiting, has an n, a label and a source", () => {
    for (const p of PANELS) {
      for (const m of p.numbers) {
        const at = `${p.id}: ${m.value}`;
        expect(Number.isInteger(m.n) && m.n > 0, at).toBe(true);
        expect(m.unit.trim(), at).not.toBe("");
        expect(["LIVE", "FIXTURE", "SYNTHETIC"], at).toContain(m.label);
        expect(m.source, at).toMatch(/plan\/artifact\/board\.json|^eval\//);
      }
    }
  });

  it("a number from an eval file is shown only while that file is in the repo", () => {
    for (const p of shownPanels()) {
      for (const m of p.numbers) {
        if (m.evalFile) expect(existsSync(path.join(REPO, m.evalFile)), m.evalFile).toBe(true);
      }
    }
  });

  it("the real-photo numbers are the eval file's own rows", () => {
    const csv = readFileSync(path.join(REPO, "eval/locate_real.csv"), "utf8");
    expect(csv).toContain("locate_real,right_building,43,48,");
    expect(csv).toContain("locate_real,wrong_building,0,48,");
    expect(csv).toContain("locate_real,decoy_false_placement,0,30,");
    const costar = PANELS.find((p) => p.id === "costar")!;
    expect(costar.numbers.map((m) => m.value)).toEqual(["43 of 48", "0 of 30"]);
    expect(costar.numbers[0]!.what).toContain("0 in the wrong one");
  });

  it("every Show me link that is shown opens a route the router has", () => {
    for (const p of shownPanels()) {
      for (const l of links(p)) expect(routed(l.href), `${p.id}: ${l.href}`).toBe(true);
    }
  });

  it("the deep links open the exact state: the trace tab, a ring on a day, the sample case", () => {
    const show = Object.fromEntries(PANELS.map((p) => [p.id, p.show.href]));
    expect(matchRoute("/case/deep-sample/twin")).toEqual({ name: "twin", id: "deep-sample" });
    expect(show.langchain).toBe("/case/deep-sample/twin?team=trace");
    expect(teamTabFromSearch("?team=trace")).toBe("trace");
    expect(teamTabFromSearch("?team=meet")).toBe("team");
    expect(teamTabFromSearch("")).toBe("live");
    expect(teamTabFromSearch("?team=nonsense")).toBe("live");
    expect(show.arlequin).toBe("/investigate?day=45&ring=B");
    expect(show.photon).toBe("/proof-room?case=sample");
  });
});

describe("the switches", () => {
  it("ship off for work that is not on main, and hide every line waiting on them", () => {
    const waiting = PANELS.flatMap((p) => [...p.used, ...p.numbers, ...p.more]).filter(
      (x) => x.when,
    );
    expect(waiting.length).toBeGreaterThan(0);
    const shown = shownPanels(ALL_OFF).flatMap((p) => [...p.used, ...p.numbers, ...p.more]);
    expect(shown.filter((x) => x.when)).toEqual([]);
  });

  it("one switch shows exactly its own lines", () => {
    const arlequin = PANELS.find((p) => p.id === "arlequin")!;
    const off = shownPanel(arlequin, ALL_OFF);
    const on = shownPanel(arlequin, only("caseFile"));
    expect(off.used.map((u) => u.tech)).not.toContain("Case file");
    expect(on.used.map((u) => u.tech)).toContain("Case file");
    expect(on.more.map((l) => l.href)).toContain("/investigate/case/B");
    expect(on.numbers).toEqual(off.numbers);
    expect(shownPanel(arlequin, only("paraphraseEval")).numbers.length).toBe(
      off.numbers.length + 1,
    );
  });

  it("every switch has something waiting on it", () => {
    const used = new Set(
      PANELS.flatMap((p) => [...p.used, ...p.numbers, ...p.more]).map((x) => x.when),
    );
    for (const s of Object.keys(MERGED)) expect(used.has(s as Switch), s).toBe(true);
  });

  it("a switch cannot be on while its route or eval file is missing", () => {
    // Runs on the shipped switches: turning one on before its PR merges fails here or above.
    for (const p of shownPanels(MERGED)) {
      for (const l of links(p)) expect(routed(l.href), l.href).toBe(true);
      for (const m of p.numbers)
        if (m.evalFile) expect(existsSync(path.join(REPO, m.evalFile)), m.evalFile).toBe(true);
    }
  });
});

describe("the page", () => {
  it("draws each panel with its sentence, its numbers with n and label, and its Show me", () => {
    render(<HoodPage />);
    for (const p of shownPanels()) {
      const panel = screen.getByTestId(`hood-${p.id}`);
      expect(within(panel).getByRole("heading", { name: new RegExp(p.sponsor) })).toBeVisible();
      expect(within(panel).getByText(p.does)).toBeVisible();
      expect(within(panel).getByRole("link", { name: new RegExp(p.show.label) })).toHaveAttribute(
        "href",
        p.show.href,
      );
      const figures = within(panel).queryAllByTestId("hood-number");
      expect(figures.length).toBe(p.numbers.length);
      figures.forEach((f, i) => {
        const m = p.numbers[i]!;
        expect(f).toHaveTextContent(m.value);
        expect(f).toHaveTextContent(`n = ${m.n.toLocaleString("en-US")}`);
        expect(f).toHaveTextContent(m.label);
      });
    }
  });

  it("hides waiting lines and shows them when their switch is on", () => {
    const { unmount } = render(<HoodPage switches={ALL_OFF} />);
    expect(screen.queryByText("Case file")).toBeNull();
    expect(screen.queryByText("Re-planning")).toBeNull();
    expect(screen.queryByText("43 of 48")).toBeNull();
    unmount();
    render(<HoodPage switches={ALL_ON} />);
    expect(screen.getByText("Case file")).toBeVisible();
    expect(screen.getByText("Re-planning")).toBeVisible();
    expect(screen.getByText("43 of 48")).toBeVisible();
  });

  it("keeps to the rules: no AWS claim, no CoStar record figure, sponsors as text only", () => {
    const { container } = render(<HoodPage switches={ALL_ON} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\bAWS\b|Bedrock|SageMaker|Amazon Web Services/i);
    expect(text).not.toMatch(/\$\s?\d/); // no rent
    expect(text).not.toMatch(/\(?\d{3}\)?[ -]\d{3}-\d{4}/); // no phone
    expect(text).not.toMatch(/doesn.t detect scams/i);
    expect(text).not.toMatch(/[–—]/);
    // The only pictures are crops of our own screens, each with words for a screen reader.
    const imgs = [...container.querySelectorAll("img")];
    expect(imgs.length).toBe(PANELS.filter((p) => p.shot.kind === "screen").length);
    for (const img of imgs) {
      expect(img.closest(".uh-shot")).not.toBeNull();
      expect(img.getAttribute("alt")?.trim()).toBeTruthy();
    }
  });

  it("jumps to a sponsor's panel from the strip at the top", () => {
    render(<HoodPage />);
    const strip = screen.getByRole("navigation", { name: "Sponsors" });
    expect(
      within(strip)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(PANELS.map((p) => `#${p.id}`));
  });
});

describe("the screen pictures", () => {
  it("every panel shows the screen its Show me opens, or the sample thread, inside the link", () => {
    render(<HoodPage />);
    for (const p of PANELS) {
      const link = within(screen.getByTestId(`hood-${p.id}`)).getByRole("link", {
        name: new RegExp(p.show.label),
      });
      if (p.shot.kind === "screen") {
        expect(within(link).getByRole("img", { name: p.shot.alt })).toBeInTheDocument();
        expect(within(link).getByRole("img", { name: p.shot.alt })).toHaveAttribute("src");
      } else {
        expect(within(link).getByRole("img", { name: /sample iMessage thread/i })).toBeVisible();
      }
    }
  });
});

describe("the way in", () => {
  it("has its own route", () => {
    expect(matchRoute("/under-the-hood")).toEqual({ name: "hood" });
    expect(matchRoute("/under-the-hood/")).toEqual({ name: "hood" });
  });

  it("is linked from the footer of every page, and marked when you are on it", () => {
    const { unmount } = render(<AppShell section="home">x</AppShell>);
    expect(screen.getByRole("link", { name: "Under the hood" })).toHaveAttribute(
      "href",
      "/under-the-hood",
    );
    unmount();
    render(<AppShell section="hood">x</AppShell>);
    expect(screen.getByRole("link", { name: "Under the hood" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
