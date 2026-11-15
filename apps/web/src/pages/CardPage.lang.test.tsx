import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { Card } from "../contracts";
import { READ_TOKEN_PREFIX } from "../api";
import { LANG_KEY } from "../lang";
import { CardPage } from "./CardPage";

const en = { ...(cardHold as Card), source: "live", lang: "en" } as Card;
const es = {
  ...en,
  lang: "es",
  headline: "Espere: pide dinero antes de que usted haya visto el lugar",
} as Card;

let asked: string[] = [];

function fetchStub(input: RequestInfo | URL): Promise<Response> {
  const path = String(input);
  asked.push(path);
  const body = path.includes("/card") ? (path.includes("lang=es") ? es : en) : null;
  if (!body) return Promise.resolve(new Response("{}", { status: 404 }));
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

beforeEach(() => {
  asked = [];
  vi.stubEnv("VITE_API_URL", "/api");
  vi.stubGlobal("fetch", vi.fn(fetchStub));
  window.history.replaceState(null, "", "/case/7Q2M");
  // The reads beyond the card need this browser to hold the case's read token.
  window.sessionStorage.setItem(READ_TOKEN_PREFIX + "7Q2M", "t");
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("the report's EN | ES switch", () => {
  it("asks for English by default and shows the switch with EN pressed", async () => {
    render(<CardPage caseId="7Q2M" variant="result" />);
    await screen.findByTestId("lang-switch");
    expect(asked.some((p) => p.includes("/cases/7Q2M/card?lang=en"))).toBe(true);
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-pressed", "true");
  });

  it("?lang=es opens in Spanish and every case read carries lang=es", async () => {
    window.history.replaceState(null, "", "/case/7Q2M?lang=es");
    render(<CardPage caseId="7Q2M" variant="result" />);
    await screen.findByText(es.headline as string);
    await waitFor(() => {
      for (const what of ["real-listing", "copy-alert", "report"]) {
        expect(asked.some((p) => p.includes(`/${what}?lang=es`))).toBe(true);
      }
    });
    expect(asked.filter((p) => p.includes("/card")).every((p) => p.includes("lang=es"))).toBe(true);
  });

  it("switching refetches the card in Spanish, keeps the report up, and remembers it", async () => {
    render(<CardPage caseId="7Q2M" variant="result" />);
    await screen.findByTestId("lang-switch");
    fireEvent.click(screen.getByRole("button", { name: "Español" }));
    await screen.findByText(es.headline as string);
    expect(screen.getByRole("button", { name: "Español" })).toHaveAttribute("aria-pressed", "true");
    expect(window.localStorage.getItem(LANG_KEY)).toBe("es");
    await waitFor(() => expect(asked.some((p) => p.includes("/report?lang=es"))).toBe(true));
  });

  it("opens in the remembered language next time", async () => {
    window.localStorage.setItem(LANG_KEY, "es");
    render(<CardPage caseId="7Q2M" variant="result" />);
    await screen.findByText(es.headline as string);
  });

  it("has no switch when there is no API (only the English fixture)", () => {
    vi.stubEnv("VITE_API_URL", "");
    render(<CardPage caseId="7Q2M" variant="result" />);
    return waitFor(() => expect(screen.queryByTestId("lang-switch")).toBeNull());
  });
});
