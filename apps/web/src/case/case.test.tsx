import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { STATE_WORD } from "../cardStrings";
import type { Card, VerdictState } from "../contracts";
import { CardPage } from "../pages/CardPage";
import record from "../../../../fixtures/demo/a/property_record.json";
import {
  AnnotatedAd,
  CaseResult,
  Ledger,
  PriceBar,
  ProofPair,
  RealListing,
  SaferTiles,
  flaggedLines,
  hostLink,
  markRuns,
  outLink,
  priceScale,
  realListingLink,
  saferTiles,
  stampPlace,
  type ProofCard,
  type RealListingData,
  type SaferPlace,
} from ".";

const card = cardHold as Card;
const HERE = __dirname;
const sources = readdirSync(HERE)
  .filter((name) => /\.(ts|tsx|css|html)$/.test(name) && !name.includes(".test."))
  .map((name) => ({ name, text: readFileSync(join(HERE, name), "utf8") }));
const css = readFileSync(join(HERE, "case.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

describe("code sets the words", () => {
  it("no verdict sentence or rule is typed inside case/", () => {
    expect(sources.length).toBeGreaterThanOrEqual(8);
    // Every headline in cardStrings.ts, plus the fragments a retyped one would contain.
    const banned = [
      ...Object.values(STATE_WORD),
      "Don't pay",
      "Dont pay",
      "Hold off",
      "Checks passed",
      "Could not place",
      "doesn't match.",
      "never pay",
      "two rules",
    ].map((s) => s.toLowerCase());
    for (const { name, text } of sources) {
      const lower = text.toLowerCase();
      for (const words of banned) expect(lower.includes(words), `${name}: "${words}"`).toBe(false);
    }
  });

  it("writes no em or en dash and never the banned words", () => {
    for (const { name, text } of sources) {
      expect(text, name).not.toMatch(/[–—]/);
      expect(text.toLowerCase(), name).not.toMatch(/scam|\bsafe\b/);
    }
  });

  it.each(Object.keys(STATE_WORD) as VerdictState[])(
    "the %s headline is the cardStrings one, with its own bar colour",
    (state) => {
      render(<CaseResult card={{ ...card, state }} />);
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(STATE_WORD[state]);
      const tone = { dont_pay: "dont-pay", hold: "hold", verified: "ok", unverified: "slate" };
      expect(screen.getByTestId("case-band")).toHaveAttribute("data-verdict", tone[state]);
    },
  );

  it("the one why sentence is the worst failing API line, as given, and the rest are counted", () => {
    render(<CaseResult card={card} />);
    expect(flaggedLines(card).map((l) => l.text)).toEqual([
      "Zelle before a viewing. Red flag.",
      "NOT SHOWN. Being inside does not mean they may rent it.",
    ]);
    const why = screen.getByTestId("case-why");
    expect(why).toHaveTextContent("Payment ask. Zelle before a viewing. Red flag.");
    expect(why).toHaveTextContent("1 more below");
    expect(why).not.toHaveTextContent("NOT SHOWN");
  });

  it("a card with nothing flagged shows no why line", () => {
    const clean: Card = {
      ...card,
      rows: card.rows.map((r) => ({ ...r, lines: r.lines.filter((l) => l.tone === "ok") })),
    };
    render(<CaseResult card={clean} />);
    expect(screen.queryByTestId("case-why")).toBeNull();
  });

  it("prints the two rules from the card's footer", () => {
    render(<CaseResult card={card} />);
    const rules = screen.getByTestId("case-rules");
    for (const line of card.footer) expect(rules).toHaveTextContent(line);
  });
});

describe("a failed check", () => {
  it("shows the slate band and a problem row, never a pass", async () => {
    // Fixture mode knows one case; any other code fails to load.
    render(<CardPage caseId="ZZZZ" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-failed")).toBeInTheDocument());
    expect(screen.getByTestId("case-band")).toHaveAttribute("data-verdict", "slate");
    expect(screen.getByTestId("problem")).toHaveTextContent("Not checked");
    expect(document.body.textContent).not.toMatch(/Matches|Checks passed|Warning/);
    expect(screen.queryByTestId("case-primary")).toBeNull();
  });
});

describe("one primary button", () => {
  it("the result has exactly one, in the band", () => {
    render(<CaseResult card={card} />);
    expect(document.querySelectorAll(".case-primary")).toHaveLength(1);
    const primary = screen.getByTestId("case-primary");
    expect(primary).toHaveTextContent("Walk it first");
    expect(primary).toHaveAttribute("href", "/case/7Q2M/twin");
    expect(screen.getByTestId("case-band")).toContainElement(primary);
  });

  it("with no photo placed the one primary is the safer places, not a walk", () => {
    const unplaced: Card = {
      ...card,
      state: "unverified",
      rows: card.rows.filter((r) => r.kind !== "place"),
    };
    render(<CaseResult card={unplaced} />);
    expect(document.querySelectorAll(".case-primary")).toHaveLength(1);
    expect(screen.getByTestId("case-primary")).toHaveTextContent("Find me safer places");
  });

  it("the verify page has none, and one LIVE or FIXTURE tag", () => {
    render(<CaseResult card={card} variant="verify" />);
    expect(document.querySelectorAll(".case-primary")).toHaveLength(0);
    expect(screen.getAllByTestId("source-chip")).toHaveLength(1);
  });
});

describe("what to do now", () => {
  it("a case that did not pass hands off to the Apartments.com search, labelled as a search", () => {
    render(<CaseResult card={card} />);
    const link = screen.getByTestId("case-handoff");
    expect(link).toHaveTextContent("Search verified listings on Apartments.com");
    expect(link).toHaveAttribute("href", "https://www.apartments.com/houston-tx/");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("a case that passed has no hand-off", () => {
    render(<CaseResult card={{ ...card, state: "verified" }} />);
    expect(screen.queryByTestId("case-handoff")).toBeNull();
  });
});

describe("beside the ledger", () => {
  it("the real listing, else the pasted ad, sits in the side column; else the ledger is alone", () => {
    const alone = render(<CaseResult card={card} />);
    expect(document.querySelector(".case-side")).toBeNull();
    expect(document.querySelector(".case-body-with-side")).toBeNull();
    alone.unmount();
    const ad = render(<CaseResult card={card} adText="2 bed near downtown." />);
    expect(document.querySelector(".case-side")).toHaveAttribute("data-side", "ad");
    expect(document.querySelector(".case-side")).toContainElement(screen.getByTestId("case-ad"));
    ad.unmount();
    render(
      <CaseResult
        card={card}
        adText="2 bed near downtown."
        realListing={{ case_id: "7Q2M", source: "fixture", building_name: "Fixture Court" }}
      />,
    );
    const side = document.querySelector(".case-body-with-side > .case-side")!;
    expect(side).toHaveAttribute("data-side", "real");
    expect(side.firstElementChild).toBe(screen.getByTestId("case-real"));
  });

  it("keeps every character of a NOT SHOWN line and leaves the state to the state word", () => {
    render(<Ledger card={card} />);
    const row = screen.getByText(/Being inside does not mean/).closest("tr")!;
    expect(row).toHaveTextContent("NOT SHOWN. Being inside does not mean they may rent it.");
    expect(row.querySelector(".case-line-tone")).toHaveTextContent("NOT SHOWN.");
    expect(row.querySelector(".ui-state")).toHaveTextContent("Not confirmed");
    expect(css).toMatch(/\.case-line-tone\s*\{[^}]*text-transform:\s*lowercase/);
  });

  it("the case page mounts no chart block and no old places strip", async () => {
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-band")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByTestId("case-tile").length).toBeGreaterThan(0));
    expect(screen.getAllByTestId("case-tile").length).toBeLessThanOrEqual(3);
    expect(document.querySelector("[data-testid='place-row'], .pf-row")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Every number comes from eval/);
  });
});

describe("the ledger", () => {
  it("puts every check on the table: what fails first, then what passes, then what was not checked", () => {
    render(<Ledger card={card} />);
    const blocks = [...document.querySelectorAll(".case-group-block")];
    expect(blocks.map((b) => b.getAttribute("data-group"))).toEqual([
      "fails",
      "passes",
      "unchecked",
    ]);
    const [fails, passes, unchecked] = blocks as [HTMLElement, HTMLElement, HTMLElement];
    expect(screen.getByTestId("group-fails")).toHaveTextContent("What doesn't check out");
    expect(fails).toHaveTextContent("Zelle before a viewing. Red flag.");
    expect(fails).toHaveTextContent("NOT SHOWN. Being inside does not mean they may rent it.");
    expect(passes).toHaveTextContent("Taken in this building");
    expect(passes).not.toHaveTextContent("Red flag");
    expect(unchecked).toHaveTextContent("Not checked (our data has no rent for this building).");
    expect(within(unchecked).getByTestId("not-checked")).toBeInTheDocument();
    // Nothing sits behind a tap.
    expect(document.querySelector(".case-ledger details")).toBeNull();
    expect(document.querySelectorAll(".case-row")).toHaveLength(5);
  });

  it("never makes up the ad side: with no ad words there is no ad column at all", () => {
    render(<Ledger card={card} />);
    expect(screen.queryByText("The ad says")).toBeNull();
    expect(screen.getAllByText("What we found").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".case-cell-ad")).toHaveLength(0);
  });

  it("shows the ad's words only on the line the caller gave them for", () => {
    render(
      <Ledger
        card={card}
        adSays={(_row, line) => (line.label === "Payment ask" ? "send it by Zelle today" : null)}
      />,
    );
    expect(screen.getAllByText("The ad says").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".case-cell-ad")).toHaveLength(1);
    const row = screen.getByText("send it by Zelle today").closest("tr");
    expect(row).toHaveTextContent("Zelle before a viewing. Red flag.");
    expect(row).toHaveTextContent("Warning");
    // A line with no ad words runs across both columns.
    const other = screen.getByText(/Being inside does not mean/).closest("td");
    expect(other).toHaveAttribute("colspan", "2");
  });

  it("counts the checks from the card and names the record only where it is known", () => {
    render(<Ledger card={card} />);
    expect(screen.getByTestId("case-set-by")).toHaveTextContent("5 CHECKS · SET BY CODE");
    // "Real" is read from the 3D scan; the not-checked rent line prints no record line.
    const lines = screen.getAllByTestId("record-line").map((el) => el.textContent);
    expect(lines).toEqual(["3D SCAN · FIXTURE"]);
  });
});

describe("the price bar", () => {
  const price = { listed: 900, min: 1600, max: 1900 };

  it("puts the mark and the range on the track from the figures", () => {
    const { mark, start, width } = priceScale(price);
    expect(mark).toBeGreaterThan(0);
    expect(mark).toBeLessThan(start);
    expect(start + width).toBeLessThan(100);
    const above = priceScale({ listed: 2400, min: 1600, max: 1900 });
    expect(above.mark).toBeGreaterThan(above.start + above.width);
    expect(above.mark).toBeLessThan(100);
  });

  it("labels both, the lower one first, and keeps them apart in CSS", () => {
    render(<PriceBar price={price} />);
    const labels = [...document.querySelectorAll(".case-price-label")].map((el) => el.textContent);
    expect(labels).toEqual(["$900 in the ad", "$1,600 to $1,900 on record"]);
    // One row, pushed to its two ends, with a gap, each label unbreakable: they wrap, never touch.
    const row = /\.case-price-labels\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(row).toMatch(/justify-content:\s*space-between/);
    expect(row).toMatch(/flex-wrap:\s*wrap/);
    expect(row).toMatch(/gap:\s*\d+px\s+\d+px/);
    expect(/\.case-price-label\s*\{([^}]*)\}/.exec(css)?.[1]).toMatch(/white-space:\s*nowrap/);
    expect(css).not.toMatch(/\.case-price-label[^{]*\{[^}]*position:\s*absolute/);
  });
});

describe("the proof pair", () => {
  it("moves the stamp off any corner a pin sits in", () => {
    expect(stampPlace([])).toBe("bottom");
    expect(stampPlace([{ x: 30, y: 50 }])).toBe("bottom");
    expect(stampPlace([{ x: 30, y: 90 }])).toBe("top");
    expect(stampPlace([{ x: 90, y: 90 }])).toBe("bottom");
    expect(
      stampPlace([
        { x: 30, y: 90 },
        { x: 20, y: 10 },
      ]),
    ).toBe("below");
  });

  it("stamps both photos and numbers the pins the same on each", () => {
    const shot = { src: "/x.jpg", alt: "A living room", stamp: "sample" as const };
    render(
      <ProofPair
        ad={{ ...shot, stamp: "ad" }}
        scan={shot}
        pins={[
          { ax: 20, ay: 30, sx: 24, sy: 32 },
          { ax: 60, ay: 88, sx: 62, sy: 86 },
        ]}
        caption="Taken here: Living Room"
      />,
    );
    expect(screen.getAllByTestId("case-stamp").map((el) => el.textContent)).toEqual([
      "FROM THE AD",
      "SAMPLE PHOTO",
    ]);
    const shots = [...document.querySelectorAll(".case-shot")];
    expect(shots.map((s) => s.getAttribute("data-stamp-at"))).toEqual(["top", "top"]);
    for (const s of shots)
      expect([...s.querySelectorAll(".ui-pin")].map((p) => p.textContent)).toEqual(["1", "2"]);
  });

  it("names one photo for the hand-off into the walk: the case page's ad photo, never inline", () => {
    const shot = { src: "/x.jpg", alt: "A living room", stamp: "sample" as const };
    const proof = { ad: shot, scan: shot, pins: [], caption: "x" };
    const page = render(<CaseResult card={card} proof={proof} />);
    const named = document.querySelectorAll(".case-shot-handoff");
    expect(named).toHaveLength(1);
    expect(named[0]).toBe(document.querySelector(".case-shot"));
    page.unmount();
    render(<CaseResult card={card} proof={proof} inline />);
    expect(document.querySelectorAll(".case-shot-handoff")).toHaveLength(0);
    expect(css).toMatch(
      /\.case-shot-handoff \.case-shot-photo\s*\{\s*view-transition-name:\s*ad-photo/,
    );
    expect(css.match(/view-transition-name/g)).toHaveLength(1);
  });

  it("a photo with no picture is stamped as a drawn stand-in", () => {
    const none = { src: null, alt: "No picture", stamp: "ad" as const };
    render(<ProofPair ad={none} scan={none} pins={[]} caption="x" />);
    expect(screen.getAllByTestId("case-stamp")[0]).toHaveTextContent("DRAWN STAND-IN");
  });

  it("at phone width the stamp is under the photo, whatever corner it had", () => {
    const phone = /@media \(max-width: 640px\)\s*\{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
    expect(phone).toMatch(
      /\.case-shot \.case-stamp,\s*\.case-shot\[data-stamp-at="top"\] \.case-stamp\s*\{\s*position:\s*static/,
    );
  });
});

describe("the ad you pasted", () => {
  const text = "2 bed near downtown. $900 a month. Send the deposit by Zelle today.";

  it("underlines only words that are in the ad, and keeps every character", () => {
    const runs = markRuns(text, [
      { phrase: "$900 a month", kind: "mismatch" },
      { phrase: "by zelle today", kind: "warn" },
      { phrase: "wire me the money", kind: "warn" },
    ]);
    expect(runs.map((r) => r.text).join("")).toBe(text);
    expect(runs.filter((r) => r.kind).map((r) => [r.text, r.kind])).toEqual([
      ["$900 a month", "mismatch"],
      ["by Zelle today", "warn"],
    ]);
  });

  it("shows a legend only for the kinds that are marked", () => {
    render(<AnnotatedAd text={text} marks={[{ phrase: "$900 a month", kind: "mismatch" }]} />);
    const ad = screen.getByTestId("case-ad");
    expect(ad.querySelectorAll("mark")).toHaveLength(1);
    expect(ad).toHaveTextContent("doesn't match the record");
    expect(ad).not.toHaveTextContent("a warning sign");
  });
});

describe("why this is not a good deal", () => {
  const summary = ["Sentence one from the card.", "Sentence two from the card."];

  it("prints the card's own summary sentences under the heading, in place of the fallback", () => {
    render(<CaseResult card={{ ...card, summary } as ProofCard} />);
    const block = screen.getByTestId("case-reasons");
    expect(block).toHaveTextContent("WHY THIS IS NOT A GOOD DEAL");
    expect(
      within(block)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(summary);
    expect(screen.queryByTestId("case-why")).toBeNull();
  });

  it("a card that passed keeps its summary but not that heading", () => {
    render(<CaseResult card={{ ...card, state: "verified", summary } as ProofCard} />);
    const block = screen.getByTestId("case-reasons");
    expect(block).toHaveTextContent(summary[0]!);
    expect(block).not.toHaveTextContent("NOT A GOOD DEAL");
  });

  it("with no summary on the card the block is not there", () => {
    render(<CaseResult card={card} />);
    expect(screen.queryByTestId("case-reasons")).toBeNull();
  });
});

describe("the real listing", () => {
  // The shape of GET /cases/{id}/real-listing, filled from the synthetic record of demo case a.
  const listing: RealListingData = {
    case_id: "7Q2M",
    source: "fixture",
    which: "claimed",
    building_name: "Fixture Court",
    manager_company: record.manager_company,
    website_host: record.website_host,
    plans: record.floor_plan_rents
      .filter((p) => p.beds === 2)
      .map((p) => ({ ...p, units_available: 3 })),
    photos_in_scan: 3,
    photos_total: 3,
    ad_rent: 900,
    ad_asks_irreversible: true,
    phone_is_office: "no",
    figures_shown: true,
    as_of: "2026-10-30",
  };

  it("puts the ad beside the record, with the provenance line, the date and the chip", () => {
    render(<RealListing listing={listing} />);
    const panel = screen.getByTestId("case-real");
    expect(within(panel).getByRole("heading", { name: "The ad" })).toBeInTheDocument();
    expect(
      within(panel).getByRole("heading", {
        name: "Its Apartments.com listing on CoStar's record",
      }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("real-provenance")).toHaveTextContent(
      "3 of 3 of the ad's photos are in CoStar's own scan of this building. The ad's number is not the office's on record.",
    );
    expect(panel).toHaveTextContent("$900 a month");
    expect(panel).toHaveTextContent("$1,600 to $1,900 a month · 3 units reported available");
    expect(panel).toHaveTextContent("Fixture Living LLC");
    expect(screen.getByTestId("real-source")).toHaveTextContent("FIXTURE");
    expect(within(panel).getByTestId("record-line")).toHaveTextContent(
      "COSTAR RECORD · AS OF 2026-10-30 · FIXTURE",
    );
  });

  it("has one button, to the availability link when there is one, else the building's site", () => {
    const { unmount } = render(<RealListing listing={listing} />);
    const link = screen.getByTestId("real-link");
    expect(link).toHaveTextContent("See the real listing");
    expect(link).toHaveAttribute("href", "https://fixtureliving.example");
    expect(screen.getByTestId("case-real").querySelectorAll("a, button")).toHaveLength(1);
    unmount();
    const withUrl = {
      ...listing,
      plans: [
        { ...listing.plans![0]!, availability_url: "https://www.apartments.com/fixture-court/" },
      ],
    };
    expect(realListingLink(withUrl)).toBe("https://www.apartments.com/fixture-court/");
  });

  it("never links to anything that is not a plain https address", () => {
    expect(realListingLink({ ...listing, website_host: "javascript:alert(1)" })).toBeNull();
    expect(realListingLink({ ...listing, website_host: "evil.example/path?x" })).toBeNull();
    expect(outLink("http://www.apartments.com/x")).toBeNull();
    expect(outLink("javascript:alert(1)")).toBeNull();
    expect(hostLink(" FixtureLiving.example ")).toBe("https://fixtureliving.example");
    render(<RealListing listing={{ ...listing, website_host: null }} />);
    expect(screen.queryByTestId("real-link")).toBeNull();
  });

  it("leaves the rents out when the API says figures are not shown, and says so", () => {
    render(<RealListing listing={{ ...listing, figures_shown: false }} />);
    const panel = screen.getByTestId("case-real");
    expect(panel).not.toHaveTextContent("$1,600");
    expect(panel).toHaveTextContent("3 units reported available");
    expect(panel).toHaveTextContent("Rents are not shown on this run.");
  });

  it("renders in the result only when the listing is there", () => {
    const { unmount } = render(<CaseResult card={card} />);
    expect(screen.queryByTestId("case-real")).toBeNull();
    unmount();
    render(<CaseResult card={card} realListing={listing} />);
    expect(screen.getByTestId("case-real")).toBeInTheDocument();
    // The band's button is still the only primary one.
    expect(document.querySelectorAll(".case-primary")).toHaveLength(1);
  });
});

describe("safer places to go to", () => {
  const place = (n: number, url: string | null): SaferPlace => ({
    property_id: `fx-${n}`,
    floor_plan: "1 bed / 1 bath",
    price_text: "$1,450 to $1,600 a month as of CoStar's last research",
    source: "fixture",
    handoff_url: url,
    handoff_label: "Its listing on Apartments.com",
  });
  const places = [
    place(1, "https://www.apartments.com/fx-1/"),
    place(2, null),
    place(3, "javascript:alert(1)"),
    place(4, "https://www.apartments.com/fx-4/"),
    place(5, "https://fixtureliving.example/"),
    place(6, "https://www.apartments.com/fx-6/"),
  ];

  it("shows at most three tiles, each led by a stamped photo, with one link", () => {
    render(<CaseResult card={card} saferPlaces={places} />);
    const tiles = screen.getAllByTestId("case-tile");
    expect(tiles).toHaveLength(3);
    for (const tile of tiles) {
      expect(tile.querySelectorAll("img")).toHaveLength(1);
      expect(tile).toHaveTextContent("SAMPLE PHOTO");
      expect(tile).toHaveTextContent("COSTAR RECORD · FIXTURE");
      expect(tile.querySelectorAll("a, button")).toHaveLength(0);
    }
    expect(tiles[0]).toHaveAttribute("href", "https://www.apartments.com/fx-1/");
    expect(tiles[0]).toHaveAttribute("target", "_blank");
    expect(tiles[0]).toHaveTextContent("SAFER: LISTED ON APARTMENTS.COM");
    expect(tiles[0]).toHaveTextContent("Its listing on Apartments.com");
    // The step and the rail point at the tiles on this page.
    expect(document.getElementById("safer")).toBe(screen.getByTestId("case-tiles"));
    for (const link of screen.getAllByRole("link", { name: "Find me safer places like this" }))
      expect(link).toHaveAttribute("href", "#safer");
  });

  it("uses a hand-off only when it is a plain https link; otherwise the walk or the prep", () => {
    const tiles = saferTiles([
      place(1, "javascript:alert(1)"),
      { ...place(2, null), has_3d_scan: true, plan_key: "2b/2b" },
      place(3, "https://fixtureliving.example/"),
      place(4, "https://www.apartments.com/fx-4/"),
    ]);
    expect(tiles.map((t) => [t.href, t.label, t.out])).toEqual([
      ["/prep/place/fx-1", "Tour prep", false],
      ["/tour/fx-2?plan_key=2b%2F2b", "Walk it first", false],
      ["https://fixtureliving.example/", "Its listing on Apartments.com", true],
    ]);
    render(<SaferTiles places={[place(1, null), place(3, "https://fixtureliving.example/")]} />);
    const shown = screen.getAllByTestId("case-tile");
    // Only a link to Apartments.com is labelled as an Apartments.com listing.
    expect(shown[0]).toHaveTextContent("RESEARCHED PLACE");
    expect(shown[0]).not.toHaveAttribute("target");
    expect(shown[1]).toHaveTextContent("SAFER: ON COSTAR'S RECORD");
    expect(shown[1]).not.toHaveTextContent("LISTED ON APARTMENTS.COM");
  });

  it("only at the end of a result that did not pass; else the step goes to the Finder", () => {
    const { unmount } = render(
      <CaseResult card={{ ...card, state: "verified" }} saferPlaces={places} />,
    );
    expect(screen.queryByTestId("case-tiles")).toBeNull();
    for (const link of screen.getAllByRole("link", { name: "Find me safer places like this" }))
      expect(link).toHaveAttribute("href", "/finder");
    unmount();
    const failed = render(
      <CaseResult card={{ ...card, state: "dont_pay" }} saferPlaces={places} />,
    );
    expect(screen.getByTestId("case-tiles")).toBeInTheDocument();
    failed.unmount();
    render(<CaseResult card={card} saferPlaces={[]} />);
    expect(screen.queryByTestId("case-tiles")).toBeNull();
  });

  it("never says what another site does or does not catch", () => {
    for (const { name, text } of sources)
      expect(text.toLowerCase(), name).not.toMatch(
        /apartments\.com (does not|doesn't|can't|cannot|misses|fails)/,
      );
  });
});

describe("the snap", () => {
  it("runs once, and only when motion is allowed", () => {
    const motion = css.indexOf("@media (prefers-reduced-motion: no-preference)");
    expect(motion).toBeGreaterThan(-1);
    const uses = [...css.matchAll(/animation:\s*([^;]+);/g)];
    expect(uses).toHaveLength(2);
    for (const use of uses) {
      expect(use.index!).toBeGreaterThan(motion);
      expect(use[1]).toMatch(/\b1 backwards$/);
      expect(use[1]).not.toMatch(/infinite|both/);
    }
    expect(css.slice(motion)).not.toMatch(/@media[\s\S]*@media/);
  });
});
