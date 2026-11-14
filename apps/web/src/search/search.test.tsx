import { readFileSync } from "node:fs";
import path from "node:path";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveCaseReadToken, saveCaseToken } from "../api";
import { AS_OF } from "../contracts";
import type { PlaceMatch, RenterBrief, SearchResponse, TourDraft } from "../contracts";
import { UploadPage } from "../upload/UploadPage";
import { EMPTY_BUDGET, budgetToBrief } from "./BudgetFields";
import { PlacesStrip } from "./PlacesStrip";

const place: PlaceMatch = {
  property_id: "bldg-9",
  kind: "apartment",
  floor_plan: "2 bed / 2 bath",
  plan_key: "plan-abc123",
  beds: 2,
  baths: 2,
  rent_min: 1700,
  rent_max: 1900,
  budget_fit: "within",
  price_text: `$1,700 to $1,900 a month ${AS_OF}`,
  availability_text: `2 units reported available ${AS_OF}`,
  must_haves: [
    { key: "walkup", text: "Elevator building, no walk-up", met: true },
    { key: "parking", text: "Parking: the record does not say", met: null },
  ],
  musts_met: 1,
  has_3d_scan: true,
  scan_text: "a 3D scan in this building",
  office_on_record: "Harbor Realty Group",
  source: "live",
};

const draft: TourDraft = {
  property_id: "bldg-9",
  addressee: "Harbor Realty Group",
  text: "Hello Harbor Realty Group, I would like to book a tour.",
  status: "draft",
  sent: false,
  source: "live",
};

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function search(matches: PlaceMatch[], extra: object = {}): SearchResponse {
  return {
    source: "live",
    as_of: AS_OF,
    n_considered: 40,
    n_matches: matches.length,
    matches,
    ...extra,
  };
}

beforeEach(() => {
  vi.stubEnv("VITE_API_URL", "/api");
  window.sessionStorage.clear();
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("first screen", () => {
  it("renders the headline, the paste box and the optional budget row", () => {
    vi.stubEnv("VITE_API_URL", "");
    render(<UploadPage mode="fixture" />);
    expect(
      screen.getByRole("heading", { level: 1, name: /found a place online\? paste the ad/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /see the real listing, the real office and a fair price, plus researched places that fit your budget/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/paste the ad you found/i)).toBeInTheDocument();
    const row = screen.getByTestId("budget-row");
    expect(row).toHaveTextContent(/your budget and must-haves/i);
    for (const name of [
      /max rent a month/i,
      /beds/i,
      /move in by/i,
      /no walk-up/i,
      /parking/i,
      /pets/i,
    ]) {
      expect(screen.getByLabelText(name)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/screenshots or photos/i)).toBeInTheDocument();
  });

  it("budget-only search posts the brief to /search and shows the places", async () => {
    const fetchMock = vi.fn(() => json(search([place])));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<UploadPage mode="live" />);
    await user.type(screen.getByLabelText(/max rent a month/i), "1,900");
    await user.click(screen.getByLabelText(/no walk-up/i));
    await user.click(screen.getByRole("button", { name: /just show places/i }));
    expect(await screen.findByText(place.price_text)).toBeInTheDocument();
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    const call = calls.find((c) => c[0].endsWith("/search"));
    expect(call).toBeTruthy();
    const body = JSON.parse(String(call![1].body)) as RenterBrief;
    expect(body).toEqual({ max_rent_month: 1900, needs_no_walkup: true });
    // No case, so no draft button, and the page says why.
    expect(screen.queryByRole("button", { name: /draft a tour request/i })).toBeNull();
  });
});

describe("budget row", () => {
  it("searches only when the button is pressed, never as the renter types", async () => {
    const fetchMock = vi.fn(() => json(search([place])));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<UploadPage mode="live" />);
    const searches = () =>
      (fetchMock.mock.calls as unknown as Array<[string, RequestInit]>).filter((c) =>
        c[0].endsWith("/search"),
      ).length;
    await user.type(screen.getByLabelText(/max rent a month/i), "1900");
    await user.click(screen.getByRole("button", { name: /just show places/i }));
    await screen.findByText(place.price_text);
    expect(searches()).toBe(1);
    await user.type(screen.getByLabelText(/max rent a month/i), "5");
    await user.click(screen.getByLabelText(/parking/i));
    await user.click(screen.getByLabelText(/pets/i));
    expect(searches()).toBe(1);
    await user.click(screen.getByRole("button", { name: /just show places/i }));
    await waitFor(() => expect(searches()).toBe(2));
  });

  it("the secondary button is disabled with a hint until a budget or must-have is given", async () => {
    vi.stubEnv("VITE_API_URL", "");
    const user = userEvent.setup();
    render(<UploadPage mode="fixture" />);
    const button = screen.getByRole("button", { name: /just show places/i });
    expect(button).toBeDisabled();
    expect(screen.getByText("Add a max rent or a must-have first.")).toBeInTheDocument();
    await user.click(screen.getByLabelText(/pets/i));
    expect(button).toBeEnabled();
    expect(screen.queryByText("Add a max rent or a must-have first.")).toBeNull();
  });

  it("reads the rent up to the first decimal point", () => {
    expect(budgetToBrief({ ...EMPTY_BUDGET, maxRent: "1800.00" }).max_rent_month).toBe(1800);
    expect(budgetToBrief({ ...EMPTY_BUDGET, maxRent: "$1,800" }).max_rent_month).toBe(1800);
  });

  it("offers Studio or more, not a bare Studio", () => {
    vi.stubEnv("VITE_API_URL", "");
    render(<UploadPage mode="fixture" />);
    expect(screen.getByRole("option", { name: "Studio or more" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Studio" })).toBeNull();
  });

  it("stores exactly the brief for the case, and no token, in sessionStorage", async () => {
    const user = userEvent.setup();
    const createCase = vi.fn().mockResolvedValue({
      case_id: "7Q2M",
      source: "fixture" as const,
      challenge_text: "Hi",
    });
    saveCaseToken("7Q2M", "write-secret");
    render(<UploadPage mode="fixture" createCase={createCase} navigate={vi.fn()} />);
    await user.type(screen.getByLabelText(/paste the ad you found/i), "zillow.com/x/1");
    await user.type(screen.getByLabelText(/max rent a month/i), "1,900");
    await user.selectOptions(screen.getByLabelText(/^beds$/i), "2");
    await user.click(screen.getByLabelText(/no walk-up/i));
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await screen.findByLabelText(/message to forward/i);
    const raw = window.sessionStorage.getItem("snapback.brief.7Q2M");
    expect(JSON.parse(raw ?? "null")).toEqual({
      max_rent_month: 1900,
      beds_min: 2,
      needs_no_walkup: true,
    });
    expect(raw).not.toContain("secret");
  });
});

describe("researched places strip", () => {
  it("says 'near this price' when there is no stored brief, 'fit your budget' when there is", async () => {
    saveCaseReadToken("7Q2M", "r");
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json({ case_id: "7Q2M", source: "live", as_of: AS_OF, matches: [place] })),
    );
    const { unmount } = render(<PlacesStrip caseId="7Q2M" brief={null} />);
    expect(
      await screen.findByRole("heading", { name: "Researched places near this price" }),
    ).toBeInTheDocument();
    unmount();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(search([place]))),
    );
    render(<PlacesStrip caseId="7Q2M" brief={{ max_rent_month: 2000 }} />);
    expect(
      await screen.findByRole("heading", { name: "Researched places that fit your budget" }),
    ).toBeInTheDocument();
  });

  it("with no read token on this device it says so and offers no Try again", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<PlacesStrip caseId="NOKEY" brief={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/does not hold the key/i);
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });

  it("shows the API's text verbatim with the chip and the 3D scan label", async () => {
    saveCaseReadToken("7Q2M", "read-secret");
    const fetchMock = vi.fn(() =>
      json({ case_id: "7Q2M", source: "live", as_of: AS_OF, matches: [place] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<PlacesStrip caseId="7Q2M" brief={null} />);
    expect(await screen.findByText(place.price_text)).toBeInTheDocument();
    expect(screen.getByText(place.availability_text)).toBeInTheDocument();
    expect(screen.getByText("Elevator building, no walk-up")).toBeInTheDocument();
    expect(screen.getByText("Parking: the record does not say")).toBeInTheDocument();
    expect(screen.getByText("a 3D scan in this building")).toBeInTheDocument();
    expect(screen.getByText("Harbor Realty Group")).toBeInTheDocument();
    expect(screen.getAllByText(/as of CoStar's last research/).length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("LIVE");
    // The read token travels in a header, never in the address.
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/7Q2M/alternatives");
    expect(url).not.toContain("read-secret");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer read-secret");
  });

  it("the tour-draft request sends plan_key and the write token only in the header", async () => {
    saveCaseToken("7Q2M", "write-secret");
    saveCaseReadToken("7Q2M", "read-secret");
    const fetchMock = vi.fn((url: string) =>
      url.endsWith("/tour-draft")
        ? json(draft)
        : json({ case_id: "7Q2M", source: "live", as_of: AS_OF, matches: [place] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<PlacesStrip caseId="7Q2M" brief={null} />);
    await user.click(await screen.findByRole("button", { name: /draft a tour request/i }));
    const box = await screen.findByLabelText(/tour request draft/i);
    expect(box).toHaveValue(draft.text);
    expect(screen.getByText(/we never send it for you/i)).toBeInTheDocument();
    expect(screen.getByText(/^To:/)).toHaveTextContent("To: Harbor Realty Group");
    expect(screen.getByRole("button", { name: /^copy$/i })).toBeInTheDocument();

    const post = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/tour-draft"))!;
    const [url, init] = post as unknown as [string, RequestInit];
    expect(url).toBe("/api/cases/7Q2M/tour-draft");
    expect(url).not.toContain("secret");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      property_id: "bldg-9",
      plan_key: "plan-abc123",
    });
    expect(String(init.body)).not.toContain("secret");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer write-secret");
  });

  it("copies the draft", async () => {
    saveCaseToken("7Q2M", "w");
    saveCaseReadToken("7Q2M", "r");
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.endsWith("/tour-draft")
          ? json(draft)
          : json({ case_id: "7Q2M", source: "live", as_of: AS_OF, matches: [place] }),
      ),
    );
    const writeText = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<PlacesStrip caseId="7Q2M" brief={null} />);
    await user.click(await screen.findByRole("button", { name: /draft a tour request/i }));
    await user.click(await screen.findByRole("button", { name: /^copy$/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(draft.text));
  });

  it("empty result shows the trade-off question from the API when it sends one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(search([], { tradeoff_question: "$140 a month less with a walk-up. OK?" }))),
    );
    render(<PlacesStrip caseId={null} brief={{ max_rent_month: 900 }} />);
    expect(await screen.findByTestId("places-empty")).toHaveTextContent(
      "No researched places fit this budget",
    );
    expect(screen.getByText("$140 a month less with a walk-up. OK?")).toBeInTheDocument();
  });

  it("empty result without a question shows only the empty line", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => json(search([]))),
    );
    render(<PlacesStrip caseId={null} brief={{ max_rent_month: 900 }} />);
    expect(await screen.findByTestId("places-empty")).toBeInTheDocument();
    expect(document.querySelector(".pf-tradeoff")).toBeNull();
  });

  it("a failed load says so and offers Try again; a failed draft keeps the row", async () => {
    saveCaseToken("7Q2M", "w");
    saveCaseReadToken("7Q2M", "r");
    let n = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/tour-draft"))
          return json({ detail: "That place has no leasing office on record." }, 422);
        n += 1;
        return n === 1
          ? json({ detail: "down" }, 503)
          : json({ case_id: "7Q2M", source: "live", as_of: AS_OF, matches: [place] });
      }),
    );
    const user = userEvent.setup();
    render(<PlacesStrip caseId="7Q2M" brief={null} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load places/i);
    await user.click(screen.getByRole("button", { name: /try again/i }));
    await user.click(await screen.findByRole("button", { name: /draft a tour request/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no leasing office on record/i);
    expect(screen.getByText(place.price_text)).toBeInTheDocument();
  });

  it("fixture mode is labelled FIXTURE", async () => {
    vi.stubEnv("VITE_API_URL", "");
    render(<PlacesStrip caseId="7Q2M" brief={null} />);
    expect(await screen.findAllByTestId("place-row")).not.toHaveLength(0);
    for (const chip of screen.getAllByTestId("source-chip"))
      expect(chip).toHaveTextContent("FIXTURE");
  });
});

describe("copy rules", () => {
  it("never says 'available now' anywhere in the UI or the sources", async () => {
    vi.stubEnv("VITE_API_URL", "");
    const { container } = render(
      <>
        <UploadPage mode="fixture" />
        <PlacesStrip caseId="7Q2M" brief={null} />
      </>,
    );
    await screen.findAllByTestId("place-row");
    expect(container.textContent ?? "").not.toMatch(/available now/i);
    for (const f of ["PlacesStrip.tsx", "BudgetFields.tsx", "api.ts"]) {
      const src = readFileSync(path.join(import.meta.dirname, f), "utf8");
      expect(src).not.toMatch(/available now/i);
    }
  });
});

describe("mobile layout", () => {
  it("search.css has no fixed width wider than 390px and rows can shrink", () => {
    const css = readFileSync(path.join(import.meta.dirname, "search.css"), "utf8");
    for (const m of css.matchAll(/(?:^|[;\s])(?:min-)?width:\s*(\d+)px/g)) {
      expect(Number(m[1])).toBeLessThanOrEqual(390);
    }
    expect(css).toMatch(/\.pf-row \{[^}]*min-width: 0/);
    expect(css).toMatch(/\.pf-stack \{[^}]*max-width: 880px/);
    expect(css).not.toMatch(/overflow-x:\s*scroll/);
  });
});
