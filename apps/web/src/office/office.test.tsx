import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveCaseReadToken, saveCaseToken } from "../api";
import { matchRoute } from "../App";
import { ConfirmPage } from "./ConfirmPage";
import { OfficeConfirm } from "./OfficeConfirm";
import type { OfficeStatus } from "./api";

const offered: OfficeStatus = {
  case_id: "AB12",
  source: "fixture",
  domain: "oakcourt.example",
  offered: true,
  confirmed: false,
  confirmed_domain: null,
  declined: false,
  declined_domain: null,
  delivery: "outbox",
  guidance: "Ask the poster for an email address at oakcourt.example.",
};

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

beforeEach(() => {
  vi.stubEnv("VITE_API_URL", "/api");
  window.sessionStorage.clear();
  saveCaseReadToken("AB12", "read-secret");
  saveCaseToken("AB12", "write-secret");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("OfficeConfirm", () => {
  it("shows nothing in fixture mode or without a read token", () => {
    vi.stubEnv("VITE_API_URL", "");
    const { container } = render(<OfficeConfirm caseId="AB12" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the domain on record, a FIXTURE chip, and where the link goes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(offered)),
    );
    const user = userEvent.setup();
    render(<OfficeConfirm caseId="AB12" />);
    expect(await screen.findByTestId("office-domain")).toHaveTextContent("oakcourt.example");
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    await user.click(screen.getByRole("button", { name: /ask the office to confirm/i }));
    expect(screen.getByText(/lands in a local outbox file/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/@oakcourt\.example/i)).toBeInTheDocument();
  });

  it("posts the address with the write token in a header, never in the address", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? json(
            {
              case_id: "AB12",
              source: "fixture",
              domain: "oakcourt.example",
              sent: false,
              delivery: "outbox",
              expires_in_minutes: 30,
              detail: "A one-time link was written to the outbox (nothing is sent in this demo).",
            },
            202,
          )
        : json(offered),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<OfficeConfirm caseId="AB12" />);
    await user.click(await screen.findByRole("button", { name: /ask the office to confirm/i }));
    await user.type(screen.getByLabelText(/@oakcourt\.example/i), "leasing@oakcourt.example");
    await user.click(screen.getByRole("button", { name: /make the link/i }));
    expect(await screen.findByTestId("office-sent")).toHaveTextContent(/nothing is sent/i);
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    const post = calls.find((c) => c[1]?.method === "POST")!;
    expect(post[0]).toBe("/api/cases/AB12/confirm-office");
    expect(post[0]).not.toContain("secret");
    expect(new Headers(post[1].headers).get("Authorization")).toBe("Bearer write-secret");
    expect(JSON.parse(String(post[1].body))).toEqual({ address: "leasing@oakcourt.example" });
  });

  it("shows the API's refusal when the address is not at the domain", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? json({ detail: "That address is not at oakcourt.example." }, 422)
        : json(offered),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<OfficeConfirm caseId="AB12" />);
    await user.click(await screen.findByRole("button", { name: /ask the office to confirm/i }));
    await user.type(screen.getByLabelText(/@oakcourt\.example/i), "a@gmail.com");
    await user.click(screen.getByRole("button", { name: /make the link/i }));
    expect(await screen.findByTestId("office-error")).toHaveTextContent(/not at oakcourt/i);
  });

  it("with no domain on record, says to call the office on a number you look up", async () => {
    const none: OfficeStatus = {
      ...offered,
      domain: null,
      offered: false,
      guidance:
        "No website for this office is on record, so it cannot be confirmed here. Call the office on a number you look up yourself.",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(none)),
    );
    render(<OfficeConfirm caseId="AB12" />);
    expect(await screen.findByTestId("office-guidance")).toHaveTextContent(
      /number you look up yourself/i,
    );
    expect(screen.queryByRole("button", { name: /ask the office to confirm/i })).toBeNull();
  });

  it("shows the confirmed line", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ ...offered, confirmed: true, confirmed_domain: "oakcourt.example" })),
    );
    render(<OfficeConfirm caseId="AB12" />);
    expect(await screen.findByTestId("office-confirmed")).toHaveTextContent(
      "Confirmed through oakcourt.example, the website CoStar has on record for this office.",
    );
  });
});

describe("ConfirmPage", () => {
  const peeked = {
    domain: "oakcourt.example",
    source: "fixture",
    listing: {
      building: "Fixture Lofts",
      address: "100 Fixture Way, Fixture City, TX 00000",
      unit: "204",
      rent: 1500,
      poster: "Fixture Living LLC",
      phones: [],
      emails: ["leasing@x.example"],
      links: [],
    },
  };

  beforeEach(() => {
    window.history.replaceState(null, "", "/confirm#tok123");
  });
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("reads the token from the fragment, shows the ad and sends the token only in a body", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      JSON.parse(String(init?.body)).decision
        ? json({ decision: "yes", domain: "oakcourt.example", message: "Thank you. Confirmed." })
        : json(peeked),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ConfirmPage />);
    const ad = await screen.findByTestId("confirm-ad");
    expect(ad).toHaveTextContent("Fixture Lofts, 100 Fixture Way");
    expect(ad).toHaveTextContent("204");
    expect(ad).toHaveTextContent("$1,500 a month");
    expect(ad).toHaveTextContent("Fixture Living LLC");
    expect(screen.getByText(/is this ad, posted by fixture living llc/i)).toBeInTheDocument();
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    // The token is gone from the address bar.
    expect(window.location.hash).toBe("");
    // Looking changed nothing: one call, a peek.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Yes, ours" }));
    expect(await screen.findByTestId("confirm-done")).toHaveTextContent(/confirmed/i);
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(calls.map((c) => c[0])).toEqual(["/api/office/peek", "/api/office/answer"]);
    expect(calls.every((c) => !c[0].includes("tok123"))).toBe(true);
    expect(JSON.parse(String(calls[1]![1].body))).toEqual({ token: "tok123", decision: "yes" });
  });

  it("'Not ours' sends the no decision", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      JSON.parse(String(init?.body)).decision
        ? json({ decision: "no", domain: "oakcourt.example", message: "Recorded: not yours." })
        : json(peeked),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ConfirmPage />);
    await user.click(await screen.findByRole("button", { name: "Not ours" }));
    expect(await screen.findByTestId("confirm-done")).toHaveTextContent(/not yours/i);
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    expect(JSON.parse(String(calls[1]![1].body)).decision).toBe("no");
  });

  it("shows the API's plain message for a used or expired link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ detail: "This link was already used." }, 410)),
    );
    render(<ConfirmPage />);
    expect(await screen.findByTestId("confirm-error")).toHaveTextContent(/already used/i);
  });

  it("is reached by the /confirm route", () => {
    expect(matchRoute("/confirm")).toEqual({ name: "confirm" });
    expect(matchRoute("/confirm/")).toEqual({ name: "confirm" });
  });
});

describe("OfficeConfirm declined", () => {
  it("tells the renter the office did not recognise the ad", async () => {
    window.sessionStorage.clear();
    vi.stubEnv("VITE_API_URL", "/api");
    saveCaseReadToken("AB12", "read-secret");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ ...offered, declined: true, declined_domain: "oakcourt.example" })),
    );
    render(<OfficeConfirm caseId="AB12" />);
    expect(await screen.findByTestId("office-declined")).toHaveTextContent(
      /does not recognise this ad/i,
    );
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });
});
