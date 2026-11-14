import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { toneWord } from "../cardStrings";
import type { Card, CardLine, CardRowKind } from "../contracts";
import { CardView } from "./CardPage";

const card = cardHold as Card;
const text = () => document.body.textContent ?? "";

describe("locked wording", () => {
  it("uses the locked tone words, with the row exceptions", () => {
    expect(toneWord("ok", "place")).toBe("Matches");
    expect(toneWord("red_flag", "place")).toBe("Doesn't match");
    expect(toneWord("red_flag", "person")).toBe("Doesn't match");
    expect(toneWord("red_flag", "price")).toBe("Warning");
    expect(toneWord("not_shown", "person")).toBe("Not confirmed");
    expect(toneWord("hold", "person")).toBe("Not confirmed");
    expect(toneWord("hold", "place")).toBe("Warning");
    expect(toneWord("hold", "price")).toBe("Warning");
    expect(toneWord("not_checked", "price")).toBe("Not checked");
  });

  it("the Zelle line reads Warning and the waiting reply reads Not confirmed", () => {
    render(<CardView card={card} variant="result" />);
    const zelle = screen.getByText("Zelle before a viewing. Red flag.").closest("tr");
    expect(zelle).toHaveTextContent("Warning");
    const waiting = screen.getByText(/NOT SHOWN\. Being inside/).closest("tr");
    expect(waiting).toHaveTextContent("Not confirmed");
  });

  it.each([
    ["hold", "Hold off for now"],
    ["dont_pay", "Don't pay. Something here doesn't match."],
    ["verified", "Checks passed. Still follow the two rules."],
    ["unverified", "Could not place these photos"],
  ] as const)("headline for %s", (state, words) => {
    render(<CardView card={{ ...card, state }} variant="result" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(words);
  });

  it("drops the pre-lock words", () => {
    render(<CardView card={card} variant="result" />);
    expect(text()).not.toMatch(/Held up|On hold|Not shown\b|could not verify/);
  });
});

const withLine = (kind: CardRowKind, line: CardLine): Card => ({
  ...card,
  rows: card.rows.map((r) => (r.kind === kind ? { ...r, lines: [...r.lines, line] } : r)),
});

describe("ad vs record row", () => {
  const said =
    "Not confirmed. The ad says hardwood floors. CoStar's photos of this home are labelled carpet (as of CoStar's last research).";
  const claims: Card = {
    ...card,
    rows: [
      ...card.rows,
      { kind: "claims", lines: [{ label: "Ad vs record", text: said, tone: "not_shown" }] },
    ],
  };

  it("draws the fourth row under its own title, with the line as given and the Not confirmed word", () => {
    render(<CardView card={claims} variant="result" />);
    expect(screen.getByText("WHAT THE AD CLAIMS")).toBeInTheDocument();
    const tr = screen.getByText(said).closest("tr");
    expect(tr).toHaveTextContent("Ad vs record");
    expect(tr).toHaveTextContent("Not confirmed");
    expect(tr).not.toHaveTextContent("Doesn't match");
  });

  it("a card without the row shows no such title", () => {
    render(<CardView card={card} variant="result" />);
    expect(screen.queryByText("WHAT THE AD CLAIMS")).toBeNull();
  });

  it("the row does not change the headline", () => {
    render(<CardView card={claims} variant="result" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Hold off for now");
  });
});

describe("API lines render as given", () => {
  it("a recently_rented info line keeps its API tone and text, never Doesn't match", () => {
    const text = "Rented on Oct 4 per Homes.com, the lease may have been taken.";
    const c = withLine("place", { label: "Rental history", text, tone: "not_shown" });
    render(<CardView card={c} variant="result" />);
    const tr = screen.getByText(text).closest("tr");
    expect(tr).toHaveTextContent("Rental history");
    expect(tr).toHaveTextContent("Not confirmed");
    expect(tr).not.toHaveTextContent("Doesn't match");
  });

  it("a for-sale line renders Warning with the API words", () => {
    const text =
      "Listed for sale on Homes.com. Homes for sale are sometimes also offered for lease.";
    const c = withLine("place", { label: "For sale", text, tone: "hold" });
    render(<CardView card={c} variant="result" />);
    const tr = screen.getByText(text).closest("tr");
    expect(tr).toHaveTextContent("Warning");
    expect(tr).not.toHaveTextContent("Matches");
  });

  it("a Not listed for sale line is not turned into a green Matches", () => {
    const text = "Not listed for sale on Homes.com.";
    const c = withLine("place", { label: "For sale", text, tone: "not_shown" });
    render(
      <CardView
        card={{ ...c, for_sale: { status: "none", site: "Homes.com" } }}
        variant="result"
      />,
    );
    const tr = screen.getByText(text).closest("tr");
    expect(tr).toHaveTextContent("Not confirmed");
    expect(tr).not.toHaveTextContent("Matches");
  });

  it("adds no line the API did not send, even with card.for_sale set", () => {
    const base = render(<CardView card={card} variant="result" />).container.querySelectorAll("tr");
    document.body.innerHTML = "";
    const withSale = render(
      <CardView
        card={{
          ...card,
          for_sale: { status: "recently_rented", site: "Homes.com", changed_on: "2026-10-04" },
        }}
        variant="result"
      />,
    ).container.querySelectorAll("tr");
    expect(withSale).toHaveLength(base.length);
    expect(text()).not.toContain("This home was rented");
  });

  it.each(["ok", "red_flag", "not_shown", "hold", "not_checked"] as const)(
    "tone %s shows exactly the locked row-state word and the API text",
    (tone) => {
      const words = {
        ok: "Matches",
        red_flag: "Doesn't match",
        not_shown: "Not confirmed",
        hold: "Warning",
        not_checked: "Not checked",
      };
      const line = `API sentence for ${tone}.`;
      render(
        <CardView card={withLine("place", { label: "X", text: line, tone })} variant="result" />,
      );
      expect(screen.getByText(line).closest("tr")).toHaveTextContent(words[tone]);
    },
  );

  it("shows the history strip with dates, read from card.for_sale", () => {
    render(
      <CardView
        card={{
          ...card,
          for_sale: {
            status: "recently_rented",
            site: "Homes.com",
            listed_on: "2026-09-02",
            changed_on: "2026-10-04",
          },
        }}
        variant="result"
      />,
    );
    const strip = screen.getByTestId("history-strip");
    expect(strip).toHaveTextContent("Listed");
    expect(strip).toHaveTextContent("Sep 2");
    expect(strip).toHaveTextContent("Rented");
    expect(strip).toHaveTextContent("Oct 4");
  });

  it("no history strip without dates", () => {
    render(
      <CardView
        card={{ ...card, for_sale: { status: "none", site: "Homes.com" } }}
        variant="result"
      />,
    );
    expect(screen.queryByTestId("history-strip")).toBeNull();
  });
});
