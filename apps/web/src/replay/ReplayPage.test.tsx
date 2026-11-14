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

  it("labels the header and links the source with its date", () => {
    render(<ReplayPage slug={SLUG} />);
    expect(screen.getByText("Re-created from a public report")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /FTC Consumer Advice/ });
    expect(link).toHaveAttribute("href", "https://consumer.ftc.gov/articles/rental-listing-scams");
    expect(screen.getByTestId("source-date")).toHaveTextContent("Jan 1, 2024");
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getByText(/Fictional example/)).toBeInTheDocument();
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
    const link = screen.getByRole("link", { name: /re-created from a public report/i });
    expect(link).toHaveAttribute("href", `/replay/${SLUG}`);
    expect(getReplay(SLUG)).toBeDefined();
  });
});
