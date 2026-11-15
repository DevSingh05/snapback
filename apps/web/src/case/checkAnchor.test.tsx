import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Checks } from "./Checks";
import { checkAnchor } from "./checkAnchor";

// The iMessage reply links each red flag to /case/<id>#<anchor> (apps/sidecar/src/anchors.ts).
// Same rule, same vectors as apps/sidecar/src/flaglinks.test.ts, so the two never drift.
const VECTORS: [string, string | null][] = [
  ["Payment ask: Zelle before a viewing. Red flag.", "check-payment-ask"],
  [
    "Allowed to rent it: NOT SHOWN. Being inside does not mean they may rent it.",
    "check-allowed-to-rent-it",
  ],
  ["Rent vs record: Not checked (our data has no rent for this building).", "check-rent-vs-record"],
  ["No colon here", null],
];

describe("check anchors", () => {
  it.each(VECTORS)("anchors %s as %s", (line, want) => {
    expect(checkAnchor(line)).toBe(want);
  });

  it("each 'What doesn't' line carries its anchor, once per label", () => {
    const { container } = render(
      <Checks
        source="fixture"
        doesNot={[
          "Payment ask: Zelle before a viewing. Red flag.",
          "Payment ask: A deposit or holding fee before a viewing. Red flag.",
          "Allowed to rent it: NOT SHOWN.",
        ]}
        checksOut={["Real: Taken in this building."]}
      />,
    );
    expect(container.querySelectorAll("#check-payment-ask")).toHaveLength(1);
    expect(container.querySelector("#check-allowed-to-rent-it")?.textContent).toContain(
      "NOT SHOWN",
    );
    // the "checks out" side is not a red flag: no anchors there
    expect(container.querySelector("[data-side='checks-out'] [id]")).toBeNull();
    // summary reasons in iMessage link to the section itself: /case/<id>#checks
    expect(container.querySelector("section#checks")).not.toBeNull();
  });
});
