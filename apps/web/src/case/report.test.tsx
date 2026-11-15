// The report's hide and show rules: one order, and every section there only when its data is.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { saveCaseReadToken } from "../api";
import type { Card } from "../contracts";
import { CardPage } from "../pages/CardPage";
import {
  AGENCIES,
  AlertDraft,
  CaseResult,
  Checks,
  FilePanel,
  WhatNext,
  couldNotDo,
  missingFact,
  reportText,
  withoutPhoneDigits,
} from ".";
import { sampleAlert, sampleListing, samplePack, samplePlace } from "./samples";

const card = cardHold as Card;
const full = (
  <CaseResult
    card={card}
    adText="2 bed near downtown."
    realListing={sampleListing()}
    copyAlert={sampleAlert()}
    reportPack={samplePack()}
    saferPlaces={[samplePlace(1)]}
  />
);

describe("the report, in order", () => {
  it("is named a SNAPBACK report and runs verdict, real listing, checks, next, places, limits", () => {
    render(full);
    expect(document.querySelector(".case-head")).toHaveTextContent("SNAPBACK REPORT");
    const order = [
      "case-band",
      "case-real",
      "case-checks",
      "case-todo",
      "case-safer",
      "case-could-not",
      "case-rules",
    ].map((id) => screen.getByTestId(id));
    for (let i = 1; i < order.length; i++)
      expect(
        order[i - 1]!.compareDocumentPosition(order[i]!) & Node.DOCUMENT_POSITION_FOLLOWING,
        `${order[i]!.dataset.testid} comes after ${order[i - 1]!.dataset.testid}`,
      ).toBeTruthy();
    // Every check is still on the table, under the limits.
    expect(
      screen
        .getByTestId("case-could-not")
        .compareDocumentPosition(screen.getAllByRole("table")[0]!) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("stamps every section with LIVE or FIXTURE from its own read", () => {
    render(full);
    for (const id of [
      "source-chip",
      "real-source",
      "checks-source",
      "alert-source",
      "file-source",
      "could-not-source",
    ])
      expect(screen.getByTestId(id), id).toHaveTextContent("FIXTURE");
    expect(screen.getByTestId("case-tile")).toHaveTextContent("COSTAR RECORD · FIXTURE");
  });

  it("uses the API's headline when one is sent, else the state's own words", () => {
    const sent = render(<CaseResult card={{ ...card, headline: "Nothing against it yet." }} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Nothing against it yet.");
    sent.unmount();
    render(<CaseResult card={{ ...card, headline: null }} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Hold off for now");
  });

  it("never prints a phone number, and never the words for a person who cheats", () => {
    render(full);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d{3}[\s.)-]*\d{3}[\s.-]*\d{4}/);
    expect(text).not.toMatch(/scammer|fraudster|criminal|thief/i);
  });
});

describe("what checks out and what doesn't", () => {
  it("prints both lists as the card has them, the failing side first", () => {
    render(<Checks checksOut={card.checks_out} doesNot={card.does_not} source="fixture" />);
    const cols = screen.getByTestId("case-checks").querySelectorAll(".case-checks-col");
    expect([...cols].map((c) => c.getAttribute("data-side"))).toEqual(["does-not", "checks-out"]);
    const flat = (el: Element) =>
      [...el.querySelectorAll("li")].map((li) =>
        [...li.children].map((c) => c.textContent).join(": "),
      );
    expect(flat(cols[0]!)).toEqual(card.does_not);
    expect(flat(cols[1]!)).toEqual(card.checks_out);
  });

  it("a list the card left out is a column left out; with neither there is no section", () => {
    const one = render(<Checks checksOut={["Real: Taken in this building."]} source="live" />);
    expect(screen.queryByTestId("checks-does-not")).toBeNull();
    expect(screen.getByTestId("checks-out")).toBeInTheDocument();
    one.unmount();
    render(<CaseResult card={{ ...card, checks_out: [], does_not: undefined }} />);
    expect(screen.queryByTestId("case-checks")).toBeNull();
  });
});

describe("what to do next", () => {
  it("is on a result that did not pass, and not on one that passed or on the verify page", () => {
    const failed = render(<CaseResult card={card} />);
    expect(screen.getByTestId("case-todo")).toBeInTheDocument();
    failed.unmount();
    const passed = render(<CaseResult card={{ ...card, state: "verified" }} />);
    expect(screen.queryByTestId("case-todo")).toBeNull();
    passed.unmount();
    render(<CaseResult card={card} variant="verify" copyAlert={sampleAlert()} />);
    expect(screen.queryByTestId("case-todo")).toBeNull();
    expect(screen.queryByTestId("case-alert")).toBeNull();
  });

  it("shows the note only when the API says it fires, as a draft that is never sent", () => {
    const none = render(<WhatNext />);
    expect(screen.queryByTestId("case-alert")).toBeNull();
    none.unmount();
    const off = render(
      <WhatNext alert={sampleAlert({ fires: false, why_not: "phone_is_office" })} />,
    );
    expect(screen.queryByTestId("case-alert")).toBeNull();
    expect(off.container.querySelector("[data-step='tell']")).toBeNull();
    off.unmount();
    const alert = sampleAlert();
    render(<WhatNext alert={alert} />);
    const draft = screen.getByTestId("case-alert");
    expect(draft).toHaveTextContent("DRAFT · NOT SENT");
    expect(draft).toHaveTextContent("SNAPBACK does not send this.");
    const paras = [...screen.getByTestId("alert-body").querySelectorAll("p")];
    expect(paras.map((p) => p.textContent).join("\n\n")).toBe(alert.draft_body);
    // The only control on the draft copies it; nothing on it submits or posts.
    expect(draft.querySelectorAll("button")).toHaveLength(1);
    expect(draft.querySelectorAll("form, input, textarea")).toHaveLength(0);
  });

  it("Copy the note puts the subject and the body on the clipboard and calls no server", async () => {
    const user = userEvent.setup();
    const written: string[] = [];
    vi.spyOn(navigator.clipboard, "writeText").mockImplementation(async (t) => {
      written.push(t);
    });
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    const alert = sampleAlert();
    render(<AlertDraft alert={alert} />);
    await user.click(screen.getByRole("button", { name: "Copy the note" }));
    expect(written).toEqual([`${alert.draft_subject}\n\n${alert.draft_body}`]);
    expect(await screen.findByText("Copied. Nothing was sent.")).toBeInTheDocument();
    expect(fetched).not.toHaveBeenCalled();
  });

  it("takes any phone-shaped digits out of a draft, and leaves other numbers alone", () => {
    expect(withoutPhoneDigits("Call (713) 555-0142 now. 3 of 3 photos, 44% under.")).toBe(
      "Call [number not shown] now. 3 of 3 photos, 44% under.",
    );
    expect(withoutPhoneDigits("7135550142")).toBe("[number not shown]");
    render(<AlertDraft alert={sampleAlert({ draft_body: "Ring 713.555.0142 today." })} />);
    expect(screen.getByTestId("alert-body").textContent).toBe("Ring [number not shown] today.");
  });

  it("names the office's own website for the call, and shows no link without a host", () => {
    const withHost = render(<WhatNext officeHost="fixtureliving.example" />);
    expect(screen.getByTestId("office-site")).toHaveAttribute(
      "href",
      "https://fixtureliving.example",
    );
    withHost.unmount();
    render(<WhatNext officeHost="javascript:alert(1)" />);
    expect(screen.queryByTestId("office-site")).toBeNull();
  });
});

describe("file this report", () => {
  it("always names the FTC and IC3 as plain text with a link each", () => {
    render(<FilePanel pack={null} pageUrl={null} />);
    const links = within(screen.getByTestId("file-agencies")).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://reportfraud.ftc.gov/",
      "https://www.ic3.gov/",
    ]);
    expect(links.map((a) => a.textContent)).toEqual(AGENCIES.map((a) => a.host));
    expect(screen.queryByTestId("file-pack")).toBeNull();
    expect(screen.queryByTestId("file-platforms")).toBeNull();
  });

  it("shows the pack's own lines, and the platform steps only when the pack is reportable", () => {
    const pack = samplePack();
    const yes = render(<FilePanel pack={pack} pageUrl="http://localhost:5173/c/7Q2M" />);
    expect(screen.getByTestId("file-pack")).toHaveTextContent(pack.proof_lines[0]!);
    expect(screen.getByTestId("file-platforms")).toHaveTextContent("Craigslist");
    yes.unmount();
    render(<FilePanel pack={samplePack({ reportable: false })} pageUrl={null} />);
    expect(screen.getByTestId("file-pack")).toBeInTheDocument();
    expect(screen.queryByTestId("file-platforms")).toBeNull();
    expect(reportText(pack, "http://localhost:5173/c/7Q2M")).toBe(
      `SNAPBACK report, case 7Q2M\n\n${pack.proof_lines[0]}\n\nhttp://localhost:5173/c/7Q2M`,
    );
  });
});

describe("what this check could not do", () => {
  it("is built from the card's not_checked list and its not-checked lines", () => {
    expect(couldNotDo(card)).toEqual([
      "We did not check anyone's ID.",
      "We did not read or check a lease.",
      "We did not check who owns the home.",
      "Rent vs record: Not checked (our data has no rent for this building).",
    ]);
    const more: Card = {
      ...card,
      not_checked: ["deed"],
      rows: [
        {
          kind: "price",
          lines: [
            {
              label: "Rent vs record",
              text: "Not checked (our data has no rent for this building).",
              tone: "not_checked",
            },
          ],
        },
      ],
    };
    expect(couldNotDo(more)).toEqual([
      "Not checked: deed.",
      "Rent vs record: Not checked (our data has no rent for this building).",
    ]);
    render(<CaseResult card={more} />);
    expect(screen.getByTestId("case-could-not").querySelectorAll("li")).toHaveLength(2);
  });

  it("is not there when the card lists nothing", () => {
    const rows = card.rows.map((r) => ({
      ...r,
      lines: r.lines.filter((l) => l.tone !== "not_checked"),
    }));
    render(<CaseResult card={{ ...card, not_checked: [], rows }} />);
    expect(screen.queryByTestId("case-could-not")).toBeNull();
  });
});

describe("the one fact that would settle an unsure card", () => {
  const line = (label: string, key: string | null, tone: Card["rows"][0]["lines"][0]["tone"]) => ({
    label,
    text: "x",
    tone,
    key,
  });
  const withRows = (state: Card["state"], rows: Card["rows"]): Card => ({ ...card, state, rows });

  it("names the office confirming the number on the Hold fixture, from its Not confirmed row", () => {
    expect(card.state).toBe("hold");
    expect(missingFact(card)).toBe("the office confirms this number");
    render(<CaseResult card={card} />);
    expect(screen.getByTestId("case-settle")).toHaveTextContent(
      "Would settle it: the office confirms this number",
    );
  });

  it("names the photos placed in the scan when the photo row is not checked", () => {
    const c = withRows("unverified", [
      { kind: "place", lines: [line("Real", "label.real", "not_checked")] },
    ]);
    expect(missingFact(c)).toBe("the photos placed in this building's scan");
  });

  it("names exactly one fact, the first rule with an unsure line", () => {
    const c = withRows("hold", [
      { kind: "price", lines: [line("Rent vs record", "label.rent_vs_record", "not_checked")] },
      { kind: "place", lines: [line("Real", "label.real", "not_shown")] },
    ]);
    expect(missingFact(c)).toBe("the photos placed in this building's scan");
  });

  it("falls back to the row's kind when a line has no key", () => {
    const c = withRows("hold", [{ kind: "price", lines: [line("Rent", null, "not_checked")] }]);
    expect(missingFact(c)).toBe("a rent on record for this home to compare with");
  });

  it("is absent for a clear result, a Don't pay, or a card with nothing unsure", () => {
    const unsure = [
      { kind: "person" as const, lines: [line("Allowed", "label.allowed", "not_shown")] },
    ];
    expect(missingFact(withRows("verified", unsure))).toBeNull();
    expect(missingFact(withRows("dont_pay", unsure))).toBeNull();
    expect(
      missingFact(withRows("hold", [{ kind: "place", lines: [line("Real", "label.real", "ok")] }])),
    ).toBeNull();
    render(<CaseResult card={withRows("dont_pay", unsure)} />);
    expect(screen.queryByTestId("case-settle")).toBeNull();
  });
});

describe("the report's reads", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  function server(routes: Record<string, { code: number; body: unknown }>) {
    const calls: { path: string; auth: string | null }[] = [];
    vi.stubEnv("VITE_API_URL", "/api");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
        const path = String(url);
        calls.push({ path, auth: new Headers(init?.headers).get("Authorization") });
        const hit = Object.entries(routes).find(([key]) => path.split("?")[0]!.endsWith(key));
        const { code, body } = hit ? hit[1] : { code: 404, body: { detail: "none" } };
        return new Response(JSON.stringify(body), {
          status: code,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    return calls;
  }
  const live: Card = { ...card, source: "live", state: "dont_pay", lang: "es" };

  it("sends the read token in a header, never in the address, and asks in the card's language", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server({
      "/cases/7Q2M/card": { code: 200, body: live },
      "/real-listing": { code: 200, body: sampleListing({ source: "live" }) },
      "/copy-alert": { code: 200, body: sampleAlert({ source: "live" }) },
      "/report": { code: 200, body: samplePack({ source: "live" }) },
      "/alternatives": { code: 200, body: { source: "live", as_of: "x", matches: [] } },
    });
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-real")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("case-alert")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("file-pack")).toBeInTheDocument());
    for (const what of ["real-listing", "copy-alert", "report"]) {
      const call = calls.find((c) => c.path.includes(`/${what}`))!;
      expect(call.path, what).toBe(`/api/cases/7Q2M/${what}?lang=es`);
      expect(call.auth, what).toBe("Bearer tok_read_1");
    }
    for (const c of calls) expect(c.path).not.toContain("tok_read_1");
    expect(screen.getByTestId("real-source")).toHaveTextContent("LIVE");
  });

  it("a 404 for the real listing hides that section and the report still stands", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    server({
      "/cases/7Q2M/card": { code: 200, body: live },
      "/copy-alert": {
        code: 200,
        body: sampleAlert({ fires: false, why_not: "no_record", draft_body: null }),
      },
    });
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-todo")).toBeInTheDocument());
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByTestId("case-real")).toBeNull();
    expect(screen.queryByTestId("case-alert")).toBeNull();
    expect(screen.queryByTestId("file-pack")).toBeNull();
    expect(screen.getByTestId("file-agencies")).toBeInTheDocument();
    expect(screen.getByTestId("case-checks")).toBeInTheDocument();
  });

  it("with no read token in this browser no proof read is made at all", async () => {
    const calls = server({ "/cases/7Q2M/card": { code: 200, body: live } });
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-todo")).toBeInTheDocument());
    expect(calls.filter((c) => /real-listing|copy-alert|\/report/.test(c.path))).toHaveLength(0);
  });
});
