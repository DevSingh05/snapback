import { describe, expect, it } from "vitest";

import {
  briefFromWords,
  isFacebook,
  missingFor,
  rentFrom,
  route,
  switchOf,
  viewFrom,
  withoutFacebookLinks,
} from "./intent";

const AD =
  "Sunny 2 bed 2 bath in Midtown, $1,350/month, utilities included. I'm abroad for work so I can't show it, " +
  "but send the $600 deposit by Zelle and I'll mail the keys. Text me at 713 555 0142.";

const at = (text: string, opts: { files?: number; caseOnScreen?: boolean } = {}) =>
  route({ text, files: opts.files ?? 0, caseOnScreen: opts.caseOnScreen ?? false }).kind;

describe("intent routing: code reads what the renter meant", () => {
  it("pasted ad text goes to the check", () => {
    expect(at(AD)).toBe("check");
    expect(at("2br/1ba, $1,450 a month, deposit by Venmo before viewing")).toBe("check");
  });

  it("a listing link goes to the check, bare or with a scheme, alone or inside text", () => {
    expect(at("https://www.zillow.com/homedetails/123")).toBe("check");
    expect(at("craigslist.org/apa/d/houston/123.html")).toBe("check");
    expect(at("saw this one https://houston.craigslist.org/apa/1 what do you think")).toBe("check");
  });

  it("screenshots go to the check, whatever the words say", () => {
    expect(at("", { files: 1 })).toBe("check");
    expect(at("find me something like this", { files: 2 })).toBe("check");
  });

  it("a Facebook link alone asks for the text and photos; with the text it is checked", () => {
    expect(at("https://www.facebook.com/marketplace/item/123456789/")).toBe("check-fb");
    expect(at("facebook.com/marketplace/item/1")).toBe("check-fb");
    expect(at(`https://www.facebook.com/marketplace/item/1 ${AD}`)).toBe("check");
    expect(isFacebook("https://m.facebook.com/marketplace/item/1")).toBe(true);
    expect(isFacebook("https://houston.craigslist.org/apa/1")).toBe(false);
    expect(withoutFacebookLinks(`https://www.facebook.com/marketplace/item/1 ${AD}`)).toBe(AD);
  });

  it("an ad that opens like a wish is still an ad", () => {
    expect(
      at(
        "Looking for a responsible tenant. 2 bed 1 bath, $1,200 per month, deposit by Zelle, text me 713-555-0101",
      ),
    ).toBe("check");
    expect(
      at(
        "I need someone to take over my lease asap. 1br $950/month utilities included, contact me",
      ),
    ).toBe("check");
    expect(at("Any interested renters? Studio downtown $800 a month, Zelle deposit only")).toBe(
      "check",
    );
  });

  it("finds a Facebook address with or without a scheme and never routes it anywhere else", () => {
    for (const u of [
      "facebook.com/marketplace/item/1",
      "www.facebook.com/marketplace/item/1",
      "https://m.facebook.com/marketplace/item/1",
      "https://l.facebook.com/l.php?u=x",
      "fb.com/marketplace/item/1",
      "https://fb.me/abc",
    ])
      expect(isFacebook(u), u).toBe(true);
    expect(isFacebook("notfacebook.company.com")).toBe(false);
    // With the address removed, ad text is checked; anything else asks for the text.
    expect(at("facebook.com/marketplace/item/123\n2 bed 1 bath $1500")).toBe("check");
    expect(at("is facebook.com/marketplace/item/1 legit?")).toBe("check-fb");
    expect(at("Is https://www.facebook.com/marketplace/item/1 legit?")).toBe("check-fb");
    expect(at("is facebook.com/marketplace/item/1 legit?", { caseOnScreen: true })).toBe(
      "check-fb",
    );
    expect(withoutFacebookLinks("facebook.com/marketplace/item/123\n2 bed 1 bath $1500")).toBe(
      "2 bed 1 bath $1500",
    );
  });

  it("a wish or a budget goes to the Finder", () => {
    expect(at("find me a 1 bed under 1500")).toBe("find");
    expect(at("Find me a 1 bed under $1,500 near downtown")).toBe("find");
    expect(at("looking for a studio with parking")).toBe("find");
    expect(at("2 bed under $2,000, pets ok")).toBe("find");
    expect(at("My budget is 1.5k")).toBe("find");
  });

  it("a question while a case is on screen is answered about it", () => {
    expect(at("Is the owner really abroad?", { caseOnScreen: true })).toBe("ask");
    expect(at("what should I ask before paying?", { caseOnScreen: true })).toBe("ask");
  });

  it("asking for a check with nothing to check asks for the ad", () => {
    expect(at("Check this ad I found")).toBe("check-ask");
    expect(at("Is this landlord real?")).toBe("check-ask");
    expect(at("Paste a Marketplace or Craigslist ad")).toBe("check-ask");
  });

  it("opens a view when asked by name", () => {
    expect(route({ text: "show me on the map", files: 0, caseOnScreen: false })).toEqual({
      kind: "open",
      view: "map",
    });
    expect(viewFrom("Replay a real case")).toBe("replays");
    expect(viewFrom("Walk me through a place")).toBe("walk");
    expect(viewFrom("open the investigator")).toBe("investigate");
    expect(viewFrom("find me a 1 bed")).toBeNull();
  });

  it("a short question about paying is answered from the rules, not treated as an ad", () => {
    expect(at("Is $600 by Zelle normal?")).toBe("rules");
    expect(at("should I pay a deposit before seeing it?")).toBe("rules");
    expect(at("what about this one?")).toBe("unsure");
  });

  it("offers the other reading as a one-tap switch", () => {
    expect(switchOf({ kind: "check" })).toEqual({ kind: "find" });
    expect(switchOf({ kind: "find" })).toEqual({ kind: "check" });
    expect(switchOf({ kind: "unsure" })).toBeNull();
  });
});

describe("reading a wish", () => {
  it("reads the budget and must-haves by code", () => {
    expect(rentFrom("under 1500")).toBe(1500);
    expect(rentFrom("max $1,800 a month")).toBe(1800);
    expect(rentFrom("budget is 1.5k")).toBe(1500);
    expect(rentFrom("a 1 bed near downtown")).toBeNull();
    expect(briefFromWords("1 bed under $1,500, parking, no walk-ups, a dog")).toEqual({
      max_rent_month: 1500,
      beds_min: 1,
      needs_parking: true,
      needs_no_walkup: true,
      pets: true,
    });
  });

  it("reads no-pets, ranges and amounts after other numbers correctly", () => {
    expect(briefFromWords("no pets please").pets).toBeUndefined();
    expect(briefFromWords("no dogs please").pets).toBeUndefined();
    expect(briefFromWords("2-3 bedroom near downtown").beds_min).toBe(2);
    expect(briefFromWords("2 to 3 beds").beds_min).toBe(2);
    expect(rentFrom("about 2 beds $1200")).toBe(1200);
    expect(rentFrom("My budget is 1.5k")).toBe(1500);
  });

  it("asks for the max rent only when no amount is known", () => {
    expect(missingFor("a 1 bed near downtown", null)).toBe("max_rent");
    expect(missingFor("a 1 bed under 1500", null)).toBeNull();
    expect(missingFor("a 1 bed near downtown", 1500)).toBeNull();
    expect(missingFor("any budget, 2 beds", null)).toBeNull();
  });
});
