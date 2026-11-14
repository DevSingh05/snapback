import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveCaseReadToken, saveCaseToken } from "../api";
import { OfficeConfirm } from "./OfficeConfirm";
import type { OfficeStatus } from "./api";

const offered: OfficeStatus = {
  case_id: "AB12",
  source: "fixture",
  domain: "camdenliving.com",
  offered: true,
  confirmed: false,
  confirmed_domain: null,
  delivery: "outbox",
  guidance: "Ask the poster for an email address at camdenliving.com.",
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
    expect(await screen.findByTestId("office-domain")).toHaveTextContent("camdenliving.com");
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    await user.click(screen.getByRole("button", { name: /ask the office to confirm/i }));
    expect(screen.getByText(/lands in a local outbox file/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/@camdenliving\.com/i)).toBeInTheDocument();
  });

  it("posts the address with the write token in a header, never in the address", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? json(
            {
              case_id: "AB12",
              source: "fixture",
              domain: "camdenliving.com",
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
    await user.type(screen.getByLabelText(/@camdenliving\.com/i), "leasing@camdenliving.com");
    await user.click(screen.getByRole("button", { name: /make the link/i }));
    expect(await screen.findByTestId("office-sent")).toHaveTextContent(/nothing is sent/i);
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    const post = calls.find((c) => c[1]?.method === "POST")!;
    expect(post[0]).toBe("/api/cases/AB12/confirm-office");
    expect(post[0]).not.toContain("secret");
    expect(new Headers(post[1].headers).get("Authorization")).toBe("Bearer write-secret");
    expect(JSON.parse(String(post[1].body))).toEqual({ address: "leasing@camdenliving.com" });
  });

  it("shows the API's refusal when the address is not at the domain", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? json({ detail: "That address is not at camdenliving.com." }, 422)
        : json(offered),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<OfficeConfirm caseId="AB12" />);
    await user.click(await screen.findByRole("button", { name: /ask the office to confirm/i }));
    await user.type(screen.getByLabelText(/@camdenliving\.com/i), "a@gmail.com");
    await user.click(screen.getByRole("button", { name: /make the link/i }));
    expect(await screen.findByTestId("office-error")).toHaveTextContent(/not at camdenliving/i);
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
      vi.fn(() => json({ ...offered, confirmed: true, confirmed_domain: "camdenliving.com" })),
    );
    render(<OfficeConfirm caseId="AB12" />);
    expect(await screen.findByTestId("office-confirmed")).toHaveTextContent(
      "Confirmed through camdenliving.com, the website CoStar has on record for this office.",
    );
  });
});
