import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { matchRoute } from "../App";
import { bundledReplays, FEATURED_REPLAY_SLUG, findingWord, startsWithToneWord } from "./index";
import { ReplayIndexView } from "./ReplayIndexPage";
import { replayLang } from "./text";
import { ReplayNav } from "./ReplayNav";
import { ReplayPage, ReplayView } from "./ReplayPage";
import type { Replay } from "./types";

const mode = vi.hoisted(() => ({ live: false }));
vi.mock("../api", async (orig) => ({
  ...(await orig<typeof import("../api")>()),
  dataMode: () => (mode.live ? "live" : "fixture"),
  apiBase: () => (mode.live ? "/api" : undefined),
}));

const DEMO_DIR = path.resolve(import.meta.dirname, "../../../../demo/replays");
const FILES = readdirSync(DEMO_DIR).filter((f) => f.endsWith(".json"));

const sourced: Replay = {
  slug: "sourced",
  case_id: "replay-sourced",
  title: "A sourced case",
  pattern: "person",
  fictional: false,
  source: { name: "ABC13 Houston", url: "https://example.org/x", published_on: "2025-02-15" },
  amount_usd: 2200,
  steps: [
    { id: "listing", kind: "listing", reported_on: "", label: "Ad seen", detail: "Found it." },
    { id: "pay", kind: "payment", reported_on: "", label: "Pays", detail: "Moves in." },
  ],
  snapback: {
    verdict: "hold",
    findings: [
      { step_id: "listing", status: "matches", text: "Taken in this building." },
      { step_id: "listing", status: "red_flag", text: "Pay-first ask." },
    ],
  },
  cant_catch: "A private owner who rents through family.",
};

beforeEach(() => {
  mode.live = false;
});

describe("replay index", () => {
  it("lists every file in demo/replays, with title, pattern, source and date, and no source link", () => {
    expect(FILES.length).toBeGreaterThan(0);
    const demo = bundledReplays().filter((r) => FILES.includes(`${r.slug}.json`));
    expect(demo.map((r) => `${r.slug}.json`).sort()).toEqual([...FILES].sort());
    render(<ReplayIndexView replays={demo} lang="en" />);
    const rows = within(screen.getByTestId("replay-list")).getAllByRole("listitem");
    expect(rows).toHaveLength(FILES.length);
    for (const r of demo) {
      const row = within(rows.find((li) => li.dataset.slug === r.slug) as HTMLElement);
      expect(row.getByRole("link", { name: r.title })).toHaveAttribute("href", `/replay/${r.slug}`);
      if (r.source) {
        // The source is named in plain text and never linked (it can print a renter's name).
        expect(row.getByText(new RegExp(r.source.name))).toBeInTheDocument();
        expect(row.queryByRole("link", { name: r.source.name })).toBeNull();
        expect(row.getAllByRole("link")).toHaveLength(1);
      }
    }
  });

  it("writes the source and date in Spanish when asked", () => {
    render(<ReplayIndexView replays={[sourced]} lang="es" />);
    expect(screen.getByText(/15 feb 2025/)).toBeInTheDocument();
    expect(screen.getByText("La persona")).toBeInTheDocument();
  });

  it("does not hardcode any replay slug in the loader", () => {
    const loader = readFileSync(path.resolve(import.meta.dirname, "index.ts"), "utf8");
    for (const r of bundledReplays()) {
      if (r.slug !== FEATURED_REPLAY_SLUG) expect(loader).not.toContain(r.slug);
    }
    expect(loader).toContain("import.meta.glob");
  });

  it.each(bundledReplays().map((r) => [r.slug, r] as const))(
    "/replay/%s renders its timeline",
    (slug, r) => {
      render(<ReplayPage slug={slug} />);
      expect(screen.getByRole("heading", { level: 1, name: r.title })).toBeInTheDocument();
      expect(screen.getByTestId("timeline")).toBeInTheDocument();
      expect(screen.getByTestId("stop-marker")).toBeInTheDocument();
    },
  );

  it("routes /replay to the index and keeps /replay/<slug>", () => {
    expect(matchRoute("/replay")).toEqual({ name: "replays" });
    expect(matchRoute("/replay/")).toEqual({ name: "replays" });
    expect(matchRoute("/replay/abc")).toEqual({ name: "replay", slug: "abc" });
  });
});

describe("replay page", () => {
  it("shows What happened on the left and With SNAPBACK on the right of each step", () => {
    render(<ReplayView replay={sourced} lang="en" />);
    const step = screen.getByTestId("step-listing");
    expect(within(step).getByText("Ad seen")).toBeInTheDocument();
    expect(step.querySelector(".tl-real")).toHaveTextContent("What happened");
    expect(step.querySelector(".tl-snap")).toHaveTextContent("With SNAPBACK");
    // every finding for the step is shown; a red flag on a listing step is a mismatch
    expect(step.querySelectorAll("[data-status]")).toHaveLength(2);
    expect(within(step).getByText("Doesn't match.")).toBeInTheDocument();
  });

  it("leaves out the date of a step the source did not date", () => {
    render(<ReplayView replay={sourced} lang="en" />);
    expect(screen.getByTestId("step-listing").querySelector("time")).toBeNull();
  });

  it("says in Spanish what happened and what SNAPBACK showed", () => {
    render(<ReplayView replay={sourced} lang="es" />);
    expect(screen.getByTestId("step-listing").querySelector(".tl-real")).toHaveTextContent(
      "Lo que pasó",
    );
    expect(screen.getByTestId("step-listing").querySelector(".tl-snap")).toHaveTextContent(
      "Con SNAPBACK",
    );
  });

  it("ends every sourced replay with the replay sentence and the source, as plain text", () => {
    render(<ReplayView replay={sourced} lang="en" />);
    const foot = screen.getByTestId("replay-footer");
    expect(foot).toHaveTextContent(
      "Replay of a reported case (ABC13 Houston, Feb 15, 2025). The listing and house are re-created; no real names.",
    );
    // The source is cited as plain text: no link out of the replay page.
    expect(within(foot).queryByRole("link")).toBeNull();
    expect(screen.getByTestId("source-name")).toHaveTextContent("ABC13 Houston");
    expect(document.querySelector('a[href="https://example.org/x"]')).toBeNull();
  });

  it("writes that footer in Spanish", () => {
    render(<ReplayView replay={sourced} lang="es" />);
    expect(screen.getByTestId("replay-footer")).toHaveTextContent(
      "Repetición de un caso denunciado (ABC13 Houston, 15 feb 2025). El anuncio y la casa están recreados; no hay nombres reales.",
    );
  });

  it("says what SNAPBACK cannot catch, from the file", () => {
    render(<ReplayView replay={sourced} lang="en" />);
    expect(screen.getByText("A private owner who rents through family.")).toBeInTheDocument();
  });
});

describe("Run this case", () => {
  it("starts the staged case for the replay and opens its card", async () => {
    mode.live = true;
    const run = vi.fn().mockResolvedValue("ABCD");
    render(<ReplayView replay={sourced} lang="en" runCase={run} />);
    fireEvent.click(screen.getByRole("button", { name: "Run this case" }));
    await waitFor(() => expect(run).toHaveBeenCalledWith("replay-sourced"));
    await waitFor(() => expect(window.location.pathname).toBe("/case/ABCD"));
  });

  it("says so, and does not open anything, when the case could not start", async () => {
    mode.live = true;
    window.history.pushState({}, "", "/replay/sourced");
    const run = vi.fn().mockRejectedValue(new Error("down"));
    render(<ReplayView replay={sourced} lang="en" runCase={run} />);
    fireEvent.click(screen.getByRole("button", { name: "Run this case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not start the case");
    expect(window.location.pathname).toBe("/replay/sourced");
  });

  it("is switched off with a reason when no API is connected", () => {
    render(<ReplayView replay={sourced} lang="en" />);
    expect(screen.getByRole("button", { name: "Run this case" })).toBeDisabled();
    expect(screen.getByText(/needs the live API/)).toBeInTheDocument();
  });

  it("is not offered on a fictional replay", () => {
    render(<ReplayView replay={{ ...sourced, fictional: true, source: undefined }} lang="en" />);
    expect(screen.queryByRole("button", { name: "Run this case" })).toBeNull();
  });
});

describe("header tab", () => {
  it("opens the featured Conroe replay when its file exists, otherwise the index", () => {
    render(<ReplayNav />);
    const tab = screen.getByRole("link", { name: "Real case: Conroe" });
    const has = bundledReplays().some((r) => r.slug === FEATURED_REPLAY_SLUG);
    expect(tab).toHaveAttribute("href", has ? `/replay/${FEATURED_REPLAY_SLUG}` : "/replay");
    expect(screen.getByRole("link", { name: "All replays" })).toHaveAttribute("href", "/replay");
  });
});

describe("finding labels", () => {
  const DOUBLED =
    /^(matches|doesn't match|not confirmed|warning|not checked|not shown)\.\s+(matches|doesn't match|not confirmed|warning|not checked|not shown)\b/i;

  it.each(bundledReplays().map((r) => [r.slug, r] as const))(
    "%s: no finding line opens with two tone words",
    (_slug, r) => {
      render(<ReplayView replay={r} lang="en" />);
      const lines = Array.from(document.querySelectorAll("[data-status]"));
      expect(lines.length).toBeGreaterThan(0);
      for (const line of lines) {
        expect(line.textContent ?? "").not.toMatch(DOUBLED);
      }
    },
  );

  it("adds the tone word only when the text has none of its own", () => {
    expect(startsWithToneWord("Not confirmed. Owner of record: X.")).toBe(true);
    expect(startsWithToneWord("NOT SHOWN. Being inside does not mean they may rent it.")).toBe(
      true,
    );
    expect(startsWithToneWord("Not checked (our data has no rent).")).toBe(true);
    expect(startsWithToneWord("Taken in this building.")).toBe(false);
    render(<ReplayView replay={sourced} lang="en" />);
    expect(screen.getByText("Matches.")).toBeInTheDocument();
  });

  it("words a red flag by step kind", () => {
    expect(findingWord("red_flag", "hold_request")).toBe("Warning");
    expect(findingWord("red_flag", "payment")).toBe("Warning");
    expect(findingWord("red_flag", "chat")).toBe("Doesn't match");
    expect(findingWord("matches", "chat")).toBe("Matches");
  });

  it("shows the owner's own payment rule on the Conroe hold step, not Nothing flagged", () => {
    const conroe = bundledReplays().find((r) => r.slug === FEATURED_REPLAY_SLUG);
    if (!conroe) return;
    render(<ReplayView replay={conroe} lang="en" />);
    const hold = within(screen.getByTestId("step-hold"));
    expect(hold.getByText(/only accept applications and leasing funds/)).toBeInTheDocument();
    expect(hold.queryByText(/Nothing flagged/)).toBeNull();
  });
});

describe("English is pinned for the demo", () => {
  it("ignores the browser language and reads only ?lang=es", () => {
    expect(replayLang("")).toBe("en");
    expect(replayLang("?lang=es")).toBe("es");
    expect(replayLang("?lang=fr")).toBe("en");
  });
});

describe("index chip", () => {
  it("reads FIXTURE for team-made replays even when an API is connected", () => {
    mode.live = true;
    render(<ReplayIndexView replays={[sourced]} lang="en" />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });
});
