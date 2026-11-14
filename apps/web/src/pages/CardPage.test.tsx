import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { Card } from "../contracts";
import { CardPage, CardView } from "./CardPage";

const card = cardHold as Card;

describe("CardView with card_hold.json", () => {
  it("shows PLACE, PERSON, PRICE in that order", () => {
    render(<CardView card={card} variant="result" />);
    const labels = screen.getAllByTestId("row-label").map((el) => el.textContent);
    expect(labels).toEqual(["PLACE", "PERSON", "PRICE"]);
  });

  it("shows the FIXTURE chip for fixture data and LIVE for live data", () => {
    const { unmount } = render(<CardView card={card} variant="result" />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    unmount();
    render(<CardView card={{ ...card, source: "live" }} variant="result" />);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("LIVE");
  });

  it("uses the exact strings from the card, including NOT SHOWN", () => {
    render(<CardView card={card} variant="result" />);
    expect(screen.getByText(/Being inside does not mean they may rent it/)).toBeInTheDocument();
    expect(screen.getByText(/NOT SHOWN\./)).toBeInTheDocument();
    expect(screen.getByText("Zelle before a viewing. Red flag.")).toBeInTheDocument();
  });

  it("lists what was not checked and the footer rules", () => {
    render(<CardView card={card} variant="result" />);
    const list = screen.getByTestId("not-checked");
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["ID", "lease", "ownership"]);
    expect(screen.getByText(/SNAPBACK never texts first or asks for money/)).toBeInTheDocument();
  });

  it("verify variant shows case id, expiry and a short summary", () => {
    render(<CardView card={card} variant="verify" />);
    expect(screen.getByTestId("case-id")).toHaveTextContent("7Q2M");
    expect(screen.getByTestId("expiry")).toBeInTheDocument();
    expect(screen.getByTestId("summary")).toBeInTheDocument();
  });

  it.each(["hold", "dont_pay", "unverified", "verified"] as const)(
    "headline for state %s never says safe, verified or scam",
    (state) => {
      render(<CardView card={{ ...card, state }} variant="result" />);
      const headline = screen.getByRole("heading", { level: 1 }).textContent ?? "";
      expect(headline.length).toBeGreaterThan(0);
      expect(headline.toLowerCase()).not.toMatch(/safe|verified|scam/);
    },
  );
});

describe("Lab placement", () => {
  it("is on the result page and hidden on the verify page", async () => {
    const result = render(<CardPage caseId={card.case_id} variant="result" />);
    expect(await result.findByTestId("lab-panel")).toBeInTheDocument();
    result.unmount();
    const verify = render(<CardPage caseId={card.case_id} variant="verify" />);
    await verify.findByTestId("case-id");
    expect(verify.queryByTestId("lab-panel")).toBeNull();
  });
});
