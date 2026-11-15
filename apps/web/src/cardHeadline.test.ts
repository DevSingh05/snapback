import { describe, expect, it } from "vitest";

import { STATE_WORD, headlineOf } from "./cardStrings";

// The API sends its own headline for a HOLD with nothing against it (an honest ad that only
// lacks the presence step). The page shows that, and the state's words otherwise.
describe("headlineOf", () => {
  it("uses the API's headline when it sends one", () => {
    const words = "Everything we checked matches the record. One step left before you pay.";
    expect(headlineOf({ state: "hold", headline: words })).toBe(words);
  });

  it("falls back to the state's words when there is none", () => {
    expect(headlineOf({ state: "hold" })).toBe(STATE_WORD.hold);
    expect(headlineOf({ state: "hold", headline: null })).toBe(STATE_WORD.hold);
    expect(headlineOf({ state: "hold", headline: "" })).toBe(STATE_WORD.hold);
    expect(headlineOf({ state: "dont_pay" })).toBe(STATE_WORD.dont_pay);
  });
});
