// "How we got this answer": one message per check with the card's own finding, red flags first,
// every red flag linked to its message, no link to a skipped check, and no plumbing text ever.
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import { saveCaseReadToken } from "../api";
import type { Card, CardLine, CaseTimeline, TimelineStep } from "../contracts";
import { CardPage } from "../pages/CardPage";
import { AnswerPanel, answerView, tookText } from ".";

const line = (key: string, label: string, text: string, tone: CardLine["tone"]): CardLine => ({
  key,
  label,
  text,
  tone,
});

const PAYMENT = "Payment ask: Zelle before a viewing. Red flag.";
const PHONE = "Contact on record: The phone in the ad is not the office's on record.";
const LICENCE = "License: No license number in the ad to check.";
const ALLOWED = "Allowed to rent it: NOT SHOWN. Being inside does not mean they may rent it.";

const card: Card = {
  ...(cardHold as Card),
  state: "hold",
  rows: [
    {
      kind: "place",
      lines: [line("label.real", "Real", "Taken in this building (3 of 3 photos).", "ok")],
    },
    {
      kind: "person",
      lines: [
        line(
          "label.contact",
          "Contact on record",
          "The phone in the ad is not the office's on record.",
          "hold",
        ),
        line(
          "label.allowed",
          "Allowed to rent it",
          "NOT SHOWN. Being inside does not mean they may rent it.",
          "not_shown",
        ),
        line("label.license", "License", "No license number in the ad to check.", "hold"),
      ],
    },
    {
      kind: "price",
      lines: [
        line("label.payment_ask", "Payment ask", "Zelle before a viewing. Red flag.", "red_flag"),
      ],
    },
  ],
  does_not: [PAYMENT, PHONE, ALLOWED, LICENCE],
  checks_out: ["Real: Taken in this building (3 of 3 photos)."],
};

function step(n: number, kind: string | null, over: Partial<TimelineStep> = {}): TimelineStep {
  return {
    step: n,
    label: "A step",
    started_ms: n * 100,
    took_ms: 400,
    result: "Only one option was open.",
    source: "fixture",
    by: "code",
    kind,
    ...over,
  };
}

function timeline(over: Partial<CaseTimeline> = {}): CaseTimeline {
  return {
    case_id: card.case_id,
    source: "fixture",
    mode: "policy",
    fell_back: false,
    steps: [
      step(0, null, { label: "Read the ad" }),
      step(1, "locate", { result: "Placing 3 listing photos in the twin." }),
      step(2, "record", { label: "Found the building on CoStar's record" }),
      step(3, "phone", { took_ms: 0 }),
      step(4, "owner", {
        skipped: true,
        result: "Skipped owner of record: no owner on record to read.",
      }),
      step(5, "for_sale", {
        skipped: true,
        result: "Skipped listing brokerage: the home is not listed for sale right now.",
      }),
      step(6, null, { label: "Put the report together" }),
    ],
    todos: [],
    plan: [],
    ...over,
  };
}

const bubbles = () => screen.getAllByTestId("answer-bubble");
const reason = (start: string) =>
  screen.getAllByTestId("answer-reason").find((r) => r.textContent?.startsWith(start))!;

describe("one message per check", () => {
  it("puts red-flag messages first, then hold, then ok, each with the card's own finding", () => {
    render(<AnswerPanel card={card} timeline={timeline()} />);
    expect(bubbles().map((b) => b.getAttribute("data-check"))).toEqual([
      "rules",
      "phone",
      "photos",
    ]);
    expect(bubbles()[0]).toHaveTextContent("Payment ask: Zelle before a viewing. Red flag.");
    expect(bubbles()[0]).toHaveAttribute("data-tone", "red_flag");
    expect(bubbles()[1]).toHaveAttribute("data-tone", "hold");
    expect(bubbles()[2]).toHaveAttribute("data-tone", "ok");
    expect(screen.getByTestId("answer-verdict")).toHaveTextContent("Hold off for now");
  });

  it("links every red flag to its message: rules to Rules, phone to Phone", () => {
    render(<AnswerPanel card={card} timeline={timeline()} />);
    expect(within(reason("Payment ask")).getByTestId("answer-reason-link")).toHaveAttribute(
      "href",
      "#answer-rules",
    );
    expect(within(reason("Contact on record")).getByTestId("answer-reason-link")).toHaveAttribute(
      "href",
      "#answer-phone",
    );
    expect(document.getElementById("answer-rules")).toHaveTextContent("Zelle before a viewing");
  });

  it("links the hold finding 'Allowed to rent it' to the office message, which exists", () => {
    render(<AnswerPanel card={card} timeline={timeline()} />);
    expect(within(reason("Allowed to rent it")).getByTestId("answer-reason-link")).toHaveAttribute(
      "href",
      "#answer-phone",
    );
    expect(document.getElementById("answer-phone")).toHaveTextContent("Allowed to rent it");
  });

  it("never links a reason to a skipped check, and says what was not checked in one line", () => {
    render(<AnswerPanel card={card} timeline={timeline()} />);
    const owner = reason("License");
    expect(owner).toHaveAttribute("data-linked", "no");
    expect(within(owner).queryByTestId("answer-reason-link")).toBeNull();
    expect(document.getElementById("answer-owner")).toBeNull();
    expect(screen.getByTestId("answer-not-checked")).toHaveTextContent(
      "Not checked: Owner and licence: no owner on record to read · For sale: the home is not listed for sale right now",
    );
  });

  it("shows a reason with no matching check unlinked and invents no link", () => {
    const odd = { ...card, does_not: [...card.does_not!, "Something else: odd."] };
    const view = answerView(odd, timeline())!;
    expect(view.reasons.at(-1)).toEqual({ text: "Something else: odd.", bubbleId: null });
  });

  it("never renders a step's own choice text or a step that is not a check", () => {
    render(<AnswerPanel card={card} timeline={timeline()} />);
    expect(screen.queryByText(/Only one option was open/)).toBeNull();
    expect(screen.queryByText(/Put the report together/)).toBeNull();
    expect(screen.queryByText(/Placing 3 listing photos/)).toBeNull();
  });

  it("adds the record line, the provenance and the phone line the real-listing read holds", () => {
    const listing = {
      headline: "Managed by Fixture Living; rent on record $1,400 to $1,900.",
      provenance: "3 of 3 of the ad's photos are in this building's scan.",
      phone_line: "The ad's phone is not the office's.",
    } as never;
    render(<AnswerPanel card={card} timeline={timeline()} realListing={listing} />);
    const found = (check: string) => document.getElementById(`answer-${check}`)!;
    expect(found("record")).toHaveTextContent("Managed by Fixture Living");
    expect(found("photos")).toHaveTextContent("3 of 3 of the ad's photos");
    // the card already has a phone line, so the real-listing phone line is not repeated
    expect(found("phone")).not.toHaveTextContent("The ad's phone is not the office's");
    expect(found("phone")).toHaveTextContent("The phone in the ad is not the office's on record");
  });

  it("an older card with no line keys has nothing to show, so the panel hides", () => {
    const old: Card = {
      ...card,
      rows: card.rows.map((r) => ({ ...r, lines: r.lines.map((l) => ({ ...l, key: null })) })),
    };
    render(<AnswerPanel card={old} timeline={timeline()} />);
    expect(screen.queryByTestId("case-answer")).toBeNull();
  });
});

describe("the planner", () => {
  const deep = timeline({
    mode: "deepagents",
    plan: ["record"],
    todos: [
      { content: "Hand the record checks to the record", done: true },
      { content: "Check the owner", done: false },
    ],
  });

  it("is a closed message at the top on the deep-agent path", () => {
    render(<AnswerPanel card={card} timeline={deep} />);
    const fold = screen.getByTestId("answer-plan") as HTMLDetailsElement;
    expect(fold.open).toBe(false);
    expect(fold).toHaveTextContent("Check the owner");
    expect(screen.getByTestId("answer-plan-msg")).toBe(
      screen.getByTestId("case-answer").querySelector(".case-thread")!.firstElementChild,
    );
  });

  it("is not there on the policy path", () => {
    render(<AnswerPanel card={card} timeline={timeline()} />);
    expect(screen.queryByTestId("answer-plan")).toBeNull();
  });
});

describe("words", () => {
  it("speaks Spanish for a Spanish card and times checks plainly", () => {
    render(<AnswerPanel card={{ ...card, lang: "es" }} timeline={timeline()} />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "Cómo llegamos a esta respuesta",
    );
    expect(screen.getByText("Agente de reglas")).toBeInTheDocument();
    expect(tookText(1234, "es")).toBe("1,2 s");
    expect(tookText(1234, "en")).toBe("1.2 s");
    expect(tookText(40, "en")).toBe("under 0.1 s");
  });
});

describe("on the report page", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    window.sessionStorage.clear();
  });
  const live: Card = { ...card, source: "live", lang: "es" };

  function server(timelineReply: { code: number; body?: unknown } | "throw") {
    vi.stubEnv("VITE_API_URL", "/api");
    const calls: { path: string; auth: string | null }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
        const path = String(url);
        calls.push({ path, auth: new Headers(init?.headers).get("Authorization") });
        const route = path.split("?")[0]!;
        if (route.endsWith("/timeline")) {
          if (timelineReply === "throw") throw new TypeError("network down");
          return new Response(JSON.stringify(timelineReply.body ?? {}), {
            status: timelineReply.code,
            headers: { "Content-Type": "application/json" },
          });
        }
        const isCard = route.endsWith("/card");
        return new Response(JSON.stringify(isCard ? live : { detail: "none" }), {
          status: isCard ? 200 : 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    return calls;
  }

  it("reads the timeline with the token in a header and the card's language, then shows it", async () => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server({ code: 200, body: timeline({ source: "live" }) });
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-answer")).toBeInTheDocument());
    const call = calls.find((c) => c.path.includes("/timeline"))!;
    expect(call.path).toBe("/api/cases/7Q2M/timeline?lang=es");
    expect(call.auth).toBe("Bearer tok_read_1");
    expect(screen.getByTestId("answer-source")).toHaveTextContent("LIVE");
  });

  it.each([
    ["a 500", { code: 500 }],
    ["a 404", { code: 404 }],
    ["a network error", "throw" as const],
    ["no steps", { code: 200, body: timeline({ steps: [] }) }],
  ])("hides the panel on %s and the report still works", async (_name, reply) => {
    saveCaseReadToken("7Q2M", "tok_read_1");
    const calls = server(reply);
    render(<CardPage caseId="7Q2M" variant="result" />);
    await waitFor(() => expect(screen.getByTestId("case-todo")).toBeInTheDocument());
    await waitFor(() => expect(calls.some((c) => c.path.includes("/timeline"))).toBe(true));
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.queryByTestId("case-answer")).toBeNull();
    expect(screen.getByTestId("case-checks")).toBeInTheDocument();
  });
});

describe("the not-checked line", () => {
  it("says why in a few words, without repeating 'Not checked'", () => {
    const quiet: Card = {
      ...card,
      rows: [
        {
          kind: "place",
          lines: [
            line("label.real", "Real", "Not checked (no listing photos were sent).", "not_checked"),
          ],
        },
        ...card.rows.slice(1),
      ],
    };
    render(<AnswerPanel card={quiet} timeline={timeline()} />);
    expect(screen.getByTestId("answer-not-checked")).toHaveTextContent(
      "Photos: no listing photos were sent",
    );
  });
});
