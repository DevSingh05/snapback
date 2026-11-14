import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { Card } from "../contracts";
import { CardView } from "../pages/CardPage";
import { getReplay } from "./index";
import { ReplayPage } from "./ReplayPage";
import fixture from "./fixtures/zelle-deposit-copied-tour.json";
import type { Replay } from "./types";

const SLUG = "zelle-deposit-copied-tour";

function steps() {
  return screen.getByTestId("timeline").querySelectorAll<HTMLElement>("[data-step-id]");
}

describe("ReplayPage", () => {
  it("lays the reported steps out in order, each dated", () => {
    render(<ReplayPage slug={SLUG} />);
    const real = Array.from(steps())
      .filter((el) => el.dataset.stepId !== "stop")
      .map((el) => el.dataset.stepId);
    expect(real).toEqual(["listing", "chat", "hold", "payment", "discovery"]);
    const first = screen.getByTestId("step-listing");
    expect(within(first).getByText("Mar 4, 2024")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("step-discovery")).getByText("Mar 12, 2024"),
    ).toBeInTheDocument();
  });

  it("places the stop marker before the payment step", () => {
    render(<ReplayPage slug={SLUG} />);
    const ids = Array.from(steps()).map((el) => el.dataset.stepId);
    expect(ids.indexOf("stop")).toBe(ids.indexOf("payment") - 1);
    const stop = screen.getByTestId("stop-marker");
    expect(stop).toHaveTextContent("Don't pay. Something here doesn't match.");
  });

  it("uses the hold words when the case verdict is hold", () => {
    const hold: Replay = {
      ...(fixture as Replay),
      slug: "hold-case",
      snapback: { ...(fixture as Replay).snapback, verdict: "hold" },
    };
    render(<ReplayPage slug="hold-case" replay={hold} />);
    expect(screen.getByTestId("stop-marker")).toHaveTextContent("Hold off for now");
    expect(screen.getByTestId("stop-marker")).not.toHaveTextContent("Don't pay");
  });

  it("says how much money was still in their account at the stop", () => {
    render(<ReplayPage slug={SLUG} />);
    expect(screen.getByTestId("amount-line")).toHaveTextContent(
      "$2,500 was still in their account here",
    );
  });

  it("labels a fictional replay as fictional, with no source link and no date", () => {
    render(<ReplayPage slug={SLUG} />);
    expect(screen.getByText("Fictional example")).toBeInTheDocument();
    expect(screen.queryByText("Re-created from a public report")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByTestId("source-date")).toBeNull();
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect("source" in fixture).toBe(false);
  });

  it("labels a real replay as re-created from a public report, with source link and date", () => {
    const real: Replay = {
      ...(fixture as Replay),
      slug: "real-case",
      fictional: false,
      source: {
        name: "Example Gazette",
        url: "https://example.org/story",
        published_on: "2025-02-03",
      },
    };
    render(<ReplayPage slug="real-case" replay={real} />);
    expect(screen.getByText("Re-created from a public report")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Example Gazette" })).toHaveAttribute(
      "href",
      "https://example.org/story",
    );
    expect(screen.getByTestId("source-date")).toHaveTextContent("Feb 3, 2025");
  });

  it("uses locked row words for findings and colours them by state", () => {
    render(<ReplayPage slug={SLUG} />);
    const listing = within(screen.getByTestId("step-listing"));
    expect(listing.getByText("Doesn't match.")).toBeInTheDocument();
    expect(listing.getByText(/filmed in a different home/)).toBeInTheDocument();
    const states = Array.from(document.querySelectorAll<HTMLElement>("[data-status]")).map(
      (el) => el.dataset.status,
    );
    expect(states).toEqual(["doesnt_match", "not_confirmed", "warning"]);
    expect(document.body.textContent).not.toMatch(/Red flag|Person not shown/);
  });

  it("stops before the first payment step even if stop_before is missing", () => {
    const r = JSON.parse(JSON.stringify(fixture)) as Replay;
    delete r.snapback.stop_before;
    render(<ReplayPage slug={SLUG} replay={r} />);
    const ids = Array.from(steps()).map((el) => el.dataset.stepId);
    expect(ids.indexOf("stop")).toBe(ids.indexOf("payment") - 1);
  });

  it("shows a visible error when there is no payment step or stop_before disagrees", () => {
    const base = fixture as Replay;
    const none: Replay = { ...base, steps: base.steps.filter((s) => s.kind !== "payment") };
    const { unmount } = render(<ReplayPage slug={SLUG} replay={none} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/no payment step/);
    expect(screen.queryByTestId("stop-marker")).toBeNull();
    unmount();
    const wrong: Replay = { ...base, snapback: { ...base.snapback, stop_before: "chat" } };
    render(<ReplayPage slug={SLUG} replay={wrong} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/stop_before/);
  });

  it("shows no victim name and no street address", () => {
    const { container } = render(<ReplayPage slug={SLUG} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(
      /\d{2,5}\s+[A-Z][a-z]+\s+(St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Lane|Ln)\b/,
    );
    expect(Object.keys(fixture).some((k) => /name|victim|address/i.test(k))).toBe(false);
    expect(text).not.toMatch(/victim/i);
  });

  it("shows a 404 for an unknown slug", () => {
    render(<ReplayPage slug="no-such-replay" />);
    expect(screen.getByRole("heading", { name: /not found/i })).toBeInTheDocument();
    expect(screen.queryByTestId("timeline")).toBeNull();
  });

  it("opens from the card page for its case", () => {
    render(<CardView card={cardHold as Card} variant="result" />);
    const link = screen.getByRole("link", { name: "See a fictional example" });
    expect(link).toHaveAttribute("href", `/replay/${SLUG}`);
    expect(getReplay(SLUG)).toBeDefined();
  });
});
