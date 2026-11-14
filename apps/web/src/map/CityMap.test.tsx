import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CityMap } from "./CityMap";
import { fixturePlacesMap } from "./fixture";
import { EMPTY_CRITERIA } from "./types";

// A stand-in for MapLibre that records the camera calls. WebGL never runs in these tests.
const calls: { name: string; arg: unknown }[] = [];
const handlers = new Map<string, (e?: unknown) => void>();

class FakeMap {
  constructor() {
    queueMicrotask(() => handlers.get("load")?.());
  }
  on(event: string, fn: (e?: unknown) => void) {
    handlers.set(event, fn);
  }
  once() {}
  remove() {}
  resize() {}
  stop() {}
  setStyle() {}
  hasImage() {
    return true;
  }
  addImage() {}
  removeImage() {}
  getLayer() {
    return undefined;
  }
  getSource() {
    return { setData() {}, getClusterExpansionZoom: () => Promise.resolve(12) };
  }
  queryRenderedFeatures() {
    return [];
  }
  project() {
    return { x: 0, y: 0 };
  }
  flyTo(arg: unknown) {
    calls.push({ name: "flyTo", arg });
  }
  easeTo(arg: unknown) {
    calls.push({ name: "easeTo", arg });
  }
  jumpTo(arg: unknown) {
    calls.push({ name: "jumpTo", arg });
  }
  getZoom() {
    return 13;
  }
  getBearing() {
    return 0;
  }
  getCanvas() {
    return document.createElement("canvas");
  }
  isStyleLoaded() {
    return true;
  }
}

vi.mock("./maplibre", () => ({
  loadMapLibre: () => Promise.resolve({ Map: FakeMap }),
}));

const places = fixturePlacesMap(EMPTY_CRITERIA).features;
const pid = places[5]!.properties.pid;
const base = {
  places,
  passed: new Set<string>(),
  look: "glass" as const,
  padding: { top: 0, right: 0, bottom: 0, left: 0 },
  onPick: () => {},
  onMiss: () => {},
  onStatus: () => {},
};

describe("the map camera", () => {
  beforeEach(() => {
    calls.length = 0;
    handlers.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: true })),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("jumps to the picked place under reduced motion, with no flight and no orbit", async () => {
    render(<CityMap {...base} selectedPid={pid} reducedMotion />);
    await waitFor(() => expect(calls.some((c) => c.name === "jumpTo")).toBe(true));
    expect(calls.some((c) => c.name === "flyTo")).toBe(false);
    expect(calls.some((c) => c.name === "easeTo")).toBe(false);
    const jump = calls.find((c) => c.name === "jumpTo")!.arg as { center: [number, number] };
    expect(jump.center).toEqual(places[5]!.geometry.coordinates);
  });

  it("flies for 1.2 seconds when motion is allowed", async () => {
    render(<CityMap {...base} selectedPid={pid} reducedMotion={false} />);
    await waitFor(() => expect(calls.some((c) => c.name === "flyTo")).toBe(true));
    const fly = calls.find((c) => c.name === "flyTo")!.arg as { duration: number };
    expect(fly.duration).toBe(1200);
    expect(calls.some((c) => c.name === "jumpTo")).toBe(false);
  });

  it("turns the city slowly while nothing is picked, and not under reduced motion", async () => {
    render(<CityMap {...base} selectedPid={null} reducedMotion={false} />);
    await waitFor(() => expect(calls.some((c) => c.name === "easeTo")).toBe(true));
    calls.length = 0;
    handlers.clear();
    render(<CityMap {...base} selectedPid={null} reducedMotion />);
    await new Promise((r) => setTimeout(r, 30));
    expect(calls).toEqual([]);
  });
});
