import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { proofLines, toneWord } from "../cardStrings";
import type { Card, CardProofs, ForSaleMatch } from "../contracts";
import { CardView } from "./CardPage";

const card = cardHold as Card;
const text = () => document.body.textContent ?? "";

const price = (over: Partial<NonNullable<CardProofs["price"]>>): CardProofs => ({
  price: { status: "within_range", unit: "not_checked", per_bed: false, ...over },
});
const authority = (over: Partial<NonNullable<CardProofs["authority"]>>): CardProofs => ({
  authority: {
    status: "unknown",
    office_phone_match: "not_checked",
    link_domain: "not_checked",
    ...over,
  },
});

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

describe("place, person and price proof lines", () => {
  const cases: [string, CardProofs, string, (ForSaleMatch | null)?][] = [
    [
      "for sale",
      {},
      "This home is listed for sale on Homes.com, not for rent.",
      { status: "active", site: "Homes.com", listed_on: "2026-09-02" },
    ],
    [
      "recently rented",
      {},
      "This home was rented on Oct 4.",
      { status: "recently_rented", site: "Homes.com", changed_on: "2026-10-04" },
    ],
    ["for sale none", {}, "Not listed for sale", { status: "none", site: "Homes.com" }],
    ["for sale unchecked", {}, "Not checked (no for-sale lookup", null],
    [
      "unit missing",
      { ...price({ unit: "not_on_record" }), unit_label: "4B" },
      "Unit 4B is not on this building's list",
    ],
    [
      "unit missing, unnamed",
      price({ unit: "not_on_record" }),
      "This unit is not on this building's list",
    ],
    ["beds mismatch", price({ unit: "beds_mismatch" }), "bedrooms in the listing do not match"],
    ["unit on record", price({ unit: "on_record" }), "is on this building's list"],
    ["unit unchecked", price({ unit: "not_checked" }), "Not checked (the listing names no unit"],
    [
      "phone differs",
      authority({ office_phone_match: "no" }),
      "This number is not the leasing office's on record. Agents often use their own",
    ],
    [
      "phone matches",
      authority({ office_phone_match: "yes" }),
      "The phone in the listing is the leasing office on record",
    ],
    [
      "phone unchecked",
      authority({}),
      "Not checked (the listing or the record has no phone number)",
    ],
    [
      "lookalike link",
      authority({ link_domain: "lookalike" }),
      "This link looks like the building's site but is a different address",
    ],
    ["own link", authority({ link_domain: "matches" }), "This link is the building's own site"],
    ["other link", authority({ link_domain: "other" }), "says nothing either way"],
    ["link unchecked", authority({}), "Not checked (the listing has no link"],
    [
      "call the manager",
      authority({ manager_on_record: "Oak Court Management" }),
      "Call Oak Court Management yourself.",
    ],
    [
      "per bed guard",
      price({ status: "not_checked", per_bed: true }),
      "Priced per bed here, so the rent was not compared.",
    ],
    [
      "band within",
      price({ listed_rent: 1850, record_min: 1700, record_max: 2100 }),
      "In line with the rents on record for this building. Listed $1,850; the record shows $1,700 to $2,100.",
    ],
    [
      "band below",
      price({ status: "below_range", listed_rent: 900, record_min: 1700, record_max: 2100 }),
      "Below the rents on record for this building. Ask why; discounts happen. Listed $900; the record shows $1,700 to $2,100.",
    ],
    [
      "band unchecked",
      price({ status: "not_checked" }),
      "Not checked (our data has no rent for this building)",
    ],
  ];

  it.each(cases)("renders %s", (_name, proofs, words, forSale) => {
    render(<CardView card={{ ...card, for_sale: forSale }} variant="result" proofs={proofs} />);
    expect(text()).toContain(words);
  });

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
    expect(screen.getByText("Rental history")).toBeInTheDocument();
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

  it("proof mismatches read Doesn't match, and a rent proof replaces the API line", () => {
    render(
      <CardView
        card={{ ...card, for_sale: { status: "active", site: "Homes.com" } }}
        variant="result"
        proofs={{
          ...authority({ office_phone_match: "no", link_domain: "lookalike" }),
          price: { status: "within_range", per_bed: false, unit: "not_checked" },
        }}
      />,
    );
    for (const re of [/listed for sale on Homes\.com/, /looks like the building/]) {
      expect(screen.getByText(re).closest("tr")).toHaveTextContent("Doesn't match");
    }
    // A phone that is not the office's is Not confirmed, never a mismatch (#121): agents and
    // locators often post with their own number.
    const phone = screen.getByText(/number is not the leasing office's on record/).closest("tr");
    expect(phone).toHaveTextContent("Not confirmed");
    expect(phone).not.toHaveTextContent("Doesn't match");
    expect(screen.getAllByText("Rent vs record")).toHaveLength(1);
  });

  it("skips Call X yourself when the API row already names the manager", () => {
    const withCall: Card = {
      ...card,
      rows: card.rows.map((r) =>
        r.kind === "person"
          ? {
              ...r,
              lines: [
                ...r.lines,
                {
                  label: "Next step",
                  text: "Not confirmed. Call Oak Court Management on a number you look up yourself before you pay.",
                  tone: "not_shown" as const,
                },
              ],
            }
          : r,
      ),
    };
    render(
      <CardView
        card={withCall}
        variant="result"
        proofs={authority({ manager_on_record: "Oak Court Management" })}
      />,
    );
    expect(screen.queryByText("Call Oak Court Management yourself.")).toBeNull();
  });

  it("every proof line avoids safe, verified and scam", () => {
    const all: CardProofs = {
      price: {
        status: "below_range",
        listed_rent: 900,
        record_min: 1700,
        record_max: 2100,
        per_bed: false,
        unit: "beds_mismatch",
      },
      authority: {
        status: "mismatch",
        manager_on_record: "Oak Court Management",
        office_phone_match: "no",
        link_domain: "lookalike",
      },
      unit_label: "4B",
    };
    const lines = proofLines(all, { status: "active", site: "Homes.com" }).flatMap((r) =>
      r.lines.map((l) => l.text),
    );
    expect(lines.length).toBeGreaterThan(5);
    for (const l of lines) expect(l.toLowerCase()).not.toMatch(/safe|verified|scam/);
  });

  it("never renders digits of a phone, even if one is passed in by mistake", () => {
    const sneaky = {
      authority: {
        status: "unknown",
        manager_on_record: "Oak Court Management",
        office_phone_match: "no",
        link_domain: "not_checked",
        phone: "(713) 555-0142",
        site_phone_hash: "5557140142",
      },
    } as unknown as CardProofs;
    render(<CardView card={card} variant="result" proofs={sneaky} />);
    expect(text()).not.toMatch(/\d{3}[\s().-]*\d{3,4}/);
    expect(text()).not.toContain("0142");
    expect(text()).toContain("Call Oak Court Management yourself.");
  });
});
