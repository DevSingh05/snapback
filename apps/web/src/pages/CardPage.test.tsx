import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { Card } from "../contracts";
import { CardPage, CardView } from "./CardPage";

const card = cardHold as Card;

describe("CardView with card_hold.json", () => {
  it("names the kind of every check, failing ones first, then passing, then not checked", () => {
    render(<CardView card={card} variant="result" />);
    const labels = screen.getAllByTestId("row-label").map((el) => el.textContent);
    expect(labels).toEqual(["PERSON", "PRICE", "PLACE", "PERSON", "PRICE"]);
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
    // The same lines are in the two lists above; the ledger rows are the ones checked here.
    const rows = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    expect(rows.some((t) => t.includes("Being inside does not mean they may rent it"))).toBe(true);
    expect(rows.some((t) => t.includes("NOT SHOWN."))).toBe(true);
    expect(rows.some((t) => t.includes("Zelle before a viewing. Red flag."))).toBe(true);
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
  it("is on neither the result page nor the verify page", async () => {
    // Conductor ruling, Sat 18:2x: the Lab chart block leaves the case result entirely.
    const result = render(<CardPage caseId={card.case_id} variant="result" />);
    await result.findByTestId("case-id");
    expect(result.queryByTestId("lab-panel")).toBeNull();
    result.unmount();
    const verify = render(<CardPage caseId={card.case_id} variant="verify" />);
    await verify.findByTestId("case-id");
    expect(verify.queryByTestId("lab-panel")).toBeNull();
  });
});
