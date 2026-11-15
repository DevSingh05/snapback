import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { Card } from "../contracts";
import { CardPage } from "./CardPage";

// #340 review (M): the iMessage link /case/<id>#check-<label> must land on its proof. The card
// loads after mount, so the browser's own jump to the #fragment happens before the line exists;
// the page scrolls to it once the card is ready.
const card = cardHold as Card;

describe("a /case link with a #fragment lands on its line", () => {
  let scroll: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll as unknown as Element["scrollIntoView"];
  });
  afterEach(() => {
    window.history.replaceState(null, "", "/");
    vi.unstubAllGlobals();
  });

  it("scrolls to the red flag's line once the card is ready, once", async () => {
    window.history.replaceState(null, "", `/case/${card.case_id}#check-payment-ask`);
    const page = render(<CardPage caseId={card.case_id} variant="result" />);
    await page.findByTestId("case-id");
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
    expect((scroll.mock.contexts[0] as Element).id).toBe("check-payment-ask");
    expect(scroll.mock.calls[0]?.[0]).toMatchObject({ block: "start" });
    page.rerender(<CardPage caseId={card.case_id} variant="result" />);
    expect(scroll).toHaveBeenCalledTimes(1);
  });

  it("does nothing without a #fragment, or with one that names no element", async () => {
    window.history.replaceState(null, "", `/case/${card.case_id}`);
    const a = render(<CardPage caseId={card.case_id} variant="result" />);
    await a.findByTestId("case-id");
    a.unmount();
    window.history.replaceState(null, "", `/case/${card.case_id}#no-such-line`);
    const b = render(<CardPage caseId={card.case_id} variant="result" />);
    await b.findByTestId("case-id");
    await new Promise((r) => setTimeout(r, 30));
    expect(scroll).not.toHaveBeenCalled();
  });

  it("jumps without smooth motion when the reader asks for reduced motion", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: q.includes("reduce"),
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));
    window.history.replaceState(null, "", `/case/${card.case_id}#checks`);
    const page = render(<CardPage caseId={card.case_id} variant="result" />);
    await page.findByTestId("case-id");
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
    expect(scroll.mock.calls[0]?.[0]).toMatchObject({ behavior: "auto" });
  });
});
