import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { checkAnchor } from "./anchors";
import { reportText } from "./handler";
import { howCheckedText } from "./howchecked";
import { spokenReply } from "./voice";

// XO 03:32 (rival scan, idea 2): every red flag in the iMessage reply links to its proof on the
// case card, /case/<id>#<anchor>. One link per flag, at most 3. The web card's "What doesn't"
// list carries the same anchors (apps/web/src/case/checkAnchor.ts: the same rule, same vectors).

const card = JSON.parse(
  readFileSync(new URL("../../../fixtures/contracts/card_hold.json", import.meta.url), "utf8"),
);
const LINK = "https://web.test/case/7Q2M";

// Shared test vectors: apps/web/src/case/checkAnchor.test.ts must list the same pairs.
const VECTORS: [string, string | null][] = [
  ["Payment ask: Zelle before a viewing. Red flag.", "check-payment-ask"],
  [
    "Allowed to rent it: NOT SHOWN. Being inside does not mean they may rent it.",
    "check-allowed-to-rent-it",
  ],
  ["Rent vs record: Not checked (our data has no rent for this building).", "check-rent-vs-record"],
  ["No colon here", null],
];

for (const [line, want] of VECTORS) {
  test(`anchor for "${line.slice(0, 30)}…" is ${want}`, () => {
    assert.equal(checkAnchor(line), want);
  });
}

test("each 'Before you pay' reason on the card's list ends with its link", () => {
  const text = reportText({ ...card, summary: [] }, LINK); // reasons come from does_not
  assert.match(
    text,
    /- Payment ask: Zelle before a viewing\. Red flag\. https:\/\/web\.test\/case\/7Q2M#check-payment-ask/,
  );
  assert.match(
    text,
    /- Allowed to rent it: .* https:\/\/web\.test\/case\/7Q2M#check-allowed-to-rent-it/,
  );
  assert.match(text, /Full report: https:\/\/web\.test\/case\/7Q2M\n/);
});

test("summary reasons link to the checks section, once, never to a made-up anchor", () => {
  const text = reportText(card, LINK); // the fixture's reasons are its summary lines
  assert.match(
    text,
    /- Money or personal papers were asked for before any viewing\. https:\/\/web\.test\/case\/7Q2M#checks\n/,
  );
  assert.match(text, /- We could not confirm who is allowed to rent this unit\.\n/); // no repeat
  assert.equal((text.match(/#checks\b/g) ?? []).length, 1);
});

test("at most 3 flag links, even with more red flags", () => {
  const many = {
    ...card,
    does_not: ["A one: x", "B two: x", "C three: x", "D four: x"].map((s) => s),
    rows: [
      {
        kind: "claims",
        lines: ["A one", "B two", "C three", "D four"].map((label) => ({
          label,
          text: "x",
          tone: "red_flag",
        })),
      },
    ],
  };
  const how = howCheckedText({ steps: [] }, many, LINK);
  assert.equal((how.match(/#check-/g) ?? []).length, 3);
});

test("'how did you check?' links each red flag to its line on the card", () => {
  const how = howCheckedText({ steps: [] }, card, LINK);
  assert.match(
    how,
    /- Red flag: Payment ask: Zelle before a viewing\. Red flag\. https:\/\/web\.test\/case\/7Q2M#check-payment-ask/,
  );
});

test("Spanish replies carry no flag links (the web card is English; Spanish is frozen)", () => {
  assert.doesNotMatch(reportText(card, LINK, null, null, false, "es"), /#check-/);
  assert.doesNotMatch(howCheckedText({ steps: [] }, card, LINK, "es"), /#check-/);
});

test("the spoken reply still speaks the top reason: the link is dropped, not the reason", () => {
  const said = spokenReply(reportText(card, LINK));
  // the top reason (now carrying a #checks link in the text) is still spoken, without the link
  assert.match(said, /Money or personal papers were asked for before any viewing\./);
  assert.doesNotMatch(said, /https?:|#check-/);
});
