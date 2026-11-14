import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchRead, fakeSdk } = vi.hoisted(() => ({
  fetchRead: vi.fn(),
  fakeSdk: {
    disconnect: vi.fn(),
    Sweep: { moveTo: vi.fn().mockResolvedValue(undefined), data: { subscribe: vi.fn() } },
  },
}));

vi.mock("../api", async (orig) => ({
  ...(await orig<typeof import("../api")>()),
  apiFetchRead: fetchRead,
}));
vi.mock("../twin/showcase", async (orig) => ({
  ...(await orig<typeof import("../twin/showcase")>()),
  connectShowcase: vi.fn().mockResolvedValue(fakeSdk),
  watchSweeps: (_s: unknown, on: (ids: string[]) => void) => {
    on(["fx-sweep-00", "fx-sweep-01", "fx-sweep-03", "fx-sweep-04", "fx-sweep-06"]);
    return () => {};
  },
}));
vi.mock("../twin/useReducedMotion", () => ({ usePrefersReducedMotion: () => false }));

import { FIXTURE_TOUR } from "./fixtureTour";
import { TourView } from "./TourPage";

// A plain response-shaped object, not `new Response(new Blob(...))`: jsdom's Blob has no
// `stream()`, which the Node in CI (undici) needs to wrap one. The code under test only reads
// `ok`, `headers` and `blob()`.
const jpeg = () =>
  Promise.resolve({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "image/jpeg" }),
    blob: () => Promise.resolve(new Blob([new Uint8Array([0xff, 0xd8, 0xff])])),
  } as unknown as Response);

beforeEach(() => {
  fetchRead.mockReset();
  fakeSdk.Sweep.moveTo.mockClear();
  vi.stubGlobal(
    "URL",
    Object.assign(URL, { createObjectURL: () => "blob:ad-photo", revokeObjectURL: vi.fn() }),
  );
});

async function openKitchen(props: { sdkKey?: string; modelId?: string; caseId?: string }) {
  render(<TourView plan={FIXTURE_TOUR} {...props} />);
  await userEvent.setup().click(screen.getByRole("button", { name: "Kitchen" }));
}

describe("the real ad photo in a room", () => {
  it("fetches the case's own photo by alias with the read token path and lands it", async () => {
    fetchRead.mockReturnValue(jpeg());
    await openKitchen({ caseId: "fx-7Q2M" });
    await waitFor(() =>
      expect(screen.getByTestId("photo-overlay")).toHaveAttribute("src", "blob:ad-photo"),
    );
    expect(fetchRead).toHaveBeenCalledWith(
      "/cases/fx-7Q2M/evidence/P1/photo.jpg",
      "fx-7Q2M",
      expect.anything(),
    );
    expect(screen.queryByTestId("photo-fallback")).toBeNull();
  });

  it("falls back to a labelled placeholder when the photo is not available", async () => {
    fetchRead.mockReturnValue(Promise.resolve(new Response("no", { status: 404 })));
    await openKitchen({ caseId: "fx-7Q2M", sdkKey: "k", modelId: "m" });
    expect(await screen.findByTestId("photo-fallback")).toHaveTextContent(
      "Placeholder: the ad's own photo could not be loaded here.",
    );
    expect(screen.getByTestId("photo-overlay").getAttribute("src")).toMatch(/^data:image\/svg/);
  });

  it("says the placeholder is a fixture one when there is no case or no API", async () => {
    await openKitchen({});
    expect(screen.getByTestId("photo-fallback")).toHaveTextContent("Placeholder photo (fixture).");
    expect(fetchRead).not.toHaveBeenCalled();
  });

  it("refuses a non-image answer", async () => {
    fetchRead.mockReturnValue(
      Promise.resolve(
        new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
      ),
    );
    await openKitchen({ caseId: "fx-7Q2M" });
    expect(screen.getByTestId("photo-overlay").getAttribute("src")).toMatch(/^data:image\/svg/);
  });
});

describe("the LIVE stop: the real Showcase with the photo landing over it", () => {
  it("flies the scan to the photo's sweep and lands the photo over the live view", async () => {
    fetchRead.mockReturnValue(jpeg());
    render(<TourView plan={FIXTURE_TOUR} sdkKey="k" modelId="m" caseId="fx-7Q2M" />);
    await waitFor(() => expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("LIVE"));
    await userEvent.setup().click(screen.getByRole("button", { name: "Kitchen" }));
    await waitFor(() =>
      expect(fakeSdk.Sweep.moveTo).toHaveBeenLastCalledWith("fx-sweep-03", expect.anything()),
    );
    expect(screen.getByTitle("Matterport 3D view")).toBeInTheDocument();
    const landing = screen.getByTestId("photo-landing");
    expect(landing).toHaveAttribute("data-sdk", "ready");
    await waitFor(() =>
      expect(screen.getByTestId("photo-overlay")).toHaveAttribute("src", "blob:ad-photo"),
    );
  });
});
