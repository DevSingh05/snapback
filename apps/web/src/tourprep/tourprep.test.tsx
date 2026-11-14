import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { matchRoute } from "../App";
import { saveCaseReadToken } from "../api";
import { AS_OF } from "../contracts";
import type { TourPrepPack } from "../contracts";
import { PlacesStrip } from "../search/PlacesStrip";
import { packToText } from "./api";
import { TourPrepPage } from "./TourPrepPage";

const PHONE = /\+?\d[\d\s().-]{8,}\d/;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  window.sessionStorage.clear();
});

describe("tour prep, fixture mode", () => {
  it("renders the three parts with a FIXTURE chip and the sources of each fact", async () => {
    render(<TourPrepPage target={{ kind: "place", propertyId: "p", planKey: null }} back="/" />);
    expect(await screen.findByRole("heading", { name: "Tour prep" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What the record says" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Questions to ask" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Before you pay" })).toBeInTheDocument();
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    const facts = within(screen.getByTestId("tp-facts")).getAllByRole("listitem");
    expect(facts.length).toBeGreaterThan(0);
    expect(facts[0]).toHaveTextContent("CoStar record");
    expect(screen.getByText(new RegExp(AS_OF))).toBeInTheDocument();
    expect(within(screen.getByTestId("tp-pay")).getAllByRole("listitem")).toHaveLength(3);
  });

  it("flips to Spanish and back", async () => {
    const user = userEvent.setup();
    render(<TourPrepPage target={{ kind: "place", propertyId: "p", planKey: null }} back="/" />);
    await screen.findByRole("heading", { name: "Tour prep" });
    await user.click(screen.getByRole("button", { name: "Español" }));
    expect(await screen.findByRole("heading", { name: "Prepara tu visita" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Antes de pagar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Imprimir" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(await screen.findByRole("heading", { name: "Tour prep" })).toBeInTheDocument();
  });

  it("prints with the browser's print dialog and hides the tools in the print view", async () => {
    const print = vi.fn();
    vi.stubGlobal("print", print);
    const user = userEvent.setup();
    render(<TourPrepPage target={{ kind: "place", propertyId: "p", planKey: null }} back="/" />);
    await screen.findByRole("heading", { name: "Tour prep" });
    await user.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("navigation", { name: "Tour prep tools" })).toHaveClass("no-print");
  });

  it("copies the pack as plain text", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockImplementation(writeText);
    render(<TourPrepPage target={{ kind: "place", propertyId: "p", planKey: null }} back="/" />);
    await screen.findByRole("heading", { name: "Tour prep" });
    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledTimes(1);
    const text = writeText.mock.calls[0]?.[0] as string;
    expect(text).toContain("QUESTIONS TO ASK");
    expect(text).toContain("trec.texas.gov");
    expect(text).not.toMatch(PHONE);
    expect(await screen.findByText("Copied.")).toBeInTheDocument();
  });
});

describe("tour prep, live API", () => {
  const pack: TourPrepPack = {
    source: "live",
    lang: "en",
    title: "Tour prep",
    subtitle: "s",
    note: "n",
    as_of: AS_OF,
    facts_heading: "What the record says",
    questions_heading: "Questions to ask",
    pay_heading: "Before you pay",
    facts: [{ key: "home", text: "API TEXT AS GIVEN", sources: ["CoStar record"], as_of: AS_OF }],
    questions: [{ key: "pay", text: "Ask who you pay.", sources: [] }],
    before_you_pay: ["one", "two", "three"],
  };

  beforeEach(() => {
    vi.stubEnv("VITE_API_URL", "/api");
  });

  it("asks the place route with the plan key and shows the API's text as given", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(pack)));
    vi.stubGlobal("fetch", fetchMock);
    render(<TourPrepPage target={{ kind: "place", propertyId: "b 1", planKey: "a|b" }} back="/" />);
    expect(await screen.findByText("API TEXT AS GIVEN")).toBeInTheDocument();
    expect(screen.getByTestId("source-chip")).toHaveTextContent("LIVE");
    const url = fetchMock.mock.calls[0]?.[0] as string;
    expect(url).toBe("/api/places/b%201/tour-prep?lang=en&plan_key=a%7Cb");
  });

  it("sends the case's read token in a header, never in the address", async () => {
    saveCaseReadToken("ABC123", "read-secret");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(pack)));
    vi.stubGlobal("fetch", fetchMock);
    render(<TourPrepPage target={{ kind: "case", caseId: "ABC123" }} back="/case/ABC123" />);
    await screen.findByText("API TEXT AS GIVEN");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).not.toContain("read-secret");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer read-secret");
  });

  it("says plainly when this browser holds no key for the case", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<TourPrepPage target={{ kind: "case", caseId: "NOKEY" }} back="/" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("result key");
  });

  it("shows an error with a retry when the API fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "No." }), { status: 404 })),
    );
    render(<TourPrepPage target={{ kind: "place", propertyId: "x", planKey: null }} back="/" />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("404"));
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("tour prep entry points", () => {
  it("routes /case/:id/prep and /prep/place/:id", () => {
    expect(matchRoute("/case/ABC/prep")).toEqual({ name: "prep-case", id: "ABC" });
    expect(matchRoute("/prep/place/fx-prop-3")).toEqual({
      name: "prep-place",
      propertyId: "fx-prop-3",
    });
    expect(matchRoute("/case/ABC").name).toBe("result");
  });

  it("each researched place has a Tour prep link carrying its plan key", async () => {
    render(<PlacesStrip caseId={null} brief={{ max_rent_month: 99999 }} />);
    const links = await screen.findAllByTestId("tour-prep-link");
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute("href", expect.stringMatching(/^\/prep\/place\//));
  });

  it("packToText numbers the questions and carries the label", () => {
    const text = packToText({
      source: "fixture",
      lang: "en",
      title: "T",
      subtitle: "S",
      note: "N",
      as_of: AS_OF,
      facts_heading: "F",
      questions_heading: "Q",
      pay_heading: "P",
      facts: [{ key: "a", text: "fact", sources: ["CoStar record"] }],
      questions: [{ key: "q", text: "ask", sources: [] }],
      before_you_pay: ["pay"],
    });
    expect(text).toContain("- fact (CoStar record)");
    expect(text).toContain("1. ask");
    expect(text).toContain("FIXTURE. N");
  });
});
