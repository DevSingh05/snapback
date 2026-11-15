import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AD_HOLD_MS, FADED_OPACITY, FADE_MS, TwinView } from "./TwinPage";

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    (q: string) =>
      ({
        matches: reduce && q.includes("reduce"),
        media: q,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
}

const view = () => <TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />;
const photo = () => screen.getByTestId("photo-overlay");
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

describe("TwinView photo fade", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("holds the ad photo at full, then eases it down so the scan shows through, and stays", async () => {
    stubReducedMotion(false);
    render(view());
    await tick(900); // the flight
    expect(photo()).toHaveStyle({ opacity: "1" });
    await tick(AD_HOLD_MS - 100);
    expect(photo()).toHaveStyle({ opacity: "1" });
    await tick(200);
    expect(photo()).toHaveStyle({ opacity: String(FADED_OPACITY) });
    expect(photo().style.transitionDuration).toBe(`${FADE_MS}ms`);
    await tick(10_000);
    expect(photo()).toHaveStyle({ opacity: String(FADED_OPACITY) });
  });

  it("the timings are the ones asked for", () => {
    expect([AD_HOLD_MS, FADE_MS, FADED_OPACITY]).toEqual([1200, 1500, 0.45]);
  });

  it("reduced motion: the photo is at the faded level at once, with no transition", async () => {
    stubReducedMotion(true);
    render(view());
    await tick(50);
    expect(photo()).toHaveStyle({ opacity: String(FADED_OPACITY) });
    expect(photo().style.transitionDuration).toBe("0ms");
  });

  it("Show ad photo and Show 3D scan set the photo, and a press cancels the auto fade", async () => {
    stubReducedMotion(false);
    render(view());
    await tick(1000);
    const ad = screen.getByRole("button", { name: "Show ad photo" });
    const scan = screen.getByRole("button", { name: "Show 3D scan" });
    fireEvent.click(scan);
    expect(photo()).toHaveStyle({ opacity: "0" });
    expect(scan).toHaveAttribute("aria-pressed", "true");
    await tick(AD_HOLD_MS + FADE_MS + 500);
    expect(photo()).toHaveStyle({ opacity: "0" });
    fireEvent.click(ad);
    expect(photo()).toHaveStyle({ opacity: "1" });
    expect(ad).toHaveAttribute("aria-pressed", "true");
    expect(scan).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps the slider as an extra, with a plain label", async () => {
    stubReducedMotion(true);
    render(view());
    await tick(50);
    const slider = screen.getByRole("slider", { name: "Blend ad photo and 3D scan" });
    fireEvent.change(slider, { target: { value: "0.8" } });
    expect(photo()).toHaveStyle({ opacity: "0.8" });
    expect(screen.queryByText("Photo fade")).toBeNull();
  });

  it("Side by side shows the ad photo on one half and the scan on the other", async () => {
    stubReducedMotion(true);
    render(view());
    await tick(50);
    const split = screen.getByRole("button", { name: "Side by side" });
    expect(split).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(split);
    expect(split).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-split", "yes");
    fireEvent.click(screen.getByRole("button", { name: "Show 3D scan" }));
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-split", "no");
  });

  it("says in one line why the photo fades", async () => {
    stubReducedMotion(true);
    render(view());
    await tick(50);
    expect(
      screen.getByText("The ad photo fades so you can see the real home behind it."),
    ).toBeInTheDocument();
  });
});
