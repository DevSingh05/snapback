import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { matchRoute } from "../App";
import { bundledReplays, FEATURED_REPLAY_SLUG } from "./index";
import { ReplayIndexView } from "./ReplayIndexPage";
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
  it("lists every file in demo/replays, with title, pattern, source, date and link", () => {
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
        expect(row.getByRole("link", { name: r.source.name })).toHaveAttribute(
          "href",
          r.source.url,
        );
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
    // every finding for the step is shown, a risky ask in the card's word "Warning"
    expect(step.querySelectorAll("[data-status]")).toHaveLength(2);
    expect(within(step).getByText("Warning.")).toBeInTheDocument();
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

  it("ends every sourced replay with the replay sentence, the source and the link", () => {
    render(<ReplayView replay={sourced} lang="en" />);
    const foot = screen.getByTestId("replay-footer");
    expect(foot).toHaveTextContent(
      "Replay of a reported case (ABC13 Houston, Feb 15, 2025). The listing and house are re-created; no real names.",
    );
    expect(within(foot).getByRole("link", { name: "Source" })).toHaveAttribute(
      "href",
      "https://example.org/x",
    );
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
