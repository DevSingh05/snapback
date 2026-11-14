import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveCaseReadToken } from "../api";
import type { AerialProofResponse, PropertyRecord } from "../contracts";
import { AerialProof } from "./AerialProof";
import { FIXTURE_CLAIMED, FIXTURE_MATCHED } from "./proofFixtures";

const CASE = "7Q2M";
const READ = "read-secret-1";

const rec = (id: string, source: "live" | "fixture" = "live"): PropertyRecord => ({
  property_id: id,
  source,
  lat: 29.7,
  lon: -95.4,
  model_ids: [],
  floor_plans: [],
  manager_company: "Acme Residential LLC",
});

const tile = (id: string, source: "live" | "fixture" = "live") => ({
  property_id: id,
  source,
  direction: "north",
  path: `${id}.jpg`,
});

function body(over: Partial<AerialProofResponse> = {}): AerialProofResponse {
  return {
    case_id: CASE,
    source: "live",
    claimed: {
      tile: tile("p1"),
      record: rec("p1"),
      image_url: `/cases/${CASE}/aerial/claimed.jpg?direction=north`,
    },
    matched: {
      tile: tile("p2"),
      record: rec("p2"),
      image_url: `/cases/${CASE}/aerial/matched.jpg?direction=north`,
    },
    distance_m: 640,
    ...over,
  };
}

let imageStatus: Record<string, number>;
let json: AerialProofResponse;
const calls: { url: string; auth: string | null }[] = [];

beforeEach(() => {
  vi.stubEnv("VITE_API_URL", "/api");
  window.sessionStorage.clear();
  saveCaseReadToken(CASE, READ);
  imageStatus = {};
  json = body();
  calls.length = 0;
  let n = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, auth: new Headers(init?.headers).get("Authorization") });
      if (url.includes(".jpg")) {
        const side = url.includes("/claimed.jpg") ? "claimed" : "matched";
        const status = imageStatus[side] ?? 200;
        return status === 200
          ? new Response(new Uint8Array([0xff, 0xd8, 0xff]), {
              status,
              headers: { "Content-Type": "image/jpeg" },
            })
          : new Response("{}", { status });
      }
      return new Response(JSON.stringify(json), { status: 200 });
    }),
  );
  URL.createObjectURL = vi.fn(() => `blob:http://localhost/${++n}`);
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const view = (caseId: string | undefined = CASE) => (
  <AerialProof caseId={caseId} mismatch claimed={FIXTURE_CLAIMED} matched={FIXTURE_MATCHED} />
);

describe("AerialProof live", () => {
  it("sends the read token in a header on every request and never in a URL", async () => {
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    expect(calls).toHaveLength(3);
    for (const c of calls) {
      expect(c.auth).toBe(`Bearer ${READ}`);
      expect(c.url).not.toMatch(/token/i);
      expect(c.url).not.toContain(READ);
    }
  });

  it("shows the images through blob URLs, revokes them on unmount", async () => {
    const { unmount } = render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    const srcs = screen.getAllByRole("img").map((i) => i.getAttribute("src"));
    expect(srcs.every((s) => s?.startsWith("blob:"))).toBe(true);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
  });

  it("revokes the old blob URLs when the case changes", async () => {
    saveCaseReadToken("AAAA", "other");
    const { rerender } = render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    rerender(view("AAAA"));
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
  });

  it("shows a skeleton while loading", () => {
    render(view());
    expect(screen.getByTestId("aerial-skeleton")).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("shows the not-available state for a side with tile null, and no broken image", async () => {
    json = body({ claimed: { tile: null, record: null, image_url: null } });
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(1));
    expect(screen.getByText("No aerial image for this building yet")).toBeInTheDocument();
  });

  it("shows the not-available state when the image answers 404", async () => {
    imageStatus = { matched: 404 };
    render(view());
    await waitFor(() =>
      expect(screen.getByText("No aerial image for this building yet")).toBeInTheDocument(),
    );
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("shows one building when the response has no matched side", async () => {
    json = body({ matched: null, distance_m: null });
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(1));
    expect(screen.queryByTestId("aerial-distance")).toBeNull();
    expect(screen.queryByText(/Acme/)).toBeNull();
  });

  it.each(["https://evil.example/a.jpg", ".evil.example/a.jpg", "/cases/OTHER/aerial/claimed.jpg"])(
    "never fetches an image address outside this case's own route (%s)",
    async (bad) => {
      json = body({ claimed: { ...body().claimed, image_url: bad }, matched: null });
      render(view());
      await waitFor(() =>
        expect(screen.getByText("No aerial image for this building yet")).toBeInTheDocument(),
      );
      expect(calls).toHaveLength(1);
      expect(calls[0]!.url).toBe(`/api/cases/${CASE}/aerial`);
      expect(screen.queryByRole("img")).toBeNull();
    },
  );

  it("shows company names and facts from the API, no person name field", async () => {
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    expect(screen.getAllByText(/Acme Residential LLC/).length).toBeGreaterThan(0);
  });

  it("says so when the route fails, with no LIVE chip", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 500 })),
    );
    render(view());
    await waitFor(() => expect(screen.getByText(/could not load/i)).toBeInTheDocument());
    expect(screen.queryByText(/^LIVE/)).toBeNull();
  });
});

describe("AerialProof live source chip", () => {
  it("reads LIVE when the response is live", async () => {
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    expect(screen.getByTestId("source-chip")).toHaveTextContent("LIVE");
  });

  it("reads FIXTURE when the response source is fixture, even with live-looking parts", async () => {
    json = body({ source: "fixture" });
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });

  it("reads FIXTURE when a shown record is fixture under a live response", async () => {
    json = body({ matched: { ...body().matched!, record: rec("p2", "fixture") } });
    render(view());
    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });
});

describe("AerialProof without a read token", () => {
  it("keeps the fixture path and calls nothing", () => {
    window.sessionStorage.clear();
    render(view());
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });
});
